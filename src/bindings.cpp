#include "bind_common.h"
#include <ntv2formatdescriptor.h>
#include <ntv2utils.h>

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

    m.def("get_format_width", [](NTV2VideoFormat fmt) -> uint32_t {
        NTV2FormatDescriptor fd(fmt, NTV2_FBF_8BIT_YCBCR);
        ULWord width = fd.GetRasterWidth();
        if (width == 0)
            throw std::invalid_argument("invalid video format");
        return width;
    }, nb::arg("video_format"),
       "Return the raster width in pixels for a video format.");

    m.def("get_format_height", [](NTV2VideoFormat fmt) -> uint32_t {
        NTV2FormatDescriptor fd(fmt, NTV2_FBF_8BIT_YCBCR);
        ULWord height = fd.GetVisibleRasterHeight();
        if (height == 0)
            throw std::invalid_argument("invalid video format");
        return height;
    }, nb::arg("video_format"),
       "Return the visible raster height in pixels for a video format.");

    m.def("get_format_fps", [](NTV2VideoFormat fmt) -> double {
        NTV2FrameRate rate = GetNTV2FrameRateFromVideoFormat(fmt);
        return GetFramesPerSecond(rate);
    }, nb::arg("video_format"),
       "Return the frames per second for a video format.");
}
