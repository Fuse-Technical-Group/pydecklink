#!/usr/bin/env python3
"""Sweep a card's profiles and report which of them key.

Keying is a property of a profile, not a card: the SDK manual (section
2.4.11) moves ``SupportsExternalKeying`` / ``SupportsInternalKeying`` with
the profile, and its 8K Pro table labels key and fill in
``TwoSubDevicesFullDuplex`` and both one-sub-device profiles. This script
activates each profile the card offers in turn and, for every sub-device
it exposes there, prints the duplex mode, the connector label, the two
keying flags, and whether the output keys ``--mode`` in 10-bit YUVA. The
card is returned to the profile it started in.

A profile change is card-wide and stops any open stream, so run this on a
bench with nothing else holding the card.

Run:
    python examples/keying_sweep.py [--device 0] [--mode HD1080p5994]
"""

from __future__ import annotations

import argparse
import sys
import threading

import pydecklink
from pydecklink._connectors import lookup

ACTIVATION_TIMEOUT_S = 10.0


class _Settled(pydecklink.ProfileCallback):
    def __init__(self) -> None:
        super().__init__()
        self.event = threading.Event()

    def profile_changing(self, profile, streams_will_be_forced_to_stop) -> None:
        pass

    def profile_activated(self, profile) -> None:
        self.event.set()


def _activate(dev: pydecklink.Device, manager, wanted: pydecklink.ProfileID) -> None:
    """Activate ``wanted`` and block until the card reports it."""
    if dev.active_profile() == wanted:
        return
    settled = _Settled()
    manager.set_callback(settled)
    try:
        manager.get_profile(wanted).set_active()
        settled.event.wait(ACTIVATION_TIMEOUT_S)
        actual = dev.active_profile()
        if actual != wanted:
            raise RuntimeError(f"card is in {actual.name}, not {wanted.name}")
    finally:
        manager.set_callback(None)


def _flag(dev: pydecklink.Device, attr: pydecklink.AttributeID) -> str:
    try:
        return "yes" if dev.get_attribute_flag(attr) else "no"
    except RuntimeError:
        return "n/a"


def _duplex(dev: pydecklink.Device) -> str:
    try:
        return pydecklink.DuplexMode(
            dev.get_attribute_int(pydecklink.AttributeID.Duplex)
        ).name
    except (RuntimeError, ValueError):
        return "n/a"


def _keys_mode(dev: pydecklink.Device, mode: pydecklink.DisplayMode) -> str:
    try:
        ok = dev.does_support_video_mode(
            pydecklink.VideoConnection.Unspecified,
            mode,
            pydecklink.PixelFormat.Format10BitYUVA,
            flags=pydecklink.SupportedVideoModeFlag.Keying,
        )
    except RuntimeError:
        return "n/a"
    return "yes" if ok else "no"


def _sub_devices(model: str) -> list[pydecklink.DeviceInfo]:
    """Every enumerated sub-device of ``model``, fresh after a profile change."""
    return [info for info in pydecklink.list_devices() if info.model_name == model]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--device", type=int, default=0, help="index of any sub-device of the card"
    )
    parser.add_argument(
        "--mode", default="HD1080p5994", help="DisplayMode name to test for keying"
    )
    args = parser.parse_args()
    mode = pydecklink.DisplayMode[args.mode]

    head = pydecklink.Device(index=args.device)
    model = head.model_name
    manager = head.profile_manager
    if manager is None:
        print(f"{model}: single-profile card, nothing to sweep")
        sys.exit(0)
    original = head.active_profile()
    profiles = [p.id for p in manager.get_profiles()]
    print(f"{model}: profiles {[p.name for p in profiles]}, active {original.name}")
    print(f"keying test mode: {mode.name} in Format10BitYUVA\n")

    columns = (
        "profile",
        "sub",
        "label",
        "duplex",
        "external",
        "internal",
        f"keys {mode.name}",
    )
    print("\t".join(columns))
    try:
        for profile in profiles:
            _activate(head, manager, profile)
            for info in _sub_devices(model):
                dev = pydecklink.Device(index=info.index)
                sub = dev.get_attribute_int(pydecklink.AttributeID.SubDeviceIndex)
                row = (
                    profile.name,
                    str(sub),
                    lookup(model, profile.name, sub) or "-",
                    _duplex(dev),
                    _flag(dev, pydecklink.AttributeID.SupportsExternalKeying),
                    _flag(dev, pydecklink.AttributeID.SupportsInternalKeying),
                    _keys_mode(dev, mode),
                )
                print("\t".join(row))
    finally:
        _activate(head, manager, original)
        print(f"\nrestored {original.name}")


if __name__ == "__main__":
    main()
