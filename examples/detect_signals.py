#!/usr/bin/env python3
"""Walk all DeckLink inputs and report which ones have an active signal.

Annotates each device with its physical SDI connector label via
``Device.connector_label`` — see ``pydecklink._connectors`` for the
underlying lookup table.
"""

from __future__ import annotations

import sys

import pydecklink


def _physical_label(dev: pydecklink.Device) -> str:
    """Return the physical SDI connector label, or '?' if unknown."""
    return pydecklink.connector_label(dev) or "?"


def _reference_info(dev: pydecklink.Device) -> str:
    """Return the reference (genlock) lock state for the ``ref=`` field.

    ``locked@<DisplayMode>`` when the device is locked to a resolvable
    reference mode, ``unlocked`` when a REF BNC exists but no reference
    is applied (or the mode is unknown), and ``n/a`` for devices without
    a REF BNC. SPEC §5.11.
    """
    if not dev.get_attribute_flag(pydecklink.AttributeID.HasReferenceInput):
        return "n/a"

    status = dev.reference_status
    if status.locked and status.mode is not None:
        return f"locked@{status.mode.name}"
    return "unlocked"


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
    ref = _reference_info(dev)
    suffix = f"[decklink #{index}] {name}  profile={profile}  ref={ref}"

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
                f"{frame.width}x{frame.height}  "
                f"mode={mode_name}  pixel_format={pix_name}"
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
        ref = _reference_info(dev)
        del dev
        try:
            line = probe_input(info.index, info.display_name)
        except RuntimeError as exc:
            line = (
                f"  {label:<8}  skipped ({exc})  "
                f"[decklink #{info.index}] {info.display_name}  ref={ref}"
            )
        rows.append((label, line))

    rows.sort(key=lambda r: _sdi_sort_key(r[0]))
    for _, line in rows:
        print(line)


if __name__ == "__main__":
    main()
