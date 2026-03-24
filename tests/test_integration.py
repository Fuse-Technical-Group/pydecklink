"""Integration tests — require AJA hardware with CH3↔CH4 SDI loopback cable.

Run with: pytest -m hardware tests/test_integration.py

The NTV2 kernel driver has no capability checks; it requires only
read/write access to /dev/ajantv20 (mode 666) and sufficient
RLIMIT_MEMLOCK for DMA page pinning.  The devcontainer uses
--userns=keep-id so the host user's permissions pass through.

The probe uses the same channels and routing as the real tests
(CH3 playout → SDI3 cable → SDI4 → CH4 capture) so that:
  1. Signal routing is configured — without it, input VBI interrupts
     never fire and AutoCirculate stays in STARTING state forever.
  2. The playout side provides a live signal on the loopback cable,
     giving the capture side a valid video reference.
  3. The actual autocirculate_transfer (card→host DMA) is attempted,
     which is the operation that requires elevated capabilities.
"""

from __future__ import annotations

import numpy as np
import pytest

from _helpers import (
    CAPTURE_CH,
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
    PixelFormat,
    ReferenceSource,
    Transfer,
    VideoFormat,
    get_frame_bytes,
)

pytestmark = pytest.mark.hardware

# ── Constants ────────────────────────────────────────────────────────

VIDEO_FORMAT = VideoFormat.FORMAT_1080i_5994
FRAME_BYTES = get_frame_bytes(VIDEO_FORMAT, PixelFormat.FBF_10BIT_YCBCR)
MAX_FRAME_BYTES = 3840 * 2160 * 4  # conservative upper-bound for any format
PASSTHROUGH_FRAMES = 300  # ~10 s at 59.94 fps interlaced


# ── Probe ────────────────────────────────────────────────────────────

_CAPTURE_DMA_WORKS = probe_loopback_dma(VIDEO_FORMAT, MAX_FRAME_BYTES)

if not _CAPTURE_DMA_WORKS:
    pytestmark = [
        pytest.mark.hardware,
        pytest.mark.skip(
            reason=(
                "capture DMA probe failed — ensure /dev/ajantv20 is "
                "accessible (mode 666) and RLIMIT_MEMLOCK is sufficient"
            )
        ),
    ]


# ── Helpers ──────────────────────────────────────────────────────────


def _fill_pattern(buf: np.ndarray, name: str) -> None:
    """Fill *buf* in-place with the named test pattern."""
    if name == "zeros":
        buf[:] = 0
    elif name == "ramp":
        buf[:] = np.arange(len(buf), dtype=np.uint8)
    elif name == "0xAA":
        buf[:] = 0xAA
    elif name == "0x55":
        buf[:] = 0x55
    else:
        msg = f"unknown pattern: {name}"
        raise ValueError(msg)


# ── CPU Loopback ─────────────────────────────────────────────────────


class TestCpuLoopback:
    """Playout a known pattern on CH3, capture on CH4, compare byte-for-byte."""

    @pytest.mark.parametrize("pattern", ["zeros", "ramp", "0xAA", "0x55"])
    def test_data_integrity(
        self,
        loopback_card: LoopbackSession,
        pattern: str,
    ) -> None:
        card = loopback_card.card

        configure_playout(card, VIDEO_FORMAT)
        configure_capture(card, VIDEO_FORMAT)
        card.set_reference(ReferenceSource.FREERUN)
        apply_loopback_routes(card)

        _out_mm, out_buf = loopback_card.alloc_buffer(MAX_FRAME_BYTES)
        _cap_mm, cap_buf = loopback_card.alloc_buffer(MAX_FRAME_BYTES)
        _fill_pattern(out_buf, pattern)
        expected = out_buf.copy()

        stop_pair(card)

        card.autocirculate_init_for_output(PLAYOUT_CH)
        card.autocirculate_init_for_input(CAPTURE_CH)

        out_xfer = Transfer()
        out_xfer.set_video_buffer(out_buf)
        cap_xfer = Transfer()
        cap_xfer.set_video_buffer(cap_buf)

        card.autocirculate_start(PLAYOUT_CH)
        card.autocirculate_start(CAPTURE_CH)

        # Prime: push pattern frames into the playout ring buffer.
        for _ in range(PRIME_FRAMES):
            status = card.autocirculate_get_status(PLAYOUT_CH)
            if status.can_accept_more_output_frames:
                card.autocirculate_transfer(PLAYOUT_CH, out_xfer)
            card.wait_for_input_vertical_interrupt(PLAYOUT_CH)

        # Settle: let frames propagate through loopback cable.
        for _ in range(SETTLE_VBIS):
            card.wait_for_input_vertical_interrupt(CAPTURE_CH)

        # Capture one frame.
        cap_status = card.autocirculate_get_status(CAPTURE_CH)
        assert cap_status.has_available_input_frame, "no frame available to capture"
        card.autocirculate_transfer(CAPTURE_CH, cap_xfer)

        np.testing.assert_array_equal(
            cap_buf[:FRAME_BYTES],
            expected[:FRAME_BYTES],
        )


# ── CPU Passthrough ──────────────────────────────────────────────────


class TestCpuPassthrough:
    """Sustained capture→playout loop over CPU memory. Assert zero drops."""

    def test_zero_dropped_frames(
        self,
        loopback_card: LoopbackSession,
    ) -> None:
        card = loopback_card.card

        configure_playout(card, VIDEO_FORMAT)
        configure_capture(card, VIDEO_FORMAT)
        card.set_reference(ReferenceSource.FREERUN)
        apply_loopback_routes(card)

        _buf_mm, buf = loopback_card.alloc_buffer(MAX_FRAME_BYTES)

        cap_xfer = Transfer()
        cap_xfer.set_video_buffer(buf)
        out_xfer = Transfer()
        out_xfer.set_video_buffer(buf)

        stop_pair(card)

        card.autocirculate_init_for_output(PLAYOUT_CH)
        card.autocirculate_init_for_input(CAPTURE_CH)
        card.autocirculate_start(PLAYOUT_CH)
        card.autocirculate_start(CAPTURE_CH)

        # Bootstrap: push dummy frames so loopback cable carries signal.
        for _ in range(PRIME_FRAMES):
            status = card.autocirculate_get_status(PLAYOUT_CH)
            if status.can_accept_more_output_frames:
                card.autocirculate_transfer(PLAYOUT_CH, out_xfer)
            card.wait_for_input_vertical_interrupt(PLAYOUT_CH)

        # snapshot drop counters after warmup — drops during
        # prime/settle are expected and not under test
        cap_baseline = card.autocirculate_get_status(CAPTURE_CH).dropped_frame_count
        out_baseline = card.autocirculate_get_status(PLAYOUT_CH).dropped_frame_count

        # Sustained transfer loop.
        transferred = 0
        while transferred < PASSTHROUGH_FRAMES:
            cap_status = card.autocirculate_get_status(CAPTURE_CH)
            out_status = card.autocirculate_get_status(PLAYOUT_CH)

            if (
                cap_status.has_available_input_frame
                and out_status.can_accept_more_output_frames
            ):
                card.autocirculate_transfer(CAPTURE_CH, cap_xfer)
                card.autocirculate_transfer(PLAYOUT_CH, out_xfer)
                transferred += 1
            else:
                card.wait_for_input_vertical_interrupt(CAPTURE_CH)

        cap_status = card.autocirculate_get_status(CAPTURE_CH)
        out_status = card.autocirculate_get_status(PLAYOUT_CH)
        cap_drops = cap_status.dropped_frame_count - cap_baseline
        out_drops = out_status.dropped_frame_count - out_baseline
        assert cap_drops == 0, f"capture dropped {cap_drops} frames"
        assert out_drops == 0, f"playout dropped {out_drops} frames"
