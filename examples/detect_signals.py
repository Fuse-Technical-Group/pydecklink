#!/usr/bin/env python3
"""Walk all DeckLink inputs and report which ones have an active signal.

Includes physical SDI connector labels where known. The DeckLink SDK does
not expose a programmatic physical-port query — the mapping is derived from
the table on page 31 of the DeckLink SDK 15.3 manual and varies by card
model and active profile.
"""

from __future__ import annotations

import sys

import pydecklink

# Physical SDI connector labels by (model_prefix, profile, sub_device_index).
# Sourced from DeckLink SDK 15.3 manual, Section 2.4.11, page 31.
_SDI_LABEL: dict[tuple[str, str, int], str] = {
    # DeckLink 8K Pro — 4 sub-devices half-duplex
    ("DeckLink 8K Pro", "FourSubDevicesHalfDuplex", 0): "SDI 1",
    ("DeckLink 8K Pro", "FourSubDevicesHalfDuplex", 1): "SDI 3",
    ("DeckLink 8K Pro", "FourSubDevicesHalfDuplex", 2): "SDI 2",
    ("DeckLink 8K Pro", "FourSubDevicesHalfDuplex", 3): "SDI 4",
    # DeckLink 8K Pro — 2 sub-devices full-duplex
    ("DeckLink 8K Pro", "TwoSubDevicesFullDuplex", 0): "SDI 1+2",
    ("DeckLink 8K Pro", "TwoSubDevicesFullDuplex", 1): "SDI 3+4",
    # DeckLink Quad 2 — 2 sub-devices half-duplex (8 sub-devices visible)
    ("DeckLink Quad 2", "TwoSubDevicesHalfDuplex", 0): "SDI 1",
    ("DeckLink Quad 2", "TwoSubDevicesHalfDuplex", 1): "SDI 3",
    ("DeckLink Quad 2", "TwoSubDevicesHalfDuplex", 2): "SDI 5",
    ("DeckLink Quad 2", "TwoSubDevicesHalfDuplex", 3): "SDI 7",
    ("DeckLink Quad 2", "TwoSubDevicesHalfDuplex", 4): "SDI 2",
    ("DeckLink Quad 2", "TwoSubDevicesHalfDuplex", 5): "SDI 4",
    ("DeckLink Quad 2", "TwoSubDevicesHalfDuplex", 6): "SDI 6",
    ("DeckLink Quad 2", "TwoSubDevicesHalfDuplex", 7): "SDI 8",
    # DeckLink Duo 2 — 2 sub-devices half-duplex
    ("DeckLink Duo 2", "TwoSubDevicesHalfDuplex", 0): "SDI 1",
    ("DeckLink Duo 2", "TwoSubDevicesHalfDuplex", 1): "SDI 3",
    ("DeckLink Duo 2", "TwoSubDevicesHalfDuplex", 2): "SDI 2",
    ("DeckLink Duo 2", "TwoSubDevicesHalfDuplex", 3): "SDI 4",
}


def _physical_label(dev: pydecklink.Device) -> str:
    """Return the physical SDI connector label, or '?' if unknown."""
    model = dev.model_name
    try:
        profile = dev.active_profile().name
        sub_idx = dev.get_attribute_int(pydecklink.AttributeID.SubDeviceIndex)
    except RuntimeError:
        return "?"

    for prefix, prof, idx in _SDI_LABEL:
        if model.startswith(prefix) and prof == profile and idx == sub_idx:
            return _SDI_LABEL[(prefix, prof, idx)]
    return "?"


def _profile_info(dev: pydecklink.Device) -> str:
    """Return a human-readable profile + duplex summary, or 'n/a'."""
    try:
        profile = dev.active_profile().name
    except RuntimeError:
        return "n/a"

    try:
        duplex_val = dev.get_attribute_int(pydecklink.AttributeID.Duplex)
        duplex = pydecklink.DuplexMode(duplex_val).name
    except (RuntimeError, ValueError):
        duplex = "?"

    return f"{profile} (duplex={duplex})"


def _sdi_sort_key(label: str) -> tuple[int, int]:
    """Sort key for SDI labels: known ports first, ordered by lowest port number."""
    if label == "?":
        return (1, 0)
    digits = "".join(c if c.isdigit() else " " for c in label).split()
    return (0, int(digits[0]) if digits else 9999)


def probe_input(index: int, name: str) -> str:
    """Enable format detection on a device, capture one frame, return a status line."""
    dev = pydecklink.Device(index=index)
    label = _physical_label(dev)
    profile = _profile_info(dev)
    suffix = f"[decklink #{index}] {name}  profile={profile}"

    dev.enable_video_input(
        mode=pydecklink.DisplayMode.HD1080p25,
        pixel_format=pydecklink.PixelFormat.Format8BitYUV,
        flags=pydecklink.VideoInputFlag.EnableFormatDetection,
    )
    dev.start_streams()

    try:
        # Signal lock + format detection can take several seconds.
        frame = None
        fmt = None
        for _ in range(10):
            frame = dev.pop_capture_frame(timeout_ms=500)
            if frame is not None and frame.has_signal:
                fmt = dev.current_input_format
                if fmt is not None and fmt.mode != pydecklink.DisplayMode.Unknown:
                    break

        if frame is None or not frame.has_signal:
            body = "no signal"
        else:
            if fmt is not None and fmt.mode != pydecklink.DisplayMode.Unknown:
                mode_name = pydecklink.DisplayMode(fmt.mode).name
                pix_name = pydecklink.PixelFormat(fmt.pixel_format).name
            else:
                mode_name = "unknown"
                pix_name = "unknown"
            body = (
                f"{frame.width}x{frame.height}  mode={mode_name}  pixel_format={pix_name}"
            )
    finally:
        dev.stop_streams()
        dev.disable_video_input()

    return f"  {label:<8}  {body}  {suffix}"


def main() -> None:
    devices = pydecklink.list_devices()
    if not devices:
        print("No DeckLink devices found.")
        sys.exit(1)

    print(f"Found {len(devices)} DeckLink device(s):\n")

    rows: list[tuple[str, str]] = []
    for info in devices:
        dev = pydecklink.Device(index=info.index)
        label = _physical_label(dev)
        del dev
        try:
            line = probe_input(info.index, info.display_name)
        except RuntimeError as exc:
            line = f"  {label:<8}  skipped ({exc})  [decklink #{info.index}] {info.display_name}"
        rows.append((label, line))

    rows.sort(key=lambda r: _sdi_sort_key(r[0]))
    for _, line in rows:
        print(line)


if __name__ == "__main__":
    main()
