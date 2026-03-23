#include "bind_common.h"
#include <ntv2formatdescriptor.h>

NB_MODULE(_bindings, m) {
    m.doc() = "pyntv2: Python bindings for libajantv2";
    init_enums(m);
    init_card(m);
    init_transfer(m);

    m.def("get_frame_bytes", [](NTV2VideoFormat fmt, NTV2FrameBufferFormat pf) -> uint32_t {
        NTV2FormatDescriptor fd(fmt, pf);
        ULWord bytes = fd.GetTotalBytes();
        if (bytes == 0)
            throw std::invalid_argument("invalid video/pixel format combination");
        return bytes;
    }, nb::arg("video_format"), nb::arg("pixel_format"),
       "Return the total frame byte count for a video format and pixel format.");
}
