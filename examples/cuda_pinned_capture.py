"""CUDA-pinned-memory capture patterns for pydecklink.

Two ways to feed DeckLink DMA into CUDA-pinned host memory. pydecklink
has no GPU dependency; this example wires NVIDIA's `cuda-python`
bindings to the allocator surface from SPEC §gpu-pinned-memory.

Pattern A -- ``cudaHostAlloc`` via the allocator API
    Consumer-supplied alloc/free callables wrap ``cudaHostAlloc`` and
    ``cudaFreeHost``. Plug them into ``VideoBufferAllocatorProvider``
    and call ``device.enable_video_input_with_allocator``. The SDK
    DMAs straight into pinned memory. Best when the consumer controls
    the buffer pool from start.

Pattern B -- ``cudaHostRegister`` post-allocation
    The SDK allocates buffers normally (malloc); the consumer calls
    ``cudaHostRegister`` on each unique buffer pointer the first time
    it sees it (idempotent via a set). Buffers are unregistered on
    shutdown. No allocator override required. Best when the consumer
    cannot influence the SDK's allocator.

Synchronization contract (SPEC §gpu-pinned-memory):
    DeckLink DMA and GPU copies must not overlap on the same buffer.
    Wait for the frame callback before launching ``cudaMemcpyAsync``;
    hold the ``CaptureFrameRef`` until the CUDA stream completes.
    This example does not run a GPU copy -- it demonstrates the
    pinning plumbing only. Real consumers add a triple-buffer
    pattern (DeckLink fills N, GPU copies N-1, GPU processes N-2).

Install:
    pip install pydecklink[cuda-examples]

Usage:
    python examples/cuda_pinned_capture.py --mode alloc --device 0
    python examples/cuda_pinned_capture.py --mode register --device 0

    # Self-loop on a single card via a BNC jumper between two SDI ports
    # (drives --source-device as output, captures on --device):
    python examples/cuda_pinned_capture.py --mode alloc --source self \\
        --device 0 --source-device 2

This script requires DeckLink hardware. ``--source external`` (default)
needs an active SDI input on ``--device``; ``--source self`` only needs
a physical BNC cable between the two configured sub-devices.
"""

from __future__ import annotations

import argparse
import contextlib
import signal
import sys
import time
from collections.abc import Callable

import pydecklink

# cuda-python is an optional dependency. Import lazily inside the
# pattern functions so the module can be imported (and unit-tested)
# without cuda installed.


# Default capture format -- override on the command line if needed.
_DEFAULT_MODE = pydecklink.DisplayMode.HD1080p25
_DEFAULT_PIXEL_FORMAT = pydecklink.PixelFormat.Format8BitYUV


def _check(err: object, op: str) -> None:
    """Raise on a non-zero CUDA error code."""
    # cuda-python returns a cudaError_t enum whose .value is the int code.
    code = getattr(err, "value", err)
    if code != 0:
        raise RuntimeError(f"{op} failed: cudaError={code}")


def _print_status(line: str) -> None:
    """Overwrite the current terminal line with ``line`` (CR + clear-to-EOL)."""
    sys.stdout.write(f"\r{line}\033[K")
    sys.stdout.flush()


def _capture_with_progress(
    dev: pydecklink.Device,
    frame_count: int,
    on_frame: Callable[[object], None],
) -> tuple[int, bool]:
    """Run a capture loop with a live progress indicator.

    Without this, the example sits silently on ``pop_capture_frame_ref``
    when no SDI signal is present, indistinguishable from a hang. Here
    we tick a status line each poll so the user can see "waiting for
    signal" with elapsed seconds, switching to "capturing N/M" once
    frames arrive. A SIGINT handler flips a flag so Ctrl-C exits the
    loop cleanly instead of raising mid-pop.

    Returns ``(captured, interrupted)``.

    The SIGINT handler is *not* restored on exit. Restoring it before
    device teardown re-arms the default handler, and a follow-up SIGINT
    (or pending one) would then raise KeyboardInterrupt during
    ``stop_streams`` / ``disable_video_input``, leaking SDK state.
    Callers that need the original handler back must save and restore
    it themselves around this call.
    """
    stop_requested = [False]

    def _on_sigint(_sig: int, _frame: object) -> None:
        stop_requested[0] = True

    signal.signal(signal.SIGINT, _on_sigint)

    captured = 0
    started = time.monotonic()
    last_status = 0.0
    try:
        while captured < frame_count and not stop_requested[0]:
            frame = dev.pop_capture_frame_ref(timeout_ms=1000)
            now = time.monotonic()
            if frame is None or not frame.has_signal:
                if now - last_status >= 0.5:
                    elapsed = int(now - started)
                    state = "waiting for signal" if captured == 0 else "signal lost"
                    _print_status(
                        f"{state}: {elapsed}s elapsed, "
                        f"{captured}/{frame_count} frames"
                    )
                    last_status = now
                continue
            on_frame(frame)
            captured += 1
            _print_status(f"capturing: {captured}/{frame_count} frames")
    finally:
        sys.stdout.write("\n")
        sys.stdout.flush()
    return captured, stop_requested[0]


class _SelfSource:
    """Drive a second DeckLink sub-device with a continuous neutral-gray
    test pattern, so the example can self-loop over a BNC jumper between
    two SDI ports on the same card.

    Why: ``pop_capture_frame_ref`` only returns valid frames when an SDI
    signal is present. Without a generator (camera, switcher, etc.) the
    example sits in "waiting for signal" forever. Driving one sub-device
    as output and the other as input — with a physical BNC jumper —
    closes the loop on a single card. Mirrors the wiring used by
    ``tests/test_decklink_integration.py``.

    Lifecycle: ``__enter__`` only enables the output and creates the
    frame pool — playback is *not* started yet. The caller must enable
    and start the input streams next, then call ``start_playback()``
    to pre-roll and begin output. This matches the order in
    ``tests/test_decklink_integration.py``: input must be listening
    before output produces a signal, otherwise the input device fails
    to lock and only delivers the first frame before stalling.
    Pre-rolling ``PREROLL`` frames before playback gives SDI sync time
    to lock; ``schedule_next()`` keeps the queue fed thereafter.
    """

    PREROLL = 15
    POOL_DEPTH = PREROLL + 5  # Extra slack for in-flight scheduled frames.

    def __init__(
        self,
        dev: pydecklink.Device,
        mode: pydecklink.DisplayMode,
        pixel_format: pydecklink.PixelFormat,
    ) -> None:
        self._dev = dev
        self._mode = mode
        self._pixel_format = pixel_format
        duration, timescale = pydecklink.get_mode_frame_duration(mode)
        self._duration = duration
        self._timescale = timescale
        self._display_time = 0
        self._playback_started = False
        self._output_enabled = False

    def __enter__(self) -> _SelfSource:
        self._dev.enable_video_output(self._mode)
        self._output_enabled = True
        width = pydecklink.get_mode_width(self._mode)
        height = pydecklink.get_mode_height(self._mode)
        row_bytes = self._dev.row_bytes_for_pixel_format(
            self._pixel_format, width
        )
        self._dev.create_frame_pool(
            self.POOL_DEPTH, width, height, row_bytes, self._pixel_format
        )
        return self

    def start_playback(self) -> None:
        """Pre-roll the configured number of frames and start scheduled
        playback. Call only after input streams are running, so the
        first output frames don't arrive at a deaf input."""
        for i in range(self.PREROLL):
            self._schedule_one(i * self._duration)
        self._dev.start_scheduled_playback(
            start_time=0, timescale=self._timescale
        )
        self._playback_started = True
        self._display_time = self.PREROLL * self._duration

    def _schedule_one(self, display_time: int) -> None:
        mf = self._dev.acquire_output_frame(timeout_ms=1000)
        # Neutral gray YCbCr fill: valid SDI signal, easy to recognize.
        mf.data[:] = 0x80
        self._dev.schedule_output_frame(
            mf,
            display_time=display_time,
            duration=self._duration,
            timescale=self._timescale,
        )

    def schedule_next(self) -> None:
        """Push one more output frame onto the queue, advancing the
        display timeline. Call once per captured input frame to keep
        the playback queue from underrunning."""
        self._schedule_one(self._display_time)
        self._display_time += self._duration

    def __exit__(self, *_exc: object) -> None:
        if self._playback_started:
            with contextlib.suppress(RuntimeError):
                self._dev.stop_scheduled_playback()
        if self._output_enabled:
            with contextlib.suppress(RuntimeError):
                self._dev.disable_video_output()


def run_alloc_mode(
    device_index: int = 0,
    mode: pydecklink.DisplayMode = _DEFAULT_MODE,
    pixel_format: pydecklink.PixelFormat = _DEFAULT_PIXEL_FORMAT,
    frame_count: int = 30,
    source_device_index: int | None = None,
) -> None:
    """Pattern A: SDK DMAs into ``cudaHostAlloc`` buffers via the
    allocator provider.

    The consumer supplies ``alloc``/``free`` callables that wrap
    ``cudaHostAlloc``/``cudaFreeHost``. The allocator's free-list
    recycles buffers across frames; ``free`` runs only at allocator
    teardown. ``recycled_count`` reports reuse.

    When ``source_device_index`` is set, that device is opened as an
    output and driven with a neutral-gray test pattern via
    ``_SelfSource`` so the example can self-loop over a BNC jumper.
    """
    from cuda.bindings import runtime as cudart

    def cuda_host_alloc(size: int) -> int:
        # cudaHostAllocDefault: cached host memory. Use
        # cudaHostAllocWriteCombined when the CPU never reads the
        # frame (GPU-only processing) -- see SPEC §gpu-pinned-memory.
        err, ptr = cudart.cudaHostAlloc(size, cudart.cudaHostAllocDefault)
        _check(err, "cudaHostAlloc")
        return int(ptr)

    def cuda_free_host(ptr: int, _size: int) -> None:
        (err,) = cudart.cudaFreeHost(ptr)
        _check(err, "cudaFreeHost")

    provider = pydecklink.VideoBufferAllocatorProvider(
        alloc=cuda_host_alloc,
        free=cuda_free_host,
    )

    src_dev = (
        pydecklink.Device(index=source_device_index)
        if source_device_index is not None
        else None
    )
    src_cm: contextlib.AbstractContextManager[_SelfSource | None] = (
        _SelfSource(src_dev, mode, pixel_format)
        if src_dev is not None
        else contextlib.nullcontext()
    )

    with src_cm as src:
        dev = pydecklink.Device(index=device_index)
        dev.enable_video_input_with_allocator(
            mode=mode,
            pixel_format=pixel_format,
            flags=pydecklink.VideoInputFlag(0),
            allocator_provider=provider,
            zero_copy=True,
        )
        # Pre-fill the allocator's free-list before start_streams. With
        # Python alloc callbacks (cudaHostAlloc here) the SDK input
        # pipeline cannot tolerate SLOW-path latency at signal rate;
        # pre-filling on the main thread keeps all runtime allocations
        # on the FAST path. ``row_bytes_for_pixel_format`` requires
        # video output to be enabled, so derive row_bytes from
        # frame_bytes / height instead — the provider only uses
        # buffer_size for cache lookup anyway.
        frame_bytes = pydecklink.get_frame_bytes(mode, pixel_format)
        width = pydecklink.get_mode_width(mode)
        height = pydecklink.get_mode_height(mode)
        row_bytes = frame_bytes // height
        in_alloc = provider.get_allocator(
            buffer_size=frame_bytes,
            width=width,
            height=height,
            row_bytes=row_bytes,
            pixel_format=pixel_format,
        )
        in_alloc.prefill(32)

        dev.start_streams()
        if src is not None:
            src.start_playback()

        def _on_frame(_f: object) -> None:
            if src is not None:
                src.schedule_next()

        try:
            captured, interrupted = _capture_with_progress(
                dev, frame_count, on_frame=_on_frame
            )
            if captured == 0:
                print("[alloc] no frames captured (interrupted)." if interrupted
                      else "[alloc] no frames captured.")
                return
            suffix = " (interrupted)" if interrupted else ""
            print(
                f"[alloc] frames={captured} "
                f"allocated={in_alloc.allocated_count} "
                f"recycled={in_alloc.recycled_count}{suffix}"
            )
        finally:
            dev.stop_streams()
            dev.disable_video_input()
            # Allocator destruction (when `provider` and `alloc` go out of
            # scope) drains the free-list and calls cuda_free_host once
            # per backing buffer.


def run_register_mode(
    device_index: int = 0,
    mode: pydecklink.DisplayMode = _DEFAULT_MODE,
    pixel_format: pydecklink.PixelFormat = _DEFAULT_PIXEL_FORMAT,
    frame_count: int = 30,
    source_device_index: int | None = None,
) -> None:
    """Pattern B: register SDK-allocated buffers with CUDA on first
    sight.

    Each ``CaptureFrameRef`` exposes ``data`` as a numpy view of the
    underlying SDK buffer. The first time a pointer is seen, register
    it with ``cudaHostRegister``; track the (ptr, size) pairs so each
    is unregistered exactly once at shutdown.

    When ``source_device_index`` is set, that device is opened as an
    output and driven with a neutral-gray test pattern via
    ``_SelfSource`` so the example can self-loop over a BNC jumper.
    """
    from cuda.bindings import runtime as cudart

    src_dev = (
        pydecklink.Device(index=source_device_index)
        if source_device_index is not None
        else None
    )
    src_cm: contextlib.AbstractContextManager[_SelfSource | None] = (
        _SelfSource(src_dev, mode, pixel_format)
        if src_dev is not None
        else contextlib.nullcontext()
    )

    with src_cm as src:
        dev = pydecklink.Device(index=device_index)
        dev.enable_video_input(
            mode=mode,
            pixel_format=pixel_format,
            zero_copy=True,
        )
        dev.start_streams()
        if src is not None:
            src.start_playback()

        registered: dict[int, int] = {}  # ptr -> size

        def _on_frame(frame: object) -> None:
            arr = frame.data  # type: ignore[attr-defined]
            ptr = int(arr.ctypes.data)
            size = int(arr.nbytes)
            if ptr not in registered:
                (err,) = cudart.cudaHostRegister(
                    ptr, size, cudart.cudaHostRegisterDefault
                )
                _check(err, "cudaHostRegister")
                registered[ptr] = size
            if src is not None:
                src.schedule_next()

        try:
            captured, interrupted = _capture_with_progress(
                dev, frame_count, on_frame=_on_frame
            )
            suffix = " (interrupted)" if interrupted else ""
            print(
                f"[register] frames={captured} "
                f"unique_buffers={len(registered)}{suffix}"
            )
        finally:
            dev.stop_streams()
            dev.disable_video_input()
            # Unregister every buffer we touched. The SDK frees its own
            # buffers later; unregistering before free is the correct order.
            for ptr in registered:
                (err,) = cudart.cudaHostUnregister(ptr)
                _check(err, "cudaHostUnregister")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CUDA-pinned-memory capture patterns for pydecklink."
    )
    parser.add_argument(
        "--mode",
        choices=["alloc", "register"],
        required=True,
        help="alloc: cudaHostAlloc via allocator API. "
        "register: cudaHostRegister on SDK buffers.",
    )
    parser.add_argument(
        "--device", type=int, default=0, help="DeckLink device index for capture"
    )
    parser.add_argument(
        "--frames", type=int, default=30, help="Number of frames to capture"
    )
    parser.add_argument(
        "--pixel-format",
        choices=["8bit", "10bit"],
        default="8bit",
    )
    parser.add_argument(
        "--source",
        choices=["external", "self"],
        default="external",
        help=(
            "external: capture from an external SDI source on --device. "
            "self: drive --source-device as output with a neutral-gray "
            "test pattern (BNC jumper required between the two ports)."
        ),
    )
    parser.add_argument(
        "--source-device",
        type=int,
        default=2,
        help="DeckLink device index to drive as output when --source=self.",
    )
    args = parser.parse_args()

    pixel_format = (
        pydecklink.PixelFormat.Format10BitYUV
        if args.pixel_format == "10bit"
        else pydecklink.PixelFormat.Format8BitYUV
    )

    devices = pydecklink.list_devices()
    if args.device >= len(devices):
        print(
            f"Device index {args.device} out of range "
            f"({len(devices)} devices found).",
            file=sys.stderr,
        )
        sys.exit(1)

    source_device_index: int | None = None
    if args.source == "self":
        if args.source_device == args.device:
            print(
                f"--source-device must differ from --device "
                f"(both = {args.device}).",
                file=sys.stderr,
            )
            sys.exit(1)
        if args.source_device >= len(devices):
            print(
                f"--source-device {args.source_device} out of range "
                f"({len(devices)} devices found).",
                file=sys.stderr,
            )
            sys.exit(1)
        source_device_index = args.source_device

    if args.mode == "alloc":
        run_alloc_mode(
            device_index=args.device,
            pixel_format=pixel_format,
            frame_count=args.frames,
            source_device_index=source_device_index,
        )
    else:
        run_register_mode(
            device_index=args.device,
            pixel_format=pixel_format,
            frame_count=args.frames,
            source_device_index=source_device_index,
        )


if __name__ == "__main__":
    main()
