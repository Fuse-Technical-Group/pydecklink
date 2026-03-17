#include <nanobind/nanobind.h>

namespace nb = nanobind;

NB_MODULE(_bindings, m) {
    m.doc() = "pyntv2: Python bindings for libajantv2";
}
