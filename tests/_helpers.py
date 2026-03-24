"""Shared constants, helpers, and probe for hardware loopback tests."""

from __future__ import annotations

import mmap
import os

import numpy as np

from pyntv2 import (
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

# ── Loopback pair constants ──────────────────────────────────────────

PLAYOUT_CH = Channel.CH3
CAPTURE_CH = Channel.CH4
PLAYOUT_DEST = OutputDest.SDI3
CAPTURE_SRC = InputSource.SDI4
PIXEL_FORMAT = PixelFormat.FBF_10BIT_YCBCR

APP_SIG = 0x54455354  # NTV2_FOURCC('T','E','S','T')
OEM_TASKS = 2  # NTV2_OEM_TASKS

PRIME_FRAMES = 10
SETTLE_VBIS = 5


# ── Helpers ──────────────────────────────────────────────────────────


def page_aligned_buffer(size: int) -> tuple[mmap.mmap, np.ndarray]:
    """Allocate a page-aligned numpy buffer backed by anonymous mmap."""
    backing = mmap.mmap(-1, size)
    return backing, np.frombuffer(backing, dtype=np.uint8)


def configure_playout(card: Card, video_format: VideoFormat) -> None:
    """Set up PLAYOUT_CH for playout over PLAYOUT_DEST."""
    card.set_sdi_transmit_enable(PLAYOUT_CH, True)
    card.enable_channel(PLAYOUT_CH)
    card.set_mode(PLAYOUT_CH, Mode.DISPLAY)
    card.set_video_format(video_format, channel=PLAYOUT_CH)
    card.set_frame_buffer_format(PLAYOUT_CH, PIXEL_FORMAT)


def configure_capture(card: Card, video_format: VideoFormat) -> None:
    """Set up CAPTURE_CH for capture from CAPTURE_SRC."""
    card.set_sdi_transmit_enable(CAPTURE_CH, False)
    card.enable_channel(CAPTURE_CH)
    card.set_mode(CAPTURE_CH, Mode.CAPTURE)
    card.set_video_format(video_format, channel=CAPTURE_CH)
    card.set_frame_buffer_format(CAPTURE_CH, PIXEL_FORMAT)


def apply_loopback_routes(card: Card) -> None:
    """Route PLAYOUT_CH → PLAYOUT_DEST cable → CAPTURE_SRC → CAPTURE_CH."""
    card.clear_routing()
    card.apply_signal_route(
        route_playout(PLAYOUT_CH, PLAYOUT_DEST, PIXEL_FORMAT),
        replace=False,
    )
    card.apply_signal_route(
        route_capture(CAPTURE_SRC, CAPTURE_CH, PIXEL_FORMAT),
        replace=False,
    )


def stop_pair(card: Card) -> None:
    """Stop autocirculate on both loopback channels."""
    card.autocirculate_stop(PLAYOUT_CH, abort=True)
    card.autocirculate_stop(CAPTURE_CH, abort=True)


# ── Probe ────────────────────────────────────────────────────────────


def probe_loopback_dma(
    video_format: VideoFormat,
    buffer_size: int,
) -> bool:
    """Return True if two-hop DMA works on the CH3↔CH4 loopback pair.

    Fully self-contained: opens a card, acquires the stream, configures
    both channels at *video_format*, attempts a playout+capture DMA
    round-trip, then tears everything down and releases the stream.
    """
    locked_bufs: list[np.ndarray] = []
    backings: list[mmap.mmap] = []
    try:
        with Card(device_index=0) as card:
            card.acquire_stream_for_application(APP_SIG, os.getpid())
            card.set_every_frame_services(OEM_TASKS)

            configure_playout(card, video_format)
            configure_capture(card, video_format)

            card.set_reference(ReferenceSource.FREERUN)
            apply_loopback_routes(card)

            try:
                stop_pair(card)

                card.autocirculate_init_for_output(PLAYOUT_CH)
                card.autocirculate_start(PLAYOUT_CH)

                blank_mm, blank = page_aligned_buffer(buffer_size)
                backings.append(blank_mm)
                card.dma_buffer_lock(blank)
                locked_bufs.append(blank)
                out_xfer = Transfer()
                out_xfer.set_video_buffer(blank)
                card.wait_for_input_vertical_interrupt(PLAYOUT_CH)
                card.autocirculate_transfer(PLAYOUT_CH, out_xfer)

                card.autocirculate_init_for_input(CAPTURE_CH)
                card.autocirculate_start(CAPTURE_CH)

                for _ in range(30):
                    card.wait_for_input_vertical_interrupt(CAPTURE_CH)
                    status = card.autocirculate_get_status(CAPTURE_CH)
                    if status.has_available_input_frame:
                        break
                else:
                    return False

                cap_mm, cap_buf = page_aligned_buffer(buffer_size)
                backings.append(cap_mm)
                card.dma_buffer_lock(cap_buf)
                locked_bufs.append(cap_buf)
                cap_xfer = Transfer()
                cap_xfer.set_video_buffer(cap_buf)
                card.autocirculate_transfer(CAPTURE_CH, cap_xfer)
                return True
            finally:
                stop_pair(card)
                for buf in locked_bufs:
                    card.dma_buffer_unlock(buf)
                card.clear_routing()
                card.release_stream_for_application(APP_SIG, os.getpid())
    except RuntimeError:
        return False
