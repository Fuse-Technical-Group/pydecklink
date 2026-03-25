#include <nanobind/nanobind.h>

namespace nb = nanobind;

NB_MODULE(_bindings, m) {
    m.doc() = "pydecklink: Python bindings for Blackmagic DeckLink SDK";
}
