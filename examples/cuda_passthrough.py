"""Canonical SDI → CUDA → SDI passthrough recipe.

Captures from one DeckLink sub-device into pinned CUDA memory, runs a
Python-callable kernel on each frame on a CUDA stream, stages the
result into a pinned output frame, and schedules the result for
playout on a second sub-device. Auto-detects the input mode; output
matches by construction.

Implements §spec:canonical-gpu-passthrough / §road:cuda-passthrough-example.

Pipeline:

    SDI cable -> DeckLink DMA -> [pinned input frame]
                                       |
                                  H2D N bytes
                                       v
                              [device input slot]
                                       |
                              kernel(stream, d_in, d_out, w, h, n)
                                       v
                              [device output slot]
                                       |
                                  D2H N bytes
                                       v
                              [pinned output frame]
                                       |
                              schedule_output_frame
                                       v
                          DeckLink DMA -> SDI cable

Threading mirrors ``cuda_loopback_latency.py``: a capture thread
submits H2D + kernel + D2H, a consumer thread waits on the D2H event
and schedules the output frame, and the main thread runs the
lifecycle. The default kernel is identity (``cudaMemcpyAsync``
device-to-device on the stream) — true passthrough so consumers can
verify wiring before plugging in their own kernel.

Defaults: 4K UHD 59.94p, 10-bit YUV 4:2:2 (v210), output device 0,
input device 2.

Consumers replace the kernel by importing the example as a module and
passing their own callable to ``run_passthrough``:

    from examples import cuda_passthrough

    def my_kernel(stream, d_in, d_out, width, height, frame_bytes):
        ...  # cudaLaunchKernel / cupy / numba / etc.

    cuda_passthrough.run_passthrough(
        input_device_index=2,
        output_device_index=0,
        kernel=my_kernel,
        duration_seconds=5.0,
    )

Usage:
    uv run examples/cuda_passthrough.py --input 2 --output 0 --duration 5

Install:
    uv pip install -e ".[cuda-examples]"
"""

from __future__ import annotations

import argparse
import contextlib
import gc
import queue
import signal
import sys
import threading
import time
from collections.abc import Callable

import pydecklink

# cuda-python is imported lazily inside run_passthrough so the module
# can be imported (and unit-tested) on hosts without it.


_DEFAULT_MODE = pydecklink.DisplayMode.Mode4K2160p5994
_DEFAULT_PIXEL_FORMAT = pydecklink.PixelFormat.Format10BitYUV

# Output preroll: frames queued before start_scheduled_playback. Deeper
# than the input's queue depth so SDI sync has time to lock before the
# first measured frame.
_PREROLL = 8

# Output pool size: preroll + a few slots in flight for steady-state
# scheduling.
_POOL_DEPTH = _PREROLL + 5

# Input allocator prefill: minimum that bridges the no-signal →
# signal-locked transition with input_queue_depth=1.
_PREFILL = 4

# Pipeline depth: device-side slots for in-flight H2D + kernel + D2H.
_PIPELINE_DEPTH = 3

# Bound the wait for the input device to lock onto the SDI signal
# after start_streams. A missing BNC, wrong device index, or mode
# mismatch otherwise manifests as a silent multi-minute spin.
# SPEC §5.11 will replace this poll with an IDeckLinkStatus query.
_LOCK_TIMEOUT_S = 2.0

# Bound the format-detection pre-flight. Same root cause as the lock
# timeout — a missing source manifests as an indefinite wait without it.
_DETECTION_TIMEOUT_S = 2.0


# Type alias for the consumer-supplied kernel callable. Documented in
# the module docstring and §spec:canonical-gpu-passthrough.
KernelFn = Callable[[object, int, int, int, int, int], None]


# ---------------------------------------------------------------------------
# CUDA error-check helper.
# ---------------------------------------------------------------------------


def _check(err: object, op: str) -> None:
    """Raise on a non-zero CUDA error code."""
    code = getattr(err, "value", err)
    if code != 0:
        raise RuntimeError(f"{op} failed: cudaError={code}")


def _print_status(line: str) -> None:
    """Overwrite the current terminal line with ``line``."""
    sys.stdout.write(f"\r{line}\033[K")
    sys.stdout.flush()


def _percentiles(samples: list[float], qs: tuple[float, ...]) -> dict[float, float]:
    if not samples:
        return {q: 0.0 for q in qs}
    s = sorted(samples)
    n = len(s)
    return {q: s[max(0, min(n - 1, round(q / 100.0 * (n - 1))))] for q in qs}


# ---------------------------------------------------------------------------
# Default kernel: device-to-device identity copy on the stream.
# ---------------------------------------------------------------------------


def _make_identity_kernel(cudart: object) -> KernelFn:
    """Build the default identity kernel bound to the live cudart
    module. Returns a callable matching ``KernelFn`` that performs
    ``cudaMemcpyAsync(d_output, d_input, frame_bytes, D2D, stream)``.
    Consumers replace this with their own kernel callable.
    """
    D2D = cudart.cudaMemcpyKind.cudaMemcpyDeviceToDevice

    def _identity(
        stream: object,
        d_input: int,
        d_output: int,
        width: int,
        height: int,
        frame_bytes: int,
    ) -> None:
        del width, height  # passthrough doesn't care about dims
        (err,) = cudart.cudaMemcpyAsync(d_output, d_input, frame_bytes, D2D, stream)
        _check(err, "cudaMemcpyAsync(identity D2D)")

    return _identity


# ---------------------------------------------------------------------------
# Bounded probes (signal lock + format detection). Same shape as the
# capture-only CUDA examples; a missing source must surface as a clear
# RuntimeError, not an indefinite wait.
# ---------------------------------------------------------------------------


def _wait_for_input_signal(in_dev: object, timeout_s: float) -> bool:
    """Drain captures until one arrives with ``has_signal=True``, or the
    deadline passes. Returns whether the input locked. Probed frames are
    discarded; the caller owns the post-lock capture path."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        cfr = in_dev.pop_capture_frame_ref(timeout_ms=100)
        if cfr is None:
            continue
        if cfr.has_signal:
            return True
    return False


def _detect_input_mode(
    dev: object,
    pixel_format: pydecklink.PixelFormat,
    timeout_s: float,
) -> pydecklink.DisplayMode:
    """Enable input with ``EnableFormatDetection``, poll until the SDK
    reports a known display mode, then disable input. Returns the
    detected mode; raises ``RuntimeError`` on timeout. The caller
    re-enables input with the returned mode + allocator + zero-copy
    for the actual capture path."""
    # _DEFAULT_MODE as placeholder — the SDK swaps to the detected mode
    # regardless of the placeholder, but it must be a mode the device
    # actually supports.
    dev.enable_video_input(
        _DEFAULT_MODE,
        pixel_format,
        pydecklink.VideoInputFlag.EnableFormatDetection,
    )
    dev.start_streams()
    try:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            frame = dev.pop_capture_frame(timeout_ms=100)
            if frame is None or not frame.has_signal:
                continue
            fmt = dev.current_input_format
            if fmt is not None and fmt.mode != pydecklink.DisplayMode.Unknown:
                return fmt.mode
    finally:
        dev.stop_streams()
        dev.disable_video_input()
    raise RuntimeError(
        f"no SDI signal detected on capture device within "
        f"{timeout_s:.1f}s. Check the BNC connection and source."
    )


# ---------------------------------------------------------------------------
# Pipeline: GPU input/output slots + capture/consumer threads.
# ---------------------------------------------------------------------------


class _Slot:
    """One GPU pipeline slot: input + output device pointers + the
    CUDA event that fires after the D2H of the kernel result."""

    __slots__ = ("d_input", "d_output", "ev_done")

    def __init__(self, d_input: int, d_output: int, ev_done: object) -> None:
        self.d_input = d_input
        self.d_output = d_output
        self.ev_done = ev_done


class _Frame:
    """An in-flight frame handed from capture thread to consumer
    thread. Carries the SDK capture-frame ref (so the input buffer
    stays alive until H2D completes), the device pipeline slot, the
    pinned output ``MutableFrame`` to schedule, and the wall-clock
    arrival timestamp for end-to-end latency."""

    __slots__ = ("callback_arrived_us", "cfr", "mf", "slot")

    def __init__(
        self,
        cfr: object,
        slot: _Slot,
        mf: object,
        callback_arrived_us: int,
    ) -> None:
        self.cfr = cfr
        self.slot = slot
        self.mf = mf
        self.callback_arrived_us = callback_arrived_us


class _Pipeline:
    """GPU buffer pool + the two thread bodies.

    Capture thread: pop a free slot, pop a CaptureFrameRef, acquire a
    pool MutableFrame, submit ``H2D → kernel → D2H → event`` on the
    stream, hand the frame to the consumer.

    Consumer thread: wait on the post-D2H event, schedule the
    MutableFrame, recycle the slot. The CaptureFrameRef goes out of
    scope at frame teardown, returning the SDK input buffer to the
    allocator's free-list.
    """

    def __init__(
        self,
        frame_bytes: int,
        depth: int,
        kernel: KernelFn,
        cudart: object,
        width: int,
        height: int,
    ) -> None:
        self._cudart = cudart
        self._frame_bytes = frame_bytes
        self._kernel = kernel
        self._width = width
        self._height = height
        self.frames_processed = 0
        self.frames_dropped_no_slot = 0
        self.frames_dropped_no_signal = 0
        self.frames_dropped_no_output = 0
        self.delivery_us: list[float] = []  # callback → schedule
        # CUDA stream for all transfers + kernel launches.
        err, stream = cudart.cudaStreamCreate()
        _check(err, "cudaStreamCreate")
        self._stream = stream
        # Allocate slot pool: input + output device buffers + post-D2H event.
        self._slots: list[_Slot] = []
        for _ in range(depth):
            err, d_in = cudart.cudaMalloc(frame_bytes)
            _check(err, "cudaMalloc(input)")
            err, d_out = cudart.cudaMalloc(frame_bytes)
            _check(err, "cudaMalloc(output)")
            err, ev = cudart.cudaEventCreate()
            _check(err, "cudaEventCreate")
            self._slots.append(
                _Slot(d_input=int(d_in), d_output=int(d_out), ev_done=ev)
            )
        self.free_slots: queue.Queue[_Slot] = queue.Queue(maxsize=depth)
        for s in self._slots:
            self.free_slots.put_nowait(s)
        self.in_flight: queue.Queue[_Frame] = queue.Queue(maxsize=depth)

    def close(self) -> None:
        cudart = self._cudart
        for s in self._slots:
            cudart.cudaEventDestroy(s.ev_done)
            cudart.cudaFree(s.d_input)
            cudart.cudaFree(s.d_output)
        cudart.cudaStreamDestroy(self._stream)

    def capture_loop(
        self,
        in_dev: pydecklink.Device,
        out_dev: pydecklink.Device,
        stop: threading.Event,
    ) -> None:
        """Capture-thread body: pop frame → submit H2D + kernel + D2H →
        handoff. Submission is non-blocking; the consumer waits on the
        D2H event and does the scheduling work."""
        cudart = self._cudart
        H2D = cudart.cudaMemcpyKind.cudaMemcpyHostToDevice
        D2H = cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost
        while not stop.is_set():
            try:
                slot = self.free_slots.get(timeout=0.1)
            except queue.Empty:
                continue
            cfr = in_dev.pop_capture_frame_ref(timeout_ms=100)
            if cfr is None:
                self.free_slots.put_nowait(slot)
                continue
            if not cfr.has_signal:
                self.frames_dropped_no_signal += 1
                self.free_slots.put_nowait(slot)
                continue
            # Acquire an output frame from the pinned pool.
            try:
                mf = out_dev.acquire_output_frame(timeout_ms=100)
            except RuntimeError:
                # Output queue starved — drop this captured frame. The
                # cfr falls out of scope, returning the SDK buffer to
                # the input allocator's free-list.
                self.frames_dropped_no_output += 1
                self.free_slots.put_nowait(slot)
                continue
            host_in = int(cfr.data.ctypes.data)
            host_out = int(mf.data.ctypes.data)
            # H2D the captured frame into the input device slot.
            (err,) = cudart.cudaMemcpyAsync(
                slot.d_input, host_in, self._frame_bytes, H2D, self._stream
            )
            _check(err, "cudaMemcpyAsync(H2D)")
            # Run the consumer-supplied kernel on the stream.
            self._kernel(
                self._stream,
                slot.d_input,
                slot.d_output,
                self._width,
                self._height,
                self._frame_bytes,
            )
            # D2H the kernel result into the pinned output frame.
            (err,) = cudart.cudaMemcpyAsync(
                host_out, slot.d_output, self._frame_bytes, D2H, self._stream
            )
            _check(err, "cudaMemcpyAsync(D2H)")
            # Event after the D2H — consumer syncs on this before
            # handing the pinned buffer to the SDK for DMA.
            (err,) = cudart.cudaEventRecord(slot.ev_done, self._stream)
            _check(err, "cudaEventRecord(done)")
            frame = _Frame(
                cfr=cfr,
                slot=slot,
                mf=mf,
                callback_arrived_us=cfr.callback_arrived_us,
            )
            try:
                self.in_flight.put_nowait(frame)
            except queue.Full:
                # Consumer behind — drop this captured frame.
                self.frames_dropped_no_slot += 1
                self.free_slots.put_nowait(slot)
                continue

    def consumer_loop(
        self,
        out_dev: pydecklink.Device,
        frame_duration: int,
        frame_timescale: int,
        stop: threading.Event,
    ) -> None:
        """Consumer-thread body: wait on D2H event → schedule output
        → release input cfr → recycle slot."""
        cudart = self._cudart
        # Output display time runs ahead by _PREROLL frames; preroll
        # has already scheduled 0..PREROLL-1, so the first consumer
        # frame goes out at PREROLL.
        display_time = _PREROLL * frame_duration
        while not stop.is_set() or not self.in_flight.empty():
            try:
                frame = self.in_flight.get(timeout=0.1)
            except queue.Empty:
                continue
            (err,) = cudart.cudaEventSynchronize(frame.slot.ev_done)
            _check(err, "cudaEventSynchronize")
            out_dev.schedule_output_frame(
                frame.mf,
                display_time=display_time,
                duration=frame_duration,
                timescale=frame_timescale,
            )
            display_time += frame_duration
            self.frames_processed += 1
            scheduled_us = pydecklink.clock_us()
            self.delivery_us.append(float(scheduled_us - frame.callback_arrived_us))
            slot = frame.slot
            frame.cfr = None  # release SDK input buffer
            del frame
            self.free_slots.put_nowait(slot)

    def report(self, run_seconds: float, output_status: object) -> None:
        n = self.frames_processed
        if n == 0:
            print(f"[passthrough] no frames processed in {run_seconds:.1f}s.")
            return
        qs = (50.0, 95.0, 99.0)
        d = _percentiles(self.delivery_us, qs)
        print(
            f"[passthrough] frames={n} dropped="
            f"(no_slot={self.frames_dropped_no_slot}, "
            f"no_signal={self.frames_dropped_no_signal}, "
            f"no_output={self.frames_dropped_no_output})"
        )
        print(
            f"              run={run_seconds:.1f}s  "
            f"effective_fps={n / run_seconds:.1f}  "
            f"({self._frame_bytes / 1_000_000:.2f} MB/frame)"
        )
        print("              min     p50     p95     p99     max     (microseconds)")
        print(
            "  delivery   "
            f" {min(self.delivery_us):>6.0f}  {d[50]:>6.0f}  "
            f"{d[95]:>6.0f}  {d[99]:>6.0f}  {max(self.delivery_us):>6.0f}"
        )
        print(
            f"[output]      completed={output_status.completed} "
            f"late={output_status.late} dropped={output_status.dropped} "
            f"flushed={output_status.flushed} "
            f"underrun={output_status.underrun}"
        )


# ---------------------------------------------------------------------------
# Run loop: setup, threading, GC config, teardown.
# ---------------------------------------------------------------------------


def run_passthrough(
    input_device_index: int = 2,
    output_device_index: int = 0,
    kernel: KernelFn | None = None,
    pixel_format: pydecklink.PixelFormat = _DEFAULT_PIXEL_FORMAT,
    frame_count: int = 0,
    duration_seconds: float = 0.0,
) -> None:
    """Run the SDI → CUDA → SDI passthrough until ``frame_count``
    frames are processed (if > 0) or ``duration_seconds`` elapse (if
    > 0), or SIGINT is received. Either bound is the first to fire.

    The input mode is auto-detected via the SDK's FormatDetection;
    output is configured to match. ``kernel=None`` (default) runs the
    identity kernel — ``cudaMemcpyAsync`` device-to-device on the
    stream — producing a true passthrough that consumers run unchanged
    to verify their wiring.
    """
    if input_device_index == output_device_index:
        raise ValueError(
            f"input and output device indices must differ (both = {input_device_index})"
        )

    from cuda.bindings import runtime as cudart

    if kernel is None:
        kernel = _make_identity_kernel(cudart)

    def _alloc(size: int) -> int:
        err, ptr = cudart.cudaHostAlloc(size, cudart.cudaHostAllocDefault)
        _check(err, "cudaHostAlloc")
        return int(ptr)

    def _free(ptr: int, _size: int) -> None:
        (err,) = cudart.cudaFreeHost(ptr)
        _check(err, "cudaFreeHost")

    in_dev = pydecklink.Device(index=input_device_index)
    out_dev = pydecklink.Device(index=output_device_index)

    mode = _detect_input_mode(in_dev, pixel_format, _DETECTION_TIMEOUT_S)
    print(f"[passthrough] detected input mode={mode.name}", flush=True)

    width = pydecklink.get_mode_width(mode)
    height = pydecklink.get_mode_height(mode)
    frame_bytes = pydecklink.get_frame_bytes(mode, pixel_format)
    frame_duration, frame_timescale = pydecklink.get_mode_frame_duration(mode)

    in_provider = pydecklink.VideoBufferAllocatorProvider(alloc=_alloc, free=_free)
    out_alloc = pydecklink.VideoBufferAllocator(frame_bytes, alloc=_alloc, free=_free)

    out_dev.enable_video_output(mode)
    try:
        row_bytes = out_dev.row_bytes_for_pixel_format(pixel_format, width)
        out_dev.create_frame_pool_pinned(
            _POOL_DEPTH, width, height, row_bytes, pixel_format, out_alloc
        )
        in_dev.enable_video_input_with_allocator(
            mode=mode,
            pixel_format=pixel_format,
            flags=pydecklink.VideoInputFlag(0),
            allocator_provider=in_provider,
            zero_copy=True,
            input_queue_depth=1,
        )
        in_alloc = in_provider.get_allocator(
            buffer_size=frame_bytes,
            width=width,
            height=height,
            row_bytes=frame_bytes // height,
            pixel_format=pixel_format,
        )
        in_alloc.prefill(_PREFILL)

        pipeline = _Pipeline(
            frame_bytes=frame_bytes,
            depth=_PIPELINE_DEPTH,
            kernel=kernel,
            cudart=cudart,
            width=width,
            height=height,
        )

        # Pre-roll the output queue with neutral frames at display
        # times 0..PREROLL-1. The consumer thread continues from
        # PREROLL onwards.
        for i in range(_PREROLL):
            mf = out_dev.acquire_output_frame(timeout_ms=1000)
            mf.data[:] = 0x80  # neutral mid-gray for v210 / 2vuy
            out_dev.schedule_output_frame(
                mf,
                display_time=i * frame_duration,
                duration=frame_duration,
                timescale=frame_timescale,
            )

        in_dev.start_streams()

        if not _wait_for_input_signal(in_dev, _LOCK_TIMEOUT_S):
            raise RuntimeError(
                f"no SDI signal locked on input device {input_device_index} "
                f"within {_LOCK_TIMEOUT_S:.1f}s of starting streams "
                f"for detected mode {mode.name}. Check the BNC connection."
            )

        # GC tuning for the hot loop (matches cuda_pinned_pipelined.py).
        gc.collect()
        gc.freeze()
        gc.disable()

        stop = threading.Event()

        def _on_sigint(_sig: int, _frame: object) -> None:
            stop.set()

        prev_sigint = signal.signal(signal.SIGINT, _on_sigint)

        capture_thread = threading.Thread(
            target=pipeline.capture_loop,
            args=(in_dev, out_dev, stop),
            name="decklink-capture",
            daemon=True,
        )
        consumer_thread = threading.Thread(
            target=pipeline.consumer_loop,
            args=(out_dev, frame_duration, frame_timescale, stop),
            name="decklink-consumer",
            daemon=True,
        )

        out_dev.start_scheduled_playback(start_time=0, timescale=frame_timescale)

        started = time.monotonic()
        capture_thread.start()
        consumer_thread.start()

        last_status = 0.0
        try:
            while not stop.is_set():
                now = time.monotonic()
                elapsed = now - started
                if frame_count > 0 and pipeline.frames_processed >= frame_count:
                    break
                if duration_seconds > 0 and elapsed >= duration_seconds:
                    break
                if now - last_status >= 0.5:
                    state = (
                        "running"
                        if pipeline.frames_processed > 0
                        else "waiting for signal"
                    )
                    _print_status(
                        f"{state}: {int(elapsed)}s elapsed, "
                        f"{pipeline.frames_processed} processed "
                        f"(no_slot={pipeline.frames_dropped_no_slot} "
                        f"no_signal={pipeline.frames_dropped_no_signal} "
                        f"no_output={pipeline.frames_dropped_no_output})"
                    )
                    last_status = now
                time.sleep(0.05)
        finally:
            stop.set()
            sys.stdout.write("\n")
            sys.stdout.flush()

        run_seconds = time.monotonic() - started
        capture_thread.join(timeout=2.0)
        consumer_thread.join(timeout=2.0)

        gc.enable()
        signal.signal(signal.SIGINT, prev_sigint)

        try:
            pipeline.report(run_seconds, out_dev.output_status)
        finally:
            pipeline.close()
            in_dev.stop_streams()
            in_dev.disable_video_input()
    finally:
        with contextlib.suppress(RuntimeError):
            out_dev.stop_scheduled_playback()
        with contextlib.suppress(RuntimeError):
            out_dev.disable_video_output()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DeckLink SDI → CUDA → SDI passthrough.",
    )
    parser.add_argument(
        "--input",
        type=int,
        default=2,
        help="DeckLink device index for capture (default 2).",
    )
    parser.add_argument(
        "--output",
        type=int,
        default=0,
        help="DeckLink device index for playout (default 0).",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=0,
        help="Stop after N processed frames. 0 = unlimited (use --duration or Ctrl-C).",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Stop after S seconds. 0 = unlimited.",
    )
    parser.add_argument(
        "--pixel-format",
        choices=["8bit", "10bit"],
        default="10bit",
        help="10bit (default, v210, ~22 MB/frame at 4K) or 8bit "
        "(2vuy, ~8 MB/frame at 4K).",
    )
    args = parser.parse_args()

    if args.frames == 0 and args.duration == 0.0:
        args.duration = 5.0  # default: 5 seconds.

    pixel_format = (
        pydecklink.PixelFormat.Format10BitYUV
        if args.pixel_format == "10bit"
        else pydecklink.PixelFormat.Format8BitYUV
    )

    devices = pydecklink.list_devices()
    for label, idx in (("--input", args.input), ("--output", args.output)):
        if idx >= len(devices):
            print(
                f"{label}={idx} out of range ({len(devices)} devices found).",
                file=sys.stderr,
            )
            sys.exit(1)

    run_passthrough(
        input_device_index=args.input,
        output_device_index=args.output,
        pixel_format=pixel_format,
        frame_count=args.frames,
        duration_seconds=args.duration,
    )


if __name__ == "__main__":
    main()
