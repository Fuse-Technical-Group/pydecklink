#include "bind_api_info.h"
#include "platform.h"
#include "comptr.h"
#include <nanobind/stl/string.h>
#include <cstdint>
#include <stdexcept>
#include <string>

// IDeckLinkAPIInformation reports the running Desktop Video runtime
// (libDeckLinkAPI.so / CoreFoundation plug-in / COM server), not the
// vendored SDK headers pydecklink built against.  It is a process-global
// singleton — there is no per-device version — so the binding exposes a
// module-level ``api_version()`` rather than a Device property.

/// Python-visible record of the Desktop Video runtime version.
/// Built once per call to ``api_version()`` from the SDK's packed value
/// and formatted string.  Kept as a plain struct (not nb::tuple) so
/// callers can read a string for logs and the parts for threshold gating
/// without re-parsing.
struct APIVersion {
    std::string string;
    int64_t packed;
    int major;
    int minor;
    int sub;
    int extra;
};

void init_decklink_api_info(nb::module_& m) {
    nb::class_<APIVersion>(m, "APIVersion")
        .def_ro("string", &APIVersion::string,
            "Formatted version string reported by the SDK (e.g. \"15.3.0\").")
        .def_ro("packed", &APIVersion::packed,
            "Raw 32-bit packed version as returned by the SDK.")
        .def_ro("major", &APIVersion::major,
            "Major version (high byte of packed).")
        .def_ro("minor", &APIVersion::minor,
            "Minor version (second byte of packed).")
        .def_ro("sub", &APIVersion::sub,
            "Sub version (third byte of packed).")
        .def_ro("extra", &APIVersion::extra,
            "Extra version (low byte of packed).")
        .def("__str__", [](const APIVersion& self) { return self.string; })
        .def("__repr__", [](const APIVersion& self) {
            return "APIVersion('" + self.string + "')";
        });

    m.def("api_version", []() -> APIVersion {
        // CreateDeckLinkAPIInformationInstance returns a fresh ref; wrap
        // it in ComPtr so the SDK singleton is released on early return.
        ComPtr<IDeckLinkAPIInformation> info(CreateDeckLinkAPIInformationInstance());
        if (!info)
            throw std::runtime_error(
                "DeckLink driver not installed (CreateDeckLinkAPIInformationInstance returned NULL). "
                "Install Desktop Video from blackmagicdesign.com.");

        int64_t packed = 0;
        HRESULT hr = info->GetInt(BMDDeckLinkAPIVersion, &packed);
        if (hr != S_OK)
            throw std::runtime_error(
                "IDeckLinkAPIInformation::GetInt(BMDDeckLinkAPIVersion) failed (HRESULT " +
                std::to_string(hr) + ")");

        dlstring_t raw_str = nullptr;
        hr = info->GetString(BMDDeckLinkAPIVersion, &raw_str);
        if (hr != S_OK)
            throw std::runtime_error(
                "IDeckLinkAPIInformation::GetString(BMDDeckLinkAPIVersion) failed (HRESULT " +
                std::to_string(hr) + ")");
        // DeckLinkStringToStd takes ownership and frees on return.
        std::string version_str = DeckLinkStringToStd(raw_str);

        // The SDK packs four byte-sized fields into a 32-bit value:
        //   byte 3 (high) = major,  byte 2 = minor,
        //   byte 1        = sub,    byte 0 (low) = extra.
        const uint32_t bits = static_cast<uint32_t>(packed);
        APIVersion v;
        v.string = std::move(version_str);
        v.packed = packed;
        v.major  = static_cast<int>((bits >> 24) & 0xFFu);
        v.minor  = static_cast<int>((bits >> 16) & 0xFFu);
        v.sub    = static_cast<int>((bits >>  8) & 0xFFu);
        v.extra  = static_cast<int>( bits        & 0xFFu);
        return v;
    },
    "Return the running Desktop Video runtime version. "
    "Raises RuntimeError if Desktop Video is not installed.");
}
