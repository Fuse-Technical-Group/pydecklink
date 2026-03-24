#pragma once

#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <stdexcept>
#include <string>

namespace nb = nanobind;

inline void check(bool result, const char* method) {
    if (!result) throw std::runtime_error(std::string(method) + " failed");
}

/// Validate that an ndarray is C-contiguous. Raises ValueError if not.
inline void check_contiguous(const nb::ndarray<>& buffer) {
    if (buffer.ndim() == 0) return;
    size_t expected = buffer.itemsize();
    for (int i = buffer.ndim() - 1; i >= 0; --i) {
        if (buffer.stride(i) != (nb::ssize_t)expected)
            throw nb::value_error("buffer must be C-contiguous");
        expected *= buffer.shape(i);
    }
}

void init_enums(nb::module_& m);
void init_card(nb::module_& m);
void init_transfer(nb::module_& m);
