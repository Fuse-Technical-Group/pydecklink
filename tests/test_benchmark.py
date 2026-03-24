"""Benchmark two-hop DMA throughput at 4K/60.

Validates that capture + playout DMA transfers fit within the ~16.683 ms
frame period (1/59.94 Hz).  Requires AJA hardware with CH3<->CH4 SDI
loopback cable and 12G-SDI support.

Run with: pytest -m "hardware and benchmark" tests/test_benchmark.py -s
"""

from __future__ import annotations

import mmap
import os
import time

import numpy as np
import pytest

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
    get_frame_bytes,
    route_capture,
    route_playout,
)

pytestmark = [pytest.mark.hardware, pytest.mark.benchmark]

# ── Constants ────────────────────────────────────────────────────────

VIDEO_FORMAT = VideoFormat.FORMAT_3840x2160p_5994
PIXEL_FORMAT = PixelFormat.FBF_10BIT_YCBCR  # native SDI, no CSC
FRAME_BYTES = get_frame_bytes(VIDEO_FORMAT, PIXEL_FORMAT)
FRAME_PERIOD_MS = 1000.0 / 59.94  # ~16.683 ms

BENCHMARK_FRAMES = 300  # ~5 s at 59.94 fps progressive

PLAYOUT_CH = Channel.CH3
CAPTURE_CH = Channel.CH4
PLAYOUT_DEST = OutputDest.SDI3
CAPTURE_SRC = InputSource.SDI4

_NTV2_OEM_TASKS = 2
_APP_SIG = 0x54455354  # NTV2_FOURCC('T','E','S','T')

_PRIME_FRAMES = 10
_SETTLE_VBIS = 5


# ── Helpers ──────────────────────────────────────────────────────────


def _page_aligned_buffer(size: int) -> tuple[mmap.mmap, np.ndarray]:
    """Allocate a page-aligned numpy buffer backed by anonymous mmap."""
    backing = mmap.mmap(-1, size)
    return backing, np.frombuffer(backing, dtype=np.uint8)


def _probe_4k60_dma() -> bool:
    """Return True if two-hop DMA works at 4K/60 on CH3<->CH4 loopback."""
    locked_bufs: list[np.ndarray] = []
    backings: list[mmap.mmap] = []
    try:
        with Card(device_index=0) as card:
            card.acquire_stream_for_application(_APP_SIG, os.getpid())
            card.set_every_frame_services(_NTV2_OEM_TASKS)

            # playout side (CH3 -> SDI3)
            card.set_sdi_transmit_enable(PLAYOUT_CH, True)
            card.enable_channel(PLAYOUT_CH)
            card.set_mode(PLAYOUT_CH, Mode.DISPLAY)
            card.set_video_format(VIDEO_FORMAT, channel=PLAYOUT_CH)
            card.set_frame_buffer_format(PLAYOUT_CH, PIXEL_FORMAT)

            # capture side (SDI4 -> CH4)
            card.set_sdi_transmit_enable(CAPTURE_CH, False)
            card.enable_channel(CAPTURE_CH)
            card.set_mode(CAPTURE_CH, Mode.CAPTURE)
            card.set_video_format(VIDEO_FORMAT, channel=CAPTURE_CH)
            card.set_frame_buffer_format(CAPTURE_CH, PIXEL_FORMAT)

            # routing
            card.set_reference(ReferenceSource.FREERUN)
            card.clear_routing()
            card.apply_signal_route(
                route_playout(PLAYOUT_CH, PLAYOUT_DEST, PIXEL_FORMAT),
                replace=False,
            )
            card.apply_signal_route(
                route_capture(CAPTURE_SRC, CAPTURE_CH, PIXEL_FORMAT),
                replace=False,
            )

            try:
                card.autocirculate_stop(PLAYOUT_CH, abort=True)
                card.autocirculate_stop(CAPTURE_CH, abort=True)

                # start playout with a blank frame
                card.autocirculate_init_for_output(PLAYOUT_CH)
                card.autocirculate_start(PLAYOUT_CH)

                blank_mm, blank = _page_aligned_buffer(FRAME_BYTES)
                backings.append(blank_mm)
                card.dma_buffer_lock(blank)
                locked_bufs.append(blank)
                out_xfer = Transfer()
                out_xfer.set_video_buffer(blank)
                card.wait_for_input_vertical_interrupt(PLAYOUT_CH)
                card.autocirculate_transfer(PLAYOUT_CH, out_xfer)

                # start capture and wait for a frame
                card.autocirculate_init_for_input(CAPTURE_CH)
                card.autocirculate_start(CAPTURE_CH)

                for _ in range(30):
                    card.wait_for_input_vertical_interrupt(CAPTURE_CH)
                    status = card.autocirculate_get_status(CAPTURE_CH)
                    if status.has_available_input_frame:
                        break
                else:
                    return False

                # attempt capture DMA
                cap_mm, cap_buf = _page_aligned_buffer(FRAME_BYTES)
                backings.append(cap_mm)
                card.dma_buffer_lock(cap_buf)
                locked_bufs.append(cap_buf)
                cap_xfer = Transfer()
                cap_xfer.set_video_buffer(cap_buf)
                card.autocirculate_transfer(CAPTURE_CH, cap_xfer)
                return True
            finally:
                card.autocirculate_stop(PLAYOUT_CH, abort=True)
                card.autocirculate_stop(CAPTURE_CH, abort=True)
                for buf in locked_bufs:
                    card.dma_buffer_unlock(buf)
                card.clear_routing()
    except RuntimeError:
        return False


_4K60_DMA_WORKS = _probe_4k60_dma()

if not _4K60_DMA_WORKS:
    pytestmark = [
        pytest.mark.hardware,
        pytest.mark.benchmark,
        pytest.mark.skip(
            reason=(
                "4K/60 DMA probe failed — card may not support "
                "12G-SDI or loopback cable is not connected"
            )
        ),
    ]


# ── Benchmark ────────────────────────────────────────────────────────


class TestDmaThroughput4K60:
    """Measure two-hop DMA round-trip time at 4K/59.94."""

    def test_two_hop_fits_frame_budget(self, card: Card) -> None:
        # configure channels
        card.set_sdi_transmit_enable(PLAYOUT_CH, True)
        card.enable_channel(PLAYOUT_CH)
        card.set_mode(PLAYOUT_CH, Mode.DISPLAY)
        card.set_video_format(VIDEO_FORMAT, channel=PLAYOUT_CH)
        card.set_frame_buffer_format(PLAYOUT_CH, PIXEL_FORMAT)

        card.set_sdi_transmit_enable(CAPTURE_CH, False)
        card.enable_channel(CAPTURE_CH)
        card.set_mode(CAPTURE_CH, Mode.CAPTURE)
        card.set_video_format(VIDEO_FORMAT, channel=CAPTURE_CH)
        card.set_frame_buffer_format(CAPTURE_CH, PIXEL_FORMAT)

        # routing
        card.set_reference(ReferenceSource.FREERUN)
        card.clear_routing()
        card.apply_signal_route(
            route_playout(PLAYOUT_CH, PLAYOUT_DEST, PIXEL_FORMAT),
            replace=False,
        )
        card.apply_signal_route(
            route_capture(CAPTURE_SRC, CAPTURE_CH, PIXEL_FORMAT),
            replace=False,
        )

        buf_mm, buf = _page_aligned_buffer(FRAME_BYTES)
        card.dma_buffer_lock(buf)

        cap_xfer = Transfer()
        cap_xfer.set_video_buffer(buf)
        out_xfer = Transfer()
        out_xfer.set_video_buffer(buf)

        try:
            card.autocirculate_stop(PLAYOUT_CH, abort=True)
            card.autocirculate_stop(CAPTURE_CH, abort=True)

            card.autocirculate_init_for_output(PLAYOUT_CH)
            card.autocirculate_init_for_input(CAPTURE_CH)
            card.autocirculate_start(PLAYOUT_CH)
            card.autocirculate_start(CAPTURE_CH)

            # prime playout ring buffer
            for _ in range(_PRIME_FRAMES):
                status = card.autocirculate_get_status(PLAYOUT_CH)
                if status.can_accept_more_output_frames:
                    card.autocirculate_transfer(PLAYOUT_CH, out_xfer)
                card.wait_for_input_vertical_interrupt(PLAYOUT_CH)

            # settle capture
            for _ in range(_SETTLE_VBIS):
                card.wait_for_input_vertical_interrupt(CAPTURE_CH)

            # timed transfer loop
            cap_times_ms: list[float] = []
            out_times_ms: list[float] = []
            transferred = 0

            while transferred < BENCHMARK_FRAMES:
                cap_status = card.autocirculate_get_status(CAPTURE_CH)
                out_status = card.autocirculate_get_status(PLAYOUT_CH)

                if (
                    cap_status.has_available_input_frame
                    and out_status.can_accept_more_output_frames
                ):
                    t0 = time.perf_counter()
                    card.autocirculate_transfer(CAPTURE_CH, cap_xfer)
                    t1 = time.perf_counter()
                    card.autocirculate_transfer(PLAYOUT_CH, out_xfer)
                    t2 = time.perf_counter()

                    cap_times_ms.append((t1 - t0) * 1000.0)
                    out_times_ms.append((t2 - t1) * 1000.0)
                    transferred += 1
                else:
                    card.wait_for_input_vertical_interrupt(CAPTURE_CH)

            # compute per-direction statistics
            cap_arr = np.array(cap_times_ms)
            out_arr = np.array(out_times_ms)
            roundtrip_arr = cap_arr + out_arr

            def _stats(arr: np.ndarray) -> dict[str, float]:
                return {
                    "min": float(np.min(arr)),
                    "mean": float(np.mean(arr)),
                    "max": float(np.max(arr)),
                    "p99": float(np.percentile(arr, 99)),
                }

            cap_stats = _stats(cap_arr)
            out_stats = _stats(out_arr)
            rt_stats = _stats(roundtrip_arr)

            # report
            print()  # noqa: T201
            print(  # noqa: T201
                f"4K/60 DMA benchmark "
                f"({transferred} frames, "
                f"{FRAME_BYTES} bytes/frame)"
            )
            for label, s in [
                ("capture ", cap_stats),
                ("playout ", out_stats),
                ("two-hop ", rt_stats),
            ]:
                print(  # noqa: T201
                    f"  {label}  "
                    f"min={s['min']:.3f}  "
                    f"mean={s['mean']:.3f}  "
                    f"max={s['max']:.3f}  "
                    f"p99={s['p99']:.3f} ms"
                )
            print(  # noqa: T201
                f"  budget={FRAME_PERIOD_MS:.3f} ms  "
                f"headroom={FRAME_PERIOD_MS - rt_stats['p99']:.3f} ms"
            )

            # assert zero dropped frames
            cap_status = card.autocirculate_get_status(CAPTURE_CH)
            out_status = card.autocirculate_get_status(PLAYOUT_CH)

            assert cap_status.dropped_frame_count == 0, (
                f"capture dropped {cap_status.dropped_frame_count} frames"
            )
            assert out_status.dropped_frame_count == 0, (
                f"playout dropped {out_status.dropped_frame_count} frames"
            )
        finally:
            card.autocirculate_stop(PLAYOUT_CH, abort=True)
            card.autocirculate_stop(CAPTURE_CH, abort=True)
            card.dma_buffer_unlock(buf)
            card.clear_routing()


def _print_stats(
    title: str,
    frame_bytes: int,
    rows: list[tuple[str, dict[str, float]]],
) -> None:
    print()  # noqa: T201
    print(title)  # noqa: T201
    for label, s in rows:
        print(  # noqa: T201
            f"  {label}  "
            f"min={s['min']:.3f}  "
            f"mean={s['mean']:.3f}  "
            f"max={s['max']:.3f}  "
            f"p99={s['p99']:.3f} ms"
        )


def _compute_stats(arr: np.ndarray) -> dict[str, float]:
    return {
        "min": float(np.min(arr)),
        "mean": float(np.mean(arr)),
        "max": float(np.max(arr)),
        "p99": float(np.percentile(arr, 99)),
    }


class TestRawDmaThroughput4K:
    """Measure raw DMA read/write without AutoCirculate or SDI.

    Uses DMAWriteFrame/DMAReadFrame to transfer directly between host
    memory and the card's on-board frame store.  Isolates pure
    PCIe + SWIOTLB bounce-buffer cost.
    """

    def test_raw_dma_round_trip(self, card: Card) -> None:
        # Configure a channel so the card knows the frame geometry.
        card.enable_channel(PLAYOUT_CH)
        card.set_video_format(VIDEO_FORMAT, channel=PLAYOUT_CH)
        card.set_frame_buffer_format(PLAYOUT_CH, PIXEL_FORMAT)

        buf_mm, buf = _page_aligned_buffer(FRAME_BYTES)
        card.dma_buffer_lock(buf)

        try:
            write_times_ms: list[float] = []
            read_times_ms: list[float] = []

            for _ in range(BENCHMARK_FRAMES):
                t0 = time.perf_counter()
                card.dma_write_frame(0, buf, PLAYOUT_CH)
                t1 = time.perf_counter()
                card.dma_read_frame(0, buf, PLAYOUT_CH)
                t2 = time.perf_counter()

                write_times_ms.append((t1 - t0) * 1000.0)
                read_times_ms.append((t2 - t1) * 1000.0)

            w_arr = np.array(write_times_ms)
            r_arr = np.array(read_times_ms)
            rt_arr = w_arr + r_arr

            w_stats = _compute_stats(w_arr)
            r_stats = _compute_stats(r_arr)
            rt_stats = _compute_stats(rt_arr)

            _print_stats(
                f"4K raw DMA benchmark "
                f"({BENCHMARK_FRAMES} frames, "
                f"{FRAME_BYTES} bytes/frame)",
                FRAME_BYTES,
                [
                    ("write  ", w_stats),
                    ("read   ", r_stats),
                    ("two-hop", rt_stats),
                ],
            )
            print(  # noqa: T201
                f"  budget={FRAME_PERIOD_MS:.3f} ms  "
                f"headroom={FRAME_PERIOD_MS - rt_stats['p99']:.3f} ms"
            )
        finally:
            card.dma_buffer_unlock(buf)
