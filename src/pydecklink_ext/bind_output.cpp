#include "bind_output.h"
#include "bind_input.h"
#include "bind_device.h"
#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/tuple.h>
#include <cstring>
#include <stdexcept>
#include <string>

void init_decklink_output(nb::module_& m, nb::class_<Device>& device) {

    // -- OutputStatus --
    nb::class_<OutputStatus>(m, "OutputStatus")
        .def(nb::init<>())
        .def_rw("completed", &OutputStatus::completed)
        .def_rw("late", &OutputStatus::late)
        .def_rw("dropped", &OutputStatus::dropped)
        .def_rw("flushed", &OutputStatus::flushed)
        .def_rw("underrun", &OutputStatus::underrun)
        .def("__repr__", [](const OutputStatus& s) {
            return "OutputStatus(completed=" + std::to_string(s.completed) +
                   ", late=" + std::to_string(s.late) +
                   ", dropped=" + std::to_string(s.dropped) +
                   ", flushed=" + std::to_string(s.flushed) +
                   ", underrun=" + std::string(s.underrun ? "True" : "False") + ")";
        }, nb::sig("def __repr__(self) -> str")); // avoid platform-specific C++ type in stub

    // -- MutableFrame --
    nb::class_<MutableFrame>(m, "MutableFrame")
        .def_prop_ro("width", &MutableFrame::width)
        .def_prop_ro("height", &MutableFrame::height)
        .def_prop_ro("row_bytes", &MutableFrame::row_bytes)
        .def_prop_ro("data", [](nb::handle self) {
            auto& mf = nb::cast<MutableFrame&>(self);
            void* bytes = mf.get_data_ptr();
            size_t total = static_cast<size_t>(mf.row_bytes()) * mf.height();
            return nb::ndarray<nb::numpy, uint8_t, nb::ndim<1>>(
                bytes, {total}, self);
        }, "Writeable numpy uint8 view of the frame buffer.")
        .def("end_access", &MutableFrame::end_access,
             "Release buffer access (called automatically on frame use).");

    // -- Device output methods (added to existing Device class) --

    device.def("enable_video_output",
        [](Device& self, _BMDDisplayMode mode, uint32_t flags) {
            ComPtr<IDeckLinkOutput> output;
            if (self.dl->QueryInterface(IID_IDeckLinkOutput, (void**)output.put()) != S_OK)
                throw std::runtime_error("Device does not support output");
            HRESULT hr = output->EnableVideoOutput(mode, static_cast<BMDVideoOutputFlags>(flags));
            if (hr != S_OK)
                throw std::runtime_error("EnableVideoOutput failed (HRESULT " + std::to_string(hr) + ")");
            // Store output interface and create callback.
            self.output_ = std::move(output);
            self.output_callback_ = ComPtr<OutputCallback>(new OutputCallback());
            self.output_->SetScheduledFrameCompletionCallback(self.output_callback_.get());
        },
        nb::arg("mode"), nb::arg("flags") = static_cast<uint32_t>(bmdVideoOutputFlagDefault),
        "Enable video output for the given display mode.");

    device.def("row_bytes_for_pixel_format",
        [](Device& self, _BMDPixelFormat pixelFormat, int32_t width) -> int32_t {
            if (!self.output_)
                throw std::runtime_error("Video output not enabled");
            int32_t rowBytes = 0;
            HRESULT hr = self.output_->RowBytesForPixelFormat(pixelFormat, width, &rowBytes);
            if (hr != S_OK)
                throw std::runtime_error("RowBytesForPixelFormat failed (HRESULT " + std::to_string(hr) + ")");
            return rowBytes;
        },
        nb::arg("pixel_format"), nb::arg("width"),
        "Get the row bytes for a given pixel format and width.");

    device.def("create_frame_pool",
        [](Device& self, int count, int32_t width, int32_t height,
           int32_t row_bytes, _BMDPixelFormat pixel_format) {
            if (!self.output_)
                throw std::runtime_error("Video output not enabled");
            if (!self.output_callback_)
                throw std::runtime_error("No output callback");
            self.output_callback_->create_pool(
                self.output_.get(), count, width, height, row_bytes, pixel_format);
        },
        nb::arg("count"), nb::arg("width"), nb::arg("height"),
        nb::arg("row_bytes"), nb::arg("pixel_format"),
        "Pre-allocate a pool of output frames. Completed frames return to the pool automatically.");

    device.def("acquire_output_frame",
        [](Device& self, int timeout_ms) -> MutableFrame {
            if (!self.output_callback_)
                throw std::runtime_error("No output callback");
            nb::gil_scoped_release release;
            auto* raw = self.output_callback_->acquire(timeout_ms);
            if (!raw)
                throw std::runtime_error("Timed out waiting for output frame from pool");
            // AddRef — pool owns the frame, MutableFrame gets its own ref.
            raw->AddRef();
            MutableFrame mf;
            mf.frame = ComPtr<IDeckLinkMutableVideoFrame>(raw);
            raw->QueryInterface(IID_IDeckLinkVideoBuffer, (void**)mf.buffer.put());
            return mf;
        },
        nb::arg("timeout_ms") = 1000,
        "Acquire a pre-allocated output frame from the pool. Blocks until one is available.");

    device.def("schedule_output_frame",
        [](Device& self, MutableFrame& mf,
           int64_t display_time, int64_t duration, int64_t timescale) {
            if (!self.output_)
                throw std::runtime_error("Video output not enabled");
            if (!mf.frame)
                throw std::runtime_error("MutableFrame has no frame");
            // End buffer access before scheduling.
            if (mf.buffer)
                mf.buffer->EndAccess(bmdBufferAccessReadAndWrite);
            HRESULT hr = self.output_->ScheduleVideoFrame(
                mf.frame.get(), display_time, duration, timescale);
            if (hr != S_OK)
                throw std::runtime_error(
                    "ScheduleVideoFrame failed (HRESULT " + std::to_string(hr) + ")");
        },
        nb::arg("frame"), nb::arg("display_time"),
        nb::arg("duration"), nb::arg("timescale"),
        "Schedule a pre-allocated output frame. No allocation, no copy.");

    device.def_prop_ro("pool_available",
        [](Device& self) -> size_t {
            if (!self.output_callback_) return 0;
            return self.output_callback_->pool_available();
        },
        "Number of output frames available in the pool.");

    device.def("disable_video_output",
        [](Device& self) {
            if (!self.output_)
                throw std::runtime_error("Video output not enabled");
            self.output_->SetScheduledFrameCompletionCallback(nullptr);
            self.output_->DisableVideoOutput();
            self.output_callback_ = ComPtr<OutputCallback>();
            self.output_ = ComPtr<IDeckLinkOutput>();
        },
        "Disable video output.");

    device.def("create_video_frame",
        [](Device& self, int32_t width, int32_t height, int32_t row_bytes,
           _BMDPixelFormat pixel_format) -> MutableFrame {
            if (!self.output_)
                throw std::runtime_error("Video output not enabled");
            MutableFrame mf;
            HRESULT hr = self.output_->CreateVideoFrame(
                width, height, row_bytes, pixel_format,
                bmdFrameFlagDefault, mf.frame.put());
            if (hr != S_OK || !mf.frame)
                throw std::runtime_error("CreateVideoFrame failed (HRESULT " + std::to_string(hr) + ")");
            mf.frame->QueryInterface(IID_IDeckLinkVideoBuffer, (void**)mf.buffer.put());
            return mf;
        },
        nb::arg("width"), nb::arg("height"), nb::arg("row_bytes"),
        nb::arg("pixel_format"),
        "Create a mutable video frame for output.");

    device.def("display_frame_sync",
        [](Device& self, nb::ndarray<uint8_t, nb::ndim<1>> buffer,
           int32_t width, int32_t height, int32_t row_bytes,
           _BMDPixelFormat pixel_format) {
            if (!self.output_)
                throw std::runtime_error("Video output not enabled");
            // Create a frame.
            ComPtr<IDeckLinkMutableVideoFrame> frame;
            HRESULT hr = self.output_->CreateVideoFrame(
                width, height, row_bytes, pixel_format,
                bmdFrameFlagDefault, frame.put());
            if (hr != S_OK || !frame)
                throw std::runtime_error("CreateVideoFrame failed");
            // Copy data into frame buffer.
            ComPtr<IDeckLinkVideoBuffer> buf;
            frame->QueryInterface(IID_IDeckLinkVideoBuffer, (void**)buf.put());
            if (!buf) throw std::runtime_error("Frame has no video buffer");
            buf->StartAccess(bmdBufferAccessWrite);
            void* dest = nullptr;
            buf->GetBytes(&dest);
            if (!dest) {
                buf->EndAccess(bmdBufferAccessWrite);
                throw std::runtime_error("Failed to get frame buffer bytes");
            }
            size_t expected = static_cast<size_t>(row_bytes) * height;
            size_t provided = buffer.size();
            if (provided < expected)
                throw std::invalid_argument(
                    "Buffer too small: need " + std::to_string(expected) +
                    " bytes, got " + std::to_string(provided));
            std::memcpy(dest, buffer.data(), expected);
            buf->EndAccess(bmdBufferAccessWrite);
            // Display synchronously.
            hr = self.output_->DisplayVideoFrameSync(frame.get());
            if (hr != S_OK)
                throw std::runtime_error("DisplayVideoFrameSync failed (HRESULT " + std::to_string(hr) + ")");
        },
        nb::arg("buffer"), nb::arg("width"), nb::arg("height"),
        nb::arg("row_bytes"), nb::arg("pixel_format"),
        "Display a frame synchronously (blocking). Copies buffer into a new frame.");

    device.def("schedule_capture_frame",
        [](Device& self, CaptureFrameRef& capture_frame,
           int64_t display_time, int64_t duration, int64_t timescale) {
            if (!self.output_)
                throw std::runtime_error("Video output not enabled");
            if (!capture_frame.frame)
                throw std::runtime_error("CaptureFrameRef has no frame");
            // IDeckLinkVideoInputFrame inherits IDeckLinkVideoFrame.
            // Upcast directly — no QI needed.
            IDeckLinkVideoFrame* vf = static_cast<IDeckLinkVideoFrame*>(capture_frame.frame.get());
            HRESULT hr = self.output_->ScheduleVideoFrame(vf, display_time, duration, timescale);
            if (hr != S_OK)
                throw std::runtime_error("ScheduleVideoFrame failed (HRESULT " + std::to_string(hr) + ")");
        },
        nb::arg("capture_frame"),
        nb::arg("display_time"), nb::arg("duration"), nb::arg("timescale"),
        "Schedule a zero-copy captured frame for playback. No memcpy.");

    device.def("start_scheduled_playback",
        [](Device& self, int64_t start_time, int64_t timescale, double speed) {
            if (!self.output_)
                throw std::runtime_error("Video output not enabled");
            HRESULT hr = self.output_->StartScheduledPlayback(start_time, timescale, speed);
            if (hr != S_OK)
                throw std::runtime_error("StartScheduledPlayback failed (HRESULT " + std::to_string(hr) + ")");
        },
        nb::arg("start_time"), nb::arg("timescale"), nb::arg("speed") = 1.0,
        "Start scheduled playback.");

    device.def("stop_scheduled_playback",
        [](Device& self) {
            if (!self.output_)
                throw std::runtime_error("Video output not enabled");
            BMDTimeValue actual = 0;
            HRESULT hr = self.output_->StopScheduledPlayback(0, &actual, 0);
            if (hr != S_OK)
                throw std::runtime_error("StopScheduledPlayback failed (HRESULT " + std::to_string(hr) + ")");
        },
        "Stop scheduled playback.");

    device.def_prop_ro("is_scheduled_playback_running",
        [](Device& self) -> bool {
            if (!self.output_) return false;
            dlbool_t active = false;
            self.output_->IsScheduledPlaybackRunning(&active);
            return static_cast<bool>(active);
        },
        "True if scheduled playback is currently running.");

    device.def_prop_ro("output_status",
        [](Device& self) -> OutputStatus {
            if (!self.output_callback_) return OutputStatus{};
            return self.output_callback_->get_status();
        },
        "Current output frame completion statistics.");

    // -- Configuration methods on Device --
    device.def("set_config_flag",
        [](Device& self, _BMDDeckLinkConfigurationID cfgID, bool value) {
            ComPtr<IDeckLinkConfiguration> config;
            if (self.dl->QueryInterface(IID_IDeckLinkConfiguration, (void**)config.put()) != S_OK)
                throw std::runtime_error("Device does not support configuration");
            HRESULT hr = config->SetFlag(cfgID, static_cast<dlbool_t>(value));
            if (hr != S_OK)
                throw std::runtime_error("SetFlag failed (HRESULT " + std::to_string(hr) + ")");
        },
        nb::arg("flag"), nb::arg("value"),
        "Set a boolean configuration flag.");

    device.def("get_config_flag",
        [](Device& self, _BMDDeckLinkConfigurationID cfgID) -> bool {
            ComPtr<IDeckLinkConfiguration> config;
            if (self.dl->QueryInterface(IID_IDeckLinkConfiguration, (void**)config.put()) != S_OK)
                throw std::runtime_error("Device does not support configuration");
            dlbool_t value = false;
            HRESULT hr = config->GetFlag(cfgID, &value);
            if (hr != S_OK)
                throw std::runtime_error("GetFlag failed (HRESULT " + std::to_string(hr) + ")");
            return static_cast<bool>(value);
        },
        nb::arg("flag"),
        "Get a boolean configuration flag.");

    device.def("set_config_int",
        [](Device& self, _BMDDeckLinkConfigurationID cfgID, int64_t value) {
            ComPtr<IDeckLinkConfiguration> config;
            if (self.dl->QueryInterface(IID_IDeckLinkConfiguration, (void**)config.put()) != S_OK)
                throw std::runtime_error("Device does not support configuration");
            HRESULT hr = config->SetInt(cfgID, value);
            if (hr != S_OK)
                throw std::runtime_error("SetInt failed (HRESULT " + std::to_string(hr) + ")");
        },
        nb::arg("setting"), nb::arg("value"),
        "Set an integer configuration value.");

    device.def("get_config_int",
        [](Device& self, _BMDDeckLinkConfigurationID cfgID) -> int64_t {
            ComPtr<IDeckLinkConfiguration> config;
            if (self.dl->QueryInterface(IID_IDeckLinkConfiguration, (void**)config.put()) != S_OK)
                throw std::runtime_error("Device does not support configuration");
            int64_t value = 0;
            HRESULT hr = config->GetInt(cfgID, &value);
            if (hr != S_OK)
                throw std::runtime_error("GetInt failed (HRESULT " + std::to_string(hr) + ")");
            return value;
        },
        nb::arg("setting"),
        "Get an integer configuration value.");

    device.def("write_config",
        [](Device& self) {
            ComPtr<IDeckLinkConfiguration> config;
            if (self.dl->QueryInterface(IID_IDeckLinkConfiguration, (void**)config.put()) != S_OK)
                throw std::runtime_error("Device does not support configuration");
            HRESULT hr = config->WriteConfigurationToPreferences();
            if (hr != S_OK)
                throw std::runtime_error("WriteConfigurationToPreferences failed (HRESULT " + std::to_string(hr) + ")");
        },
        "Persist configuration changes to preferences.");
}
