"""Threaded capture pipeline: real-time DeckLink → CUDA H2D recipe.

The capture pipeline runs across two threads so the SDK input thread
is never blocked by Python work or H2D synchronization:

* **Capture thread** pops a frame, submits ``cudaMemcpyAsync`` to a
  free GPU buffer slot, records an event, and hands off to the
  consumer queue. Submission is non-blocking; the next ``pop`` runs
  while the H2D for the previous frame is still in flight.
* **Consumer thread** waits on the H2D event, then drops the
  ``CaptureFrameRef`` (returning the SDK buffer to the allocator's
  free-list) and recycles the GPU slot back into the pool. A real
  consumer would run kernels on the device pointer between event-sync
  and pool-release; the example just measures.
* **Main thread** does GC tuning (``gc.collect`` → ``gc.freeze`` →
  ``gc.disable``) before threads start, monitors progress, and joins
  on shutdown.

This is the pattern to copy for production. The per-frame budget at
4K UHD 59.94p / 10-bit YUV is 16.7 ms; the pipeline keeps the SDK
input thread off the GIL hot path entirely, so capture latency is
dominated by C++/CUDA waits rather than Python jitter.

Why this is different from ``cuda_pinned_capture.py``: that example
showed the allocator + zero-copy plumbing in a single-threaded loop,
useful for understanding the API. This example shows the architecture
to actually use in a real-time consumer.

Install:
    pip install pydecklink[cuda-examples]

Usage:
    python examples/cuda_pinned_pipelined.py --device 0
    python examples/cuda_pinned_pipelined.py --source self \\
        --device 0 --source-device 2 --frames 600

Defaults to 4K UHD 59.94p / 10-bit YUV. Override with --pixel-format.
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

import pydecklink

# cuda-python is imported lazily inside the run loop so the module can
# be imported (and unit-tested) on hosts without it.


_DEFAULT_MODE = pydecklink.DisplayMode.Mode4K2160p5994
_DEFAULT_PIXEL_FORMAT = pydecklink.PixelFormat.Format10BitYUV

# Pipeline depth: how many frames can be in flight from capture
# submission to consumer release. Must match the device-buffer pool
# size and event count.
#
# Why 3: capture-side has frame N being H2D'd, consumer-side has
# frame N-1 being processed, plus 1 slot of slack so capture never
# blocks waiting for a slot. Depth 2 works but is tight — a momentary
# consumer-side stall blocks the capture thread on slot acquisition.
_PIPELINE_DEPTH = 3

# Allocator free-list prefill: with ``input_queue_depth=1`` (default),
# minimum that bridges the no-signal → signal-locked transition is 2.
# 4 is a small safety margin.
_PREFILL = 4


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
# Self-loopback test source (drives a second sub-device for self-testing).
# Same as in ``cuda_pinned_capture.py``; duplicated rather than imported so
# each example reads independently.
# ---------------------------------------------------------------------------


class _SelfSource:
    """Drive a second DeckLink sub-device with neutral-gray to self-loop
    over a BNC jumper. Lifecycle: ``__enter__`` enables output and
    creates the frame pool but does *not* start playback — call
    ``start_playback()`` after input streams are running, then
    ``schedule_next()`` once per captured frame to keep the queue fed.
    """

    PREROLL = 15
    POOL_DEPTH = PREROLL + 5

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
        self._lock = threading.Lock()
        self._playback_started = False
        self._output_enabled = False

    def __enter__(self) -> _SelfSource:
        self._dev.enable_video_output(self._mode)
        self._output_enabled = True
        width = pydecklink.get_mode_width(self._mode)
        height = pydecklink.get_mode_height(self._mode)
        row_bytes = self._dev.row_bytes_for_pixel_format(self._pixel_format, width)
        self._dev.create_frame_pool(
            self.POOL_DEPTH, width, height, row_bytes, self._pixel_format
        )
        return self

    def start_playback(self) -> None:
        for i in range(self.PREROLL):
            self._schedule_one(i * self._duration)
        self._dev.start_scheduled_playback(start_time=0, timescale=self._timescale)
        self._playback_started = True
        self._display_time = self.PREROLL * self._duration

    def _schedule_one(self, display_time: int) -> None:
        mf = self._dev.acquire_output_frame(timeout_ms=1000)
        mf.data[:] = 0x80
        self._dev.schedule_output_frame(
            mf,
            display_time=display_time,
            duration=self._duration,
            timescale=self._timescale,
        )

    def schedule_next(self) -> None:
        """Schedule one more output frame. Thread-safe — the capture
        thread calls this from inside its hot loop."""
        with self._lock:
            self._schedule_one(self._display_time)
            self._display_time += self._duration

    def __exit__(self, *_exc: object) -> None:
        if self._playback_started:
            with contextlib.suppress(RuntimeError):
                self._dev.stop_scheduled_playback()
        if self._output_enabled:
            with contextlib.suppress(RuntimeError):
                self._dev.disable_video_output()


# ---------------------------------------------------------------------------
# Pipeline: GPU buffer slots + capture/consumer threads.
# ---------------------------------------------------------------------------


class _Slot:
    """One GPU pipeline slot: device pointer + reusable CUDA event."""

    __slots__ = ("d_ptr", "event")

    def __init__(self, d_ptr: int, event: object) -> None:
        self.d_ptr = d_ptr
        self.event = event


class _Frame:
    """An in-flight frame handed from capture thread to consumer thread."""

    __slots__ = ("callback_arrived_us", "cfr", "slot", "submit_us")

    def __init__(
        self,
        cfr: object,
        slot: _Slot,
        callback_arrived_us: int,
        submit_us: int,
    ) -> None:
        self.cfr = cfr
        self.slot = slot
        self.callback_arrived_us = callback_arrived_us
        self.submit_us = submit_us


class _Pipeline:
    """GPU buffer pool + the two thread bodies.

    Slots are reused round-robin: capture thread pops a free slot,
    submits H2D into ``slot.d_ptr``, records ``slot.event``, hands the
    slot to the consumer via ``in_flight``. Consumer waits on the
    event, releases the CaptureFrameRef (which returns the SDK buffer
    to the allocator's free-list), and pushes the slot back to
    ``free_slots``.
    """

    def __init__(
        self,
        frame_bytes: int,
        depth: int,
        cudart: object,
    ) -> None:
        self._cudart = cudart
        self._frame_bytes = frame_bytes
        self.frames_captured = 0
        self.frames_dropped_no_slot = 0
        self.frames_dropped_no_signal = 0
        self.delivery_us: list[float] = []  # callback → consumer release
        self.h2d_gpu_us: list[float] = []  # GPU-timeline H2D event elapsed
        # CUDA stream for all transfers.
        err, stream = cudart.cudaStreamCreate()
        _check(err, "cudaStreamCreate")
        self._stream = stream
        # Allocate slot pool.
        self._slots: list[_Slot] = []
        for _ in range(depth):
            err, d_ptr = cudart.cudaMalloc(frame_bytes)
            _check(err, "cudaMalloc")
            err, ev = cudart.cudaEventCreate()
            _check(err, "cudaEventCreate")
            self._slots.append(_Slot(d_ptr=int(d_ptr), event=ev))
        # Free-slot queue (capture thread pops; consumer thread pushes).
        self.free_slots: queue.Queue[_Slot] = queue.Queue(maxsize=depth)
        for s in self._slots:
            self.free_slots.put_nowait(s)
        # In-flight queue (capture thread pushes; consumer thread pops).
        self.in_flight: queue.Queue[_Frame] = queue.Queue(maxsize=depth)

    def close(self) -> None:
        cudart = self._cudart
        for s in self._slots:
            cudart.cudaEventDestroy(s.event)
            cudart.cudaFree(s.d_ptr)
        cudart.cudaStreamDestroy(self._stream)

    def capture_loop(
        self,
        dev: pydecklink.Device,
        stop: threading.Event,
        source: _SelfSource | None,
    ) -> None:
        """Capture-thread body: pop → H2D submit → handoff. Never waits
        for H2D; the consumer thread does that. Drops frames if the
        in_flight queue is full (consumer is behind)."""
        cudart = self._cudart
        H2D = cudart.cudaMemcpyKind.cudaMemcpyHostToDevice
        while not stop.is_set():
            try:
                slot = self.free_slots.get(timeout=0.1)
            except queue.Empty:
                continue
            cfr = dev.pop_capture_frame_ref(timeout_ms=100)
            if cfr is None:
                self.free_slots.put_nowait(slot)
                continue
            if not cfr.has_signal:
                self.frames_dropped_no_signal += 1
                self.free_slots.put_nowait(slot)
                continue
            # Submit H2D and record the event. ``cfr.data.ctypes.data``
            # is the SDK's pinned buffer pointer (zero-copy view); the
            # CaptureFrameRef keeps the SDK frame alive until the
            # consumer releases it.
            host_ptr = int(cfr.data.ctypes.data)
            (err,) = cudart.cudaMemcpyAsync(
                slot.d_ptr,
                host_ptr,
                self._frame_bytes,
                H2D,
                self._stream,
            )
            _check(err, "cudaMemcpyAsync")
            (err,) = cudart.cudaEventRecord(slot.event, self._stream)
            _check(err, "cudaEventRecord")
            frame = _Frame(
                cfr=cfr,
                slot=slot,
                callback_arrived_us=cfr.callback_arrived_us,
                submit_us=pydecklink.clock_us(),
            )
            try:
                self.in_flight.put_nowait(frame)
            except queue.Full:
                # Consumer is behind — drop this frame. The cfr goes
                # out of scope here, releasing the SDK buffer.
                self.frames_dropped_no_slot += 1
                self.free_slots.put_nowait(slot)
                continue
            if source is not None:
                source.schedule_next()

    def consumer_loop(self, stop: threading.Event) -> None:
        """Consumer-thread body: wait on event → release SDK frame →
        recycle slot. A real consumer would run kernels between the
        event-sync and the slot release; we just measure end-to-end
        delivery latency.
        """
        cudart = self._cudart
        while not stop.is_set() or not self.in_flight.empty():
            try:
                frame = self.in_flight.get(timeout=0.1)
            except queue.Empty:
                continue
            (err,) = cudart.cudaEventSynchronize(frame.slot.event)
            _check(err, "cudaEventSynchronize")
            done_us = pydecklink.clock_us()
            self.delivery_us.append(float(done_us - frame.callback_arrived_us))
            self.frames_captured += 1
            # Hold slot in a local before dropping the frame.
            slot = frame.slot
            # Drop the CaptureFrameRef → SDK buffer recycles to free-list.
            frame.cfr = None  # explicit release
            del frame
            # Return the slot to the pool. Ready for capture thread to reuse.
            self.free_slots.put_nowait(slot)

    def report(self, run_seconds: float) -> None:
        n = self.frames_captured
        if n == 0:
            print(f"[pipelined] no frames captured in {run_seconds:.1f}s.")
            return
        qs = (50.0, 95.0, 99.0)
        d = _percentiles(self.delivery_us, qs)
        print(
            f"[pipelined] frames={n} dropped="
            f"(no_slot={self.frames_dropped_no_slot}, "
            f"no_signal={self.frames_dropped_no_signal})"
        )
        print(
            f"            run={run_seconds:.1f}s  "
            f"effective_fps={n / run_seconds:.1f}  "
            f"({self._frame_bytes / 1_000_000:.2f} MB/frame)"
        )
        print("            min     p50     p95     p99     max     (microseconds)")
        print(
            "  delivery"
            f"  {min(self.delivery_us):>6.0f}  {d[50]:>6.0f}  "
            f"{d[95]:>6.0f}  {d[99]:>6.0f}  {max(self.delivery_us):>6.0f}"
        )


# ---------------------------------------------------------------------------
# Run loop: setup, threading, GC config, teardown.
# ---------------------------------------------------------------------------


def run_pipelined(
    device_index: int = 0,
    mode: pydecklink.DisplayMode = _DEFAULT_MODE,
    pixel_format: pydecklink.PixelFormat = _DEFAULT_PIXEL_FORMAT,
    frame_count: int = 0,
    duration_seconds: float = 0.0,
    source_device_index: int | None = None,
) -> None:
    """Run the pipeline until ``frame_count`` frames are captured (if
    > 0) or ``duration_seconds`` elapse (if > 0), or SIGINT is
    received. Either bound is the first to fire.
    """
    from cuda.bindings import runtime as cudart

    def cuda_host_alloc(size: int) -> int:
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
    frame_bytes = pydecklink.get_frame_bytes(mode, pixel_format)
    width = pydecklink.get_mode_width(mode)
    height = pydecklink.get_mode_height(mode)

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
            input_queue_depth=1,
        )
        in_alloc = provider.get_allocator(
            buffer_size=frame_bytes,
            width=width,
            height=height,
            row_bytes=frame_bytes // height,
            pixel_format=pixel_format,
        )
        in_alloc.prefill(_PREFILL)

        pipeline = _Pipeline(frame_bytes, _PIPELINE_DEPTH, cudart)

        dev.start_streams()
        if src is not None:
            src.start_playback()

        # ----- GC tuning for the hot loop -----
        # Allocations in the threads are bounded (Slot/Frame dataclasses
        # cycle through pre-sized queues). After warm-up there should be
        # no garbage, but freeze the current set so the cycle collector
        # never re-scans them, then disable automatic collection. Tip:
        # add ``gc.collect()`` at known idle points if your real
        # consumer creates cycles.
        gc.collect()
        gc.freeze()
        gc.disable()

        stop = threading.Event()

        def _on_sigint(_sig: int, _frame: object) -> None:
            stop.set()

        prev_sigint = signal.signal(signal.SIGINT, _on_sigint)

        capture_thread = threading.Thread(
            target=pipeline.capture_loop,
            args=(dev, stop, src),
            name="decklink-capture",
            daemon=True,
        )
        consumer_thread = threading.Thread(
            target=pipeline.consumer_loop,
            args=(stop,),
            name="decklink-consumer",
            daemon=True,
        )

        started = time.monotonic()
        capture_thread.start()
        consumer_thread.start()

        last_status = 0.0
        try:
            while not stop.is_set():
                now = time.monotonic()
                elapsed = now - started
                if frame_count > 0 and pipeline.frames_captured >= frame_count:
                    break
                if duration_seconds > 0 and elapsed >= duration_seconds:
                    break
                if now - last_status >= 0.5:
                    state = (
                        "running"
                        if pipeline.frames_captured > 0
                        else "waiting for signal"
                    )
                    _print_status(
                        f"{state}: {int(elapsed)}s elapsed, "
                        f"{pipeline.frames_captured} captured "
                        f"(dropped no_slot={pipeline.frames_dropped_no_slot} "
                        f"no_signal={pipeline.frames_dropped_no_signal})"
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

        # Re-enable GC and restore SIGINT before teardown.
        gc.enable()
        signal.signal(signal.SIGINT, prev_sigint)

        try:
            pipeline.report(run_seconds)
            print(
                f"[allocator] allocated={in_alloc.allocated_count} "
                f"recycled={in_alloc.recycled_count}"
            )
        finally:
            pipeline.close()
            dev.stop_streams()
            dev.disable_video_input()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Threaded DeckLink → CUDA H2D capture pipeline.",
    )
    parser.add_argument(
        "--device",
        type=int,
        default=0,
        help="DeckLink device index for capture.",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=0,
        help="Stop after N captured frames. 0 = unlimited (use --duration or Ctrl-C).",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Stop after S seconds of capture. 0 = unlimited.",
    )
    parser.add_argument(
        "--pixel-format",
        choices=["8bit", "10bit"],
        default="10bit",
        help="10bit (default, v210, ~22 MB/frame at 4K) or 8bit "
        "(2vuy, ~8 MB/frame at 4K).",
    )
    parser.add_argument(
        "--source",
        choices=["external", "self"],
        default="external",
        help=(
            "external: capture from an external SDI source on --device. "
            "self: drive --source-device as output with neutral-gray "
            "(BNC jumper required between the two ports)."
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

    if args.frames == 0 and args.duration == 0.0:
        # Default: 5 seconds.
        args.duration = 5.0

    devices = pydecklink.list_devices()
    if args.device >= len(devices):
        print(
            f"Device index {args.device} out of range ({len(devices)} devices found).",
            file=sys.stderr,
        )
        sys.exit(1)

    source_device_index: int | None = None
    if args.source == "self":
        if args.source_device == args.device:
            print(
                f"--source-device must differ from --device (both = {args.device}).",
                file=sys.stderr,
            )
            sys.exit(1)
        if args.source_device >= len(devices):
            print(
                f"--source-device {args.source_device} out of range.", file=sys.stderr
            )
            sys.exit(1)
        source_device_index = args.source_device

    run_pipelined(
        device_index=args.device,
        pixel_format=pixel_format,
        frame_count=args.frames,
        duration_seconds=args.duration,
        source_device_index=source_device_index,
    )


if __name__ == "__main__":
    main()
