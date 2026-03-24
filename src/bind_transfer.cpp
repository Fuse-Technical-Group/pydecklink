#include "bind_common.h"
#include <ntv2publicinterface.h>
#include <nanobind/ndarray.h>

void init_transfer(nb::module_& m) {
    // ── Status ───────────────────────────────────────────────────────
    nb::class_<AUTOCIRCULATE_STATUS>(m, "Status")
        .def_prop_ro("is_running", &AUTOCIRCULATE_STATUS::IsRunning)
        .def_prop_ro("is_stopped", &AUTOCIRCULATE_STATUS::IsStopped)
        .def_prop_ro("has_available_input_frame", &AUTOCIRCULATE_STATUS::HasAvailableInputFrame)
        .def_prop_ro("can_accept_more_output_frames", &AUTOCIRCULATE_STATUS::CanAcceptMoreOutputFrames)
        .def_prop_ro("dropped_frame_count", &AUTOCIRCULATE_STATUS::GetDroppedFrameCount)
        .def_prop_ro("buffer_level", &AUTOCIRCULATE_STATUS::GetBufferLevel)
        .def_prop_ro("with_audio", &AUTOCIRCULATE_STATUS::WithAudio)
        .def_prop_ro("with_custom_anc", &AUTOCIRCULATE_STATUS::WithCustomAnc);

    // ── Transfer ─────────────────────────────────────────────────────
    nb::class_<AUTOCIRCULATE_TRANSFER>(m, "Transfer")
        .def(nb::init<>())
        .def("set_video_buffer", [](AUTOCIRCULATE_TRANSFER& self, nb::ndarray<> buffer) {
            check_contiguous(buffer);
            self.SetVideoBuffer(reinterpret_cast<ULWord*>(buffer.data()), static_cast<ULWord>(buffer.nbytes()));
        }, nb::arg("buffer"))
        .def_prop_ro("captured_audio_byte_count", &AUTOCIRCULATE_TRANSFER::GetCapturedAudioByteCount)
        .def_prop_ro("captured_anc_byte_count", [](const AUTOCIRCULATE_TRANSFER& self) {
            return self.GetCapturedAncByteCount(false);
        })
        .def_prop_ro("transferred_frame", [](const AUTOCIRCULATE_TRANSFER& self) {
            return self.GetTransferStatus().GetTransferFrame();
        });
}
