#pragma once

#include <nanobind/nanobind.h>

namespace nb = nanobind;

void init_decklink_device(nb::module_& m);
