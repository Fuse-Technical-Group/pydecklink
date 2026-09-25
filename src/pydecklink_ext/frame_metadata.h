#pragma once

#include "bind_device.h"
#include "bind_enums.h"
#include <cstdint>
#include <limits>
#include <optional>

/// HDR10 static metadata defaults: Rec.2020 (ITU-R BT.2020) reference
/// display primaries, the D65 white point, and the SMPTE ST 2086 /
/// CTA-861.3 mastering-display and content-light-level defaults ported
/// from bmd-signal-gen (§spec:hdr-metadata).
namespace hdr_defaults {
    constexpr double kRec2020RedX = 0.708;
    constexpr double kRec2020RedY = 0.292;
    constexpr double kRec2020GreenX = 0.170;
    constexpr double kRec2020GreenY = 0.797;
    constexpr double kRec2020BlueX = 0.131;
    constexpr double kRec2020BlueY = 0.046;
    constexpr double kD65WhiteX = 0.3127;
    constexpr double kD65WhiteY = 0.3290;
    constexpr double kMaxDisplayMasteringLuminance = 1000.0;   // cd/m²
    constexpr double kMinDisplayMasteringLuminance = 0.0001;   // cd/m²
    constexpr double kMaxCLL = 1000.0;                         // cd/m²
    constexpr double kMaxFALL = 50.0;                          // cd/m²
}

/// HDR10 static metadata for a frame — SMPTE ST 2086
/// mastering-display colour volume plus CTA-861.3 content light levels.
/// Defaults describe a Rec.2020 / PQ HDR10 signal; override any field
/// before ``MutableFrame.set_hdr_metadata`` (§spec:hdr-metadata).
/// Captured frames report the same record (§spec:hdr-metadata-capture).
struct HDRMetadata {
    EOTF eotf = EOTF::PQ;
    _BMDColorspace colorspace = bmdColorspaceRec2020;
    double red_x = hdr_defaults::kRec2020RedX;
    double red_y = hdr_defaults::kRec2020RedY;
    double green_x = hdr_defaults::kRec2020GreenX;
    double green_y = hdr_defaults::kRec2020GreenY;
    double blue_x = hdr_defaults::kRec2020BlueX;
    double blue_y = hdr_defaults::kRec2020BlueY;
    double white_x = hdr_defaults::kD65WhiteX;
    double white_y = hdr_defaults::kD65WhiteY;
    double max_display_mastering_luminance = hdr_defaults::kMaxDisplayMasteringLuminance;
    double min_display_mastering_luminance = hdr_defaults::kMinDisplayMasteringLuminance;
    double max_cll = hdr_defaults::kMaxCLL;
    double max_fall = hdr_defaults::kMaxFALL;
};

/// Flags, colorimetry and HDR metadata read from a video frame
/// (§spec:hdr-metadata-capture). A value the frame does not carry, or one
/// the Python enum has no member for, is ``std::nullopt``: nanobind
/// refuses to cast a raw value naming no member.
struct FrameMetadata {
    uint32_t flags = 0;
    std::optional<_BMDColorspace> colorspace;
    std::optional<EOTF> eotf;
    std::optional<HDRMetadata> hdr;
};

inline std::optional<_BMDColorspace> colorspace_from_int(int64_t value) {
    switch (value) {
        case bmdColorspaceRec601:
        case bmdColorspaceRec709:
        case bmdColorspaceRec2020:
            return static_cast<_BMDColorspace>(value);
        default:
            return std::nullopt;
    }
}

inline std::optional<EOTF> eotf_from_int(int64_t value) {
    switch (value) {
        case static_cast<int64_t>(EOTF::Reserved):
        case static_cast<int64_t>(EOTF::SDR):
        case static_cast<int64_t>(EOTF::PQ):
        case static_cast<int64_t>(EOTF::HLG):
            return static_cast<EOTF>(value);
        default:
            return std::nullopt;
    }
}

/// Read a frame's metadata through ``IDeckLinkVideoFrameMetadataExtensions``.
/// ``hdr`` is set only when the frame carries ``bmdFrameContainsHDRMetadata``
/// and a colorspace and EOTF the enums name; a float the SDK does not
/// report reads as NaN rather than a default that looks received.
inline FrameMetadata read_frame_metadata(IDeckLinkVideoFrame* frame) {
    FrameMetadata md;
    if (!frame) return md;
    md.flags = static_cast<uint32_t>(frame->GetFlags());

    ComPtr<IDeckLinkVideoFrameMetadataExtensions> ext;
    if (frame->QueryInterface(IID_IDeckLinkVideoFrameMetadataExtensions,
                              (void**)ext.put()) != S_OK || !ext)
        return md;

    int64_t value = 0;
    if (ext->GetInt(bmdDeckLinkFrameMetadataColorspace, &value) == S_OK)
        md.colorspace = colorspace_from_int(value);
    if (ext->GetInt(bmdDeckLinkFrameMetadataHDRElectroOpticalTransferFunc, &value) == S_OK)
        md.eotf = eotf_from_int(value);

    if (!(md.flags & bmdFrameContainsHDRMetadata) || !md.colorspace || !md.eotf)
        return md;

    auto get_float = [&ext](BMDDeckLinkFrameMetadataID id) {
        double v = 0.0;
        return ext->GetFloat(id, &v) == S_OK
                   ? v
                   : std::numeric_limits<double>::quiet_NaN();
    };
    HDRMetadata hdr;
    hdr.eotf = *md.eotf;
    hdr.colorspace = *md.colorspace;
    hdr.red_x = get_float(bmdDeckLinkFrameMetadataHDRDisplayPrimariesRedX);
    hdr.red_y = get_float(bmdDeckLinkFrameMetadataHDRDisplayPrimariesRedY);
    hdr.green_x = get_float(bmdDeckLinkFrameMetadataHDRDisplayPrimariesGreenX);
    hdr.green_y = get_float(bmdDeckLinkFrameMetadataHDRDisplayPrimariesGreenY);
    hdr.blue_x = get_float(bmdDeckLinkFrameMetadataHDRDisplayPrimariesBlueX);
    hdr.blue_y = get_float(bmdDeckLinkFrameMetadataHDRDisplayPrimariesBlueY);
    hdr.white_x = get_float(bmdDeckLinkFrameMetadataHDRWhitePointX);
    hdr.white_y = get_float(bmdDeckLinkFrameMetadataHDRWhitePointY);
    hdr.max_display_mastering_luminance =
        get_float(bmdDeckLinkFrameMetadataHDRMaxDisplayMasteringLuminance);
    hdr.min_display_mastering_luminance =
        get_float(bmdDeckLinkFrameMetadataHDRMinDisplayMasteringLuminance);
    hdr.max_cll = get_float(bmdDeckLinkFrameMetadataHDRMaximumContentLightLevel);
    hdr.max_fall = get_float(bmdDeckLinkFrameMetadataHDRMaximumFrameAverageLightLevel);
    md.hdr = hdr;
    return md;
}
