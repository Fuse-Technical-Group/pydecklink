#pragma once

#include <nanobind/nanobind.h>
#include "bind_device.h"

namespace nb = nanobind;

void init_decklink_output(nb::module_& m, nb::class_<Device>& device);
