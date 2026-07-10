"""Integration tests for pydecklink — require DeckLink hardware.

Run with: pytest -m hardware tests/test_decklink_integration.py

Requires an SDI loopback: a DeckLink output connected back to a DeckLink
input by an SDI cable. Two topologies are supported:

- Single full-duplex device (e.g. UltraStudio 4K Mini): loop the device's
  SDI OUT to its own SDI IN. This is the default — output and input both
  resolve to device index 0.
- Multi-sub-device card or two cards: play out on one sub-device, capture
  on another. Set ``PYDECKLINK_LOOPBACK_OUTPUT`` / ``PYDECKLINK_LOOPBACK_INPUT``
  to the indices matching the physical cabling.

The output is forced to 4:2:2 YCbCr so the SDI wire carries the 8-bit YUV
we generate; a fixed-mode YUV input then matches the wire and captures a
faithful round-trip. Tests verify the full path: host → DeckLink output →
SDI cable → DeckLink input → host. When no signal reaches the input
(cable absent or wired to a different port), the affected tests skip
rather than fail.
"""

from __future__ import annotations

import contextlib
import ctypes
import ctypes.util
import os

import numpy as np
import pytest

import pydecklink

_HAS_SDK = getattr(pydecklink, "HAS_SDK", False)

# Loopback endpoints. Default to single-device self-loopback (output and
# input on the same full-duplex device); override for multi-device rigs.
_OUTPUT_INDEX = int(os.environ.get("PYDECKLINK_LOOPBACK_OUTPUT", "0"))
_INPUT_INDEX = int(os.environ.get("PYDECKLINK_LOOPBACK_INPUT", str(_OUTPUT_INDEX)))

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


def _luma_band_frame() -> np.ndarray:
    """A UYVY frame with a bright top half and dark bottom half.

    Chroma neutral (0x80); luma 0xC0 in the top rows, 0x40 in the bottom.
    Distinctive enough that a faithful loopback recovers the spatial
    structure, and clear of the SMPTE reserved luma codes (0x00 / 0xFF).
    UYVY byte order is Cb Y Cr Y, so luma occupies the odd byte offsets.
    """
    frame = np.full((HEIGHT, ROW_BYTES), 0x80, dtype=np.uint8)  # neutral chroma
    frame[: HEIGHT // 2, 1::2] = 0xC0  # bright top
    frame[HEIGHT // 2 :, 1::2] = 0x40  # dark bottom
    return frame.reshape(-1)


# -- Fixtures -----------------------------------------------------------------


@pytest.fixture()
def output_device():
    """Open the loopback output device, forced to 4:2:2 YCbCr SDI output.

    Index from ``PYDECKLINK_LOOPBACK_OUTPUT`` (default 0). The SDI output
    is set to 4:2:2 (``Config444SDIVideoOutput`` = False) so the wire
    carries the 8-bit YUV we generate; left at its 4:4:4 RGB default the
    card would convert on the wire and the loopback would not be a
    faithful YUV round-trip. The original setting is restored on teardown.
    """
    if pydecklink.device_count() <= _OUTPUT_INDEX:
        pytest.skip(f"No DeckLink device at output index {_OUTPUT_INDEX}")
    dev = pydecklink.Device(index=_OUTPUT_INDEX)
    c444 = pydecklink.ConfigurationID.Config444SDIVideoOutput
    try:
        original_444 = dev.get_config_flag(c444)
        dev.set_config_flag(c444, False)
    except RuntimeError:
        original_444 = None  # Flag unsupported; use the device default.
    yield dev
    if original_444 is not None:
        with contextlib.suppress(RuntimeError):
            dev.set_config_flag(c444, original_444)


@pytest.fixture()
def input_device(output_device):
    """Open the loopback input device (``PYDECKLINK_LOOPBACK_INPUT``, default 0).

    On single-device self-loopback (input index == output index) the input
    shares the output's `Device` handle: two separate handles to the same
    full-duplex device do not route output → input, so the capture never
    locks. Distinct indices get their own handle.
    """
    if _INPUT_INDEX == _OUTPUT_INDEX:
        yield output_device
        return
    if pydecklink.device_count() <= _INPUT_INDEX:
        pytest.skip(f"No DeckLink device at input index {_INPUT_INDEX}")
    yield pydecklink.Device(index=_INPUT_INDEX)


def _teardown_loopback(output_device, input_device) -> None:
    for step in (
        output_device.stop_scheduled_playback,
        input_device.stop_streams,
        input_device.disable_video_input,
        output_device.disable_video_output,
    ):
        with contextlib.suppress(RuntimeError):
            step()


@pytest.fixture()
def loopback_pair(output_device, input_device):
    """Playout → capture loopback in fixed-mode 8-bit YUV.

    Output plays out; input captures the same signal over the SDI cable.
    With the output forced to 4:2:2 (see ``output_device``) the wire is
    8-bit YCbCr, so a fixed-mode YUV input matches it and locks — no
    format detection needed. Both endpoints default to the same
    full-duplex device (self-loopback); override the indices for
    multi-device rigs. Tears down on exit.
    """
    output_device.enable_video_output(MODE)
    input_device.enable_video_input(MODE, PIXEL_FORMAT)
    input_device.start_streams()
    yield output_device, input_device
    _teardown_loopback(output_device, input_device)


@pytest.fixture()
def loopback_detect(output_device, input_device):
    """Loopback with input format detection enabled (for the detection test)."""
    output_device.enable_video_output(MODE)
    input_device.enable_video_input(
        MODE, PIXEL_FORMAT, flags=pydecklink.VideoInputFlag.EnableFormatDetection.value
    )
    input_device.start_streams()
    yield output_device, input_device
    _teardown_loopback(output_device, input_device)


# -- Signal Detection ---------------------------------------------------------


class TestSignalDetection:
    """Verify format detection resolves the mode and format we output."""

    def test_detects_known_signal(self, loopback_detect):
        """Format detection reports the mode and pixel format we output."""
        out_dev, in_dev = loopback_detect

        out_dev.create_frame_pool(20, WIDTH, HEIGHT, ROW_BYTES, PIXEL_FORMAT)
        for i in range(15):
            mf = out_dev.acquire_output_frame(timeout_ms=1000)
            mf.data[:] = 0x80  # Valid YCbCr neutral gray.
            out_dev.schedule_output_frame(
                mf,
                display_time=i * FRAME_DURATION,
                duration=FRAME_DURATION,
                timescale=TIMESCALE,
            )
        out_dev.start_scheduled_playback(start_time=0, timescale=TIMESCALE)

        frame = None
        display_time = 15 * FRAME_DURATION
        for _ in range(60):
            frame = in_dev.pop_capture_frame(timeout_ms=1000)
            with contextlib.suppress(RuntimeError):
                mf = out_dev.acquire_output_frame(timeout_ms=50)
                mf.data[:] = 0x80
                out_dev.schedule_output_frame(
                    mf,
                    display_time=display_time,
                    duration=FRAME_DURATION,
                    timescale=TIMESCALE,
                )
                display_time += FRAME_DURATION
            if frame is not None and frame.has_signal:
                break

        if frame is None or not frame.has_signal:
            pytest.skip("No SDI signal on loopback input — check OUT→IN cabling")
        assert frame.width == WIDTH
        assert frame.height == HEIGHT
        # Detection must report what we actually output — 4:2:2 YCbCr at the
        # output mode — not a different colorspace or bit depth.
        fmt = in_dev.current_input_format
        assert fmt is not None
        assert fmt.mode == MODE
        assert fmt.pixel_format == PIXEL_FORMAT, (
            f"format detection reported {fmt.pixel_format}, expected "
            f"{PIXEL_FORMAT} for a 4:2:2 YCbCr output"
        )


# -- Loopback Data Integrity --------------------------------------------------


class TestLoopbackIntegrity:
    """Playout a known pattern, capture it back, verify it survives."""

    def test_loopback_reproduces_pattern(self, loopback_pair):
        """A known luma-band pattern survives the SDI loopback.

        Output a frame with a bright top half and dark bottom half (neutral
        chroma) and verify the captured frame reproduces that spatial
        structure. 4:2:2 YCbCr is bit-exact on the SDI wire, so a faithful
        loopback recovers the bands; a blank, garbled, or vertically
        misaligned capture does not.
        """
        out_dev, in_dev = loopback_pair
        pattern = _luma_band_frame()

        preroll = 15
        out_dev.create_frame_pool(preroll + 5, WIDTH, HEIGHT, ROW_BYTES, PIXEL_FORMAT)

        def schedule(display_time: int) -> None:
            mf = out_dev.acquire_output_frame(timeout_ms=1000)
            mf.data[:] = pattern
            out_dev.schedule_output_frame(
                mf,
                display_time=display_time,
                duration=FRAME_DURATION,
                timescale=TIMESCALE,
            )

        for i in range(preroll):
            schedule(i * FRAME_DURATION)
        out_dev.start_scheduled_playback(start_time=0, timescale=TIMESCALE)
        display_time = preroll * FRAME_DURATION

        frame = None
        for _ in range(200):
            f = in_dev.pop_capture_frame(timeout_ms=1000)
            with contextlib.suppress(RuntimeError):
                schedule(display_time)
                display_time += FRAME_DURATION
            if f is not None and f.has_signal:
                frame = f
                break

        if frame is None:
            pytest.skip("No SDI signal on loopback input — check OUT→IN cabling")

        assert frame.pixel_format == PIXEL_FORMAT
        cap = np.array(frame.data)
        row_bytes = len(cap) // frame.height
        luma = cap.reshape(frame.height, row_bytes)[:, 1::2].astype(np.int32)
        top = float(luma[: frame.height // 2].mean())
        bottom = float(luma[frame.height // 2 :].mean())
        # Sent 0xC0 (192) over 0x40 (64). Allow generous SDI level tolerance,
        # but the bands must be clearly separated and on the correct sides.
        assert top - bottom > 80, (
            f"luma bands not recovered: top mean {top:.0f}, bottom {bottom:.0f}"
        )
        assert top > 150, f"bright band captured too dark: {top:.0f}"
        assert bottom < 110, f"dark band captured too bright: {bottom:.0f}"


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

        if not signal_acquired:
            pytest.skip("Input never acquired SDI signal — check OUT→IN cabling")

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
        libc_name = ctypes.util.find_library("c")
        if libc_name is None:
            pytest.skip("libc not found for custom-allocator test")
        libc = ctypes.CDLL(libc_name)
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
            flags=pydecklink.VideoInputFlag.Default.value,
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

            if not signal_acquired:
                pytest.skip("Input never acquired SDI signal — check OUT→IN cabling")

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
