#include "bind_common.h"
#include <ntv2card.h>
#include <ntv2signalrouter.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/map.h>

void init_card(nb::module_& m) {
    nb::class_<CNTV2Card>(m, "Card")
        .def(nb::init<>())
        .def("__init__", [](CNTV2Card* self, UWord device_index) {
            new (self) CNTV2Card();
            if (!self->Open(device_index))
                throw std::runtime_error("Card.open failed");
        }, nb::arg("device_index"))

        // ── Lifecycle ────────────────────────────────────────────────
        .def("open", [](CNTV2Card& self, UWord index) {
            check(self.Open(index), "Card.open");
        }, nb::arg("index"))
        .def("close", [](CNTV2Card& self) { if (self.IsOpen()) self.Close(); })
        .def_prop_ro("is_open", &CNTV2Card::IsOpen)
        .def("__enter__", [](nb::object self) -> nb::object { return self; })
        .def("__exit__", [](CNTV2Card& self, nb::args) {
            if (!self.IsOpen()) return;
            // Stop AutoCirculate on every channel to prevent the DMA
            // engine from wedging when the device handle closes with
            // transfers still in flight.
            for (int ch = NTV2_CHANNEL1; ch < NTV2_MAX_NUM_CHANNELS; ++ch)
                self.AutoCirculateStop(static_cast<NTV2Channel>(ch), true);
            self.Close();
        })

        // ── Device Ownership ────────────────────────────────────────
        .def("acquire_stream_for_application", [](CNTV2Card& self, ULWord app_type, int32_t process_id) {
            check(self.AcquireStreamForApplication(app_type, process_id), "Card.acquire_stream_for_application");
        }, nb::arg("app_type"), nb::arg("process_id"))
        .def("release_stream_for_application", [](CNTV2Card& self, ULWord app_type, int32_t process_id) {
            check(self.ReleaseStreamForApplication(app_type, process_id), "Card.release_stream_for_application");
        }, nb::arg("app_type"), nb::arg("process_id"))

        // ── Format Detection & Configuration ─────────────────────────
        .def("get_input_video_format", [](CNTV2Card& self, NTV2InputSource source, bool is_progressive) {
            return self.GetInputVideoFormat(source, is_progressive);
        }, nb::arg("source"), nb::arg("is_progressive") = false)
        .def("set_video_format", [](CNTV2Card& self, NTV2VideoFormat format, NTV2Channel channel) {
            check(self.SetVideoFormat(format, false, false, channel), "Card.set_video_format");
        }, nb::arg("format"), nb::arg("channel") = NTV2_CHANNEL1)
        .def("set_frame_buffer_format", [](CNTV2Card& self, NTV2Channel channel, NTV2FrameBufferFormat pixel_format) {
            check(self.SetFrameBufferFormat(channel, pixel_format), "Card.set_frame_buffer_format");
        }, nb::arg("channel"), nb::arg("pixel_format"))
        .def("enable_channel", [](CNTV2Card& self, NTV2Channel channel) {
            check(self.EnableChannel(channel), "Card.enable_channel");
        }, nb::arg("channel"))
        .def("set_mode", [](CNTV2Card& self, NTV2Channel channel, NTV2Mode mode) {
            check(self.SetMode(channel, mode), "Card.set_mode");
        }, nb::arg("channel"), nb::arg("mode"))
        .def("set_sdi_transmit_enable", [](CNTV2Card& self, NTV2Channel channel, bool enable) {
            check(self.SetSDITransmitEnable(channel, enable), "Card.set_sdi_transmit_enable");
        }, nb::arg("channel"), nb::arg("enable"))
        .def("set_reference", [](CNTV2Card& self, NTV2ReferenceSource source) {
            check(self.SetReference(source), "Card.set_reference");
        }, nb::arg("source"))

        // ── Signal Routing ───────────────────────────────────────────
        .def("connect", [](CNTV2Card& self, NTV2InputCrosspointID input_xpt, NTV2OutputCrosspointID output_xpt, bool validate) {
            check(self.Connect(input_xpt, output_xpt, validate), "Card.connect");
        }, nb::arg("input_xpt"), nb::arg("output_xpt"), nb::arg("validate") = false)
        .def("disconnect", [](CNTV2Card& self, NTV2InputCrosspointID input_xpt) {
            check(self.Disconnect(input_xpt), "Card.disconnect");
        }, nb::arg("input_xpt"))
        .def("clear_routing", [](CNTV2Card& self) {
            check(self.ClearRouting(), "Card.clear_routing");
        })
        .def("apply_signal_route", [](CNTV2Card& self, const NTV2XptConnections& connections, bool replace) {
            check(self.ApplySignalRoute(connections, replace), "Card.apply_signal_route");
        }, nb::arg("connections"), nb::arg("replace") = false)

        // ── AutoCirculate ────────────────────────────────────────────
        .def("autocirculate_init_for_input", [](CNTV2Card& self, NTV2Channel channel, UWord frame_count, NTV2AudioSystem audio_system, ULWord option_flags) {
            if (frame_count < 3)
                throw std::invalid_argument("frame_count must be >= 3 (HasAvailableInputFrame requires buffer_level > 1)");
            check(self.AutoCirculateInitForInput(channel, frame_count, audio_system, option_flags), "Card.autocirculate_init_for_input");
        }, nb::arg("channel"), nb::arg("frame_count") = 7, nb::arg("audio_system") = NTV2_AUDIOSYSTEM_INVALID, nb::arg("option_flags") = 0)
        .def("autocirculate_init_for_output", [](CNTV2Card& self, NTV2Channel channel, UWord frame_count, NTV2AudioSystem audio_system, ULWord option_flags) {
            if (frame_count < 3)
                throw std::invalid_argument("frame_count must be >= 3 (CanAcceptMoreOutputFrames requires (frame_count - buffer_level) > 1)");
            check(self.AutoCirculateInitForOutput(channel, frame_count, audio_system, option_flags), "Card.autocirculate_init_for_output");
        }, nb::arg("channel"), nb::arg("frame_count") = 7, nb::arg("audio_system") = NTV2_AUDIOSYSTEM_INVALID, nb::arg("option_flags") = 0)
        .def("autocirculate_start", [](CNTV2Card& self, NTV2Channel channel) {
            check(self.AutoCirculateStart(channel), "Card.autocirculate_start");
        }, nb::arg("channel"))
        .def("autocirculate_stop", [](CNTV2Card& self, NTV2Channel channel, bool abort) {
            check(self.AutoCirculateStop(channel, abort), "Card.autocirculate_stop");
        }, nb::arg("channel"), nb::arg("abort") = false)
        .def("autocirculate_get_status", [](CNTV2Card& self, NTV2Channel channel) {
            AUTOCIRCULATE_STATUS status;
            check(self.AutoCirculateGetStatus(channel, status), "Card.autocirculate_get_status");
            return status;
        }, nb::arg("channel"))
        .def("autocirculate_transfer", [](CNTV2Card& self, NTV2Channel channel, AUTOCIRCULATE_TRANSFER& transfer) {
            errno = 0;
            bool ok = self.AutoCirculateTransfer(channel, transfer);
            int saved_errno = errno;
            if (!ok) {
                AUTOCIRCULATE_STATUS st;
                self.AutoCirculateGetStatus(channel, st);
                std::string msg = "Card.autocirculate_transfer failed (ch=";
                msg += std::to_string(channel);
                msg += " state=";
                msg += std::to_string(st.acState);
                msg += " bufLevel=";
                msg += std::to_string(st.GetBufferLevel());
                msg += " vidBufSize=";
                msg += std::to_string(transfer.GetVideoBuffer().GetByteCount());
                msg += " vidBufPtr=";
                msg += std::to_string(reinterpret_cast<uintptr_t>(transfer.GetVideoBuffer().GetHostPointer()));
                msg += " errno=";
                msg += std::to_string(saved_errno);
                msg += ")";
                throw std::runtime_error(msg);
            }
        }, nb::arg("channel"), nb::arg("transfer"), nb::call_guard<nb::gil_scoped_release>())

        .def("get_every_frame_services", [](CNTV2Card& self) {
            NTV2EveryFrameTaskMode mode;
            check(self.GetEveryFrameServices(mode), "Card.get_every_frame_services");
            return static_cast<int>(mode);
        })
        .def("set_every_frame_services", [](CNTV2Card& self, int mode) {
            check(self.SetEveryFrameServices(static_cast<NTV2EveryFrameTaskMode>(mode)), "Card.set_every_frame_services");
        }, nb::arg("mode"))

        // ── VBI ──────────────────────────────────────────────────────
        .def("wait_for_input_vertical_interrupt", [](CNTV2Card& self, NTV2Channel channel, UWord repeat_count) {
            check(self.WaitForInputVerticalInterrupt(channel, repeat_count), "Card.wait_for_input_vertical_interrupt");
        }, nb::arg("channel") = NTV2_CHANNEL1, nb::arg("repeat_count") = 1, nb::call_guard<nb::gil_scoped_release>())
        .def("wait_for_output_vertical_interrupt", [](CNTV2Card& self, NTV2Channel channel, UWord repeat_count) {
            check(self.WaitForOutputVerticalInterrupt(channel, repeat_count), "Card.wait_for_output_vertical_interrupt");
        }, nb::arg("channel") = NTV2_CHANNEL1, nb::arg("repeat_count") = 1, nb::call_guard<nb::gil_scoped_release>())

        // ── Direct DMA ───────────────────────────────────────────────
        .def("dma_read_frame", [](CNTV2Card& self, ULWord frame_number, nb::ndarray<> buffer, NTV2Channel channel) {
            check(self.DMAReadFrame(frame_number,
                                    reinterpret_cast<ULWord*>(buffer.data()),
                                    static_cast<ULWord>(buffer.nbytes()),
                                    channel),
                  "Card.dma_read_frame");
        }, nb::arg("frame_number"), nb::arg("buffer"), nb::arg("channel"), nb::call_guard<nb::gil_scoped_release>())
        .def("dma_write_frame", [](CNTV2Card& self, ULWord frame_number, nb::ndarray<> buffer, NTV2Channel channel) {
            check(self.DMAWriteFrame(frame_number,
                                     reinterpret_cast<const ULWord*>(buffer.data()),
                                     static_cast<ULWord>(buffer.nbytes()),
                                     channel),
                  "Card.dma_write_frame");
        }, nb::arg("frame_number"), nb::arg("buffer"), nb::arg("channel"), nb::call_guard<nb::gil_scoped_release>())

        // ── DMA Buffer Lock ──────────────────────────────────────────
        .def("dma_buffer_lock", [](CNTV2Card& self, nb::ndarray<> buffer) {
            auto ptr = reinterpret_cast<uintptr_t>(buffer.data());
            if (ptr % 4096 != 0)
                throw std::invalid_argument(
                    "DMA buffer must be page-aligned (4096 bytes). "
                    "Use mmap.mmap(-1, size) + numpy.frombuffer() "
                    "instead of numpy.zeros().");
            bool rdma = buffer.device_type() == nb::device::cuda::value;
            NTV2Buffer buf(buffer.data(), buffer.nbytes());
            check(self.DMABufferLock(buf, true, rdma), "Card.dma_buffer_lock");
        }, nb::arg("buffer"))
        .def("dma_buffer_unlock", [](CNTV2Card& self, nb::ndarray<> buffer) {
            NTV2Buffer buf(buffer.data(), buffer.nbytes());
            check(self.DMABufferUnlock(buf), "Card.dma_buffer_unlock");
        }, nb::arg("buffer"));
}
