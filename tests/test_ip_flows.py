"""The IP flows of a DeckLink IP (§spec:ip-flows).

Two halves, as in `test_ethernet.py`. The enum membership and the surface
are device-free. The rest needs the card: each sub-device's flows, the SDP
an output flow sends, and the peer SDP an input flow receives.

Run the second half with: pytest -m hardware tests/test_ip_flows.py
"""

from __future__ import annotations

import pytest

import pydecklink
from test_ethernet import LINK_DISCONNECTED

_HAS_SDK = getattr(pydecklink, "HAS_SDK", False)

#: MCAST-TEST-NET groups (RFC 5771) for the probe offers. Two, so a write
#: is told apart from what the card already held.
PROBE_GROUPS = ("233.252.0.1", "233.252.0.2")


def _probe_sdp(group: str) -> str:
    """A 1080p59.94 ST 2110-20 offer from a documentation-range sender
    (RFC 5737) to `group`: nothing on a real fabric sends it, so an input
    flow pointed at it receives nothing."""
    return (
        "v=0\r\n"
        "o=- 1 1 IN IP4 192.0.2.10\r\n"
        "s=pydecklink probe\r\n"
        "t=0 0\r\n"
        "m=video 5004 RTP/AVP 96\r\n"
        f"c=IN IP4 {group}/64\r\n"
        f"a=source-filter: incl IN IP4 {group} 192.0.2.10\r\n"
        "a=rtpmap:96 raw/90000\r\n"
        "a=fmtp:96 sampling=YCbCr-4:2:2; width=1920; height=1080; "
        "exactframerate=60000/1001; depth=10; TCS=SDR; colorimetry=BT709; "
        "PM=2110GPM; SSN=ST2110-20:2017; TP=2110TPN\r\n"
        "a=ts-refclk:localmac=00-00-5e-00-53-01\r\n"
        "a=mediaclk:direct=0\r\n"
    )


# --- device-free -------------------------------------------------------------


@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_the_flow_identifiers_are_bound() -> None:
    """An unbound ID is unreachable: nanobind refuses a raw value naming no
    member (§spec:enums)."""
    assert pydecklink.IPFlowAttributeID.ID.value == 0x32666169  # '2fai'
    assert pydecklink.IPFlowAttributeID.Direction.value == 0x32666164  # '2fad'
    assert pydecklink.IPFlowAttributeID.Type.value == 0x32666174  # '2fat'
    assert pydecklink.IPFlowStatusID.SDP.value == 0x32666173  # '2fas'
    assert pydecklink.IPFlowSettingID.PeerSDP.value == 0x32667073  # '2fps'


@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_a_flow_names_its_direction_and_type() -> None:
    assert pydecklink.IPFlowDirection.Output.value == 0
    assert pydecklink.IPFlowDirection.Input.value == 1
    assert pydecklink.IPFlowType.Video.value == 0
    assert pydecklink.IPFlowType.Audio.value == 1
    assert pydecklink.IPFlowType.Ancillary.value == 2


@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_the_flow_interfaces_are_bound() -> None:
    assert hasattr(pydecklink.Device, "ip_extensions")
    for name in ("get_ip_flows", "get_ip_flow_by_id"):
        assert hasattr(pydecklink.IPExtensions, name), name
    for name in (
        "enable",
        "disable",
        "get_attribute_int",
        "get_status_string",
        "get_setting_string",
        "set_setting_string",
        "id",
        "direction",
        "type",
    ):
        assert hasattr(pydecklink.IPFlow, name), name


# --- on the card -------------------------------------------------------------


def _ip_devices() -> list[pydecklink.Device]:
    devices = [pydecklink.Device(i) for i in range(pydecklink.device_count())]
    return [d for d in devices if d.ip_extensions is not None]


@pytest.fixture
def ip_devices() -> list[pydecklink.Device]:
    if pydecklink.device_count() == 0:
        pytest.skip("no DeckLink device")
    devices = _ip_devices()
    if not devices:
        pytest.skip("no device exposes IP flows — not a DeckLink IP")
    return devices


def _extensions(device: pydecklink.Device) -> pydecklink.IPExtensions:
    extensions = device.ip_extensions
    assert extensions is not None
    return extensions


def _flow(
    device: pydecklink.Device,
    direction: pydecklink.IPFlowDirection,
    kind: pydecklink.IPFlowType,
) -> pydecklink.IPFlow:
    matches = [
        f
        for f in _extensions(device).get_ip_flows()
        if f.direction == direction and f.type == kind
    ]
    assert len(matches) == 1, (direction, kind, len(matches))
    return matches[0]


def _groups(sdp: str) -> list[str]:
    """The destination of each `c=` line, without its TTL."""
    return [
        line.split()[2].split("/")[0]
        for line in sdp.splitlines()
        if line.startswith("c=")
    ]


@pytest.mark.hardware
@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_a_sub_device_sends_and_receives_each_essence(
    ip_devices: list[pydecklink.Device],
) -> None:
    """One flow per direction and essence: video, audio and ancillary, out
    and in — the senders and receivers the card's NMOS node advertises."""
    every = {
        (direction, kind)
        for direction in pydecklink.IPFlowDirection
        for kind in pydecklink.IPFlowType
    }
    for device in ip_devices:
        flows = _extensions(device).get_ip_flows()
        assert len(flows) == len(every)
        assert {(f.direction, f.type) for f in flows} == every


@pytest.mark.hardware
@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_a_flow_is_found_again_by_its_id(
    ip_devices: list[pydecklink.Device],
) -> None:
    for device in ip_devices:
        extensions = _extensions(device)
        for flow in extensions.get_ip_flows():
            again = extensions.get_ip_flow_by_id(flow.id)
            assert (again.id, again.direction, again.type) == (
                flow.id,
                flow.direction,
                flow.type,
            )


@pytest.mark.hardware
@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_a_flow_id_names_a_flow_within_its_sub_device_only(
    ip_devices: list[pydecklink.Device],
) -> None:
    """Unique within a sub-device, and repeated across them: every sub-device
    numbers its flows from zero, so an ID alone does not name one on the card
    (§spec:ip-flows)."""
    listings = [
        [flow.id for flow in _extensions(device).get_ip_flows()]
        for device in ip_devices
    ]
    for ids in listings:
        assert len(set(ids)) == len(ids)
    if len(listings) > 1:
        assert set(listings[0]) & set(listings[1])


@pytest.mark.hardware
@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_an_output_flow_offers_the_groups_its_connectors_report(
    ip_devices: list[pydecklink.Device],
) -> None:
    """The SDP the card sends names, leg by leg, the video group each
    connector reports it sends to (§spec:ethernet).

    Every connector needs link: an unlinked card offers an empty SDP, and a
    connector without link has no resolved group to compare against."""
    device = ip_devices[0]
    connectors = device.get_attribute_int(
        pydecklink.AttributeID.NumberOfEthernetConnectors
    )
    link = pydecklink.StatusID.ParamEthernetLink
    if any(
        device.get_status_int_with_param(link, connector) == LINK_DISCONNECTED
        for connector in range(connectors)
    ):
        pytest.skip("a connector has no link")
    flow = _flow(device, pydecklink.IPFlowDirection.Output, pydecklink.IPFlowType.Video)
    sdp = flow.get_status_string(pydecklink.IPFlowStatusID.SDP)
    assert sdp.startswith("v=0")
    reported = [
        device.get_status_string_with_param(
            pydecklink.StatusID.ParamEthernetVideoOutputAddress, connector
        )
        for connector in range(connectors)
    ]
    assert _groups(sdp) == reported


@pytest.mark.hardware
@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_a_peer_sdp_round_trips_on_an_input_flow(
    ip_devices: list[pydecklink.Device],
) -> None:
    """Set, read back through a fresh handle, and restore what the card held.

    The fresh handle is the point: a setting that lived only as long as the
    interface that wrote it would read back through the same one and be gone
    for any other caller (§spec:configuration). A card holding no peer SDP is
    left alone, because no write returns it to none (§spec:ip-flows)."""
    device = ip_devices[0]
    setting = pydecklink.IPFlowSettingID.PeerSDP
    flow = _flow(device, pydecklink.IPFlowDirection.Input, pydecklink.IPFlowType.Video)
    held = flow.get_setting_string(setting)
    if not held:
        pytest.skip("the flow holds no peer SDP, and none can be restored")
    probe = next(_probe_sdp(g) for g in PROBE_GROUPS if _groups(held) != [g])
    try:
        flow.set_setting_string(setting, probe)
        del flow
        again = _flow(
            device, pydecklink.IPFlowDirection.Input, pydecklink.IPFlowType.Video
        )
        assert _groups(again.get_setting_string(setting)) == _groups(probe)
    finally:
        _flow(
            device, pydecklink.IPFlowDirection.Input, pydecklink.IPFlowType.Video
        ).set_setting_string(setting, held)


@pytest.mark.hardware
@pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers")
def test_a_peer_sdp_the_card_rejects_changes_nothing(
    ip_devices: list[pydecklink.Device],
) -> None:
    """The write answers `S_OK` and the setting keeps what it held: an empty
    string is not a way to clear one (§spec:ip-flows)."""
    device = ip_devices[0]
    setting = pydecklink.IPFlowSettingID.PeerSDP
    flow = _flow(device, pydecklink.IPFlowDirection.Input, pydecklink.IPFlowType.Video)
    held = flow.get_setting_string(setting)
    for rejected in ("", "not an sdp", "v=0\r\n"):
        flow.set_setting_string(setting, rejected)
        assert flow.get_setting_string(setting) == held, repr(rejected)
