"""Integration tests for pydecklink — require DeckLink hardware.

Run with: pytest -m hardware tests/test_decklink_integration.py

Requires:
- At least two DeckLink sub-devices (or two cards).
- Device 0 (SDI 1) output connected to device 2 (SDI 2) input via SDI cable (loopback).

Tests verify the full path: host → DeckLink output → SDI cable →
DeckLink input → host.
"""

from __future__ import annotations

import contextlib
import ctypes

import numpy as np
import pytest

import pydecklink

_HAS_SDK = getattr(pydecklink, "HAS_SDK", False)

pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers"),
]

# -- Constants ----------------------------------------------------------------
# Deferred to avoid AttributeError when built without SDK headers.

if _HAS_SDK:
    MODE = pydecklink.DisplayMode.HD1080p25
    PIXEL_FORMAT = pydecklink.PixelFormat.Format8BitYUV
    WIDTH = pydecklink.get_mode_width(MODE)
    HEIGHT = pydecklink.get_mode_height(MODE)
    FRAME_BYTES = pydecklink.get_frame_bytes(MODE, PIXEL_FORMAT)
    ROW_BYTES = FRAME_BYTES // HEIGHT
    FPS = pydecklink.get_mode_fps(MODE)
    TIMESCALE = 10_000_000
    FRAME_DURATION = round(TIMESCALE / FPS)
else:
    # Placeholders so the module parses without errors during collection.
    MODE = None  # type: ignore[assignment]
    PIXEL_FORMAT = None  # type: ignore[assignment]
    WIDTH = HEIGHT = FRAME_BYTES = ROW_BYTES = 0
    FPS = 0.0
    TIMESCALE = FRAME_DURATION = 0


# -- Fixtures -----------------------------------------------------------------


@pytest.fixture()
def output_device():
    """Open DeckLink device 0 for output."""
    dev = pydecklink.Device(index=0)
    yield dev


@pytest.fixture()
def input_device():
    """Open DeckLink device 2 (SDI 2) for input."""
    dev = pydecklink.Device(index=2)
    yield dev


@pytest.fixture()
def loopback_pair(output_device, input_device):
    """Configure a playout → capture loopback pair.

    Device 0 (SDI 1) outputs; device 2 (SDI 2) captures.
    Tears down on exit.
    """
    output_device.enable_video_output(MODE)
    input_device.enable_video_input(MODE, PIXEL_FORMAT)
    input_device.start_streams()
    yield output_device, input_device
    # Teardown
    with contextlib.suppress(RuntimeError):
        output_device.stop_scheduled_playback()
    with contextlib.suppress(RuntimeError):
        input_device.stop_streams()
    with contextlib.suppress(RuntimeError):
        input_device.disable_video_input()
    with contextlib.suppress(RuntimeError):
        output_device.disable_video_output()


# -- Signal Detection ---------------------------------------------------------


class TestSignalDetection:
    """Verify format detection resolves the correct mode."""

    def test_detects_known_signal(self, loopback_pair):
        """Output a known mode, verify input detects it."""
        out_dev, in_dev = loopback_pair

        # Schedule a few frames to establish a signal.
        out_dev.create_frame_pool(8, WIDTH, HEIGHT, ROW_BYTES, PIXEL_FORMAT)
        for i in range(5):
            mf = out_dev.acquire_output_frame(timeout_ms=1000)
            mf.data[:] = 0x80  # Valid YCbCr neutral gray.
            out_dev.schedule_output_frame(
                mf,
                display_time=i * FRAME_DURATION,
                duration=FRAME_DURATION,
                timescale=TIMESCALE,
            )
        out_dev.start_scheduled_playback(start_time=0, timescale=TIMESCALE)

        # Wait for input to receive frames.
        frame = None
        for _ in range(20):
            frame = in_dev.pop_capture_frame(timeout_ms=500)
            if frame is not None and frame.has_signal:
                break

        assert frame is not None, "No frame captured — SDI loopback cable connected?"
        assert frame.has_signal, "Captured frame has no input signal"
        assert frame.width == WIDTH
        assert frame.height == HEIGHT


# -- Loopback Data Integrity --------------------------------------------------


class TestLoopbackIntegrity:
    """Playout a known pattern, capture it back, verify non-trivial data."""

    def test_captured_frame_is_not_empty(self, loopback_pair):
        """SDI loopback delivers real video data, not zeros.

        SDI transport inserts timing references in blanking, so
        byte-exact comparison against the sent pattern is not
        meaningful. Instead, assert the captured frame has substantial
        non-zero content.
        """
        out_dev, in_dev = loopback_pair

        # Schedule enough frames for the pipeline to stabilize.
        preroll = 8
        out_dev.create_frame_pool(preroll + 5, WIDTH, HEIGHT, ROW_BYTES, PIXEL_FORMAT)

        def schedule_pattern(display_time: int) -> None:
            mf = out_dev.acquire_output_frame(timeout_ms=1000)
            mf.data[:] = 0x80  # Valid YCbCr neutral gray.
            out_dev.schedule_output_frame(
                mf,
                display_time=display_time,
                duration=FRAME_DURATION,
                timescale=TIMESCALE,
            )

        for i in range(preroll):
            schedule_pattern(i * FRAME_DURATION)
        out_dev.start_scheduled_playback(start_time=0, timescale=TIMESCALE)

        # Drain a few frames to let the pipeline settle.
        for _ in range(5):
            in_dev.pop_capture_frame(timeout_ms=1000)

        # Continue scheduling so output doesn't underrun.
        display_time = preroll * FRAME_DURATION
        for _ in range(5):
            schedule_pattern(display_time)
            display_time += FRAME_DURATION

        # Capture a settled frame.
        frame = in_dev.pop_capture_frame(timeout_ms=2000)
        assert frame is not None, "No frame captured after settling"
        assert frame.has_signal, "Captured frame reports no signal"

        data = np.array(frame.data)
        nonzero_ratio = np.count_nonzero(data) / len(data)
        assert nonzero_ratio > 0.5, (
            f"Captured frame is mostly zeros ({nonzero_ratio:.1%} non-zero). "
            f"SDI loopback path may not be delivering data."
        )


# -- Sustained Streaming (Passthrough) ----------------------------------------


class TestPassthroughStreaming:
    """Run N frames through playout → capture, assert zero drops."""

    def test_sustained_streaming_no_drops(self, loopback_pair):
        """Stream frames for a sustained period. Verify no drops or late frames."""
        out_dev, in_dev = loopback_pair

        target_frames = 50  # ~2 seconds at 25 fps
        # Pool sized for preroll plus a few frames in flight. Preroll is
        # deeper than minimum so SDI sync has time to lock before the
        # output underruns: 15 frames = 600 ms at 25 fps.
        preroll = 15
        pool_size = preroll + 5

        out_dev.create_frame_pool(pool_size, WIDTH, HEIGHT, ROW_BYTES, PIXEL_FORMAT)

        def schedule_pattern(display_time: int) -> None:
            mf = out_dev.acquire_output_frame(timeout_ms=1000)
            mf.data[:] = 0x80  # Valid YCbCr neutral gray.
            out_dev.schedule_output_frame(
                mf,
                display_time=display_time,
                duration=FRAME_DURATION,
                timescale=TIMESCALE,
            )

        # Pre-roll output.
        for i in range(preroll):
            schedule_pattern(i * FRAME_DURATION)
        out_dev.start_scheduled_playback(start_time=0, timescale=TIMESCALE)
        display_time = preroll * FRAME_DURATION

        # The input stream was started in the fixture before output had
        # any data, so the input queue may be backed up with no-signal
        # frames. Drain them without scheduling more output — the
        # pre-roll above keeps the output fed during this drain.
        signal_acquired = False
        for _ in range(200):
            frame = in_dev.pop_capture_frame(timeout_ms=1000)
            if frame is not None and frame.has_signal:
                signal_acquired = True
                break

        assert signal_acquired, "Input never acquired SDI signal from output"

        captured = 1  # The acquisition frame above counts.
        consecutive_no_signal = 0

        for _ in range(target_frames + 20):  # Allow extra attempts.
            frame = in_dev.pop_capture_frame(timeout_ms=1000)
            if frame is None:
                continue
            if not frame.has_signal:
                consecutive_no_signal += 1
                if consecutive_no_signal > 5:
                    pytest.fail("Lost signal during streaming")
                continue
            consecutive_no_signal = 0

            captured += 1

            schedule_pattern(display_time)
            display_time += FRAME_DURATION

            if captured >= target_frames:
                break

        assert captured >= target_frames, (
            f"Only captured {captured}/{target_frames} frames"
        )

        status = out_dev.output_status
        assert status.dropped == 0, f"Output dropped {status.dropped} frames"
        assert status.late == 0, f"Output had {status.late} late frames"
        assert not status.underrun, "Output underran during streaming"


# -- Custom Allocator + Zero-Copy + Signal-Locked Capture --------------------


class TestCustomAllocatorZeroCopy:
    """Exercise the custom-allocator + zero-copy + signal-locked path.

    This is the configuration the original stall regressed under: a
    Python-callback allocator (cudaHostAlloc, libc.malloc through
    ctypes, anything that takes the GIL) combined with zero-copy
    delivery, under sustained signal-locked load. The SDK input
    pipeline calls ``AllocateVideoBuffer`` mid-stream when its
    auto-pool runs short; without ``prefill`` to seat buffers on the
    free-list, that call hits the SLOW path on the SDK input thread,
    blocks on the GIL, and the pipeline stalls.

    The test asserts three invariants:

    * **Frames are delivered.** The original bug stalled within the
      first signal-locked frame; a non-zero capture count proves the
      input thread didn't lock up.
    * **The free-list recycles.** ``recycled_count`` should climb
      steadily — every consumer-released wrapper returns its
      ``ManagedBuffer`` to the free-list, and the SDK's next
      ``AllocateVideoBuffer`` pops it back FAST. ``recycled_count > 0``
      proves the cycle is closed.
    * **The pool doesn't grow during streaming.** ``allocated_count``
      should stay flat after the prefill; any growth means the SLOW
      path ran on the SDK thread, which is the failure mode this test
      guards against.

    Uses ``libc.malloc`` / ``libc.free`` via ctypes as a stand-in for
    a real pinning allocator. Faster than ``cudaHostAlloc`` but
    exhibits the same threading/GIL characteristics — the original
    stall reproduced identically with both, so this avoids a CUDA
    dependency in the test suite while still exercising the failure
    mode.
    """

    def test_zero_copy_streams_with_custom_allocator(self, output_device, input_device):
        """Stream signal-locked frames through a custom allocator,
        verify recycle behavior."""
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc.restype = ctypes.c_void_p
        libc.malloc.argtypes = [ctypes.c_size_t]
        libc.free.argtypes = [ctypes.c_void_p]

        def py_alloc(size: int) -> int:
            ptr = libc.malloc(size)
            if not ptr:
                raise MemoryError("libc.malloc returned NULL")
            return ptr

        def py_free(ptr: int, _size: int) -> None:
            libc.free(ctypes.c_void_p(ptr))

        provider = pydecklink.VideoBufferAllocatorProvider(
            alloc=py_alloc,
            free=py_free,
        )

        # Set up output side (provides the SDI signal we'll capture back).
        output_device.enable_video_output(MODE)
        preroll = 15
        output_device.create_frame_pool(
            preroll + 5, WIDTH, HEIGHT, ROW_BYTES, PIXEL_FORMAT
        )

        def schedule_pattern(display_time: int) -> None:
            mf = output_device.acquire_output_frame(timeout_ms=1000)
            mf.data[:] = 0x80
            output_device.schedule_output_frame(
                mf,
                display_time=display_time,
                duration=FRAME_DURATION,
                timescale=TIMESCALE,
            )

        # Set up input side with the custom allocator.
        input_device.enable_video_input_with_allocator(
            mode=MODE,
            pixel_format=PIXEL_FORMAT,
            flags=pydecklink.VideoInputFlag(0),
            allocator_provider=provider,
            zero_copy=True,
            input_queue_depth=1,
        )

        # Prefill before start_streams so the SDK input thread never
        # hits the SLOW path under signal-locked load.
        in_alloc = provider.get_allocator(
            buffer_size=FRAME_BYTES,
            width=WIDTH,
            height=HEIGHT,
            row_bytes=ROW_BYTES,
            pixel_format=PIXEL_FORMAT,
        )
        in_alloc.prefill(4)
        allocated_after_prefill = in_alloc.allocated_count

        try:
            input_device.start_streams()

            # Pre-roll output and start playback.
            for i in range(preroll):
                schedule_pattern(i * FRAME_DURATION)
            output_device.start_scheduled_playback(start_time=0, timescale=TIMESCALE)
            display_time = preroll * FRAME_DURATION

            # Drain no-signal frames until signal locks.
            signal_acquired = False
            for _ in range(200):
                f = input_device.pop_capture_frame_ref(timeout_ms=1000)
                if f is not None and f.has_signal:
                    signal_acquired = True
                    break

            assert signal_acquired, (
                "Input never acquired signal — SDI loopback cable connected?"
            )

            # Stream signal-locked frames. The capture count is the
            # core "did the SDK input thread stall?" signal.
            target = 30
            captured = 1  # the acquisition frame counts
            for _ in range(target + 30):
                f = input_device.pop_capture_frame_ref(timeout_ms=1000)
                if f is None or not f.has_signal:
                    continue
                captured += 1
                schedule_pattern(display_time)
                display_time += FRAME_DURATION
                if captured >= target:
                    break

            assert captured >= target, (
                f"Only captured {captured}/{target} signal-locked frames "
                f"with custom allocator — input thread may be stalling"
            )
            assert in_alloc.recycled_count > 0, (
                f"recycled_count={in_alloc.recycled_count} after streaming "
                f"{captured} frames — buffers are not being returned to the "
                f"free-list, recycling path is broken"
            )
            assert in_alloc.allocated_count == allocated_after_prefill, (
                f"allocated_count grew from {allocated_after_prefill} to "
                f"{in_alloc.allocated_count} during streaming — the SDK "
                f"input thread hit the SLOW (Python callback) path, which "
                f"means prefill was insufficient or the recycle path is "
                f"broken"
            )
        finally:
            with contextlib.suppress(RuntimeError):
                output_device.stop_scheduled_playback()
            with contextlib.suppress(RuntimeError):
                input_device.stop_streams()
            with contextlib.suppress(RuntimeError):
                input_device.disable_video_input()
            with contextlib.suppress(RuntimeError):
                output_device.disable_video_output()
