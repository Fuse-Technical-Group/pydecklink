"""Canonical SDI -> CUDA -> SDI passthrough recipe with synchronized
output fanout.

Captures from one DeckLink sub-device into pinned CUDA memory, runs a
Python-callable kernel on each frame on a CUDA stream, fans the kernel
result out to *every* non-input sub-device via N parallel D2H copies
into N pinned output pools, and schedules the resulting frames on a
shared SDK playback group so all outputs present each scheduled frame
at the same wall-clock instant.

Implements §spec:canonical-gpu-passthrough +
§spec:synchronized-output-fanout / §road:cuda-passthrough-fanout.

Pipeline (with N = number of outputs auto-discovered):

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
                              N x D2H N bytes (one per output)
                                       v
                            [pinned output frame_0..N-1]
                                       |
                       schedule_output_frame on each output device
                                       v
                    DeckLink DMA -> SDI cable (x N, in lockstep)

Threading mirrors ``cuda_loopback_latency.py``: a capture thread
submits H2D + kernel + N D2H, a consumer thread waits on the post-D2H
event and schedules the output frames, and the main thread runs the
lifecycle. The default kernel is identity (``cudaMemcpyAsync``
device-to-device on the stream) — true passthrough so consumers can
verify wiring before plugging in their own kernel.

Defaults: 4K UHD 59.94p, 10-bit YUV 4:2:2 (v210). Outputs are every
non-input sub-device on the host. With a 4-sub-device card and
``--input 2`` the discovered outputs are ``[0, 1, 3]``; with a
2-sub-device card the sync group degenerates and is not configured.

Consumers replace the kernel by importing the example as a module and
passing their own callable to ``run_passthrough``::

    from examples import cuda_passthrough

    def my_kernel(stream, d_in, d_out, width, height, frame_bytes):
        ...  # cudaLaunchKernel / cupy / numba / etc.

    cuda_passthrough.run_passthrough(
        input_device_index=2,
        kernel=my_kernel,
        duration_seconds=5.0,
    )

Usage:
    uv run examples/cuda_passthrough.py --input 2 --duration 5

Install:
    uv pip install -e ".[cuda-examples]"
"""

from __future__ import annotations

import argparse
import contextlib
import gc
import os
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
# scheduling. Each output gets an independent pool of this depth.
_POOL_DEPTH = _PREROLL + 5

# Input allocator prefill: minimum that bridges the no-signal ->
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

# SDK playback-group ID type is int64_t. Truncate the PID into that
# range so each process gets a distinct group; same-process retries
# reuse the PID, cross-process invocations get distinct IDs.
_GROUP_ID_MASK = (1 << 63) - 1


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
# Output discovery: every non-input sub-device the host exposes.
# ---------------------------------------------------------------------------


def _discover_output_indices(input_device_index: int) -> list[int]:
    """Return playback-capable sub-device indices, excluding the input.
    Order matches ``list_devices()`` so the first output is the lowest
    index — the "primary" output for delivery-latency reporting.

    Per §spec:synchronized-output-fanout, the example fans out to every
    non-input sub-device on the host. Capture-only devices are skipped.
    """
    devices = pydecklink.list_devices()
    if input_device_index >= len(devices) or input_device_index < 0:
        raise ValueError(
            f"--input={input_device_index} out of range ({len(devices)} devices found)."
        )
    outputs: list[int] = []
    for info in devices:
        if info.index == input_device_index:
            continue
        # Open just long enough to query supports_playback. Devices
        # that lack output capability (e.g. a single-direction capture
        # card) cannot participate.
        with pydecklink.Device(index=info.index) as dev:
            if dev.supports_playback:
                outputs.append(info.index)
    return outputs


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
# Sync-group setup: probe capability, assign group ID, enable each
# output with the SynchronizeToPlaybackGroup flag.
# ---------------------------------------------------------------------------


def _configure_sync_group(
    out_devs: list[pydecklink.Device],
    mode: pydecklink.DisplayMode,
    group_id: int,
) -> None:
    """Configure ``out_devs`` as a single playback sync group at
    ``group_id`` and enable video output on each with the
    SynchronizeToPlaybackGroup flag. Raises ``RuntimeError`` if any
    device lacks the SupportsSynchronizeToPlaybackGroup capability —
    fail fast rather than discover the misconfiguration as silent
    drift at runtime.
    """
    for dev in out_devs:
        if not dev.get_attribute_flag(
            pydecklink.AttributeID.SupportsSynchronizeToPlaybackGroup
        ):
            raise RuntimeError(
                f"device {dev.display_name!r} does not support "
                "SynchronizeToPlaybackGroup; cannot fan out across "
                "this hardware."
            )
    for dev in out_devs:
        dev.set_config_int(pydecklink.ConfigurationID.PlaybackGroup, group_id)
        dev.enable_video_output(
            mode,
            int(pydecklink.VideoOutputFlag.SynchronizeToPlaybackGroup),
        )


def _start_sync_group(
    out_devs: list[pydecklink.Device],
    frame_timescale: int,
) -> None:
    """Start scheduled playback on the group leader (``out_devs[0]``).

    Per SDK §2.4.13.2, ``StartScheduledPlayback`` on any one output in
    a playback group releases the whole group on a common SDI frame
    boundary; arming additional members returns HRESULT 0x80000008
    ("group already started"). The single-output (no group engaged)
    path uses the same call — there's just nothing to fan out to.
    """
    out_devs[0].start_scheduled_playback(start_time=0, timescale=frame_timescale)


# ---------------------------------------------------------------------------
# Pipeline: GPU input/output slots + capture/consumer threads.
# ---------------------------------------------------------------------------


class _Slot:
    """One GPU pipeline slot: input + single device-output buffer + the
    CUDA event that fires after the **last** D2H of the kernel result.
    The single device output buffer is shared across all output D2Hs:
    the kernel writes once, every D2H reads from the same source.
    """

    __slots__ = ("d_input", "d_output", "ev_done")

    def __init__(self, d_input: int, d_output: int, ev_done: object) -> None:
        self.d_input = d_input
        self.d_output = d_output
        self.ev_done = ev_done


class _Frame:
    """An in-flight frame handed from capture thread to consumer
    thread. Carries the SDK capture-frame ref (so the input buffer
    stays alive until H2D completes), the device pipeline slot, the N
    pinned output ``MutableFrame``s to schedule (one per output device),
    and the wall-clock arrival timestamp for end-to-end latency."""

    __slots__ = ("callback_arrived_us", "cfr", "mfs", "slot")

    def __init__(
        self,
        cfr: object,
        slot: _Slot,
        mfs: list[object],
        callback_arrived_us: int,
    ) -> None:
        self.cfr = cfr
        self.slot = slot
        self.mfs = mfs
        self.callback_arrived_us = callback_arrived_us


class _Pipeline:
    """GPU buffer pool + the two thread bodies.

    Capture thread: pop a free slot, pop a CaptureFrameRef, acquire one
    pool MutableFrame per output, submit ``H2D -> kernel -> N x D2H ->
    event`` on the stream, hand the frame to the consumer.

    Consumer thread: wait on the post-D2H event, schedule each
    MutableFrame on its respective output at the same display time,
    recycle the slot. The CaptureFrameRef goes out of scope at frame
    teardown, returning the SDK input buffer to the allocator's
    free-list.
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
        # Sync-group starvation: at least one output's pool drained
        # while others had free slots. Distinct anomaly from
        # frames_dropped_no_output (where ALL outputs starved together,
        # i.e. consumer-behind under load).
        self.sync_group_starvations = 0
        self._starvation_warned = False
        self.delivery_us: list[float] = []  # callback -> schedule
        # CUDA stream for all transfers + kernel launches.
        err, stream = cudart.cudaStreamCreate()
        _check(err, "cudaStreamCreate")
        self._stream = stream
        # Allocate slot pool: input + single output device buffer +
        # post-D2H event. The kernel writes one device output buffer;
        # N D2H copies fan that single buffer out into N pinned host
        # frames. Per-output device buffers would waste VRAM and force
        # the kernel to write N times.
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

    def _acquire_all_outputs(
        self,
        out_devs: list[pydecklink.Device],
    ) -> list[object] | None:
        """Acquire one MutableFrame from each output's pool, or return
        ``None`` and release any partially acquired frames if any pool
        is starved.

        Sync-group starvation — one pool empty while another has
        frames — is incoherent in a working sync group. Possible
        causes: (1) the group is misconfigured or never engaged,
        (2) one output's underlying device lost signal lock or hit a
        hardware fault, (3) pool depths drifted. Either way scheduling
        a partial set creates permanent timing offset on the starved
        output that the SDK does not auto-correct, so the caller drops
        this frame across all outputs and the partial frames return
        to their pools at scope exit. See §spec:synchronized-output-fanout.
        """
        mfs: list[object] = []
        for i, dev in enumerate(out_devs):
            try:
                mfs.append(dev.acquire_output_frame(timeout_ms=100))
            except RuntimeError:
                if mfs:
                    # Partial acquisition: at least one earlier output
                    # had a frame, this one didn't. Confirmed sync-group
                    # starvation. Already-acquired frames drop back to
                    # their pools when ``mfs`` goes out of scope.
                    self._note_sync_group_starvation(dev)
                    return None
                # First output starved with no others tried yet.
                # Probe remaining outputs non-blocking — if any has
                # frames, that confirms starvation (asymmetric pools).
                # Acquired probe-frames go out of scope at loop exit
                # and return to their pools.
                for later_dev in out_devs[i + 1 :]:
                    try:
                        later_dev.acquire_output_frame(timeout_ms=0)
                    except RuntimeError:
                        continue
                    self._note_sync_group_starvation(dev)
                    return None
                # Every output starved together. Plain consumer-behind,
                # not a sync-group anomaly.
                return None
        return mfs

    def _note_sync_group_starvation(self, starved_dev: pydecklink.Device) -> None:
        self.sync_group_starvations += 1
        if not self._starvation_warned:
            self._starvation_warned = True
            print(
                f"WARNING: sync-group starvation on output "
                f"{starved_dev.display_name!r}: one output's pool drained "
                f"while another had free slots. Likely causes: "
                f"(1) the playback group is misconfigured or never engaged; "
                f"(2) this output's underlying device lost signal lock or "
                f"hit a hardware fault; "
                f"(3) pool depths are not equal across outputs. "
                f"Subsequent occurrences are counted in the [anomaly] "
                f"section of the final report.",
                file=sys.stderr,
                flush=True,
            )

    def capture_loop(
        self,
        in_dev: pydecklink.Device,
        out_devs: list[pydecklink.Device],
        stop: threading.Event,
    ) -> None:
        """Capture-thread body: pop frame -> submit H2D + kernel + N x
        D2H -> handoff. Submission is non-blocking; the consumer waits
        on the post-D2H event and does the scheduling work."""
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
            # Acquire one output frame from each output's pinned pool.
            # All-or-nothing: a partial acquisition triggers a sync-group
            # starvation event (see _acquire_all_outputs).
            mfs = self._acquire_all_outputs(out_devs)
            if mfs is None:
                self.frames_dropped_no_output += 1
                self.free_slots.put_nowait(slot)
                continue
            host_in = int(cfr.data.ctypes.data)
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
            # N D2H copies on the same stream — one per output. All
            # read from slot.d_output; each writes to its own pinned
            # output frame. The N copies serialize on the single stream,
            # avoiding CPU pixel touches.
            for mf in mfs:
                host_out = int(mf.data.ctypes.data)
                (err,) = cudart.cudaMemcpyAsync(
                    host_out, slot.d_output, self._frame_bytes, D2H, self._stream
                )
                _check(err, "cudaMemcpyAsync(D2H)")
            # Event after the last D2H — consumer syncs on this before
            # handing the pinned buffers to the SDK for DMA.
            (err,) = cudart.cudaEventRecord(slot.ev_done, self._stream)
            _check(err, "cudaEventRecord(done)")
            frame = _Frame(
                cfr=cfr,
                slot=slot,
                mfs=mfs,
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
        out_devs: list[pydecklink.Device],
        frame_duration: int,
        frame_timescale: int,
        stop: threading.Event,
    ) -> None:
        """Consumer-thread body: wait on D2H event -> schedule each
        output's frame at the same display time -> release input cfr ->
        recycle slot."""
        cudart = self._cudart
        # Output display time runs ahead by _PREROLL frames; preroll
        # has already scheduled 0..PREROLL-1 on each output, so the
        # first consumer frame goes out at PREROLL.
        display_time = _PREROLL * frame_duration
        while not stop.is_set() or not self.in_flight.empty():
            try:
                frame = self.in_flight.get(timeout=0.1)
            except queue.Empty:
                continue
            (err,) = cudart.cudaEventSynchronize(frame.slot.ev_done)
            _check(err, "cudaEventSynchronize")
            # Schedule the same display_time on every output. The SDK
            # playback group aligns presentation across outputs; this
            # loop submits N independent ScheduleVideoFrame calls.
            for dev, mf in zip(out_devs, frame.mfs, strict=True):
                dev.schedule_output_frame(
                    mf,
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

    def report(
        self,
        run_seconds: float,
        out_devs: list[pydecklink.Device],
    ) -> None:
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
            f"({self._frame_bytes / 1_000_000:.2f} MB/frame)  "
            f"outputs={len(out_devs)}"
        )
        print("              min     p50     p95     p99     max     (microseconds)")
        print(
            "  delivery   "
            f" {min(self.delivery_us):>6.0f}  {d[50]:>6.0f}  "
            f"{d[95]:>6.0f}  {d[99]:>6.0f}  {max(self.delivery_us):>6.0f}"
        )
        for dev in out_devs:
            status = dev.output_status
            print(
                f"[output {dev.display_name!r}]  completed={status.completed} "
                f"late={status.late} dropped={status.dropped} "
                f"flushed={status.flushed} "
                f"underrun={status.underrun}"
            )
        # [anomaly] block: explicit, non-fatal sync-group event count.
        # Distinct from the dropped= line above because these drops are
        # not equivalent to "consumer behind" or "no signal" — they
        # indicate the sync group is not behaving as a sync group.
        print(f"[anomaly] sync-group starvation events: {self.sync_group_starvations}")


# ---------------------------------------------------------------------------
# Run loop: setup, threading, GC config, teardown.
# ---------------------------------------------------------------------------


def run_passthrough(
    input_device_index: int = 2,
    kernel: KernelFn | None = None,
    pixel_format: pydecklink.PixelFormat = _DEFAULT_PIXEL_FORMAT,
    frame_count: int = 0,
    duration_seconds: float = 0.0,
    output_device_indices: list[int] | None = None,
) -> None:
    """Run the SDI -> CUDA -> SDI fanout passthrough until ``frame_count``
    frames are processed (if > 0) or ``duration_seconds`` elapse (if
    > 0), or SIGINT is received. Either bound is the first to fire.

    The input mode is auto-detected via the SDK's FormatDetection;
    every output is configured to match. ``kernel=None`` (default) runs
    the identity kernel — ``cudaMemcpyAsync`` device-to-device on the
    stream — producing a true passthrough that consumers run unchanged
    to verify their wiring.

    ``output_device_indices=None`` (default) auto-discovers every
    non-input playback-capable sub-device on the host. Consumers with
    selective deployments may pass an explicit list, but the canonical
    recipe takes the host's full topology.
    """
    if output_device_indices is None:
        output_device_indices = _discover_output_indices(input_device_index)
    if input_device_index in output_device_indices:
        raise ValueError(f"input device {input_device_index} cannot also be an output.")
    if not output_device_indices:
        raise RuntimeError(
            f"no output sub-devices discovered (input={input_device_index}). "
            f"This example requires at least one playback device other "
            f"than the input."
        )

    print(f"[fanout] outputs={output_device_indices}", flush=True)

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
    out_devs = [pydecklink.Device(index=i) for i in output_device_indices]

    mode = _detect_input_mode(in_dev, pixel_format, _DETECTION_TIMEOUT_S)
    print(f"[passthrough] detected input mode={mode.name}", flush=True)

    width = pydecklink.get_mode_width(mode)
    height = pydecklink.get_mode_height(mode)
    frame_bytes = pydecklink.get_frame_bytes(mode, pixel_format)
    frame_duration, frame_timescale = pydecklink.get_mode_frame_duration(mode)

    in_provider = pydecklink.VideoBufferAllocatorProvider(alloc=_alloc, free=_free)
    # One pinned output allocator per output device. Sharing across
    # outputs is unsafe — each device's frame pool keeps its own
    # set of buffers in flight; intermixing them would corrupt the
    # SDK's per-device buffer accounting.
    out_allocs = [
        pydecklink.VideoBufferAllocator(frame_bytes, alloc=_alloc, free=_free)
        for _ in out_devs
    ]

    # Sync group: only configure when >= 2 outputs participate. With one
    # output the group "degenerates" — there is nothing to synchronize
    # with — and putting the lone output into a group adds latency for
    # no benefit.
    fanout_engaged = len(out_devs) >= 2
    if fanout_engaged:
        group_id = os.getpid() & _GROUP_ID_MASK
        _configure_sync_group(out_devs, mode, group_id)
        print(
            f"[fanout] sync group engaged group_id={group_id} "
            f"(N={len(out_devs)} outputs)",
            flush=True,
        )
    else:
        # Single-output case: enable normally, no group.
        out_devs[0].enable_video_output(mode)
    try:
        # Build a pinned output pool on every output. Equal depth across
        # outputs is required — unequal depths would themselves manifest
        # as sync-group starvation.
        for dev, alloc in zip(out_devs, out_allocs, strict=True):
            row_bytes = dev.row_bytes_for_pixel_format(pixel_format, width)
            dev.create_frame_pool_pinned(
                _POOL_DEPTH, width, height, row_bytes, pixel_format, alloc
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

        # Pre-roll every output's queue with neutral frames at display
        # times 0..PREROLL-1. The consumer thread continues from
        # PREROLL onwards. Per-output preroll keeps each output's SDK
        # queue at the same depth before scheduled playback starts —
        # asymmetric preroll would manifest as sync-group starvation
        # within the first few frames.
        for i in range(_PREROLL):
            for dev in out_devs:
                mf = dev.acquire_output_frame(timeout_ms=1000)
                mf.data[:] = 0x80  # neutral mid-gray for v210 / 2vuy
                dev.schedule_output_frame(
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

        # GC tuning for the hot loop.
        gc.collect()
        gc.freeze()
        gc.disable()

        stop = threading.Event()

        def _on_sigint(_sig: int, _frame: object) -> None:
            stop.set()

        prev_sigint = signal.signal(signal.SIGINT, _on_sigint)

        capture_thread = threading.Thread(
            target=pipeline.capture_loop,
            args=(in_dev, out_devs, stop),
            name="decklink-capture",
            daemon=True,
        )
        consumer_thread = threading.Thread(
            target=pipeline.consumer_loop,
            args=(out_devs, frame_duration, frame_timescale, stop),
            name="decklink-consumer",
            daemon=True,
        )

        _start_sync_group(out_devs, frame_timescale)

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
                        f"no_output={pipeline.frames_dropped_no_output} "
                        f"sync_starv={pipeline.sync_group_starvations})"
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
            pipeline.report(run_seconds, out_devs)
        finally:
            pipeline.close()
            in_dev.stop_streams()
            in_dev.disable_video_input()
    finally:
        for dev in out_devs:
            with contextlib.suppress(RuntimeError):
                dev.stop_scheduled_playback()
            with contextlib.suppress(RuntimeError):
                dev.disable_video_output()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DeckLink SDI -> CUDA -> SDI passthrough with synchronized "
        "output fanout. Outputs are auto-discovered (every non-input "
        "sub-device).",
    )
    parser.add_argument(
        "--input",
        type=int,
        default=2,
        help="DeckLink device index for capture (default 2).",
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

    pixel_format = (
        pydecklink.PixelFormat.Format10BitYUV
        if args.pixel_format == "10bit"
        else pydecklink.PixelFormat.Format8BitYUV
    )

    devices = pydecklink.list_devices()
    if args.input >= len(devices):
        print(
            f"--input={args.input} out of range ({len(devices)} devices found).",
            file=sys.stderr,
        )
        sys.exit(1)

    run_passthrough(
        input_device_index=args.input,
        pixel_format=pixel_format,
        frame_count=args.frames,
        duration_seconds=args.duration,
    )


if __name__ == "__main__":
    main()
