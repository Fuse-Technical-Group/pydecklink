"""Benchmark two-hop DMA throughput at 4K/60.

Validates that capture + playout DMA transfers fit within the ~16.683 ms
frame period (1/59.94 Hz).  Requires AJA hardware with CH3<->CH4 SDI
loopback cable and 12G-SDI support.

Run with: pytest -m "hardware and benchmark" tests/test_benchmark.py -s
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from _helpers import (
    CAPTURE_CH,
    PIXEL_FORMAT,
    PLAYOUT_CH,
    PRIME_FRAMES,
    SETTLE_VBIS,
    apply_loopback_routes,
    configure_capture,
    configure_playout,
    probe_loopback_dma,
    stop_pair,
)
from conftest import LoopbackSession
from pyntv2 import (
    ReferenceSource,
    Transfer,
    VideoFormat,
    get_frame_bytes,
)

pytestmark = [pytest.mark.hardware, pytest.mark.benchmark]

# ── Constants ────────────────────────────────────────────────────────

VIDEO_FORMAT = VideoFormat.FORMAT_3840x2160p_5994
FRAME_BYTES = get_frame_bytes(VIDEO_FORMAT, PIXEL_FORMAT)
FRAME_PERIOD_MS = 1000.0 / 59.94  # ~16.683 ms
BENCHMARK_FRAMES = 300  # ~5 s at 59.94 fps progressive


# ── Probe ────────────────────────────────────────────────────────────

_4K60_DMA_WORKS = probe_loopback_dma(VIDEO_FORMAT, FRAME_BYTES)

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


# ── Helpers ──────────────────────────────────────────────────────────


def _compute_stats(arr: np.ndarray) -> dict[str, float]:
    return {
        "min": float(np.min(arr)),
        "mean": float(np.mean(arr)),
        "max": float(np.max(arr)),
        "p99": float(np.percentile(arr, 99)),
    }


def _print_stats(
    title: str,
    rows: list[tuple[str, dict[str, float]]],
) -> None:
    print()
    print(title)
    for label, s in rows:
        print(
            f"  {label}  "
            f"min={s['min']:.3f}  "
            f"mean={s['mean']:.3f}  "
            f"max={s['max']:.3f}  "
            f"p99={s['p99']:.3f} ms"
        )


# ── Benchmark ────────────────────────────────────────────────────────


class TestDmaThroughput4K60:
    """Measure two-hop DMA round-trip time at 4K/59.94."""

    def test_two_hop_fits_frame_budget(
        self,
        loopback_card: LoopbackSession,
    ) -> None:
        card = loopback_card.card

        configure_playout(card, VIDEO_FORMAT)
        configure_capture(card, VIDEO_FORMAT)
        card.set_reference(ReferenceSource.FREERUN)
        apply_loopback_routes(card)

        _buf_mm, buf = loopback_card.alloc_buffer(FRAME_BYTES)

        cap_xfer = Transfer()
        cap_xfer.set_video_buffer(buf)
        out_xfer = Transfer()
        out_xfer.set_video_buffer(buf)

        stop_pair(card)

        card.autocirculate_init_for_output(PLAYOUT_CH)
        card.autocirculate_init_for_input(CAPTURE_CH)
        card.autocirculate_start(PLAYOUT_CH)
        card.autocirculate_start(CAPTURE_CH)

        # prime playout ring buffer
        for _ in range(PRIME_FRAMES):
            status = card.autocirculate_get_status(PLAYOUT_CH)
            if status.can_accept_more_output_frames:
                card.autocirculate_transfer(PLAYOUT_CH, out_xfer)
            card.wait_for_input_vertical_interrupt(PLAYOUT_CH)

        # settle capture
        for _ in range(SETTLE_VBIS):
            card.wait_for_input_vertical_interrupt(CAPTURE_CH)

        # snapshot drop counters after warmup — drops during
        # prime/settle are expected and not under test
        cap_baseline = card.autocirculate_get_status(CAPTURE_CH).dropped_frame_count
        out_baseline = card.autocirculate_get_status(PLAYOUT_CH).dropped_frame_count

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

        cap_stats = _compute_stats(cap_arr)
        out_stats = _compute_stats(out_arr)
        rt_stats = _compute_stats(roundtrip_arr)

        _print_stats(
            f"4K/60 DMA benchmark ({transferred} frames, {FRAME_BYTES} bytes/frame)",
            [
                ("capture ", cap_stats),
                ("playout ", out_stats),
                ("two-hop ", rt_stats),
            ],
        )
        print(
            f"  budget={FRAME_PERIOD_MS:.3f} ms  "
            f"headroom={FRAME_PERIOD_MS - rt_stats['p99']:.3f} ms"
        )

        # assert zero dropped frames during the timed window
        cap_status = card.autocirculate_get_status(CAPTURE_CH)
        out_status = card.autocirculate_get_status(PLAYOUT_CH)
        cap_drops = cap_status.dropped_frame_count - cap_baseline
        out_drops = out_status.dropped_frame_count - out_baseline

        assert cap_drops == 0, f"capture dropped {cap_drops} frames"
        assert out_drops == 0, f"playout dropped {out_drops} frames"


class TestRawDmaThroughput4K:
    """Measure raw DMA read/write without AutoCirculate or SDI.

    Uses DMAWriteFrame/DMAReadFrame to transfer directly between host
    memory and the card's on-board frame store.  Isolates pure
    PCIe + SWIOTLB bounce-buffer cost.
    """

    def test_raw_dma_round_trip(
        self,
        loopback_card: LoopbackSession,
    ) -> None:
        card = loopback_card.card

        # Configure a channel so the card knows the frame geometry.
        card.enable_channel(PLAYOUT_CH)
        card.set_video_format(VIDEO_FORMAT, channel=PLAYOUT_CH)
        card.set_frame_buffer_format(PLAYOUT_CH, PIXEL_FORMAT)

        _buf_mm, buf = loopback_card.alloc_buffer(FRAME_BYTES)

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
            [
                ("write  ", w_stats),
                ("read   ", r_stats),
                ("two-hop", rt_stats),
            ],
        )
        print(
            f"  budget={FRAME_PERIOD_MS:.3f} ms  "
            f"headroom={FRAME_PERIOD_MS - rt_stats['p99']:.3f} ms"
        )
