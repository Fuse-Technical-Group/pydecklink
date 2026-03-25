#include <nanobind/nanobind.h>

namespace nb = nanobind;

#ifdef HAVE_DECKLINK_SDK
#include "bind_enums.h"
#include "bind_device.h"
#include "bind_format.h"
#include "bind_output.h"
#include "bind_input.h"
#endif

NB_MODULE(_bindings, m) {
    m.doc() = "pydecklink: Python bindings for Blackmagic DeckLink SDK";
#ifdef HAVE_DECKLINK_SDK
    m.attr("HAS_SDK") = true;
    init_decklink_enums(m);
    auto device_cls = init_decklink_device(m);
    init_decklink_format(m);
    init_decklink_output(m, device_cls);
    init_decklink_input(m, device_cls);
#else
    m.attr("HAS_SDK") = false;
#endif
}
