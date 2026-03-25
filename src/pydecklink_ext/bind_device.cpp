#include "bind_device.h"
#include "DeckLinkAPI.h"
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>
#include <stdexcept>
#include <string>
#include <vector>

// --- Device implementation ---

Device::Device(int index) {
    IDeckLinkIterator* iter = CreateDeckLinkIteratorInstance();
    if (!iter)
        throw std::runtime_error(
            "DeckLink driver not installed. "
            "Install Desktop Video from blackmagicdesign.com.");
    ComPtr<IDeckLinkIterator> guard(iter);
    IDeckLink* p = nullptr;
    int i = 0;
    while (guard->Next(&p) == S_OK) {
        if (i == index) {
            dl = ComPtr<IDeckLink>(p);
            return;
        }
        p->Release();
        ++i;
    }
    throw std::out_of_range(
        "Device index " + std::to_string(index) +
        " out of range (found " + std::to_string(i) + " devices)");
}

std::string Device::model_name() const {
    const char* str = nullptr;
    if (dl->GetModelName(&str) != S_OK || !str) return "";
    std::string result(str);
    free(const_cast<char*>(str));
    return result;
}

std::string Device::display_name() const {
    const char* str = nullptr;
    if (dl->GetDisplayName(&str) != S_OK || !str) return "";
    std::string result(str);
    free(const_cast<char*>(str));
    return result;
}

bool Device::supports_capture() const {
    IDeckLinkProfileAttributes* attrs = nullptr;
    if (dl->QueryInterface(IID_IDeckLinkProfileAttributes, (void**)&attrs) != S_OK)
        return false;
    int64_t io = 0;
    attrs->GetInt(BMDDeckLinkVideoIOSupport, &io);
    attrs->Release();
    return (io & bmdDeviceSupportsCapture) != 0;
}

bool Device::supports_playback() const {
    IDeckLinkProfileAttributes* attrs = nullptr;
    if (dl->QueryInterface(IID_IDeckLinkProfileAttributes, (void**)&attrs) != S_OK)
        return false;
    int64_t io = 0;
    attrs->GetInt(BMDDeckLinkVideoIOSupport, &io);
    attrs->Release();
    return (io & bmdDeviceSupportsPlayback) != 0;
}

bool Device::supports_input_format_detection() const {
    IDeckLinkProfileAttributes* attrs = nullptr;
    if (dl->QueryInterface(IID_IDeckLinkProfileAttributes, (void**)&attrs) != S_OK)
        return false;
    bool flag = false;
    attrs->GetFlag(BMDDeckLinkSupportsInputFormatDetection, &flag);
    attrs->Release();
    return flag;
}

bool Device::supports_hdr() const {
    IDeckLinkProfileAttributes* attrs = nullptr;
    if (dl->QueryInterface(IID_IDeckLinkProfileAttributes, (void**)&attrs) != S_OK)
        return false;
    bool flag = false;
    attrs->GetFlag(BMDDeckLinkSupportsHDRMetadata, &flag);
    attrs->Release();
    return flag;
}

// --- Module bindings ---

/// Get an IDeckLinkIterator, throwing if the driver is not installed.
static ComPtr<IDeckLinkIterator> require_iterator() {
    IDeckLinkIterator* iter = CreateDeckLinkIteratorInstance();
    if (!iter)
        throw std::runtime_error(
            "DeckLink driver not installed (CreateDeckLinkIteratorInstance returned NULL). "
            "Install Desktop Video from blackmagicdesign.com.");
    return ComPtr<IDeckLinkIterator>(iter);
}

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
        IDeckLink* dl = nullptr;
        while (iter->Next(&dl) == S_OK) {
            dl->Release();
            ++count;
        }
        return count;
    }, "Return the number of DeckLink devices present.");

    // -- list_devices --
    m.def("list_devices", []() -> std::vector<DeviceInfo> {
        auto iter = require_iterator();
        std::vector<DeviceInfo> result;
        IDeckLink* dl = nullptr;
        int idx = 0;
        while (iter->Next(&dl) == S_OK) {
            DeviceInfo info;
            info.index = idx++;
            const char* str = nullptr;
            if (dl->GetModelName(&str) == S_OK && str) {
                info.model_name = str;
                free(const_cast<char*>(str));
            }
            str = nullptr;
            if (dl->GetDisplayName(&str) == S_OK && str) {
                info.display_name = str;
                free(const_cast<char*>(str));
            }
            dl->Release();
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
        .def("__exit__", [](Device&, nb::args) {});

    return device_cls;
}
