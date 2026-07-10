"""Configuration round-trip tests — require DeckLink hardware.

Regression coverage for the configuration interface lifetime. The
``Device`` config methods must share one held ``IDeckLinkConfiguration``:
DeckLink applies ``SetFlag`` / ``SetInt`` to the live session only while
that interface is retained. A transient per-call interface discards the
change the moment it is released, so ``set_config_flag`` silently had no
effect and ``get_config_flag`` always read back the unchanged value.

Run with: pytest -m hardware tests/test_config.py
"""

from __future__ import annotations

import pytest

import pydecklink

_HAS_SDK = getattr(pydecklink, "HAS_SDK", False)

pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers"),
]


@pytest.fixture()
def device():
    if pydecklink.device_count() == 0:
        pytest.skip("No DeckLink device present")
    return pydecklink.Device(index=0)


def test_set_config_flag_persists(device):
    """A set flag must be observable through a subsequent get.

    Before the held-interface fix this failed: each call acquired and
    released a fresh configuration interface, so the flag reverted before
    the next read. Toggles ``Config444SDIVideoOutput`` and restores it.
    """
    flag = pydecklink.ConfigurationID.Config444SDIVideoOutput
    try:
        original = device.get_config_flag(flag)
    except RuntimeError:
        pytest.skip("Config444SDIVideoOutput not supported on this device")

    try:
        device.set_config_flag(flag, not original)
        assert device.get_config_flag(flag) == (not original), (
            "set_config_flag did not persist — configuration interface not held"
        )
        device.set_config_flag(flag, original)
        assert device.get_config_flag(flag) == original
    finally:
        device.set_config_flag(flag, original)
