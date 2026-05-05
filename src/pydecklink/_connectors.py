"""Physical SDI connector labels for multi-sub-device DeckLinks.

The DeckLink SDK does not expose a programmatic physical-port query.
The mapping from `(model, profile, sub_device_index)` to an SDI port
label printed on the card is documented in the DeckLink SDK 15.3
manual, section 2.4.11, page 31. This module reproduces that table
and exposes it via :attr:`pydecklink.Device.connector_label`.

The parenthesized number in `IDeckLink::GetDisplayName` (e.g.
"DeckLink 8K Pro (3)") is the SDK's logical sub-device numbering
(`sub_device_index + 1`), *not* the SDI port label. On the 8K Pro
in 4-sub-device half-duplex profile, sub-device 1 maps to SDI 3 and
sub-device 2 maps to SDI 2 — the opposite of what the display name
suggests.

Returns ``None`` for any (model, profile, sub_device_index) tuple
not in the table. Callers are expected to fall back to raw
attributes (`Device.get_attribute_int(AttributeID.SubDeviceIndex)`,
`Device.display_name`) for unmapped cards.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydecklink._bindings import Device

# Keyed on (model_name_prefix, BMDProfileID.name, sub_device_index).
# Source: DeckLink SDK 15.3 manual, section 2.4.11, page 31.
_SDI_LABEL: dict[tuple[str, str, int], str] = {
    # DeckLink 8K Pro — 4 sub-devices half-duplex (4x single-link)
    ("DeckLink 8K Pro", "FourSubDevicesHalfDuplex", 0): "SDI 1",
    ("DeckLink 8K Pro", "FourSubDevicesHalfDuplex", 1): "SDI 3",
    ("DeckLink 8K Pro", "FourSubDevicesHalfDuplex", 2): "SDI 2",
    ("DeckLink 8K Pro", "FourSubDevicesHalfDuplex", 3): "SDI 4",
    # DeckLink 8K Pro — 2 sub-devices full-duplex (2x dual-link)
    ("DeckLink 8K Pro", "TwoSubDevicesFullDuplex", 0): "SDI 1+2",
    ("DeckLink 8K Pro", "TwoSubDevicesFullDuplex", 1): "SDI 3+4",
    # DeckLink Quad 2 — 8 sub-devices visible in two-sub-devices half-duplex
    ("DeckLink Quad 2", "TwoSubDevicesHalfDuplex", 0): "SDI 1",
    ("DeckLink Quad 2", "TwoSubDevicesHalfDuplex", 1): "SDI 3",
    ("DeckLink Quad 2", "TwoSubDevicesHalfDuplex", 2): "SDI 5",
    ("DeckLink Quad 2", "TwoSubDevicesHalfDuplex", 3): "SDI 7",
    ("DeckLink Quad 2", "TwoSubDevicesHalfDuplex", 4): "SDI 2",
    ("DeckLink Quad 2", "TwoSubDevicesHalfDuplex", 5): "SDI 4",
    ("DeckLink Quad 2", "TwoSubDevicesHalfDuplex", 6): "SDI 6",
    ("DeckLink Quad 2", "TwoSubDevicesHalfDuplex", 7): "SDI 8",
    # DeckLink Duo 2 — 2 sub-devices half-duplex (4 sub-devices visible)
    ("DeckLink Duo 2", "TwoSubDevicesHalfDuplex", 0): "SDI 1",
    ("DeckLink Duo 2", "TwoSubDevicesHalfDuplex", 1): "SDI 3",
    ("DeckLink Duo 2", "TwoSubDevicesHalfDuplex", 2): "SDI 2",
    ("DeckLink Duo 2", "TwoSubDevicesHalfDuplex", 3): "SDI 4",
}


def lookup(model_name: str, profile_name: str, sub_device_index: int) -> str | None:
    """Return the SDI port label for a (model, profile, sub_idx) tuple.

    Match is by model-name prefix so that minor SDK display-name
    variations (whitespace, suffixes) don't break the lookup.
    Returns ``None`` for any tuple not in the table.
    """
    for (prefix, prof, idx), label in _SDI_LABEL.items():
        if (
            model_name.startswith(prefix)
            and prof == profile_name
            and idx == sub_device_index
        ):
            return label
    return None


def connector_label(device: Device) -> str | None:
    """Return the SDI port label for ``device``, or ``None`` if unknown.

    Reads the device's model name, active profile, and sub-device
    index, then consults the static table. Returns ``None`` for any
    SDK error (device closed, attributes unavailable) or unmapped
    (model, profile, sub_device_index) tuple.
    """
    from pydecklink._bindings import AttributeID

    try:
        model = device.model_name
        profile_name = device.active_profile().name
        sub_idx = device.get_attribute_int(AttributeID.SubDeviceIndex)
    except (RuntimeError, AttributeError):
        return None
    return lookup(model, profile_name, sub_idx)
