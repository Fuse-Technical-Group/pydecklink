#include "bind_device.h"
#include "bind_input.h"   // Complete InputCallback type for ~Device synthesis.
#include "bind_output.h"  // Complete OutputCallback type for ~Device synthesis.
#include "bind_profile.h" // Complete ProfileManager type for ~Device synthesis.
#include <nanobind/stl/string.h>
#include <nanobind/stl/tuple.h>
#include <nanobind/stl/vector.h>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

// --- Device implementation ---

Device::~Device() {
    // Drop the SDK's refs to our callbacks before the ComPtrs auto-release.
    // Without this, the SDK retains a ref to input_callback_ via SetCallback,
    // and InputCallback holds a ComPtr<IDeckLinkInput> back — a refcount
    // cycle that Device destruction alone cannot break.
    // This is cycle-break only; full SDK shutdown (stop streams, release
    // hardware) is the caller's job via disable_video_input / _output.
    if (input_) input_->SetCallback(nullptr);
    if (output_) output_->SetScheduledFrameCompletionCallback(nullptr);
    // Profile callback follows the same pattern: clear the SDK's
    // registration so the adapter (which holds an ``nb::object`` to a
    // Python ``ProfileCallback``) can be destroyed without a lingering
    // SDK-side ref. ``ProfileManager`` owns the adapter via ComPtr; we
    // just need to break the SDK->adapter edge here.
    if (profile_manager_ && profile_manager_->mgr)
        profile_manager_->mgr->SetCallback(nullptr);
}

Device::Device(int index) {
    auto iter = require_iterator();
    int i = 0;
    for (;;) {
        ComPtr<IDeckLink> p;
        if (iter->Next(p.put()) != S_OK) break;
        if (i == index) {
            dl = std::move(p);
            return;
        }
        ++i;
    }
    throw std::out_of_range(
        "Device index " + std::to_string(index) +
        " out of range (found " + std::to_string(i) + " devices)");
}

std::string Device::model_name() const {
    dlstring_t str = nullptr;
    if (dl->GetModelName(&str) != S_OK || !str) return "";
    return DeckLinkStringToStd(str);
}

std::string Device::display_name() const {
    dlstring_t str = nullptr;
    if (dl->GetDisplayName(&str) != S_OK || !str) return "";
    return DeckLinkStringToStd(str);
}

bool Device::supports_capture() const {
    ComPtr<IDeckLinkProfileAttributes> attrs;
    if (dl->QueryInterface(IID_IDeckLinkProfileAttributes, (void**)attrs.put()) != S_OK)
        return false;
    int64_t io = 0;
    attrs->GetInt(BMDDeckLinkVideoIOSupport, &io);
    return (io & bmdDeviceSupportsCapture) != 0;
}

bool Device::supports_playback() const {
    ComPtr<IDeckLinkProfileAttributes> attrs;
    if (dl->QueryInterface(IID_IDeckLinkProfileAttributes, (void**)attrs.put()) != S_OK)
        return false;
    int64_t io = 0;
    attrs->GetInt(BMDDeckLinkVideoIOSupport, &io);
    return (io & bmdDeviceSupportsPlayback) != 0;
}

bool Device::supports_input_format_detection() const {
    ComPtr<IDeckLinkProfileAttributes> attrs;
    if (dl->QueryInterface(IID_IDeckLinkProfileAttributes, (void**)attrs.put()) != S_OK)
        return false;
    dlbool_t flag = false;
    attrs->GetFlag(BMDDeckLinkSupportsInputFormatDetection, &flag);
    return flag;
}

bool Device::supports_hdr() const {
    ComPtr<IDeckLinkProfileAttributes> attrs;
    if (dl->QueryInterface(IID_IDeckLinkProfileAttributes, (void**)attrs.put()) != S_OK)
        return false;
    dlbool_t flag = false;
    attrs->GetFlag(BMDDeckLinkSupportsHDRMetadata, &flag);
    return flag;
}

/// Python-visible display mode properties extracted from IDeckLinkDisplayMode.
struct DisplayModeInfo {
    _BMDDisplayMode mode;
    std::string name;
    long width;
    long height;
    std::tuple<int64_t, int64_t> frame_rate;  // (duration, timescale)
    _BMDFieldDominance field_dominance;
    uint32_t flags;
};

/// Extract DisplayModeInfo from an IDeckLinkDisplayMode pointer.
/// The caller must ensure dm is non-null.
static DisplayModeInfo extract_display_mode_info(IDeckLinkDisplayMode* dm) {
    DisplayModeInfo info;
    info.mode = static_cast<_BMDDisplayMode>(dm->GetDisplayMode());
    info.width = dm->GetWidth();
    info.height = dm->GetHeight();
    info.field_dominance = static_cast<_BMDFieldDominance>(dm->GetFieldDominance());
    info.flags = dm->GetFlags();

    BMDTimeValue duration = 0;
    BMDTimeScale timescale = 0;
    dm->GetFrameRate(&duration, &timescale);
    info.frame_rate = std::make_tuple(static_cast<int64_t>(duration),
                                      static_cast<int64_t>(timescale));

    dlstring_t str = nullptr;
    if (dm->GetName(&str) == S_OK && str) {
        info.name = DeckLinkStringToStd(str);
    }
    return info;
}

// --- Module bindings ---

nb::class_<Device> init_decklink_device(nb::module_& m) {

    // -- DeviceInfo --
    nb::class_<DeviceInfo>(m, "DeviceInfo")
        .def_ro("model_name", &DeviceInfo::model_name)
        .def_ro("display_name", &DeviceInfo::display_name)
        .def_ro("index", &DeviceInfo::index)
        .def("__repr__", [](const DeviceInfo& self) {
            return "DeviceInfo(index=" + std::to_string(self.index) +
                   ", model='" + self.model_name +
                   "', display='" + self.display_name + "')";
        });

    // -- device_count --
    m.def("device_count", []() -> int {
        auto iter = require_iterator();
        int count = 0;
        for (;;) {
            ComPtr<IDeckLink> dl;
            if (iter->Next(dl.put()) != S_OK) break;
            ++count;
        }
        return count;
    }, "Return the number of DeckLink devices present.");

    // -- list_devices --
    m.def("list_devices", []() -> std::vector<DeviceInfo> {
        auto iter = require_iterator();
        std::vector<DeviceInfo> result;
        int idx = 0;
        for (;;) {
            ComPtr<IDeckLink> dl;
            if (iter->Next(dl.put()) != S_OK) break;
            DeviceInfo info;
            info.index = idx++;
            dlstring_t str = nullptr;
            if (dl->GetModelName(&str) == S_OK && str)
                info.model_name = DeckLinkStringToStd(str);
            str = nullptr;
            if (dl->GetDisplayName(&str) == S_OK && str)
                info.display_name = DeckLinkStringToStd(str);
            result.push_back(std::move(info));
        }
        return result;
    }, "Return a list of DeviceInfo for each DeckLink device.");

    // -- Device --
    auto device_cls = nb::class_<Device>(m, "Device")
        .def(nb::init<int>(), nb::arg("index") = 0)
        .def_prop_ro("model_name", &Device::model_name)
        .def_prop_ro("display_name", &Device::display_name)
        .def_prop_ro("supports_capture", &Device::supports_capture)
        .def_prop_ro("supports_playback", &Device::supports_playback)
        .def_prop_ro("supports_input_format_detection", &Device::supports_input_format_detection)
        .def_prop_ro("supports_hdr", &Device::supports_hdr)
        .def("__repr__", [](const Device& self) {
            return "Device('" + self.display_name() + "')";
        })
        .def("__enter__", [](nb::object self) -> nb::object { return self; })
        .def("__exit__", [](Device&, nb::args) {})
        .def("get_attribute_int",
            [](Device& self, _BMDDeckLinkAttributeID attrID) -> int64_t {
                ComPtr<IDeckLinkProfileAttributes> attrs;
                if (self.dl->QueryInterface(IID_IDeckLinkProfileAttributes, (void**)attrs.put()) != S_OK)
                    throw std::runtime_error("Device does not support profile attributes");
                int64_t value = 0;
                HRESULT hr = attrs->GetInt(attrID, &value);
                if (hr != S_OK)
                    throw std::runtime_error("GetInt failed (HRESULT " + std::to_string(hr) + ")");
                return value;
            },
            nb::arg("attr_id"),
            "Get an integer profile attribute.")
        .def("active_profile",
            [](Device& self) -> _BMDProfileID {
                ComPtr<IDeckLinkProfileAttributes> attrs;
                if (self.dl->QueryInterface(IID_IDeckLinkProfileAttributes, (void**)attrs.put()) != S_OK)
                    throw std::runtime_error("Device does not support profile attributes");
                int64_t value = 0;
                HRESULT hr = attrs->GetInt(BMDDeckLinkProfileID, &value);
                if (hr != S_OK)
                    throw std::runtime_error("Failed to read ProfileID (HRESULT " + std::to_string(hr) + ")");
                return static_cast<_BMDProfileID>(value);
            },
            "Return the active profile ID for this device.")
        .def("set_profile",
            [](Device& self, _BMDProfileID profileID) {
                // Convenience wrapper: equivalent to
                //   self.profile_manager.get_profile(id).set_active()
                // Phrased the long way here to keep the error messages
                // ("Device does not support profile management",
                // "Profile not available", "SetActive failed") identical
                // to the pre-refactor surface that downstream consumers
                // may match on.
                ComPtr<IDeckLinkProfileManager> mgr;
                if (self.dl->QueryInterface(IID_IDeckLinkProfileManager, (void**)mgr.put()) != S_OK)
                    throw std::runtime_error("Device does not support profile management");

                ComPtr<IDeckLinkProfile> profile;
                HRESULT hr = mgr->GetProfile(profileID, profile.put());
                if (hr != S_OK || !profile)
                    throw std::runtime_error("Profile not available (HRESULT " + std::to_string(hr) + ")");

                hr = profile->SetActive();
                if (hr != S_OK)
                    throw std::runtime_error("SetActive failed (HRESULT " + std::to_string(hr) + ")");
            },
            nb::arg("profile_id"),
            "Activate a connector profile. Affects all sub-devices on this card.")
        .def("get_attribute_flag",
            [](Device& self, _BMDDeckLinkAttributeID attrID) -> bool {
                ComPtr<IDeckLinkProfileAttributes> attrs;
                if (self.dl->QueryInterface(IID_IDeckLinkProfileAttributes, (void**)attrs.put()) != S_OK)
                    throw std::runtime_error("Device does not support profile attributes");
                dlbool_t value = false;
                HRESULT hr = attrs->GetFlag(attrID, &value);
                if (hr != S_OK)
                    throw std::runtime_error("GetFlag failed (HRESULT " + std::to_string(hr) + ")");
                return static_cast<bool>(value);
            },
            nb::arg("attr_id"),
            "Get a boolean profile attribute.");

    // -- DisplayModeInfo --
    nb::class_<DisplayModeInfo>(m, "DisplayModeInfo")
        .def_ro("mode", &DisplayModeInfo::mode)
        .def_ro("name", &DisplayModeInfo::name)
        .def_ro("width", &DisplayModeInfo::width)
        .def_ro("height", &DisplayModeInfo::height)
        .def_ro("frame_rate", &DisplayModeInfo::frame_rate)
        .def_ro("field_dominance", &DisplayModeInfo::field_dominance)
        .def_ro("flags", &DisplayModeInfo::flags)
        .def("__repr__", [](const DisplayModeInfo& self) {
            auto [dur, ts] = self.frame_rate;
            return "DisplayModeInfo('" + self.name +
                   "', " + std::to_string(self.width) +
                   "x" + std::to_string(self.height) +
                   ", " + std::to_string(static_cast<double>(ts) / dur) + " fps)";
        });

    // -- Display mode query methods on Device --

    device_cls.def("get_display_mode",
        [](Device& self, _BMDDisplayMode mode) -> DisplayModeInfo {
            ComPtr<IDeckLinkOutput> output;
            if (self.dl->QueryInterface(IID_IDeckLinkOutput, (void**)output.put()) != S_OK)
                throw std::runtime_error("Device does not support output");

            ComPtr<IDeckLinkDisplayMode> dm;
            HRESULT hr = output->GetDisplayMode(mode, dm.put());
            if (hr != S_OK || !dm)
                throw std::runtime_error("GetDisplayMode failed (HRESULT " + std::to_string(hr) + ")");
            return extract_display_mode_info(dm.get());
        },
        nb::arg("mode"),
        "Get display mode properties for a given BMDDisplayMode.");

    device_cls.def("list_output_modes",
        [](Device& self) -> std::vector<DisplayModeInfo> {
            ComPtr<IDeckLinkOutput> output;
            if (self.dl->QueryInterface(IID_IDeckLinkOutput, (void**)output.put()) != S_OK)
                throw std::runtime_error("Device does not support output");

            ComPtr<IDeckLinkDisplayModeIterator> iter;
            HRESULT hr = output->GetDisplayModeIterator(iter.put());
            if (hr != S_OK || !iter)
                throw std::runtime_error("GetDisplayModeIterator failed (HRESULT " + std::to_string(hr) + ")");

            std::vector<DisplayModeInfo> result;
            for (;;) {
                ComPtr<IDeckLinkDisplayMode> dm;
                if (iter->Next(dm.put()) != S_OK) break;
                result.push_back(extract_display_mode_info(dm.get()));
            }
            return result;
        },
        "List all output display modes supported by the device.");

    device_cls.def("does_support_video_mode",
        [](Device& self,
           _BMDVideoConnection connection,
           _BMDDisplayMode mode,
           _BMDPixelFormat pixel_format,
           _BMDVideoOutputConversionMode conversion_mode,
           _BMDSupportedVideoModeFlags flags) -> bool {
            ComPtr<IDeckLinkOutput> output;
            if (self.dl->QueryInterface(IID_IDeckLinkOutput, (void**)output.put()) != S_OK)
                throw std::runtime_error("Device does not support output");

            BMDDisplayMode actual_mode = bmdModeUnknown;
            dlbool_t supported = false;
            HRESULT hr = output->DoesSupportVideoMode(
                connection, mode, pixel_format, conversion_mode, flags,
                &actual_mode, &supported);
            if (hr != S_OK)
                throw std::runtime_error("DoesSupportVideoMode failed (HRESULT " + std::to_string(hr) + ")");
            return static_cast<bool>(supported);
        },
        nb::arg("connection"),
        nb::arg("mode"),
        nb::arg("pixel_format"),
        nb::arg("conversion_mode") = bmdNoVideoOutputConversion,
        nb::arg("flags") = bmdSupportedVideoModeDefault,
        "Check whether the device supports a given video mode, pixel format, and connection.");

    return device_cls;
}
