"""SDI passthrough: capture on port 1, playout on port 2.

Waits for a signal on SDI1, matches the output format, and loops
frames through CPU memory. Ctrl-C to stop.

Usage:
    python examples/passthrough.py
"""

import signal
import sys
import time

import numpy as np

from pyntv2 import (
    AudioSystem,
    Card,
    Channel,
    InputSource,
    Mode,
    OutputDest,
    PixelFormat,
    ReferenceSource,
    Transfer,
    VideoFormat,
    route_capture,
    route_playout,
)

PIXEL_FORMAT = PixelFormat.FBF_10BIT_YCBCR
# 10-bit YCbCr: 16 bytes per 6 pixels, worst case ~4 bytes/pixel
MAX_FRAME_BYTES = 3840 * 2160 * 4


def wait_for_signal(card: Card) -> VideoFormat:
    """Poll SDI1 until a valid signal appears."""
    print("Waiting for signal on SDI1...", end="", flush=True)
    while True:
        fmt = card.get_input_video_format(InputSource.SDI1)
        if fmt != VideoFormat.FORMAT_UNKNOWN:
            print(f" {fmt.name}")
            return fmt
        print(".", end="", flush=True)
        time.sleep(0.5)


def main() -> None:
    running = True

    def on_sigint(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, on_sigint)

    with Card(device_index=0) as card:
        # ── Detect input ──────────────────────────────────────────
        card.set_sdi_transmit_enable(Channel.CH1, False)  # CH1 = receive
        video_format = wait_for_signal(card)

        # ── Configure capture (CH1) ───────────────────────────────
        card.enable_channel(Channel.CH1)
        card.set_mode(Channel.CH1, Mode.CAPTURE)
        card.set_video_format(video_format, channel=Channel.CH1)
        card.set_frame_buffer_format(Channel.CH1, PIXEL_FORMAT)

        # ── Configure playout (CH2) ───────────────────────────────
        card.set_sdi_transmit_enable(Channel.CH2, True)  # CH2 = transmit
        card.enable_channel(Channel.CH2)
        card.set_mode(Channel.CH2, Mode.DISPLAY)
        card.set_video_format(video_format, channel=Channel.CH2)
        card.set_frame_buffer_format(Channel.CH2, PIXEL_FORMAT)

        # ── Reference clock ───────────────────────────────────────
        card.set_reference(ReferenceSource.INPUT1)

        # ── Signal routing ────────────────────────────────────────
        card.clear_routing()
        cap_routes = route_capture(InputSource.SDI1, Channel.CH1, PIXEL_FORMAT)
        out_routes = route_playout(Channel.CH2, OutputDest.SDI2, PIXEL_FORMAT)
        card.apply_signal_route(cap_routes, replace=False)
        card.apply_signal_route(out_routes, replace=False)

        # ── Allocate buffer (page-aligned for DMA) ────────────────
        import mmap
        _backing = mmap.mmap(-1, MAX_FRAME_BYTES)
        buf = np.frombuffer(_backing, dtype=np.uint8)
        card.dma_buffer_lock(buf)

        cap_xfer = Transfer()
        cap_xfer.set_video_buffer(buf)
        out_xfer = Transfer()
        out_xfer.set_video_buffer(buf)

        # ── Start AutoCirculate ───────────────────────────────────
        card.autocirculate_stop(Channel.CH1, abort=True)
        card.autocirculate_stop(Channel.CH2, abort=True)

        card.autocirculate_init_for_input(Channel.CH1)
        card.autocirculate_init_for_output(Channel.CH2)
        card.autocirculate_start(Channel.CH1)
        card.autocirculate_start(Channel.CH2)

        print("Passthrough running (Ctrl-C to stop)...")
        frames = 0
        dropped = 0

        # ── Frame loop ────────────────────────────────────────────
        while running:
            cap_status = card.autocirculate_get_status(Channel.CH1)
            out_status = card.autocirculate_get_status(Channel.CH2)

            if cap_status.has_available_input_frame and out_status.can_accept_more_output_frames:
                card.autocirculate_transfer(Channel.CH1, cap_xfer)
                card.autocirculate_transfer(Channel.CH2, out_xfer)
                frames += 1

                new_dropped = cap_status.dropped_frame_count
                if new_dropped != dropped:
                    dropped = new_dropped
                    print(f"  dropped: {dropped}", flush=True)
            else:
                card.wait_for_input_vertical_interrupt(Channel.CH1)

        # ── Cleanup ───────────────────────────────────────────────
        print(f"\nStopping. {frames} frames transferred, {dropped} dropped.")
        card.autocirculate_stop(Channel.CH1, abort=True)
        card.autocirculate_stop(Channel.CH2, abort=True)
        card.dma_buffer_unlock(buf)
        card.clear_routing()


if __name__ == "__main__":
    main()
