#pragma once

#include <nanobind/nanobind.h>
#include "bind_device.h"

namespace nb = nanobind;

/// Lightweight ``IDeckLinkIPExtensions`` wrapper: the IP flows of one
/// sub-device (§spec:ip-flows).
struct IPExtensions {
    ComPtr<IDeckLinkIPExtensions> ext;

    IPExtensions() = default;
    explicit IPExtensions(ComPtr<IDeckLinkIPExtensions> e) : ext(std::move(e)) {}
};

/// Lightweight ``IDeckLinkIPFlow`` wrapper. The attribute, status and
/// setting interfaces are queried from the flow per call.
struct IPFlow {
    ComPtr<IDeckLinkIPFlow> flow;

    IPFlow() = default;
    explicit IPFlow(ComPtr<IDeckLinkIPFlow> f) : flow(std::move(f)) {}
};

void init_decklink_ip_flow(nb::module_& m, nb::class_<Device>& device);
