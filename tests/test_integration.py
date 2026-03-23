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

import mmap
import os

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


def _page_aligned_buffer(size: int) -> tuple[mmap.mmap, np.ndarray]:
    """Allocate a page-aligned numpy buffer backed by anonymous mmap.

    Returns (backing_mmap, numpy_view).  Keep the mmap alive for the
    lifetime of the numpy array.
    """
    backing = mmap.mmap(-1, size)
    return backing, np.frombuffer(backing, dtype=np.uint8)

pytestmark = pytest.mark.hardware

# ── Constants ────────────────────────────────────────────────────────

VIDEO_FORMAT = VideoFormat.FORMAT_1080i_5994
PIXEL_FORMAT = PixelFormat.FBF_10BIT_YCBCR  # native SDI, no CSC needed
FRAME_BYTES = get_frame_bytes(VIDEO_FORMAT, PIXEL_FORMAT)
MAX_FRAME_BYTES = 3840 * 2160 * 4  # conservative upper-bound for any format
PASSTHROUGH_FRAMES = 300  # ~10 s at 59.94 fps interlaced

PLAYOUT_CH = Channel.CH3
CAPTURE_CH = Channel.CH4
PLAYOUT_DEST = OutputDest.SDI3
CAPTURE_SRC = InputSource.SDI4

_NTV2_OEM_TASKS = 2
_APP_SIG = 0x54455354  # NTV2_FOURCC('T','E','S','T')

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
    locked_bufs: list[np.ndarray] = []
    backings: list[mmap.mmap] = []
    try:
        with Card(device_index=0) as card:
            # Acquire ownership and set OEM task mode
            card.acquire_stream_for_application(_APP_SIG, os.getpid())
            card.set_every_frame_services(_NTV2_OEM_TASKS)

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

            try:
                # -- start playout and push a blank frame --
                card.autocirculate_stop(PLAYOUT_CH, abort=True)
                card.autocirculate_stop(CAPTURE_CH, abort=True)
                card.autocirculate_init_for_output(PLAYOUT_CH)
                card.autocirculate_start(PLAYOUT_CH)

                blank_mm, blank = _page_aligned_buffer(MAX_FRAME_BYTES)
                backings.append(blank_mm)
                card.dma_buffer_lock(blank)
                locked_bufs.append(blank)
                out_xfer = Transfer()
                out_xfer.set_video_buffer(blank)
                card.wait_for_input_vertical_interrupt(PLAYOUT_CH)
                card.autocirculate_transfer(PLAYOUT_CH, out_xfer)

                # -- start capture and wait for a frame --
                card.autocirculate_init_for_input(CAPTURE_CH)
                card.autocirculate_start(CAPTURE_CH)

                got_frame = False
                for _ in range(30):
                    card.wait_for_input_vertical_interrupt(CAPTURE_CH)
                    status = card.autocirculate_get_status(CAPTURE_CH)
                    if status.has_available_input_frame:
                        got_frame = True
                        break

                if not got_frame:
                    return False

                # -- attempt the actual capture DMA transfer --
                cap_mm, cap_buf = _page_aligned_buffer(MAX_FRAME_BYTES)
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


_CAPTURE_DMA_WORKS = _probe_capture_dma()

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


class TestCpuLoopback:
    """Playout a known pattern on CH3, capture on CH4, compare byte-for-byte."""

    @pytest.mark.parametrize("pattern", ["zeros", "ramp", "0xAA", "0x55"])
    def test_data_integrity(self, card: Card, pattern: str) -> None:
        _configure_playout(card)
        _configure_capture(card)
        _set_reference(card)
        _apply_loopback_routes(card)

        out_mm, out_buf = _page_aligned_buffer(MAX_FRAME_BYTES)
        cap_mm, cap_buf = _page_aligned_buffer(MAX_FRAME_BYTES)
        _fill_pattern(out_buf, pattern)
        # Keep a copy for comparison — capture overwrites cap_buf.
        expected = out_buf.copy()

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

            np.testing.assert_array_equal(
                cap_buf[:FRAME_BYTES], expected[:FRAME_BYTES]
            )
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

        buf_mm, buf = _page_aligned_buffer(MAX_FRAME_BYTES)
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

    @pytest.mark.parametrize("pattern", ["zeros", "ramp", "0xAA", "0x55"])
    def test_data_integrity(self, card: Card, pattern: str) -> None:
        import cupy as cp

        _configure_playout(card)
        _configure_capture(card)
        _set_reference(card)
        _apply_loopback_routes(card)

        # Build pattern on CPU then transfer to GPU.
        cpu_mm, cpu_pattern = _page_aligned_buffer(MAX_FRAME_BYTES)
        _fill_pattern(cpu_pattern, pattern)
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

            cp.testing.assert_array_equal(
                cap_buf[:FRAME_BYTES], out_buf[:FRAME_BYTES]
            )
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
