#pragma once

#include <nanobind/nanobind.h>
#include <stdexcept>
#include <string>

namespace nb = nanobind;

inline void check(bool result, const char* method) {
    if (!result) throw std::runtime_error(std::string(method) + " failed");
}

void init_enums(nb::module_& m);
void init_card(nb::module_& m);
void init_transfer(nb::module_& m);
