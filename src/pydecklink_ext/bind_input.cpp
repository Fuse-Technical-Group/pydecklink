#include "bind_input.h"
#include "bind_device.h"
#include "DeckLinkAPI.h"
#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/tuple.h>
#include <atomic>
#include <condition_variable>
#include <cstring>
#include <mutex>
#include <optional>
#include <queue>
#include <stdexcept>
#include <string>

/// Captured frame data, copied from the SDK's callback thread.
struct CaptureFrame {
    std::vector<uint8_t> pixels;
    long width = 0;
    long height = 0;
    long row_bytes = 0;
    _BMDPixelFormat pixel_format = bmdFormatUnspecified;
    int64_t stream_time = 0;
    int64_t stream_duration = 0;
    int64_t hw_ref_timestamp = 0;
    bool has_signal = true;
};

// CaptureFrameRef is defined in bind_input.h for cross-module use.

/// Information about the currently detected input format.
struct InputFormatInfo {
    _BMDDisplayMode mode = bmdModeUnknown;
    _BMDPixelFormat pixel_format = bmdFormatUnspecified;
    _BMDVideoInputFlags flags = bmdVideoInputFlagDefault;
};

/// C++ implementation of IDeckLinkInputCallback.
/// Copies frame data into a bounded thread-safe queue.
class InputCallback : public IDeckLinkInputCallback {
public:
    InputCallback(IDeckLinkInput* input, size_t max_queue = 8, bool zero_copy = false)
        : ref_count_(1), input_(input), max_queue_(max_queue),
          format_detection_enabled_(false), zero_copy_(zero_copy) {}

    void set_format_detection(bool enabled) {
        format_detection_enabled_ = enabled;
    }

    void set_timescale(int64_t ts) { timescale_ = ts; }

    // IUnknown
    HRESULT QueryInterface(REFIID, void**) override { return E_NOINTERFACE; }
    ULONG AddRef() override { return ++ref_count_; }
    ULONG Release() override {
        ULONG c = --ref_count_;
        if (c == 0) delete this;
        return c;
    }

    HRESULT VideoInputFormatChanged(
            BMDVideoInputFormatChangedEvents events,
            IDeckLinkDisplayMode* newMode,
            BMDDetectedVideoInputFormatFlags flags) override {
        if (!format_detection_enabled_) return S_OK;

        // Determine new pixel format from detected flags.
        _BMDPixelFormat new_pf = bmdFormat8BitYUV;
        if (flags & bmdDetectedVideoInputRGB444) {
            if (flags & bmdDetectedVideoInput12BitDepth)
                new_pf = bmdFormat12BitRGB;
            else if (flags & bmdDetectedVideoInput10BitDepth)
                new_pf = bmdFormat10BitRGB;
            else
                new_pf = bmdFormat8BitARGB;
        } else {
            // YCbCr
            if (flags & bmdDetectedVideoInput10BitDepth)
                new_pf = bmdFormat10BitYUV;
            else
                new_pf = bmdFormat8BitYUV;
        }

        BMDDisplayMode new_mode = newMode->GetDisplayMode();

        // Update current format info.
        {
            std::lock_guard<std::mutex> lock(format_mutex_);
            current_format_.mode = static_cast<_BMDDisplayMode>(new_mode);
            current_format_.pixel_format = new_pf;
        }

        // Reconfigure: stop, disable, re-enable, restart.
        input_->StopStreams();
        input_->DisableVideoInput();
        input_->EnableVideoInput(new_mode, new_pf,
                                 bmdVideoInputEnableFormatDetection);
        input_->StartStreams();

        return S_OK;
    }

    HRESULT VideoInputFrameArrived(
            IDeckLinkVideoInputFrame* videoFrame,
            IDeckLinkAudioInputPacket*) override {
        if (!videoFrame) return S_OK;

        bool has_signal = !(videoFrame->GetFlags() & bmdFrameHasNoInputSource);
        int64_t st = 0, sd = 0, hw_time = 0, hw_dur = 0;
        videoFrame->GetStreamTime(&st, &sd, timescale_);
        videoFrame->GetHardwareReferenceTimestamp(timescale_, &hw_time, &hw_dur);

        if (zero_copy_) {
            // Zero-copy path: AddRef the SDK frame and enqueue.
            CaptureFrameRef cfr;
            videoFrame->AddRef();
            cfr.frame = ComPtr<IDeckLinkVideoInputFrame>(videoFrame);
            cfr.has_signal = has_signal;
            cfr.stream_time = st;
            cfr.stream_duration = sd;
            cfr.hw_ref_timestamp = hw_time;

            {
                std::lock_guard<std::mutex> lock(ref_queue_mutex_);
                if (ref_queue_.size() >= max_queue_)
                    ref_queue_.pop();
                ref_queue_.push(std::move(cfr));
            }
            ref_queue_cv_.notify_one();
        } else {
            // Copy path: memcpy pixel data into CaptureFrame.
            CaptureFrame cf;
            cf.width = videoFrame->GetWidth();
            cf.height = videoFrame->GetHeight();
            cf.row_bytes = videoFrame->GetRowBytes();
            cf.pixel_format = static_cast<_BMDPixelFormat>(videoFrame->GetPixelFormat());
            cf.has_signal = has_signal;
            cf.stream_time = st;
            cf.stream_duration = sd;
            cf.hw_ref_timestamp = hw_time;

            IDeckLinkVideoBuffer* buf = nullptr;
            videoFrame->QueryInterface(IID_IDeckLinkVideoBuffer, (void**)&buf);
            if (buf) {
                buf->StartAccess(bmdBufferAccessRead);
                void* bytes = nullptr;
                buf->GetBytes(&bytes);
                if (bytes) {
                    size_t total = static_cast<size_t>(cf.row_bytes) * cf.height;
                    cf.pixels.resize(total);
                    std::memcpy(cf.pixels.data(), bytes, total);
                }
                buf->EndAccess(bmdBufferAccessRead);
                buf->Release();
            }

            {
                std::lock_guard<std::mutex> lock(queue_mutex_);
                if (queue_.size() >= max_queue_)
                    queue_.pop();
                queue_.push(std::move(cf));
            }
            queue_cv_.notify_one();
        }

        return S_OK;
    }

    std::optional<CaptureFrame> pop(int timeout_ms) {
        std::unique_lock<std::mutex> lock(queue_mutex_);
        if (!queue_cv_.wait_for(lock, std::chrono::milliseconds(timeout_ms),
                                [this] { return !queue_.empty(); })) {
            return std::nullopt;
        }
        CaptureFrame f = std::move(queue_.front());
        queue_.pop();
        return f;
    }

    std::optional<CaptureFrameRef> pop_ref(int timeout_ms) {
        std::unique_lock<std::mutex> lock(ref_queue_mutex_);
        if (!ref_queue_cv_.wait_for(lock, std::chrono::milliseconds(timeout_ms),
                                    [this] { return !ref_queue_.empty(); })) {
            return std::nullopt;
        }
        CaptureFrameRef f = std::move(ref_queue_.front());
        ref_queue_.pop();
        return f;
    }

    InputFormatInfo current_format() const {
        std::lock_guard<std::mutex> lock(format_mutex_);
        return current_format_;
    }

    void set_current_format(_BMDDisplayMode mode, _BMDPixelFormat pf, _BMDVideoInputFlags flags) {
        std::lock_guard<std::mutex> lock(format_mutex_);
        current_format_.mode = mode;
        current_format_.pixel_format = pf;
        current_format_.flags = flags;
    }

private:
    std::atomic<ULONG> ref_count_;
    IDeckLinkInput* input_;  // Non-owning; Device owns this.
    size_t max_queue_;
    bool format_detection_enabled_;
    bool zero_copy_;
    int64_t timescale_ = 10000000;  // Default 10MHz.

    std::mutex queue_mutex_;
    std::condition_variable queue_cv_;
    std::queue<CaptureFrame> queue_;

    std::mutex ref_queue_mutex_;
    std::condition_variable ref_queue_cv_;
    std::queue<CaptureFrameRef> ref_queue_;

    mutable std::mutex format_mutex_;
    InputFormatInfo current_format_;
};

void init_decklink_input(nb::module_& m, nb::class_<Device>& device) {

    // -- CaptureFrame --
    nb::class_<CaptureFrame>(m, "CaptureFrame")
        .def_prop_ro("data", [](CaptureFrame& self) {
            size_t n = self.pixels.size();
            return nb::ndarray<nb::numpy, uint8_t, nb::ndim<1>>(
                self.pixels.data(), {n}, nb::handle());
        }, "Frame pixel data as numpy uint8 array.")
        .def_ro("width", &CaptureFrame::width)
        .def_ro("height", &CaptureFrame::height)
        .def_ro("row_bytes", &CaptureFrame::row_bytes)
        .def_ro("pixel_format", &CaptureFrame::pixel_format)
        .def_prop_ro("stream_time", [](const CaptureFrame& self) {
            return std::make_tuple(self.stream_time, self.stream_duration);
        }, "Stream time as (time, duration) tuple.")
        .def_ro("hardware_reference_timestamp", &CaptureFrame::hw_ref_timestamp)
        .def_ro("has_signal", &CaptureFrame::has_signal)
        .def("__repr__", [](const CaptureFrame& self) {
            return "CaptureFrame(" +
                   std::to_string(self.width) + "x" + std::to_string(self.height) +
                   ", signal=" + (self.has_signal ? "True" : "False") + ")";
        });

    // -- CaptureFrameRef (zero-copy) --
    nb::class_<CaptureFrameRef>(m, "CaptureFrameRef")
        .def_prop_ro("width", &CaptureFrameRef::width)
        .def_prop_ro("height", &CaptureFrameRef::height)
        .def_prop_ro("row_bytes", &CaptureFrameRef::row_bytes)
        .def_prop_ro("pixel_format", &CaptureFrameRef::pixel_format)
        .def_ro("has_signal", &CaptureFrameRef::has_signal)
        .def_ro("hardware_reference_timestamp", &CaptureFrameRef::hw_ref_timestamp)
        .def_prop_ro("stream_time", [](const CaptureFrameRef& self) {
            return std::make_tuple(self.stream_time, self.stream_duration);
        }, "Stream time as (time, duration) tuple.")
        .def("__repr__", [](const CaptureFrameRef& self) {
            return "CaptureFrameRef(" +
                   std::to_string(self.width()) + "x" + std::to_string(self.height()) +
                   ", signal=" + (self.has_signal ? "True" : "False") + ")";
        });

    // -- InputFormatInfo --
    nb::class_<InputFormatInfo>(m, "InputFormatInfo")
        .def_ro("mode", &InputFormatInfo::mode)
        .def_ro("pixel_format", &InputFormatInfo::pixel_format)
        .def("__repr__", [](const InputFormatInfo& self) {
            return "InputFormatInfo(mode=" + std::to_string(static_cast<uint32_t>(self.mode)) + ")";
        });

    // -- Device input methods (added to existing Device class) --

    device.def("enable_video_input",
        [](Device& self, _BMDDisplayMode mode, _BMDPixelFormat pixel_format,
           _BMDVideoInputFlags flags, bool zero_copy) {
            IDeckLinkInput* input = nullptr;
            if (self.dl->QueryInterface(IID_IDeckLinkInput, (void**)&input) != S_OK)
                throw std::runtime_error("Device does not support input");
            HRESULT hr = input->EnableVideoInput(mode, pixel_format, flags);
            if (hr != S_OK) {
                input->Release();
                throw std::runtime_error("EnableVideoInput failed (HRESULT " + std::to_string(hr) + ")");
            }
            self.input_ = ComPtr<IDeckLinkInput>(input);
            self.input_callback_ = new InputCallback(input, 8, zero_copy);
            self.input_callback_->set_current_format(mode, pixel_format, flags);
            bool format_detection = (flags & bmdVideoInputEnableFormatDetection) != 0;
            self.input_callback_->set_format_detection(format_detection);
            input->SetCallback(self.input_callback_);
        },
        nb::arg("mode"), nb::arg("pixel_format"),
        nb::arg("flags") = bmdVideoInputFlagDefault,
        nb::arg("zero_copy") = false,
        "Enable video input for the given display mode and pixel format.");

    device.def("disable_video_input",
        [](Device& self) {
            if (!self.input_)
                throw std::runtime_error("Video input not enabled");
            self.input_->SetCallback(nullptr);
            self.input_->DisableVideoInput();
            if (self.input_callback_) {
                self.input_callback_->Release();
                self.input_callback_ = nullptr;
            }
            self.input_ = ComPtr<IDeckLinkInput>();
        },
        "Disable video input.");

    device.def("start_streams",
        [](Device& self) {
            if (!self.input_)
                throw std::runtime_error("Video input not enabled");
            HRESULT hr = self.input_->StartStreams();
            if (hr != S_OK)
                throw std::runtime_error("StartStreams failed (HRESULT " + std::to_string(hr) + ")");
        },
        "Start capture streams.");

    device.def("stop_streams",
        [](Device& self) {
            if (!self.input_)
                throw std::runtime_error("Video input not enabled");
            HRESULT hr = self.input_->StopStreams();
            if (hr != S_OK)
                throw std::runtime_error("StopStreams failed (HRESULT " + std::to_string(hr) + ")");
        },
        "Stop capture streams.");

    device.def("pop_capture_frame",
        [](Device& self, int timeout_ms) -> std::optional<CaptureFrame> {
            if (!self.input_callback_)
                throw std::runtime_error("Video input not enabled");
            // Release the GIL while waiting.
            nb::gil_scoped_release release;
            return self.input_callback_->pop(timeout_ms);
        },
        nb::arg("timeout_ms") = 1000,
        "Pop a captured frame from the queue, or None on timeout.");

    device.def("pop_capture_frame_ref",
        [](Device& self, int timeout_ms) -> std::optional<CaptureFrameRef> {
            if (!self.input_callback_)
                throw std::runtime_error("Video input not enabled");
            nb::gil_scoped_release release;
            return self.input_callback_->pop_ref(timeout_ms);
        },
        nb::arg("timeout_ms") = 1000,
        "Pop a zero-copy captured frame reference, or None on timeout.");

    device.def_prop_ro("current_input_format",
        [](Device& self) -> std::optional<InputFormatInfo> {
            if (!self.input_callback_) return std::nullopt;
            return self.input_callback_->current_format();
        },
        "Current detected input format, or None if input is not enabled.");
}
