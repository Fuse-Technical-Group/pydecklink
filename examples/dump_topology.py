#!/usr/bin/env python3
"""Dump the topology of every DeckLink device the SDK reports.

Diagnostic script — opens each device, prints its identity and
profile attributes, no streaming. Useful when sanity-checking the
sub_device_index → physical SDI port mapping table against actual
hardware (see ``examples/detect_signals.py`` for the table).

Run:
    python examples/dump_topology.py
"""

from __future__ import annotations

import sys

import pydecklink


def _attr_int(dev: pydecklink.Device, attr: pydecklink.AttributeID) -> int | None:
    try:
        return dev.get_attribute_int(attr)
    except RuntimeError:
        return None


def _io_support(dev: pydecklink.Device) -> str:
    bits = _attr_int(dev, pydecklink.AttributeID.VideoIOSupport) or 0
    parts = []
    if bits & pydecklink.VideoIOSupport.Capture.value:
        parts.append("in")
    if bits & pydecklink.VideoIOSupport.Playback.value:
        parts.append("out")
    return ",".join(parts) or "-"


def _profile(dev: pydecklink.Device) -> str:
    try:
        return dev.active_profile().name
    except RuntimeError:
        return "n/a"


def _duplex(dev: pydecklink.Device) -> str:
    val = _attr_int(dev, pydecklink.AttributeID.Duplex)
    if val is None:
        return "n/a"
    try:
        return pydecklink.DuplexMode(val).name
    except ValueError:
        return f"raw({val})"


def main() -> None:
    devices = pydecklink.list_devices()
    if not devices:
        print("No DeckLink devices found.")
        sys.exit(1)

    rows = []
    for info in devices:
        dev = pydecklink.Device(index=info.index)
        sub = _attr_int(dev, pydecklink.AttributeID.SubDeviceIndex)
        nsub = _attr_int(dev, pydecklink.AttributeID.NumberOfSubDevices)
        pid = _attr_int(dev, pydecklink.AttributeID.PersistentID)
        rows.append(
            {
                "idx": info.index,
                "display_name": info.display_name,
                "model": info.model_name,
                "sub": sub if sub is not None else "?",
                "n_sub": nsub if nsub is not None else "?",
                "profile": _profile(dev),
                "duplex": _duplex(dev),
                "io": _io_support(dev),
                "persistent_id": f"0x{pid:08x}" if pid is not None else "?",
            }
        )

    headers = [
        "idx",
        "display_name",
        "model",
        "sub",
        "n_sub",
        "profile",
        "duplex",
        "io",
        "persistent_id",
    ]
    widths = {h: max(len(h), max(len(str(r[h])) for r in rows)) for h in headers}

    print("  ".join(h.ljust(widths[h]) for h in headers))
    print("  ".join("-" * widths[h] for h in headers))
    for r in rows:
        print("  ".join(str(r[h]).ljust(widths[h]) for h in headers))


if __name__ == "__main__":
    main()
