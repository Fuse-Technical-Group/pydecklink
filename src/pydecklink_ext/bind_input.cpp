#include "bind_input.h"
#include "bind_device.h"
#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/tuple.h>
#include <stdexcept>
#include <string>

void init_decklink_input(nb::module_& m, nb::class_<Device>& device) {

    m.def("clock_us", []() -> int64_t { return steady_clock_us(); },
          "Return monotonic time in microseconds.");

    // -- CaptureFrame --
    nb::class_<CaptureFrame>(m, "CaptureFrame")
        .def_prop_ro("data", [](nb::handle self) {
            auto& cf = nb::cast<CaptureFrame&>(self);
            size_t n = cf.pixels.size();
            return nb::ndarray<nb::numpy, uint8_t, nb::ndim<1>>(
                cf.pixels.data(), {n}, self);
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
        }, nb::sig("def __repr__(self) -> str")); // avoid platform-specific C++ type in stub

    // -- CaptureFrameRef (zero-copy) --
    nb::class_<CaptureFrameRef>(m, "CaptureFrameRef")
        .def_prop_ro("data", [](nb::handle self) {
            // The read access window is opened in
            // ``InputCallback::VideoInputFrameArrived`` and closed by
            // the ``CaptureFrameRef`` destructor — see SDK §2.5.53.2
            // and the CaptureFrameRef class doc. We just hand back a
            // numpy view of the bytes; the access window covers the
            // entire lifetime of this object, so any number of reads
            // (including zero) is valid.
            auto& cfr = nb::cast<CaptureFrameRef&>(self);
            if (!cfr.frame)
                throw std::runtime_error("CaptureFrameRef has no frame");
            if (!cfr.buf)
                throw std::runtime_error("Frame has no video buffer");
            void* bytes = nullptr;
            cfr.buf->GetBytes(&bytes);
            if (!bytes)
                throw std::runtime_error("Failed to get frame buffer bytes");
            size_t total = static_cast<size_t>(cfr.row_bytes()) * cfr.height();
            // The CaptureFrameRef (self) keeps the SDK frame alive via AddRef
            // AND keeps the read access window open until destruction.
            return nb::ndarray<nb::numpy, uint8_t, nb::ndim<1>>(
                bytes, {total}, self);
        }, "Read-only numpy view of the SDK frame buffer. "
           "The CaptureFrameRef must outlive the array.")
        .def_prop_ro("width", &CaptureFrameRef::width)
        .def_prop_ro("height", &CaptureFrameRef::height)
        .def_prop_ro("row_bytes", &CaptureFrameRef::row_bytes)
        .def_prop_ro("pixel_format", &CaptureFrameRef::pixel_format)
        .def_ro("has_signal", &CaptureFrameRef::has_signal)
        .def_ro("hardware_reference_timestamp", &CaptureFrameRef::hw_ref_timestamp)
        .def_ro("callback_arrived_us", &CaptureFrameRef::callback_arrived_us,
                "CLOCK_MONOTONIC_RAW time (microseconds) when the callback fired.")
        .def_prop_ro("stream_time", [](const CaptureFrameRef& self) {
            return std::make_tuple(self.stream_time, self.stream_duration);
        }, "Stream time as (time, duration) tuple.")
        .def("__repr__", [](const CaptureFrameRef& self) {
            return "CaptureFrameRef(" +
                   std::to_string(self.width()) + "x" + std::to_string(self.height()) +
                   ", signal=" + (self.has_signal ? "True" : "False") + ")";
        }, nb::sig("def __repr__(self) -> str")); // avoid platform-specific C++ type in stub

    // -- InputFormatInfo --
    nb::class_<InputFormatInfo>(m, "InputFormatInfo")
        .def_ro("mode", &InputFormatInfo::mode)
        .def_ro("pixel_format", &InputFormatInfo::pixel_format)
        .def("__repr__", [](const InputFormatInfo& self) {
            return "InputFormatInfo(mode=" + std::to_string(static_cast<uint32_t>(self.mode)) + ")";
        }, nb::sig("def __repr__(self) -> str")); // avoid platform-specific C++ type in stub

    // -- Device input methods (added to existing Device class) --

    device.def("enable_video_input",
        [](Device& self, _BMDDisplayMode mode, _BMDPixelFormat pixel_format,
           _BMDVideoInputFlags flags, bool zero_copy, size_t input_queue_depth) {
            ComPtr<IDeckLinkInput> input;
            if (self.dl->QueryInterface(IID_IDeckLinkInput, (void**)input.put()) != S_OK)
                throw std::runtime_error("Device does not support input");
            HRESULT hr = input->EnableVideoInput(mode, pixel_format, flags);
            if (hr != S_OK)
                throw std::runtime_error("EnableVideoInput failed (HRESULT " + std::to_string(hr) + ")");
            self.input_ = std::move(input);
            self.input_callback_ = ComPtr<InputCallback>(
                new InputCallback(self.input_, input_queue_depth, zero_copy));
            self.input_callback_->set_current_format(mode, pixel_format, flags);
            bool format_detection = (flags & bmdVideoInputEnableFormatDetection) != 0;
            self.input_callback_->set_format_detection(format_detection);
            self.input_->SetCallback(self.input_callback_.get());
        },
        nb::arg("mode"), nb::arg("pixel_format"),
        nb::arg("flags") = bmdVideoInputFlagDefault,
        nb::arg("zero_copy") = false,
        nb::arg("input_queue_depth") = 1,
        "Enable video input for the given display mode and pixel format. "
        "``input_queue_depth`` bounds the internal C++ queue between the "
        "SDK input thread (producer) and the Python consumer; on overflow "
        "the oldest frame is dropped. Default 1 (real-time: drop late "
        "frames, never lag); raise for recorder-style consumers that "
        "need to absorb consumer-side jitter.");

    device.def("disable_video_input",
        [](Device& self) {
            if (!self.input_)
                throw std::runtime_error("Video input not enabled");
            self.input_->SetCallback(nullptr);
            self.input_->DisableVideoInput();
            self.input_callback_ = ComPtr<InputCallback>();
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
