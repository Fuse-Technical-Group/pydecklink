"""The Ethernet surface of a DeckLink IP (§spec:ethernet).

Two halves. The enum membership is device-free: an ID that is not bound
cannot be reached at all, because nanobind refuses a raw value that names
no member — which is what made the Ethernet settings unreachable before
they were bound. The rest needs the card.

Run the second half with: pytest -m hardware tests/test_ethernet.py
"""

from __future__ import annotations

import pytest

import pydecklink

_HAS_SDK = getattr(pydecklink, "HAS_SDK", False)

#: `bmdEthernetLinkState*`, the values `StatusID.EthernetLink` reports.
LINK_STATES = {
    0x656C6473: "disconnected",
    0x656C6375: "connected-unbound",
    0x656C6362: "connected-bound",
}


# --- device-free -------------------------------------------------------------


@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_the_address_settings_are_bound() -> None:
    """A DeckLink IP has no network device on the host, so an address is set
    through these or not at all."""
    config = pydecklink.ConfigurationID
    for name in (
        "ConfigEthernetUseDHCP",
        "ConfigEthernetStaticLocalIPAddress",
        "ConfigEthernetStaticSubnetMask",
        "ConfigEthernetStaticGatewayIPAddress",
        "ConfigEthernetVideoOutputAddress",
    ):
        assert hasattr(config, name), name


@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_the_ptp_settings_are_bound() -> None:
    """`FollowerOnly` is what keeps the card out of the grandmaster election
    when something else on the fabric is the reference."""
    config = pydecklink.ConfigurationID
    for name in (
        "ConfigEthernetPTPFollowerOnly",
        "ConfigEthernetPTPDomain",
        "ConfigEthernetPTPPriority1",
        "ConfigEthernetPTPPriority2",
        "ConfigEthernetPTPUseUDPEncapsulation",
    ):
        assert hasattr(config, name), name


@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_the_ethernet_status_is_bound() -> None:
    status = pydecklink.StatusID
    for name in (
        "EthernetLink",
        "EthernetLinkMbps",
        "EthernetLocalIPAddress",
        "EthernetSubnetMask",
        "EthernetPTPGrandmasterIdentity",
    ):
        assert hasattr(status, name), name


@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_a_device_carries_string_accessors() -> None:
    """The addresses are strings in dotted-quad form, not packed integers:
    `SetInt` on one answers E_INVALIDARG, which is why these exist."""
    for name in ("set_config_string", "get_config_string", "get_status_string"):
        assert hasattr(pydecklink.Device, name), name


# --- on the card -------------------------------------------------------------


@pytest.fixture
def ip_device() -> pydecklink.Device:
    if pydecklink.device_count() == 0:
        pytest.skip("no DeckLink device")
    device = pydecklink.Device(0)
    try:
        device.get_status_int(pydecklink.StatusID.EthernetLink)
    except RuntimeError:
        pytest.skip("device has no Ethernet — not a DeckLink IP")
    return device


@pytest.mark.hardware
@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_the_link_state_is_one_the_sdk_names(ip_device: pydecklink.Device) -> None:
    state = ip_device.get_status_int(pydecklink.StatusID.EthernetLink)
    assert state in LINK_STATES, hex(state)


@pytest.mark.hardware
@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_a_static_address_round_trips(ip_device: pydecklink.Device) -> None:
    """Set and read back, restoring what the card held.

    The value is the configuration's, not the resolved one: the status
    address stays unavailable while the link is down (§spec:ethernet).
    """
    setting = pydecklink.ConfigurationID.ConfigEthernetStaticLocalIPAddress
    held = ip_device.get_config_string(setting)
    try:
        ip_device.set_config_string(setting, "10.10.100.40")
        assert ip_device.get_config_string(setting) == "10.10.100.40"
    finally:
        ip_device.set_config_string(setting, held)
