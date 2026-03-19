#include "bind_common.h"

NB_MODULE(_bindings, m) {
    m.doc() = "pyntv2: Python bindings for libajantv2";
    init_enums(m);
    init_card(m);
    init_transfer(m);
}
