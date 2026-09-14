"""The Ethernet surface of a DeckLink IP (§spec:ethernet).

Two halves. The enum membership is device-free: an ID that is not bound
cannot be reached at all, because nanobind refuses a raw value that names
no member — which is what made the Ethernet settings unreachable before
they were bound. The rest needs the card.

Run the second half with: pytest -m hardware tests/test_ethernet.py
"""

from __future__ import annotations

import json
import time

import pytest

import pydecklink

_HAS_SDK = getattr(pydecklink, "HAS_SDK", False)

#: `bmdEthernetLinkState*`, the values `StatusID.ParamEthernetLink` reports.
LINK_STATES = {
    0x656C6473: "disconnected",
    0x656C6375: "connected-unbound",
    0x656C6362: "connected-bound",
}
LINK_DISCONNECTED = 0x656C6473

#: A DeckLink IP 100G carries two QSFP28 connectors (ST 2022-7 red and blue).
IP_100G_CONNECTORS = 2

#: An address write unbinds the connector within ~50 ms and rebinds it about
#: a second later, so a link state counts as settled only once it has held
#: for longer than that drop.
REBIND_SETTLE_S = 3.0
REBIND_TIMEOUT_S = 30.0
REBIND_POLL_S = 0.05


# --- device-free -------------------------------------------------------------


@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_the_address_settings_are_per_connector() -> None:
    """SDK 16 moved every address onto a connector index: the four-char codes
    are the ones 15.3 used unparameterised, under a `Param` name."""
    config = pydecklink.ConfigurationID
    expected = {
        "ConfigParamEthernetUseDHCP": 0x44484350,  # 'DHCP'
        "ConfigParamEthernetStaticLocalIPAddress": 0x6E736970,  # 'nsip'
        "ConfigParamEthernetStaticSubnetMask": 0x6E73736D,  # 'nssm'
        "ConfigParamEthernetStaticGatewayIPAddress": 0x6E736777,  # 'nsgw'
        "ConfigParamEthernetStaticPrimaryDNS": 0x6E737064,  # 'nspd'
        "ConfigParamEthernetStaticSecondaryDNS": 0x6E737364,  # 'nssd'
        "ConfigParamEthernetVideoOutputAddress": 0x6E6F6176,  # 'noav'
        "ConfigParamEthernetAudioOutputAddress": 0x6E6F6161,  # 'noaa'
        "ConfigParamEthernetAncillaryOutputAddress": 0x6E6F6141,  # 'noaA'
    }
    for name, value in expected.items():
        assert getattr(config, name).value == value, name


@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_the_unparameterised_address_names_are_gone() -> None:
    """SDK 16 removed them; binding both would offer an ID the unparameterised
    accessors no longer serve."""
    for name in (
        "ConfigEthernetUseDHCP",
        "ConfigEthernetStaticLocalIPAddress",
        "ConfigEthernetVideoOutputAddress",
    ):
        assert not hasattr(pydecklink.ConfigurationID, name), name
    for name in (
        "EthernetLink",
        "EthernetLocalIPAddress",
        "EthernetVideoOutputAddress",
    ):
        assert not hasattr(pydecklink.StatusID, name), name


@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_the_device_wide_ethernet_settings_are_bound() -> None:
    """PTP and the NMOS registry belong to the card, not to one connector."""
    config = pydecklink.ConfigurationID
    for name in (
        "ConfigEthernetPTPFollowerOnly",
        "ConfigEthernetPTPDomain",
        "ConfigEthernetPTPPriority1",
        "ConfigEthernetPTPPriority2",
        "ConfigEthernetPTPUseUDPEncapsulation",
        "ConfigEthernetAudioOutputChannelOrder",
    ):
        assert hasattr(config, name), name
    assert config.ConfigEthernetUseManualNMOSRegistry.value == 0x6E6D7270  # 'nmrp'
    assert config.ConfigEthernetNMOSRegistryAddress.value == 0x6E6D7265  # 'nmre'
    assert config.ConfigEthernetVideoOutputIP10.value == 0x49503130  # 'IP10'


@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_the_ethernet_status_is_per_connector() -> None:
    status = pydecklink.StatusID
    expected = {
        "ParamEthernetLink": 0x73656C73,  # 'sels'
        "ParamEthernetLinkMbps": 0x73657370,  # 'sesp'
        "ParamEthernetLocalIPAddress": 0x73656970,  # 'seip'
        "ParamEthernetSubnetMask": 0x7365736D,  # 'sesm'
        "ParamEthernetGatewayIPAddress": 0x73656777,  # 'segw'
        "ParamEthernetPrimaryDNS": 0x73657064,  # 'sepd'
        "ParamEthernetSecondaryDNS": 0x73657364,  # 'sesd'
        "ParamEthernetSFPStaticInfo": 0x73667069,  # 'sfpi'
        "ParamEthernetVideoOutputAddress": 0x736F6176,  # 'soav'
        "ParamEthernetAudioOutputAddress": 0x736F6161,  # 'soaa'
        "ParamEthernetAncillaryOutputAddress": 0x736F6141,  # 'soaA'
    }
    for name, value in expected.items():
        assert getattr(status, name).value == value, name


@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_the_device_wide_ethernet_status_is_bound() -> None:
    status = pydecklink.StatusID
    assert hasattr(status, "EthernetPTPGrandmasterIdentity")
    assert hasattr(status, "EthernetAudioInputChannelOrder")
    assert status.EthernetManualNMOSRegistry.value == 0x6E6D6D65  # 'nmme'
    assert status.EthernetCurrentNMOSRegistry.value == 0x6E6D7265  # 'nmre'


@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_the_connector_attributes_are_bound() -> None:
    attribute = pydecklink.AttributeID
    assert attribute.NumberOfEthernetConnectors.value == 0x6E657468  # 'neth'
    assert attribute.ParamEthernetMACAddress.value == 0x704D4143  # 'pMAC'


@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_a_device_carries_per_connector_accessors() -> None:
    """The addresses are strings in dotted-quad form, not packed integers,
    and each one belongs to a connector named by a zero-based index."""
    for name in (
        "set_config_flag_with_param",
        "get_config_flag_with_param",
        "set_config_int_with_param",
        "get_config_int_with_param",
        "set_config_string_with_param",
        "get_config_string_with_param",
        "get_status_flag_with_param",
        "get_status_int_with_param",
        "get_status_string_with_param",
        "get_attribute_string_with_param",
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


def _connectors(device: pydecklink.Device) -> range:
    return range(
        device.get_attribute_int(pydecklink.AttributeID.NumberOfEthernetConnectors)
    )


def _await_settled(device: pydecklink.Device, connector: int, state: int) -> None:
    """Wait until `connector` has held link `state` for REBIND_SETTLE_S."""
    link = pydecklink.StatusID.ParamEthernetLink
    deadline = time.monotonic() + REBIND_TIMEOUT_S
    held_since = time.monotonic()
    while time.monotonic() - held_since < REBIND_SETTLE_S:
        assert time.monotonic() < deadline, f"connector {connector} did not settle"
        if device.get_status_int_with_param(link, connector) != state:
            held_since = time.monotonic()
        time.sleep(REBIND_POLL_S)


def _linked(device: pydecklink.Device) -> list[int]:
    status = pydecklink.StatusID.ParamEthernetLink
    return [
        c
        for c in _connectors(device)
        if device.get_status_int_with_param(status, c) != LINK_DISCONNECTED
    ]


@pytest.mark.hardware
@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_an_ip_100g_names_both_connectors(ip_device: pydecklink.Device) -> None:
    if ip_device.model_name != "DeckLink IP 100G":
        pytest.skip(f"not an IP 100G: {ip_device.model_name}")
    assert len(_connectors(ip_device)) == IP_100G_CONNECTORS


@pytest.mark.hardware
@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_each_connector_reports_a_link_state_the_sdk_names(
    ip_device: pydecklink.Device,
) -> None:
    for connector in _connectors(ip_device):
        state = ip_device.get_status_int_with_param(
            pydecklink.StatusID.ParamEthernetLink, connector
        )
        assert state in LINK_STATES, (connector, hex(state))


@pytest.mark.hardware
@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_each_connector_has_its_own_mac(ip_device: pydecklink.Device) -> None:
    macs = [
        ip_device.get_attribute_string_with_param(
            pydecklink.AttributeID.ParamEthernetMACAddress, connector
        )
        for connector in _connectors(ip_device)
    ]
    assert all(macs), macs
    assert len(set(macs)) == len(macs), macs


@pytest.mark.hardware
@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_a_static_address_round_trips_on_every_connector(
    ip_device: pydecklink.Device,
) -> None:
    """Set and read back, restoring what the card held.

    The value is the configuration's, not the resolved one: the status
    address stays unavailable while the link is down (§spec:ethernet).
    The write applies live — the connector drops to `ConnectedUnbound`
    and rebinds — so the test waits for the link state it found.
    """
    setting = pydecklink.ConfigurationID.ConfigParamEthernetStaticLocalIPAddress
    link = pydecklink.StatusID.ParamEthernetLink
    for connector in _connectors(ip_device):
        held = ip_device.get_config_string_with_param(setting, connector)
        state = ip_device.get_status_int_with_param(link, connector)
        probe = f"192.0.2.{40 + connector}"  # RFC 5737 documentation range
        try:
            ip_device.set_config_string_with_param(setting, connector, probe)
            assert ip_device.get_config_string_with_param(setting, connector) == probe
        finally:
            ip_device.set_config_string_with_param(setting, connector, held)
            _await_settled(ip_device, connector, state)


@pytest.mark.hardware
@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_a_linked_optical_connector_describes_its_module(
    ip_device: pydecklink.Device,
) -> None:
    """SFF-8636 static fields, as JSON — the module's identity without root."""
    linked = _linked(ip_device)
    if not linked:
        pytest.skip("no connector has link")
    info = ip_device.get_status_string_with_param(
        pydecklink.StatusID.ParamEthernetSFPStaticInfo, linked[0]
    )
    assert isinstance(json.loads(info), dict)
