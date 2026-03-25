"""Zero-copy SDI passthrough via DeckLink.

Auto-detects the input signal format, configures output to match,
and loops captured frames through scheduled playback with no memcpy.
Uses two threads (reader/writer) with a 3-frame pre-roll (~50ms
latency at 59.94fps). Ctrl-C to stop.

Requires two DeckLink sub-devices (or two cards) connected via SDI.
Default: device 3 captures, device 1 plays out.

Usage:
    python examples/passthrough_decklink.py
    python examples/passthrough_decklink.py --capture 3 --playout 1
"""

from __future__ import annotations

import argparse
import queue
import signal
import sys
import threading

import pydecklink


def detect_input(
    dev: pydecklink.Device,
    pixel_format: pydecklink.PixelFormat,
) -> pydecklink.DisplayMode:
    """Enable input with format detection and wait for a valid signal."""
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
    parser = argparse.ArgumentParser(description="Zero-copy DeckLink passthrough")
    parser.add_argument("--capture", type=int, default=3, help="Capture device index")
    parser.add_argument("--playout", type=int, default=1, help="Playout device index")
    parser.add_argument(
        "--pixel-format",
        choices=["8bit", "10bit"],
        default="10bit",
        help="Pixel format (default: 10bit)",
    )
    args = parser.parse_args()

    pixel_format = (
        pydecklink.PixelFormat.Format10BitYUV
        if args.pixel_format == "10bit"
        else pydecklink.PixelFormat.Format8BitYUV
    )

    devices = pydecklink.list_devices()
    max_idx = max(args.capture, args.playout)
    if len(devices) <= max_idx:
        print(
            f"Need at least {max_idx + 1} DeckLink sub-devices, found {len(devices)}.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Capture: {devices[args.capture]}")
    print(f"Playout: {devices[args.playout]}")

    cap_dev = pydecklink.Device(index=args.capture)
    out_dev = pydecklink.Device(index=args.playout)

    # -- Detect input signal ------------------------------------------------
    mode = detect_input(cap_dev, pixel_format)
    cap_dev.stop_streams()
    cap_dev.disable_video_input()

    width = pydecklink.get_mode_width(mode)
    height = pydecklink.get_mode_height(mode)
    fps = pydecklink.get_mode_fps(mode)
    frame_bytes = pydecklink.get_frame_bytes(mode, pixel_format)
    row_bytes = frame_bytes // height

    # Native timescale from the SDK mode table.
    frame_duration, frame_timescale = pydecklink.get_mode_frame_duration(mode)

    # Pre-roll depth: schedule this many frames before starting playback.
    # Minimum is 1 (from BMDDeckLinkMinimumPrerollFrames on 8K Pro).
    # 3 frames balances low latency (~50ms at 59.94) with jitter tolerance.
    preroll_count = 3

    print(f"Format: {width}x{height} @ {fps:.2f} fps, {frame_bytes} bytes/frame")
    print(f"Pre-roll: {preroll_count} frames ({preroll_count * frame_duration / frame_timescale * 1000:.0f} ms)")

    # -- Configure output ---------------------------------------------------
    out_dev.enable_video_output(mode)

    # -- Configure capture (zero-copy) --------------------------------------
    cap_dev.enable_video_input(mode, pixel_format, zero_copy=True)
    cap_dev.start_streams()

    # -- Pre-roll with live captured frames ------------------------------------
    print("Pre-rolling...", end="", flush=True)
    scheduled = 0
    while scheduled < preroll_count:
        frame = cap_dev.pop_capture_frame_ref(timeout_ms=1000)
        if frame is None or not frame.has_signal:
            continue
        out_dev.schedule_capture_frame(
            frame, scheduled * frame_duration, frame_duration, frame_timescale,
        )
        scheduled += 1

    out_dev.start_scheduled_playback(
        start_time=0, timescale=frame_timescale, speed=1.0,
    )
    print(" done.")

    # -- Two-thread frame loop ----------------------------------------------
    stop = threading.Event()
    frame_queue: queue.Queue[pydecklink.CaptureFrameRef] = queue.Queue(maxsize=3)

    running = True

    def on_sigint(_sig: int, _frame: object) -> None:
        nonlocal running
        running = False
        stop.set()

    signal.signal(signal.SIGINT, on_sigint)

    def reader() -> None:
        while not stop.is_set():
            f = cap_dev.pop_capture_frame_ref(timeout_ms=100)
            if f is not None and f.has_signal:
                try:
                    frame_queue.put(f, timeout=0.1)
                except queue.Full:
                    pass

    def writer() -> None:
        nonlocal scheduled
        frames = 0
        dropped = 0
        while not stop.is_set():
            try:
                f = frame_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            out_dev.schedule_capture_frame(
                f, scheduled * frame_duration, frame_duration, frame_timescale,
            )
            scheduled += 1
            frames += 1

            status = out_dev.output_status
            new_dropped = status.dropped + status.late
            if new_dropped != dropped:
                dropped = new_dropped
                print(f"  dropped/late: {dropped}", flush=True)

            if frames % 300 == 0:
                print(f"  {frames} frames", flush=True)

    reader_thread = threading.Thread(target=reader, daemon=True)
    writer_thread = threading.Thread(target=writer, daemon=True)

    print("Passthrough running (Ctrl-C to stop)...")
    reader_thread.start()
    writer_thread.start()

    try:
        while running:
            writer_thread.join(timeout=0.5)
            if not writer_thread.is_alive():
                break
    except KeyboardInterrupt:
        stop.set()

    stop.set()
    writer_thread.join(timeout=2)

    # -- Cleanup ------------------------------------------------------------
    status = out_dev.output_status
    total = status.completed + status.late + status.dropped
    print(
        f"\nStopping. {total} frames: "
        f"{status.completed} completed, {status.late} late, {status.dropped} dropped."
    )

    out_dev.stop_scheduled_playback()
    out_dev.disable_video_output()
    cap_dev.stop_streams()
    cap_dev.disable_video_input()


if __name__ == "__main__":
    main()
