"""SDI passthrough via DeckLink: capture on device 0, playout on device 1.

Auto-detects the input signal format, configures output to match,
and loops captured frames through scheduled playback. Ctrl-C to stop.

Requires two DeckLink sub-devices (or two cards) connected via SDI.
Device 0 captures; device 1 plays out.

Usage:
    python examples/passthrough_decklink.py
"""

from __future__ import annotations

import signal
import sys

import numpy as np

import pydecklink


def wait_for_signal(
    dev: pydecklink.Device,
    pixel_format: pydecklink.PixelFormat = pydecklink.PixelFormat.Format8BitYUV,
) -> pydecklink.DisplayMode:
    """Enable input with format detection and wait for a valid signal.

    Returns the detected display mode. Leaves input enabled and streams
    running on return.
    """
    dev.enable_video_input(
        pydecklink.DisplayMode.HD1080p25,
        pixel_format,
        pydecklink.VideoInputFlag.EnableFormatDetection,
    )
    dev.start_streams()

    print("Waiting for signal...", end="", flush=True)
    while True:
        frame = dev.pop_capture_frame(timeout_ms=500)
        if frame is not None and frame.has_signal:
            fmt_info = dev.current_input_format
            if fmt_info is not None and fmt_info.mode != pydecklink.DisplayMode.Unknown:
                print(f" detected {fmt_info.mode!r}")
                return fmt_info.mode
        print(".", end="", flush=True)


def main() -> None:
    running = True

    def on_sigint(_sig: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, on_sigint)

    devices = pydecklink.list_devices()
    if len(devices) < 2:
        print(
            f"Need at least 2 DeckLink sub-devices, found {len(devices)}.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Capture: {devices[0]}")
    print(f"Playout: {devices[1]}")

    cap_dev = pydecklink.Device(index=0)
    out_dev = pydecklink.Device(index=1)

    pixel_format = pydecklink.PixelFormat.Format8BitYUV

    # -- Detect input signal ------------------------------------------------
    mode = wait_for_signal(cap_dev, pixel_format)
    cap_dev.stop_streams()
    cap_dev.disable_video_input()

    width = pydecklink.get_mode_width(mode)
    height = pydecklink.get_mode_height(mode)
    fps = pydecklink.get_mode_fps(mode)
    frame_bytes = pydecklink.get_frame_bytes(mode, pixel_format)
    row_bytes = frame_bytes // height

    print(f"Format: {width}x{height} @ {fps:.2f} fps, {frame_bytes} bytes/frame")

    # -- Configure capture --------------------------------------------------
    cap_dev.enable_video_input(mode, pixel_format)
    cap_dev.start_streams()

    # -- Configure playout --------------------------------------------------
    out_dev.enable_video_output(mode)

    # -- Frame loop ---------------------------------------------------------
    print("Passthrough running (Ctrl-C to stop)...")
    frames = 0
    dropped = 0
    frame_duration, timescale = _frame_timing(mode)
    display_time = 0

    # Pre-roll: schedule a few black frames so playback can start.
    preroll_count = 3
    black_frame = np.zeros(frame_bytes, dtype=np.uint8)
    for i in range(preroll_count):
        out_dev.schedule_frame(
            black_frame,
            width,
            height,
            row_bytes,
            pixel_format,
            display_time=i * frame_duration,
            duration=frame_duration,
            timescale=timescale,
        )
    display_time = preroll_count * frame_duration
    out_dev.start_scheduled_playback(start_time=0, timescale=timescale)

    while running:
        frame = cap_dev.pop_capture_frame(timeout_ms=1000)
        if frame is None:
            continue
        if not frame.has_signal:
            continue

        out_dev.schedule_frame(
            frame.data,
            width,
            height,
            row_bytes,
            pixel_format,
            display_time=display_time,
            duration=frame_duration,
            timescale=timescale,
        )
        display_time += frame_duration
        frames += 1

        status = out_dev.output_status
        new_dropped = status.dropped + status.late
        if new_dropped != dropped:
            dropped = new_dropped
            print(f"  dropped/late: {dropped}", flush=True)

    # -- Cleanup ------------------------------------------------------------
    print(f"\nStopping. {frames} frames transferred, {dropped} dropped/late.")

    out_dev.stop_scheduled_playback()
    out_dev.disable_video_output()
    cap_dev.stop_streams()
    cap_dev.disable_video_input()


def _frame_timing(mode: pydecklink.DisplayMode) -> tuple[int, int]:
    """Return (frame_duration, timescale) for scheduling.

    Uses a 10 MHz timescale for sub-frame precision.
    """
    fps = pydecklink.get_mode_fps(mode)
    timescale = 10_000_000
    frame_duration = round(timescale / fps)
    return frame_duration, timescale


if __name__ == "__main__":
    main()
