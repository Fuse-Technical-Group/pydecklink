#pragma once

#include <nanobind/nanobind.h>
#include <cstdint>

namespace nb = nanobind;

/// Electro-optical transfer function, signalled per CTA-861.3.
/// The DeckLink SDK stores this as a raw int (0-7) under
/// ``bmdDeckLinkFrameMetadataHDRElectroOpticalTransferFunc``; it has no
/// SDK enum, so pydecklink defines the CTA-861.3 code points it uses.
enum class EOTF : int64_t {
    Reserved = 0,
    SDR = 1,   ///< Traditional gamma, SDR luminance range.
    PQ = 2,    ///< SMPTE ST 2084 perceptual quantizer (HDR10).
    HLG = 3,   ///< Hybrid log-gamma (ARIB STD-B67 / Rec.2100).
};

void init_decklink_enums(nb::module_& m);
