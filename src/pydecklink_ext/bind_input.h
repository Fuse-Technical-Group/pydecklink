#pragma once

#include <nanobind/nanobind.h>
#include "bind_device.h"
#include "DeckLinkAPI.h"

namespace nb = nanobind;

/// Zero-copy captured frame holding a ref to the SDK's IDeckLinkVideoInputFrame.
struct CaptureFrameRef {
    ComPtr<IDeckLinkVideoInputFrame> frame;
    bool has_signal = true;
    int64_t stream_time = 0;
    int64_t stream_duration = 0;
    int64_t hw_ref_timestamp = 0;

    long width() const { return frame ? frame->GetWidth() : 0; }
    long height() const { return frame ? frame->GetHeight() : 0; }
    long row_bytes() const { return frame ? frame->GetRowBytes() : 0; }
    _BMDPixelFormat pixel_format() const {
        return frame ? static_cast<_BMDPixelFormat>(frame->GetPixelFormat())
                     : bmdFormatUnspecified;
    }
};

void init_decklink_input(nb::module_& m, nb::class_<Device>& device);
