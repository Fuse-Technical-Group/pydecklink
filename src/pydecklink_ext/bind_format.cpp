#include "bind_format.h"
#include "DeckLinkAPI.h"
#include <nanobind/nanobind.h>
#include <stdexcept>
#include <unordered_map>

/// Mode metadata: width, height, frame duration, timescale.
struct ModeInfo {
    long width;
    long height;
    int64_t duration;
    int64_t timescale;
};

/// Bytes per pixel for each pixel format. Returns 0 for variable-rate codecs.
static int bytes_per_pixel_numerator(_BMDPixelFormat pf) {
    switch (pf) {
        case bmdFormat8BitYUV:     return 2;   // UYVY: 2 bytes/pixel
        case bmdFormat10BitYUV:    return 8;   // v210: 8 bytes per 3 pixels (handled specially)
        case bmdFormat8BitARGB:    return 4;
        case bmdFormat8BitBGRA:    return 4;
        case bmdFormat10BitRGB:    return 4;   // r210: 4 bytes/pixel (32-bit packed)
        case bmdFormat10BitRGBXLE: return 4;
        case bmdFormat10BitRGBX:   return 4;
        case bmdFormat12BitRGB:    return 36;  // 36 bytes per 8 pixels (handled specially)
        case bmdFormat12BitRGBLE:  return 36;
        case bmdFormat10BitYUVA:   return 0;   // Variable
        default:                   return 0;
    }
}

/// Compute row bytes for a given width and pixel format.
static long compute_row_bytes(long width, _BMDPixelFormat pf) {
    switch (pf) {
        case bmdFormat8BitYUV:     return width * 2;
        case bmdFormat10BitYUV: {
            // v210: 48 pixels per 128 bytes, rounded up to 48-pixel blocks
            long blocks = (width + 47) / 48;
            return blocks * 128;
        }
        case bmdFormat8BitARGB:    return width * 4;
        case bmdFormat8BitBGRA:    return width * 4;
        case bmdFormat10BitRGB:    return width * 4;  // r210 = 4 bytes/pixel (2:10:10:10)
        case bmdFormat10BitRGBXLE: return width * 4;
        case bmdFormat10BitRGBX:   return width * 4;
        case bmdFormat12BitRGB:    return (width * 36 + 7) / 8;  // 36 bits/pixel
        case bmdFormat12BitRGBLE:  return (width * 36 + 7) / 8;
        case bmdFormat10BitYUVA:   return width * 4;  // Approximate
        default:
            throw std::invalid_argument("unsupported pixel format for row bytes calculation");
    }
}

// Build the mode info table. Values from the DeckLink SDK documentation.
// Each mode is keyed by its BMDDisplayMode FourCC value.
static const std::unordered_map<uint32_t, ModeInfo>& mode_table() {
    static const std::unordered_map<uint32_t, ModeInfo> table = {
        // SD
        {bmdModeNTSC,        {720, 486, 1001, 30000}},
        {bmdModeNTSC2398,    {720, 486, 1001, 24000}},
        {bmdModePAL,         {720, 576, 1000, 25000}},
        {bmdModeNTSCp,       {720, 486, 1001, 30000}},
        {bmdModePALp,        {720, 576, 1000, 25000}},
        // HD 1080
        {bmdModeHD1080p2398, {1920, 1080, 1001, 24000}},
        {bmdModeHD1080p24,   {1920, 1080, 1000, 24000}},
        {bmdModeHD1080p25,   {1920, 1080, 1000, 25000}},
        {bmdModeHD1080p2997, {1920, 1080, 1001, 30000}},
        {bmdModeHD1080p30,   {1920, 1080, 1000, 30000}},
        {bmdModeHD1080p4795, {1920, 1080, 1001, 48000}},
        {bmdModeHD1080p48,   {1920, 1080, 1000, 48000}},
        {bmdModeHD1080p50,   {1920, 1080, 1000, 50000}},
        {bmdModeHD1080p5994, {1920, 1080, 1001, 60000}},
        {bmdModeHD1080p6000, {1920, 1080, 1000, 60000}},
        {bmdModeHD1080p9590, {1920, 1080, 1001, 96000}},
        {bmdModeHD1080p96,   {1920, 1080, 1000, 96000}},
        {bmdModeHD1080p100,  {1920, 1080, 1000, 100000}},
        {bmdModeHD1080p11988,{1920, 1080, 1001, 120000}},
        {bmdModeHD1080p120,  {1920, 1080, 1000, 120000}},
        {bmdModeHD1080i50,   {1920, 1080, 1000, 25000}},
        {bmdModeHD1080i5994, {1920, 1080, 1001, 30000}},
        {bmdModeHD1080i6000, {1920, 1080, 1000, 30000}},
        // HD 720
        {bmdModeHD720p50,    {1280, 720, 1000, 50000}},
        {bmdModeHD720p5994,  {1280, 720, 1001, 60000}},
        {bmdModeHD720p60,    {1280, 720, 1000, 60000}},
        // 2K
        {bmdMode2k2398,      {2048, 1556, 1001, 24000}},
        {bmdMode2k24,        {2048, 1556, 1000, 24000}},
        {bmdMode2k25,        {2048, 1556, 1000, 25000}},
        // 2K DCI
        {bmdMode2kDCI2398,   {2048, 1080, 1001, 24000}},
        {bmdMode2kDCI24,     {2048, 1080, 1000, 24000}},
        {bmdMode2kDCI25,     {2048, 1080, 1000, 25000}},
        {bmdMode2kDCI2997,   {2048, 1080, 1001, 30000}},
        {bmdMode2kDCI30,     {2048, 1080, 1000, 30000}},
        {bmdMode2kDCI4795,   {2048, 1080, 1001, 48000}},
        {bmdMode2kDCI48,     {2048, 1080, 1000, 48000}},
        {bmdMode2kDCI50,     {2048, 1080, 1000, 50000}},
        {bmdMode2kDCI5994,   {2048, 1080, 1001, 60000}},
        {bmdMode2kDCI60,     {2048, 1080, 1000, 60000}},
        {bmdMode2kDCI9590,   {2048, 1080, 1001, 96000}},
        {bmdMode2kDCI96,     {2048, 1080, 1000, 96000}},
        {bmdMode2kDCI100,    {2048, 1080, 1000, 100000}},
        {bmdMode2kDCI11988,  {2048, 1080, 1001, 120000}},
        {bmdMode2kDCI120,    {2048, 1080, 1000, 120000}},
        // 4K UHD
        {bmdMode4K2160p2398, {3840, 2160, 1001, 24000}},
        {bmdMode4K2160p24,   {3840, 2160, 1000, 24000}},
        {bmdMode4K2160p25,   {3840, 2160, 1000, 25000}},
        {bmdMode4K2160p2997, {3840, 2160, 1001, 30000}},
        {bmdMode4K2160p30,   {3840, 2160, 1000, 30000}},
        {bmdMode4K2160p4795, {3840, 2160, 1001, 48000}},
        {bmdMode4K2160p48,   {3840, 2160, 1000, 48000}},
        {bmdMode4K2160p50,   {3840, 2160, 1000, 50000}},
        {bmdMode4K2160p5994, {3840, 2160, 1001, 60000}},
        {bmdMode4K2160p60,   {3840, 2160, 1000, 60000}},
        {bmdMode4K2160p9590, {3840, 2160, 1001, 96000}},
        {bmdMode4K2160p96,   {3840, 2160, 1000, 96000}},
        {bmdMode4K2160p100,  {3840, 2160, 1000, 100000}},
        {bmdMode4K2160p11988,{3840, 2160, 1001, 120000}},
        {bmdMode4K2160p120,  {3840, 2160, 1000, 120000}},
        // 4K DCI
        {bmdMode4kDCI2398,   {4096, 2160, 1001, 24000}},
        {bmdMode4kDCI24,     {4096, 2160, 1000, 24000}},
        {bmdMode4kDCI25,     {4096, 2160, 1000, 25000}},
        {bmdMode4kDCI2997,   {4096, 2160, 1001, 30000}},
        {bmdMode4kDCI30,     {4096, 2160, 1000, 30000}},
        {bmdMode4kDCI4795,   {4096, 2160, 1001, 48000}},
        {bmdMode4kDCI48,     {4096, 2160, 1000, 48000}},
        {bmdMode4kDCI50,     {4096, 2160, 1000, 50000}},
        {bmdMode4kDCI5994,   {4096, 2160, 1001, 60000}},
        {bmdMode4kDCI60,     {4096, 2160, 1000, 60000}},
        {bmdMode4kDCI9590,   {4096, 2160, 1001, 96000}},
        {bmdMode4kDCI96,     {4096, 2160, 1000, 96000}},
        {bmdMode4kDCI100,    {4096, 2160, 1000, 100000}},
        {bmdMode4kDCI11988,  {4096, 2160, 1001, 120000}},
        {bmdMode4kDCI120,    {4096, 2160, 1000, 120000}},
        // 8K UHD
        {bmdMode8K4320p2398, {7680, 4320, 1001, 24000}},
        {bmdMode8K4320p24,   {7680, 4320, 1000, 24000}},
        {bmdMode8K4320p25,   {7680, 4320, 1000, 25000}},
        {bmdMode8K4320p2997, {7680, 4320, 1001, 30000}},
        {bmdMode8K4320p30,   {7680, 4320, 1000, 30000}},
        {bmdMode8K4320p4795, {7680, 4320, 1001, 48000}},
        {bmdMode8K4320p48,   {7680, 4320, 1000, 48000}},
        {bmdMode8K4320p50,   {7680, 4320, 1000, 50000}},
        {bmdMode8K4320p5994, {7680, 4320, 1001, 60000}},
        {bmdMode8K4320p60,   {7680, 4320, 1000, 60000}},
        // 8K DCI
        {bmdMode8kDCI2398,   {8192, 4320, 1001, 24000}},
        {bmdMode8kDCI24,     {8192, 4320, 1000, 24000}},
        {bmdMode8kDCI25,     {8192, 4320, 1000, 25000}},
        {bmdMode8kDCI2997,   {8192, 4320, 1001, 30000}},
        {bmdMode8kDCI30,     {8192, 4320, 1000, 30000}},
        {bmdMode8kDCI4795,   {8192, 4320, 1001, 48000}},
        {bmdMode8kDCI48,     {8192, 4320, 1000, 48000}},
        {bmdMode8kDCI50,     {8192, 4320, 1000, 50000}},
        {bmdMode8kDCI5994,   {8192, 4320, 1001, 60000}},
        {bmdMode8kDCI60,     {8192, 4320, 1000, 60000}},
        // PC modes (subset)
        {bmdMode640x480p60,    {640, 480, 1000, 60000}},
        {bmdMode800x600p60,    {800, 600, 1000, 60000}},
        {bmdMode1920x1200p50,  {1920, 1200, 1000, 50000}},
        {bmdMode1920x1200p60,  {1920, 1200, 1000, 60000}},
    };
    return table;
}

static const ModeInfo& lookup_mode(_BMDDisplayMode mode) {
    auto& table = mode_table();
    auto it = table.find(static_cast<uint32_t>(mode));
    if (it == table.end())
        throw std::invalid_argument("unknown display mode");
    return it->second;
}

void init_decklink_format(nb::module_& m) {

    m.def("get_mode_width", [](_BMDDisplayMode mode) -> long {
        return lookup_mode(mode).width;
    }, nb::arg("mode"),
       "Return the raster width in pixels for a display mode.");

    m.def("get_mode_height", [](_BMDDisplayMode mode) -> long {
        return lookup_mode(mode).height;
    }, nb::arg("mode"),
       "Return the raster height in pixels for a display mode.");

    m.def("get_mode_fps", [](_BMDDisplayMode mode) -> double {
        auto& info = lookup_mode(mode);
        return static_cast<double>(info.timescale) / static_cast<double>(info.duration);
    }, nb::arg("mode"),
       "Return the frames per second for a display mode.");

    m.def("get_frame_bytes", [](_BMDDisplayMode mode, _BMDPixelFormat pf) -> long {
        auto& info = lookup_mode(mode);
        long row_bytes = compute_row_bytes(info.width, pf);
        return row_bytes * info.height;
    }, nb::arg("mode"), nb::arg("pixel_format"),
       "Return the total frame byte count for a display mode and pixel format.");

    m.def("get_row_bytes", [](_BMDPixelFormat pf, long width) -> long {
        return compute_row_bytes(width, pf);
    }, nb::arg("pixel_format"), nb::arg("width"),
       "Return the row byte count for a pixel format and width.");
}
