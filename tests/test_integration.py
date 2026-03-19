"""Integration tests — require AJA hardware with CH3↔CH4 SDI loopback cable.

Run with: pytest -m hardware tests/test_integration.py

Requires sufficient Linux capabilities for capture DMA (card→host).
The devcontainer's runArgs include --cap-add=SYS_RAWIO and
--cap-add=SYS_ADMIN; if running outside the devcontainer, ensure the
capabilities are granted or tests will skip.

Background on the DMA probe
---------------------------
The NTV2 driver distinguishes output DMA (host→card) from input DMA
(card→host).  Output DMA works with CAP_SYS_RAWIO alone.  Input DMA
(capture) may require additional capabilities (CAP_SYS_ADMIN or
--privileged), depending on the host kernel and driver version.

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

pytestmark = pytest.mark.hardware

# ── Constants ────────────────────────────────────────────────────────

VIDEO_FORMAT = VideoFormat.FORMAT_1080i_5994
PIXEL_FORMAT = PixelFormat.FBF_10BIT_YCBCR  # native SDI, no CSC needed
MAX_FRAME_BYTES = 3840 * 2160 * 4  # conservative upper-bound for any format
PASSTHROUGH_FRAMES = 300  # ~10 s at 59.94 fps interlaced

PLAYOUT_CH = Channel.CH3
CAPTURE_CH = Channel.CH4
PLAYOUT_DEST = OutputDest.SDI3
CAPTURE_SRC = InputSource.SDI4

# Number of frames to push through the ring buffer before capturing,
# ensuring the loopback cable has carried at least one full frame.
_PRIME_FRAMES = 10
# VBI waits after priming to let the captured frame land.
_SETTLE_VBIS = 5


# ── Capture DMA capability probe ────────────────────────────────────


def _probe_capture_dma() -> bool:
    """Return True if capture DMA works on the loopback pair.

    Uses the full CH3→SDI3→SDI4→CH4 loopback path so that signal
    routing and video reference are valid.  Without routing, input VBI
    interrupts never fire and AutoCirculate cannot advance past the
    STARTING state.
    """
    try:
        with Card(device_index=0) as card:
            # -- playout side (CH3 → SDI3) --
            card.set_sdi_transmit_enable(PLAYOUT_CH, True)
            card.enable_channel(PLAYOUT_CH)
            card.set_mode(PLAYOUT_CH, Mode.DISPLAY)
            card.set_video_format(VIDEO_FORMAT, channel=PLAYOUT_CH)
            card.set_frame_buffer_format(PLAYOUT_CH, PIXEL_FORMAT)

            # -- capture side (SDI4 → CH4) --
            card.set_sdi_transmit_enable(CAPTURE_CH, False)
            card.enable_channel(CAPTURE_CH)
            card.set_mode(CAPTURE_CH, Mode.CAPTURE)
            card.set_video_format(VIDEO_FORMAT, channel=CAPTURE_CH)
            card.set_frame_buffer_format(CAPTURE_CH, PIXEL_FORMAT)

            # -- routing --
            card.set_reference(ReferenceSource.FREERUN)
            card.clear_routing()
            out_routes = route_playout(PLAYOUT_CH, PLAYOUT_DEST, PIXEL_FORMAT)
            cap_routes = route_capture(CAPTURE_SRC, CAPTURE_CH, PIXEL_FORMAT)
            card.apply_signal_route(out_routes, replace=False)
            card.apply_signal_route(cap_routes, replace=False)

            # -- start playout and push a blank frame --
            card.autocirculate_stop(PLAYOUT_CH, abort=True)
            card.autocirculate_stop(CAPTURE_CH, abort=True)
            card.autocirculate_init_for_output(PLAYOUT_CH, frame_count=2)
            card.autocirculate_start(PLAYOUT_CH)

            blank = np.zeros(MAX_FRAME_BYTES, dtype=np.uint8)
            out_xfer = Transfer()
            out_xfer.set_video_buffer(blank)
            card.wait_for_input_vertical_interrupt(PLAYOUT_CH)
            card.autocirculate_transfer(PLAYOUT_CH, out_xfer)

            # -- start capture and wait for a frame --
            card.autocirculate_init_for_input(CAPTURE_CH, frame_count=2)
            card.autocirculate_start(CAPTURE_CH)

            for _ in range(30):
                card.wait_for_input_vertical_interrupt(CAPTURE_CH)
                status = card.autocirculate_get_status(CAPTURE_CH)
                if status.has_available_input_frame:
                    break
            else:
                return False  # AutoCirculate never produced a frame

            # -- attempt the actual capture DMA transfer --
            cap_buf = np.zeros(MAX_FRAME_BYTES, dtype=np.uint8)
            cap_xfer = Transfer()
            cap_xfer.set_video_buffer(cap_buf)
            card.autocirculate_transfer(CAPTURE_CH, cap_xfer)

            card.autocirculate_stop(PLAYOUT_CH, abort=True)
            card.autocirculate_stop(CAPTURE_CH, abort=True)
            card.clear_routing()
            return True
    except RuntimeError:
        return False


_CAPTURE_DMA_WORKS = _probe_capture_dma()

if not _CAPTURE_DMA_WORKS:
    pytestmark = [
        pytest.mark.hardware,
        pytest.mark.skip(
            reason=(
                "capture DMA probe failed — container likely needs "
                "--cap-add=SYS_RAWIO --cap-add=SYS_ADMIN (or --privileged)"
            )
        ),
    ]


# ── Helpers ──────────────────────────────────────────────────────────


def _configure_playout(card: Card) -> None:
    """Set up CH3 for playout over SDI3."""
    card.set_sdi_transmit_enable(PLAYOUT_CH, True)
    card.enable_channel(PLAYOUT_CH)
    card.set_mode(PLAYOUT_CH, Mode.DISPLAY)
    card.set_video_format(VIDEO_FORMAT, channel=PLAYOUT_CH)
    card.set_frame_buffer_format(PLAYOUT_CH, PIXEL_FORMAT)


def _configure_capture(card: Card) -> None:
    """Set up CH4 for capture from SDI4."""
    card.set_sdi_transmit_enable(CAPTURE_CH, False)
    card.enable_channel(CAPTURE_CH)
    card.set_mode(CAPTURE_CH, Mode.CAPTURE)
    card.set_video_format(VIDEO_FORMAT, channel=CAPTURE_CH)
    card.set_frame_buffer_format(CAPTURE_CH, PIXEL_FORMAT)


def _apply_loopback_routes(card: Card) -> None:
    """Route CH3 playout → SDI3 cable → SDI4 → CH4 capture."""
    card.clear_routing()
    out_routes = route_playout(PLAYOUT_CH, PLAYOUT_DEST, PIXEL_FORMAT)
    cap_routes = route_capture(CAPTURE_SRC, CAPTURE_CH, PIXEL_FORMAT)
    card.apply_signal_route(out_routes, replace=False)
    card.apply_signal_route(cap_routes, replace=False)


def _stop_pair(card: Card) -> None:
    """Stop autocirculate on both loopback channels."""
    card.autocirculate_stop(PLAYOUT_CH, abort=True)
    card.autocirculate_stop(CAPTURE_CH, abort=True)


def _set_reference(card: Card) -> None:
    card.set_reference(ReferenceSource.FREERUN)


# ── CPU Loopback ─────────────────────────────────────────────────────


def _make_cpu_pattern(name: str, size: int) -> np.ndarray:
    """Generate a named test pattern as a numpy uint8 array."""
    if name == "zeros":
        return np.zeros(size, dtype=np.uint8)
    if name == "ramp":
        return np.arange(size, dtype=np.uint8)  # wraps at 256
    if name == "random":
        return np.random.default_rng(seed=42).integers(
            0, 256, size=size, dtype=np.uint8
        )
    if name == "0xAA":
        return np.full(size, 0xAA, dtype=np.uint8)
    if name == "0x55":
        return np.full(size, 0x55, dtype=np.uint8)
    msg = f"unknown pattern: {name}"
    raise ValueError(msg)


class TestCpuLoopback:
    """Playout a known pattern on CH3, capture on CH4, compare byte-for-byte."""

    @pytest.mark.parametrize("pattern", ["zeros", "ramp", "random", "0xAA", "0x55"])
    def test_data_integrity(self, card: Card, pattern: str) -> None:
        _configure_playout(card)
        _configure_capture(card)
        _set_reference(card)
        _apply_loopback_routes(card)

        out_buf = _make_cpu_pattern(pattern, MAX_FRAME_BYTES)
        cap_buf = np.zeros(MAX_FRAME_BYTES, dtype=np.uint8)

        card.dma_buffer_lock(out_buf)
        card.dma_buffer_lock(cap_buf)

        try:
            _stop_pair(card)

            card.autocirculate_init_for_output(PLAYOUT_CH)
            card.autocirculate_init_for_input(CAPTURE_CH)

            out_xfer = Transfer()
            out_xfer.set_video_buffer(out_buf)
            cap_xfer = Transfer()
            cap_xfer.set_video_buffer(cap_buf)

            card.autocirculate_start(PLAYOUT_CH)
            card.autocirculate_start(CAPTURE_CH)

            # Prime: push pattern frames into the playout ring buffer.
            for _ in range(_PRIME_FRAMES):
                status = card.autocirculate_get_status(PLAYOUT_CH)
                if status.can_accept_more_output_frames:
                    card.autocirculate_transfer(PLAYOUT_CH, out_xfer)
                card.wait_for_input_vertical_interrupt(PLAYOUT_CH)

            # Settle: let frames propagate through loopback cable.
            for _ in range(_SETTLE_VBIS):
                card.wait_for_input_vertical_interrupt(CAPTURE_CH)

            # Capture one frame.
            cap_status = card.autocirculate_get_status(CAPTURE_CH)
            assert cap_status.has_available_input_frame, "no frame available to capture"
            card.autocirculate_transfer(CAPTURE_CH, cap_xfer)

            np.testing.assert_array_equal(cap_buf, out_buf)
        finally:
            _stop_pair(card)
            card.dma_buffer_unlock(out_buf)
            card.dma_buffer_unlock(cap_buf)
            card.clear_routing()


# ── CPU Passthrough ──────────────────────────────────────────────────


class TestCpuPassthrough:
    """Sustained capture→playout loop over CPU memory. Assert zero drops."""

    def test_zero_dropped_frames(self, card: Card) -> None:
        _configure_playout(card)
        _configure_capture(card)
        _set_reference(card)
        _apply_loopback_routes(card)

        buf = np.zeros(MAX_FRAME_BYTES, dtype=np.uint8)
        card.dma_buffer_lock(buf)

        cap_xfer = Transfer()
        cap_xfer.set_video_buffer(buf)
        out_xfer = Transfer()
        out_xfer.set_video_buffer(buf)

        try:
            _stop_pair(card)

            card.autocirculate_init_for_output(PLAYOUT_CH)
            card.autocirculate_init_for_input(CAPTURE_CH)
            card.autocirculate_start(PLAYOUT_CH)
            card.autocirculate_start(CAPTURE_CH)

            # Bootstrap: push dummy frames so loopback cable carries signal.
            for _ in range(_PRIME_FRAMES):
                status = card.autocirculate_get_status(PLAYOUT_CH)
                if status.can_accept_more_output_frames:
                    card.autocirculate_transfer(PLAYOUT_CH, out_xfer)
                card.wait_for_input_vertical_interrupt(PLAYOUT_CH)

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
            assert cap_status.dropped_frame_count == 0, (
                f"capture dropped {cap_status.dropped_frame_count} frames"
            )
            assert out_status.dropped_frame_count == 0, (
                f"playout dropped {out_status.dropped_frame_count} frames"
            )
        finally:
            _stop_pair(card)
            card.dma_buffer_unlock(buf)
            card.clear_routing()


# ── GPU Loopback ─────────────────────────────────────────────────────


class TestGpuLoopback:
    """GPU variant of loopback: CuPy buffers with RDMA."""

    @pytest.fixture(autouse=True)
    def _require_cupy(self):
        pytest.importorskip("cupy")

    @pytest.mark.parametrize("pattern", ["zeros", "ramp", "random", "0xAA", "0x55"])
    def test_data_integrity(self, card: Card, pattern: str) -> None:
        import cupy as cp

        _configure_playout(card)
        _configure_capture(card)
        _set_reference(card)
        _apply_loopback_routes(card)

        # Build pattern on CPU then transfer to GPU.
        cpu_pattern = _make_cpu_pattern(pattern, MAX_FRAME_BYTES)
        out_buf = cp.asarray(cpu_pattern)
        cap_buf = cp.zeros(MAX_FRAME_BYTES, dtype=cp.uint8)

        card.dma_buffer_lock(out_buf)
        card.dma_buffer_lock(cap_buf)

        try:
            _stop_pair(card)

            card.autocirculate_init_for_output(PLAYOUT_CH)
            card.autocirculate_init_for_input(CAPTURE_CH)

            out_xfer = Transfer()
            out_xfer.set_video_buffer(out_buf)
            cap_xfer = Transfer()
            cap_xfer.set_video_buffer(cap_buf)

            card.autocirculate_start(PLAYOUT_CH)
            card.autocirculate_start(CAPTURE_CH)

            for _ in range(_PRIME_FRAMES):
                status = card.autocirculate_get_status(PLAYOUT_CH)
                if status.can_accept_more_output_frames:
                    card.autocirculate_transfer(PLAYOUT_CH, out_xfer)
                card.wait_for_input_vertical_interrupt(PLAYOUT_CH)

            for _ in range(_SETTLE_VBIS):
                card.wait_for_input_vertical_interrupt(CAPTURE_CH)

            cap_status = card.autocirculate_get_status(CAPTURE_CH)
            assert cap_status.has_available_input_frame, "no frame available to capture"
            card.autocirculate_transfer(CAPTURE_CH, cap_xfer)

            cp.testing.assert_array_equal(cap_buf, out_buf)
        finally:
            _stop_pair(card)
            card.dma_buffer_unlock(out_buf)
            card.dma_buffer_unlock(cap_buf)
            card.clear_routing()


# ── GPU Passthrough ──────────────────────────────────────────────────


class TestGpuPassthrough:
    """GPU variant of passthrough: CuPy buffers with RDMA both directions."""

    @pytest.fixture(autouse=True)
    def _require_cupy(self):
        pytest.importorskip("cupy")

    def test_zero_dropped_frames(self, card: Card) -> None:
        import cupy as cp

        _configure_playout(card)
        _configure_capture(card)
        _set_reference(card)
        _apply_loopback_routes(card)

        buf = cp.zeros(MAX_FRAME_BYTES, dtype=cp.uint8)
        card.dma_buffer_lock(buf)

        cap_xfer = Transfer()
        cap_xfer.set_video_buffer(buf)
        out_xfer = Transfer()
        out_xfer.set_video_buffer(buf)

        try:
            _stop_pair(card)

            card.autocirculate_init_for_output(PLAYOUT_CH)
            card.autocirculate_init_for_input(CAPTURE_CH)
            card.autocirculate_start(PLAYOUT_CH)
            card.autocirculate_start(CAPTURE_CH)

            for _ in range(_PRIME_FRAMES):
                status = card.autocirculate_get_status(PLAYOUT_CH)
                if status.can_accept_more_output_frames:
                    card.autocirculate_transfer(PLAYOUT_CH, out_xfer)
                card.wait_for_input_vertical_interrupt(PLAYOUT_CH)

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
            assert cap_status.dropped_frame_count == 0, (
                f"capture dropped {cap_status.dropped_frame_count} frames"
            )
            assert out_status.dropped_frame_count == 0, (
                f"playout dropped {out_status.dropped_frame_count} frames"
            )
        finally:
            _stop_pair(card)
            card.dma_buffer_unlock(buf)
            card.clear_routing()
