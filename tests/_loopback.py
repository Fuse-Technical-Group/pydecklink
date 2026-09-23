"""Loopback topology shared by the over-the-wire hardware tests."""

from __future__ import annotations

import pytest

import pydecklink


def skip_if_half_duplex_self_loopback(
    device: pydecklink.Device, output_index: int, input_index: int
) -> None:
    """Skip when output and input share a sub-device that cannot carry both.

    A half-duplex sub-device (an 8K Pro in FourSubDevicesHalfDuplex, say) is
    an input or an output, never both, so self-loopback fails at
    ``EnableVideoInput``. Loop it through two sub-devices instead.
    """
    if input_index != output_index:
        return
    try:
        duplex = device.get_attribute_int(pydecklink.AttributeID.Duplex)
    except RuntimeError:
        return  # No duplex attribute: nothing says self-loopback cannot work.
    if duplex == pydecklink.DuplexMode.Half.value:
        pytest.skip(
            f"Sub-device {output_index} is half duplex, so it cannot play out "
            "and capture at once. Cable one sub-device's SDI to another's and "
            "set PYDECKLINK_LOOPBACK_OUTPUT / PYDECKLINK_LOOPBACK_INPUT."
        )
