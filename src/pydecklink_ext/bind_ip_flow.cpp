#include "bind_ip_flow.h"
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

// QueryInterface one of a flow's three accessor interfaces, or throw.
template <typename T>
ComPtr<T> query_flow(const IPFlow& self, REFIID iid, const char* name) {
    if (!self.flow)
        throw std::runtime_error("IPFlow is null");
    ComPtr<T> out;
    if (self.flow->QueryInterface(iid, (void**)out.put()) != S_OK || !out)
        throw std::runtime_error(std::string("IP flow does not expose ") + name);
    return out;
}

int64_t flow_attribute_int(const IPFlow& self, BMDDeckLinkIPFlowAttributeID attrID) {
    auto attrs = query_flow<IDeckLinkIPFlowAttributes>(
        self, IID_IDeckLinkIPFlowAttributes, "IDeckLinkIPFlowAttributes");
    int64_t value = 0;
    HRESULT hr = attrs->GetInt(attrID, &value);
    if (hr != S_OK)
        throw std::runtime_error("GetInt failed (HRESULT " + std::to_string(hr) + ")");
    return value;
}

}  // namespace

// --- Module bindings ---

void init_decklink_ip_flow(nb::module_& m, nb::class_<Device>& device) {

    // -- IPFlow --
    nb::class_<IPFlow>(m, "IPFlow",
        "Wraps ``IDeckLinkIPFlow``: one essence, one direction, of one "
        "sub-device of a DeckLink IP (§spec:ip-flows).")
        .def("enable",
            [](IPFlow& self) {
                if (!self.flow)
                    throw std::runtime_error("IPFlow is null");
                HRESULT hr = self.flow->Enable();
                if (hr != S_OK)
                    throw std::runtime_error("Enable failed (HRESULT " + std::to_string(hr) + ")");
            },
            "Start the flow sending or receiving.")
        .def("disable",
            [](IPFlow& self) {
                if (!self.flow)
                    throw std::runtime_error("IPFlow is null");
                HRESULT hr = self.flow->Disable();
                if (hr != S_OK)
                    throw std::runtime_error("Disable failed (HRESULT " + std::to_string(hr) + ")");
            },
            "Stop the flow sending or receiving.")
        .def("get_attribute_int", &flow_attribute_int,
            nb::arg("attr_id"),
            "Get an integer flow attribute via IDeckLinkIPFlowAttributes.")
        .def("get_status_string",
            [](IPFlow& self, BMDDeckLinkIPFlowStatusID statusID) -> std::string {
                auto status = query_flow<IDeckLinkIPFlowStatus>(
                    self, IID_IDeckLinkIPFlowStatus, "IDeckLinkIPFlowStatus");
                dlstring_t value = nullptr;
                HRESULT hr = status->GetString(statusID, &value);
                if (hr != S_OK)
                    throw std::runtime_error("GetString failed (HRESULT " + std::to_string(hr) + ")");
                return DeckLinkStringToStd(value);
            },
            nb::arg("status_id"),
            "Get a string flow status value via IDeckLinkIPFlowStatus — the "
            "SDP the sub-device offers for this essence, which its input and "
            "output flows both read (§spec:ip-flows).")
        .def("get_setting_string",
            [](IPFlow& self, BMDDeckLinkIPFlowSettingID settingID) -> std::string {
                auto setting = query_flow<IDeckLinkIPFlowSetting>(
                    self, IID_IDeckLinkIPFlowSetting, "IDeckLinkIPFlowSetting");
                dlstring_t value = nullptr;
                HRESULT hr = setting->GetString(settingID, &value);
                if (hr != S_OK)
                    throw std::runtime_error("GetString failed (HRESULT " + std::to_string(hr) + ")");
                return DeckLinkStringToStd(value);
            },
            nb::arg("setting_id"),
            "Get a string flow setting via IDeckLinkIPFlowSetting — the SDP "
            "an input flow receives.")
        .def("set_setting_string",
            [](IPFlow& self, BMDDeckLinkIPFlowSettingID settingID, const std::string& value) {
                auto setting = query_flow<IDeckLinkIPFlowSetting>(
                    self, IID_IDeckLinkIPFlowSetting, "IDeckLinkIPFlowSetting");
                DeckLinkStringFromStd held(value);
                HRESULT hr = setting->SetString(settingID, held.get());
                if (hr != S_OK)
                    throw std::runtime_error("SetString failed (HRESULT " + std::to_string(hr) + ")");
            },
            nb::arg("setting_id"), nb::arg("value"),
            "Set a string flow setting via IDeckLinkIPFlowSetting — the SDP "
            "an input flow receives. A value the card rejects answers S_OK "
            "and changes nothing, so read it back (§spec:ip-flows).")
        // Convenience over get_attribute_int (§spec:binding-philosophy).
        .def_prop_ro("id",
            [](IPFlow& self) -> int64_t {
                return flow_attribute_int(self, bmdDeckLinkIPFlowID);
            },
            "The flow's identifier, unique within its sub-device and not "
            "across the card.")
        .def_prop_ro("direction",
            [](IPFlow& self) -> BMDIPFlowDirection {
                return static_cast<BMDIPFlowDirection>(
                    flow_attribute_int(self, bmdDeckLinkIPFlowDirection));
            },
            "Whether the flow sends or receives.")
        .def_prop_ro("type",
            [](IPFlow& self) -> BMDIPFlowType {
                return static_cast<BMDIPFlowType>(
                    flow_attribute_int(self, bmdDeckLinkIPFlowType));
            },
            "The essence the flow carries.")
        .def("__repr__",
            [](IPFlow& self) {
                return std::string("IPFlow(") +
                       (self.flow ? "valid" : "null") + ")";
            }, nb::sig("def __repr__(self) -> str"));

    // -- IPExtensions --
    nb::class_<IPExtensions>(m, "IPExtensions",
        "Wraps ``IDeckLinkIPExtensions``. Obtained via "
        "``Device.ip_extensions``.")
        .def("get_ip_flows",
            [](IPExtensions& self) -> std::vector<IPFlow> {
                if (!self.ext)
                    throw std::runtime_error("IPExtensions is null");
                ComPtr<IDeckLinkIPFlowIterator> iter;
                HRESULT hr = self.ext->GetDeckLinkIPFlowIterator(iter.put());
                if (hr != S_OK || !iter)
                    throw std::runtime_error(
                        "GetDeckLinkIPFlowIterator failed (HRESULT " +
                        std::to_string(hr) + ")");
                std::vector<IPFlow> out;
                for (;;) {
                    ComPtr<IDeckLinkIPFlow> f;
                    if (iter->Next(f.put()) != S_OK || !f) break;
                    out.emplace_back(std::move(f));
                }
                return out;
            },
            "Return every IP flow of this sub-device.")
        .def("get_ip_flow_by_id",
            [](IPExtensions& self, int64_t flowID) -> IPFlow {
                if (!self.ext)
                    throw std::runtime_error("IPExtensions is null");
                ComPtr<IDeckLinkIPFlow> f;
                HRESULT hr = self.ext->GetIPFlowByID(flowID, f.put());
                if (hr != S_OK || !f)
                    throw std::runtime_error(
                        "GetIPFlowByID failed (HRESULT " + std::to_string(hr) + ")");
                return IPFlow(std::move(f));
            },
            nb::arg("flow_id"),
            "Look up one of this sub-device's IP flows by its identifier.")
        .def("__repr__",
            [](IPExtensions& self) {
                return std::string("IPExtensions(") +
                       (self.ext ? "valid" : "null") + ")";
            }, nb::sig("def __repr__(self) -> str"));

    // -- Device.ip_extensions --
    device.def_prop_ro("ip_extensions",
        [](Device& self) -> nb::object {
            ComPtr<IDeckLinkIPExtensions> ext;
            if (self.dl->QueryInterface(IID_IDeckLinkIPExtensions,
                                        (void**)ext.put()) != S_OK || !ext)
                return nb::none();
            return nb::cast(IPExtensions(std::move(ext)));
        },
        nb::sig("def ip_extensions(self) -> IPExtensions | None"),
        "Return the sub-device's ``IPExtensions``, or ``None`` if it is not "
        "a DeckLink IP.");
}
