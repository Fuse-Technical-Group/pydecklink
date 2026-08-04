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

    // -- HDRMetadata --
    // Rec.2020 / PQ HDR10 defaults; every field is overridable via
    // constructor kwargs or attribute assignment (§spec:hdr-metadata).
    nb::class_<HDRMetadata>(m, "HDRMetadata")
        .def("__init__",
            [](HDRMetadata* self, EOTF eotf, _BMDColorspace colorspace,
               double red_x, double red_y, double green_x, double green_y,
               double blue_x, double blue_y, double white_x, double white_y,
               double max_display_mastering_luminance,
               double min_display_mastering_luminance,
               double max_cll, double max_fall) {
                new (self) HDRMetadata{
                    eotf, colorspace, red_x, red_y, green_x, green_y,
                    blue_x, blue_y, white_x, white_y,
                    max_display_mastering_luminance,
                    min_display_mastering_luminance, max_cll, max_fall};
            },
            nb::arg("eotf") = EOTF::PQ,
            nb::arg("colorspace") = bmdColorspaceRec2020,
            nb::arg("red_x") = hdr_defaults::kRec2020RedX,
            nb::arg("red_y") = hdr_defaults::kRec2020RedY,
            nb::arg("green_x") = hdr_defaults::kRec2020GreenX,
            nb::arg("green_y") = hdr_defaults::kRec2020GreenY,
            nb::arg("blue_x") = hdr_defaults::kRec2020BlueX,
            nb::arg("blue_y") = hdr_defaults::kRec2020BlueY,
            nb::arg("white_x") = hdr_defaults::kD65WhiteX,
            nb::arg("white_y") = hdr_defaults::kD65WhiteY,
            nb::arg("max_display_mastering_luminance") = hdr_defaults::kMaxDisplayMasteringLuminance,
            nb::arg("min_display_mastering_luminance") = hdr_defaults::kMinDisplayMasteringLuminance,
            nb::arg("max_cll") = hdr_defaults::kMaxCLL,
            nb::arg("max_fall") = hdr_defaults::kMaxFALL,
            "HDR10 static metadata. Defaults describe a Rec.2020 / PQ signal.")
        .def_rw("eotf", &HDRMetadata::eotf)
        .def_rw("colorspace", &HDRMetadata::colorspace)
        .def_rw("red_x", &HDRMetadata::red_x)
        .def_rw("red_y", &HDRMetadata::red_y)
        .def_rw("green_x", &HDRMetadata::green_x)
        .def_rw("green_y", &HDRMetadata::green_y)
        .def_rw("blue_x", &HDRMetadata::blue_x)
        .def_rw("blue_y", &HDRMetadata::blue_y)
        .def_rw("white_x", &HDRMetadata::white_x)
        .def_rw("white_y", &HDRMetadata::white_y)
        .def_rw("max_display_mastering_luminance",
                &HDRMetadata::max_display_mastering_luminance)
        .def_rw("min_display_mastering_luminance",
                &HDRMetadata::min_display_mastering_luminance)
        .def_rw("max_cll", &HDRMetadata::max_cll)
        .def_rw("max_fall", &HDRMetadata::max_fall);

    // -- MutableFrame --
    nb::class_<MutableFrame>(m, "MutableFrame")
        .def_prop_ro("width", &MutableFrame::width)
        .def_prop_ro("height", &MutableFrame::height)
        .def_prop_ro("row_bytes", &MutableFrame::row_bytes)
        .def_prop_ro("flags",
            [](MutableFrame& mf) -> uint32_t {
                if (!mf.frame)
                    throw std::runtime_error("MutableFrame has no frame");
                return static_cast<uint32_t>(mf.frame->GetFlags());
            },
            "Frame flags bitmask (see FrameFlag).")
        .def("set_hdr_metadata",
            [](MutableFrame& mf, const HDRMetadata& md) {
                if (!mf.frame)
                    throw std::runtime_error("MutableFrame has no frame");
                ComPtr<IDeckLinkVideoFrameMutableMetadataExtensions> ext;
                if (mf.frame->QueryInterface(
                        IID_IDeckLinkVideoFrameMutableMetadataExtensions,
                        (void**)ext.put()) != S_OK || !ext)
                    throw std::runtime_error(
                        "Frame does not support mutable HDR metadata");
                ext->SetInt(bmdDeckLinkFrameMetadataColorspace,
                            static_cast<int64_t>(md.colorspace));
                ext->SetInt(bmdDeckLinkFrameMetadataHDRElectroOpticalTransferFunc,
                            static_cast<int64_t>(md.eotf));
                ext->SetFloat(bmdDeckLinkFrameMetadataHDRDisplayPrimariesRedX, md.red_x);
                ext->SetFloat(bmdDeckLinkFrameMetadataHDRDisplayPrimariesRedY, md.red_y);
                ext->SetFloat(bmdDeckLinkFrameMetadataHDRDisplayPrimariesGreenX, md.green_x);
                ext->SetFloat(bmdDeckLinkFrameMetadataHDRDisplayPrimariesGreenY, md.green_y);
                ext->SetFloat(bmdDeckLinkFrameMetadataHDRDisplayPrimariesBlueX, md.blue_x);
                ext->SetFloat(bmdDeckLinkFrameMetadataHDRDisplayPrimariesBlueY, md.blue_y);
                ext->SetFloat(bmdDeckLinkFrameMetadataHDRWhitePointX, md.white_x);
                ext->SetFloat(bmdDeckLinkFrameMetadataHDRWhitePointY, md.white_y);
                ext->SetFloat(bmdDeckLinkFrameMetadataHDRMaxDisplayMasteringLuminance,
                              md.max_display_mastering_luminance);
                ext->SetFloat(bmdDeckLinkFrameMetadataHDRMinDisplayMasteringLuminance,
                              md.min_display_mastering_luminance);
                ext->SetFloat(bmdDeckLinkFrameMetadataHDRMaximumContentLightLevel, md.max_cll);
                ext->SetFloat(bmdDeckLinkFrameMetadataHDRMaximumFrameAverageLightLevel, md.max_fall);
                mf.frame->SetFlags(mf.frame->GetFlags() | bmdFrameContainsHDRMetadata);
            },
            nb::arg("metadata"),
            "Attach HDR10 static metadata and set FrameFlag.ContainsHDRMetadata.")
        .def_prop_ro("data", [](nb::handle self) {
            // The write access window is opened when the wrapper is
            // constructed (acquire_output_frame / create_video_frame)
            // and closed by schedule_output_frame or the destructor —
            // see SDK §2.5.53.2 and the MutableFrame class doc. We
            // just hand back a numpy view; the access window covers
            // the entire lifetime, so any number of writes is valid.
            auto& mf = nb::cast<MutableFrame&>(self);
            void* bytes = mf.get_data_ptr();
            size_t total = static_cast<size_t>(mf.row_bytes()) * mf.height();
            return nb::ndarray<nb::numpy, uint8_t, nb::ndim<1>>(
                bytes, {total}, self);
        }, "Writeable numpy uint8 view of the frame buffer.");

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
            mf.open_access();
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
            // Close the access window before handing the frame to the
            // SDK; ownership of the access state transfers with the
            // schedule call.
            mf.close_access();
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
            mf.open_access();
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

    device.def("display_frame_sync_frame",
        [](Device& self, MutableFrame& mf) {
            if (!self.output_)
                throw std::runtime_error("Video output not enabled");
            if (!mf.frame)
                throw std::runtime_error("MutableFrame has no frame");
            // Close the write window before handing the frame to the SDK;
            // the caller has finished populating pixels and metadata.
            mf.close_access();
            HRESULT hr = self.output_->DisplayVideoFrameSync(mf.frame.get());
            if (hr != S_OK)
                throw std::runtime_error(
                    "DisplayVideoFrameSync failed (HRESULT " + std::to_string(hr) + ")");
        },
        nb::arg("frame"),
        "Display a caller-built MutableFrame synchronously (blocking). "
        "Carries HDR metadata and custom pixel packing through the sync path.");

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
            HRESULT hr = self.config()->SetFlag(cfgID, static_cast<dlbool_t>(value));
            if (hr != S_OK)
                throw std::runtime_error("SetFlag failed (HRESULT " + std::to_string(hr) + ")");
        },
        nb::arg("flag"), nb::arg("value"),
        "Set a boolean configuration flag.");

    device.def("get_config_flag",
        [](Device& self, _BMDDeckLinkConfigurationID cfgID) -> bool {
            dlbool_t value = false;
            HRESULT hr = self.config()->GetFlag(cfgID, &value);
            if (hr != S_OK)
                throw std::runtime_error("GetFlag failed (HRESULT " + std::to_string(hr) + ")");
            return static_cast<bool>(value);
        },
        nb::arg("flag"),
        "Get a boolean configuration flag.");

    device.def("set_config_int",
        [](Device& self, _BMDDeckLinkConfigurationID cfgID, int64_t value) {
            HRESULT hr = self.config()->SetInt(cfgID, value);
            if (hr != S_OK)
                throw std::runtime_error("SetInt failed (HRESULT " + std::to_string(hr) + ")");
        },
        nb::arg("setting"), nb::arg("value"),
        "Set an integer configuration value.");

    device.def("get_config_int",
        [](Device& self, _BMDDeckLinkConfigurationID cfgID) -> int64_t {
            int64_t value = 0;
            HRESULT hr = self.config()->GetInt(cfgID, &value);
            if (hr != S_OK)
                throw std::runtime_error("GetInt failed (HRESULT " + std::to_string(hr) + ")");
            return value;
        },
        nb::arg("setting"),
        "Get an integer configuration value.");

    device.def("write_config",
        [](Device& self) {
            HRESULT hr = self.config()->WriteConfigurationToPreferences();
            if (hr != S_OK)
                throw std::runtime_error("WriteConfigurationToPreferences failed (HRESULT " + std::to_string(hr) + ")");
        },
        "Persist configuration changes to preferences.");
}
