#include <nanobind/nanobind.h>

namespace nb = nanobind;

#ifdef HAVE_DECKLINK_SDK
#include "bind_enums.h"
#include "bind_device.h"
#include "bind_format.h"
#endif

NB_MODULE(_bindings, m) {
    m.doc() = "pydecklink: Python bindings for Blackmagic DeckLink SDK";
#ifdef HAVE_DECKLINK_SDK
    m.attr("HAS_SDK") = true;
    init_decklink_enums(m);
    init_decklink_device(m);
    init_decklink_format(m);
#else
    m.attr("HAS_SDK") = false;
#endif
}
