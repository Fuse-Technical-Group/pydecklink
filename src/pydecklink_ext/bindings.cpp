#include <nanobind/nanobind.h>

namespace nb = nanobind;

#ifdef HAVE_DECKLINK_SDK
#include "bind_enums.h"
#include "bind_device.h"
#include "bind_format.h"
#include "bind_output.h"
#include "bind_input.h"
#include "bind_allocator.h"
#endif

NB_MODULE(_bindings, m) {
    m.doc() = "pydecklink: Python bindings for Blackmagic DeckLink SDK";
#ifdef HAVE_DECKLINK_SDK
    m.attr("HAS_SDK") = true;
    m.def("_host_frame_refs", []() {
        return g_host_frame_refs.load(std::memory_order_relaxed);
    }, "Live host-side IDeckLinkMutableVideoFrame refs held by schedule_frame.");
    init_decklink_enums(m);
    auto device_cls = init_decklink_device(m);
    init_decklink_format(m);
    init_decklink_output(m, device_cls);
    init_decklink_input(m, device_cls);
    init_decklink_allocator(m, device_cls);
#else
    m.attr("HAS_SDK") = false;
#endif
}
