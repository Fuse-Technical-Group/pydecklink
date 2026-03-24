"""Integration tests — require AJA hardware with CH3↔CH4 SDI loopback cable.

Run with: pytest -m hardware tests/test_integration.py

Validates the full DMA + SDI path: host → card frame store → SDI3 →
cable → SDI4 → card frame store → host.  Sends a known pattern out,
captures it back, and verifies the captured frame contains non-trivial
data (not byte-exact — SDI transport rewrites blanking regions with
timing references).
"""

from __future__ import annotations

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

pytestmark = pytest.mark.hardware

# ── Constants ────────────────────────────────────────────────────────

VIDEO_FORMAT = VideoFormat.FORMAT_3840x2160p_5994
FRAME_BYTES = get_frame_bytes(VIDEO_FORMAT, PIXEL_FORMAT)

# ── Probe ────────────────────────────────────────────────────────────

_4K60_DMA_WORKS = probe_loopback_dma(VIDEO_FORMAT, FRAME_BYTES)

if not _4K60_DMA_WORKS:
    pytestmark = [
        pytest.mark.hardware,
        pytest.mark.skip(
            reason=(
                "4K/60 DMA probe failed — card may not support "
                "12G-SDI or loopback cable is not connected"
            )
        ),
    ]


# ── SDI Loopback ─────────────────────────────────────────────────────


class TestSdiLoopback:
    """Verify data traverses the full SDI loopback path."""

    def test_captured_frame_is_not_empty(
        self,
        loopback_card: LoopbackSession,
    ) -> None:
        """Playout a non-zero pattern, capture back, verify DMA delivered data.

        SDI transport inserts timing references and rewrites blanking
        regions, so byte-exact comparison against the sent pattern is
        not meaningful.  Instead we assert that the captured frame
        contains substantial non-zero content — proving the full path
        (host DMA → frame store → SDI serializer → cable → SDI
        deserializer → frame store → host DMA) delivered real video.
        """
        card = loopback_card.card

        configure_playout(card, VIDEO_FORMAT)
        configure_capture(card, VIDEO_FORMAT)
        card.set_reference(ReferenceSource.FREERUN)
        apply_loopback_routes(card)

        # Playout buffer: fill with 0x80 (valid YCbCr neutral gray).
        _out_mm, out_buf = loopback_card.alloc_buffer(FRAME_BYTES)
        out_buf[:] = 0x80

        # Capture buffer: leave as zeros so any change proves DMA worked.
        _cap_mm, cap_buf = loopback_card.alloc_buffer(FRAME_BYTES)
        assert np.all(cap_buf == 0), "capture buffer should start zeroed"

        stop_pair(card)

        card.autocirculate_init_for_output(PLAYOUT_CH)
        card.autocirculate_init_for_input(CAPTURE_CH)

        out_xfer = Transfer()
        out_xfer.set_video_buffer(out_buf)
        cap_xfer = Transfer()
        cap_xfer.set_video_buffer(cap_buf)

        card.autocirculate_start(PLAYOUT_CH)
        card.autocirculate_start(CAPTURE_CH)

        for _ in range(PRIME_FRAMES):
            status = card.autocirculate_get_status(PLAYOUT_CH)
            if status.can_accept_more_output_frames:
                card.autocirculate_transfer(PLAYOUT_CH, out_xfer)
            card.wait_for_input_vertical_interrupt(PLAYOUT_CH)

        for _ in range(SETTLE_VBIS):
            card.wait_for_input_vertical_interrupt(CAPTURE_CH)

        cap_status = card.autocirculate_get_status(CAPTURE_CH)
        assert cap_status.has_available_input_frame, "no frame available to capture"
        card.autocirculate_transfer(CAPTURE_CH, cap_xfer)

        nonzero_ratio = np.count_nonzero(cap_buf[:FRAME_BYTES]) / FRAME_BYTES
        assert nonzero_ratio > 0.5, (
            f"captured frame is mostly zeros ({nonzero_ratio:.1%} non-zero) "
            f"— SDI loopback path may not be delivering data"
        )
