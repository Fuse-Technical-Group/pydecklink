"""Device statistics via IDeckLinkStatistics (§spec:statistics).

The enum and the accessors are device-free; the readings need the card.

Run the second half with: pytest -m hardware tests/test_statistics.py
"""

from __future__ import annotations

import json

import pytest

import pydecklink

_HAS_SDK = getattr(pydecklink, "HAS_SDK", False)

#: Bounds a working card's on-board temperature falls inside, in °C.
PLAUSIBLE_TEMPERATURE_C = range(0, 120)


# --- device-free -------------------------------------------------------------


@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_the_statistic_ids_are_bound() -> None:
    statistic = pydecklink.StatisticID
    expected = {
        "PTPLossOfLock": 0x6E6C6F6C,  # 'nlol'
        "PTPDPLLMarginOfError": 0x70747065,  # 'ptpe'
        "DeviceTemperature": 0x53746D70,  # 'Stmp'
        "ParamEthernetRxPackets": 0x6E747278,  # 'ntrx'
        "ParamEthernetRxDroppedPackets": 0x6E647278,  # 'ndrx'
        "ParamEthernetSFPDynamicInfo": 0x73667073,  # 'sfps'
    }
    for name, value in expected.items():
        assert getattr(statistic, name).value == value, name


@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_a_device_carries_statistic_accessors() -> None:
    for name in (
        "get_statistic_int",
        "get_statistic_int_with_param",
        "get_statistic_string_with_param",
    ):
        assert hasattr(pydecklink.Device, name), name


# --- on the card -------------------------------------------------------------


@pytest.fixture
def ip_device() -> pydecklink.Device:
    if pydecklink.device_count() == 0:
        pytest.skip("no DeckLink device")
    device = pydecklink.Device(0)
    try:
        count = device.get_attribute_int(
            pydecklink.AttributeID.NumberOfEthernetConnectors
        )
    except RuntimeError:
        pytest.skip("device has no Ethernet — not a DeckLink IP")
    if count == 0:
        pytest.skip("device has no Ethernet — not a DeckLink IP")
    return device


@pytest.mark.hardware
@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_the_temperature_is_plausible(ip_device: pydecklink.Device) -> None:
    celsius = ip_device.get_statistic_int(pydecklink.StatisticID.DeviceTemperature)
    assert celsius in PLAUSIBLE_TEMPERATURE_C, celsius


@pytest.mark.hardware
@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_the_receive_counters_never_run_backwards(ip_device: pydecklink.Device) -> None:
    statistic = pydecklink.StatisticID
    connectors = ip_device.get_attribute_int(
        pydecklink.AttributeID.NumberOfEthernetConnectors
    )
    for connector in range(connectors):
        first = ip_device.get_statistic_int_with_param(
            statistic.ParamEthernetRxPackets, connector
        )
        second = ip_device.get_statistic_int_with_param(
            statistic.ParamEthernetRxPackets, connector
        )
        assert 0 <= first <= second, (connector, first, second)
        dropped = ip_device.get_statistic_int_with_param(
            statistic.ParamEthernetRxDroppedPackets, connector
        )
        assert dropped >= 0, (connector, dropped)


@pytest.mark.hardware
@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_a_linked_optical_connector_reports_module_readings(
    ip_device: pydecklink.Device,
) -> None:
    """SFF-8636 dynamic fields — temperature, supply, per-lane power — as JSON."""
    linked = [
        c
        for c in range(
            ip_device.get_attribute_int(
                pydecklink.AttributeID.NumberOfEthernetConnectors
            )
        )
        if ip_device.get_status_int_with_param(pydecklink.StatusID.ParamEthernetLink, c)
        != 0x656C6473
    ]
    if not linked:
        pytest.skip("no connector has link")
    info = ip_device.get_statistic_string_with_param(
        pydecklink.StatisticID.ParamEthernetSFPDynamicInfo, linked[0]
    )
    assert isinstance(json.loads(info), dict)
