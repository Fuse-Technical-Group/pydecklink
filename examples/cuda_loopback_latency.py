"""CUDA loopback fingerprint benchmark for round-trip SDI latency.

Two DeckLink sub-devices wired in physical loopback (BNC jumper SDI-out
→ SDI-in). The output side stamps a 64-bit sequence number into the
luma bytes at the start of each output frame; the input side recovers
it from the matching captured frame and reports cable-to-cable RTT.

Implements §spec:latency-characterization / §road:fingerprint-loopback.

Pipeline (no CPU pixel touch on either path):

    [device staging buf] --(encode kernel)-> [device staging buf]
                                              |
                                  D2H 32 bytes |
                                              v
                                  [pinned output frame[0:32]]
                                              |
                              schedule_output |
                                              v
                              SDK DMA host -> wire
                                              |
                                              v
                                            cable
                                              |
                                              v
                              SDK DMA wire -> pinned input frame
                                              |
                                  H2D N bytes |
                                              v
                                    [device pool slot]
                                              |
                                  decode kernel
                                              v
                                    [device result buf]
                                              |
                                   D2H 8 bytes
                                              v
                                       [pinned result]

The decode kernel is bracketed by CUDA events ``ev_start``/``ev_end``;
``kernel_us`` is the GPU-timeline elapsed time. A separate ``ev_done``
records after the result D2H so the consumer thread can sync on it
before reading ``result_host`` — without that event, the consumer
would race the D2H against ``ev_end`` (kernel-done) and read stale
bytes for ~all frames.

``ex_kernel_us = RTT_us - kernel_us`` is the floor a real consumer's
pipeline would see if their kernel ran in zero time. Real consumers
project total RTT as ``ex_kernel_us + their_kernel_us``.

Defaults: 4K UHD 59.94p, 10-bit YUV 4:2:2 (v210), output device 0,
input device 2, 1000 frames or 30s.

Usage:
    python examples/cuda_loopback_latency.py
    python examples/cuda_loopback_latency.py \\
        --output-device 0 --input-device 2 --frames 1000

Install:
    pip install pydecklink[cuda-examples]
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import gc
import queue
import signal
import sys
import threading
import time

import pydecklink

# cuda-python is imported lazily inside run_loopback so the module can be
# imported (and unit-tested) on hosts without it.


_DEFAULT_MODE = pydecklink.DisplayMode.Mode4K2160p5994
_DEFAULT_PIXEL_FORMAT = pydecklink.PixelFormat.Format10BitYUV

# Output preroll: frames queued before start_scheduled_playback. Deeper
# than the input's queue depth so SDI sync has time to lock before the
# first measured frame.
_PREROLL = 8

# Output pool size: preroll + a few slots in-flight for steady-state
# scheduling.
_POOL_DEPTH = _PREROLL + 5

# Input allocator prefill: minimum that bridges no-signal → signal-locked
# transition in zero-copy mode with input_queue_depth=1.
_PREFILL = 4

# Pipeline depth: device-side slots for in-flight H2D + decode.
_PIPELINE_DEPTH = 3

# Fingerprint occupies the first 32 bytes of v210 active video —
# two 16-byte v210 groups, each carrying 6 luma slots, of which the
# first 8 across the two groups hold one byte each of the 64-bit
# sequence number (in the low 8 bits of a 10-bit luma slot). The
# remaining 4 luma slots and all chroma slots are written to
# neutral values. 12 pixels of disturbance in a 3840-wide frame
# is invisible.
_FINGERPRINT_BYTES = 32

# v210 component values for the bit-packing helpers.
_V210_LUMA_NEUTRAL = 0x200  # ~mid-range 10-bit luma (used for unused slots).
_V210_CHROMA_NEUTRAL = 0x200  # ~mid-range 10-bit chroma (neutral gray).


# ---------------------------------------------------------------------------
# CUDA kernel source (compiled at runtime via NVRTC).
# ---------------------------------------------------------------------------

#
# v210 packing recap (one group = 16 bytes = 4 little-endian 32-bit words):
#   word 0:  Cb0 [0..9]   |  Y0 [10..19]  |  Cr0 [20..29]
#   word 1:  Y1 [0..9]    |  Cb2 [10..19] |  Y2 [20..29]
#   word 2:  Cr2 [0..9]   |  Y3 [10..19]  |  Cb4 [20..29]
#   word 3:  Y4 [0..9]    |  Cr4 [10..19] |  Y5 [20..29]
# Two top bits of each 32-bit word are reserved (zero). Luma slots are
# Y0..Y5 across the 4 words. Sequence-number byte ``i`` is placed in
# luma slot ``i`` across two consecutive groups (slots 0..5 in group
# 0, slots 6..7 in group 1; remaining luma slots in group 1 hold
# neutral 0x200).
_KERNEL_SOURCE = r"""
extern "C" {

#define V210_LUMA_NEUTRAL   0x200u
#define V210_CHROMA_NEUTRAL 0x200u

// Pack three 10-bit components into a v210 32-bit word (little-endian).
__device__ unsigned int v210_word(unsigned int c0, unsigned int c1, unsigned int c2) {
    return (c0 & 0x3FFu) | ((c1 & 0x3FFu) << 10) | ((c2 & 0x3FFu) << 20);
}

// Extract the three 10-bit components from a v210 word.
__device__ void v210_unpack(unsigned int w, unsigned int* c0,
                            unsigned int* c1, unsigned int* c2) {
    *c0 = w & 0x3FFu;
    *c1 = (w >> 10) & 0x3FFu;
    *c2 = (w >> 20) & 0x3FFu;
}

__global__ void encode_fingerprint(unsigned char* dst, unsigned long long seq) {
    if (threadIdx.x != 0) return;
    unsigned int* w = (unsigned int*)dst;
    // Eight luma slots Y0..Y7 carry seq[0..7]; chroma neutral. Group 0
    // word layout: (Cb0, Y0, Cr0), (Y1, Cb2, Y2), (Cr2, Y3, Cb4),
    //              (Y4, Cr4, Y5).
    //
    // Encoded luma = byte | 0x100 — keeps every 10-bit luma value in
    // [256, 511], well clear of the SMPTE-reserved sync codes
    // (0x000-0x003 and 0x3FC-0x3FF). DeckLink hardware silently
    // rewrites in-band sync codes to 0x004, which collapses any
    // zero-valued seq byte to 0x04 on capture and corrupts the
    // recovered seq for all frames where some byte is < 4.
    unsigned int y[8];
    for (int i = 0; i < 8; ++i) {
        y[i] = (unsigned int)((seq >> (i * 8)) & 0xFFu) | 0x100u;
    }
    // Group 0.
    w[0] = v210_word(V210_CHROMA_NEUTRAL, y[0], V210_CHROMA_NEUTRAL);
    w[1] = v210_word(y[1], V210_CHROMA_NEUTRAL, y[2]);
    w[2] = v210_word(V210_CHROMA_NEUTRAL, y[3], V210_CHROMA_NEUTRAL);
    w[3] = v210_word(y[4], V210_CHROMA_NEUTRAL, y[5]);
    // Group 1.
    w[4] = v210_word(V210_CHROMA_NEUTRAL, y[6], V210_CHROMA_NEUTRAL);
    w[5] = v210_word(y[7], V210_CHROMA_NEUTRAL, V210_LUMA_NEUTRAL);
    w[6] = v210_word(V210_CHROMA_NEUTRAL, V210_LUMA_NEUTRAL, V210_CHROMA_NEUTRAL);
    w[7] = v210_word(V210_LUMA_NEUTRAL, V210_CHROMA_NEUTRAL, V210_LUMA_NEUTRAL);
}

__global__ void decode_fingerprint(const unsigned char* src,
                                   unsigned long long* result) {
    if (threadIdx.x != 0) return;
    const unsigned int* w = (const unsigned int*)src;
    unsigned int c0, c1, c2;
    unsigned int y[8];
    // Group 0 luma slots.
    v210_unpack(w[0], &c0, &y[0], &c1);
    v210_unpack(w[1], &y[1], &c0, &y[2]);
    v210_unpack(w[2], &c0, &y[3], &c1);
    v210_unpack(w[3], &y[4], &c0, &y[5]);
    // Group 1 luma slots 0..1 (slots 2..5 are unused).
    v210_unpack(w[4], &c0, &y[6], &c1);
    v210_unpack(w[5], &y[7], &c0, &c1);
    unsigned long long seq = 0;
    for (int i = 0; i < 8; ++i) {
        seq |= ((unsigned long long)(y[i] & 0xFFu)) << (i * 8);
    }
    *result = seq;
}

}
"""


# ---------------------------------------------------------------------------
# Pure-Python reference encode/decode. Validates the kernel logic at
# review time and unit-test time. The CUDA kernels above must match.
# ---------------------------------------------------------------------------


def _v210_pack(c0: int, c1: int, c2: int) -> int:
    """Pack three 10-bit components into a v210 32-bit word."""
    return (c0 & 0x3FF) | ((c1 & 0x3FF) << 10) | ((c2 & 0x3FF) << 20)


def _v210_unpack(word: int) -> tuple[int, int, int]:
    """Extract three 10-bit components from a v210 word."""
    return (word & 0x3FF, (word >> 10) & 0x3FF, (word >> 20) & 0x3FF)


def _encode_fingerprint_cpu(buf: bytearray, seq: int) -> None:
    """Reference for the encode kernel. Writes the 32-byte v210 pattern
    at ``buf[0:32]`` carrying ``seq`` in 8 luma slots across two groups.

    Each seq byte is OR'd with 0x100 to lift it above the SMPTE-reserved
    sync-code range (0x000-0x003); without this, DeckLink hardware
    rewrites zero-valued bytes to 0x04 in flight."""
    seq_bytes = seq.to_bytes(8, "little", signed=False)
    y = [b | 0x100 for b in seq_bytes]  # luma value in [256, 511]
    cn = _V210_CHROMA_NEUTRAL
    yn = _V210_LUMA_NEUTRAL
    words = [
        _v210_pack(cn, y[0], cn),
        _v210_pack(y[1], cn, y[2]),
        _v210_pack(cn, y[3], cn),
        _v210_pack(y[4], cn, y[5]),
        _v210_pack(cn, y[6], cn),
        _v210_pack(y[7], cn, yn),
        _v210_pack(cn, yn, cn),
        _v210_pack(yn, cn, yn),
    ]
    for i, w in enumerate(words):
        buf[4 * i : 4 * i + 4] = w.to_bytes(4, "little")


def _decode_fingerprint_cpu(buf: bytearray | bytes) -> int:
    """Reference for the decode kernel. Recovers the sequence number
    from the 8 luma slots in ``buf[0:32]``."""
    words = [int.from_bytes(buf[4 * i : 4 * i + 4], "little") for i in range(8)]
    # Group 0 luma: word0[mid], word1[low/high], word2[mid], word3[low/high].
    # Group 1 luma: word4[mid], word5[low].
    _, y0, _ = _v210_unpack(words[0])
    y1, _, y2 = _v210_unpack(words[1])
    _, y3, _ = _v210_unpack(words[2])
    y4, _, y5 = _v210_unpack(words[3])
    _, y6, _ = _v210_unpack(words[4])
    y7, _, _ = _v210_unpack(words[5])
    luma = [y0, y1, y2, y3, y4, y5, y6, y7]
    return int.from_bytes(bytes(v & 0xFF for v in luma), "little")


# ---------------------------------------------------------------------------
# Stats helpers.
# ---------------------------------------------------------------------------


def _percentiles(samples: list[float], qs: tuple[float, ...]) -> dict[float, float]:
    if not samples:
        return {q: 0.0 for q in qs}
    s = sorted(samples)
    n = len(s)
    return {q: s[max(0, min(n - 1, round(q / 100.0 * (n - 1))))] for q in qs}


def _print_status(line: str) -> None:
    sys.stdout.write(f"\r{line}\033[K")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# CUDA error checking + NVRTC compilation.
# ---------------------------------------------------------------------------


def _check_cuda(err: object, op: str) -> None:
    code = getattr(err, "value", err)
    if code != 0:
        raise RuntimeError(f"{op} failed: cudaError={code}")


def _check_driver(err: object, op: str) -> None:
    code = getattr(err, "value", err)
    if code != 0:
        raise RuntimeError(f"{op} failed: CUresult={code}")


def _check_nvrtc(err: object, op: str) -> None:
    code = getattr(err, "value", err)
    if code != 0:
        raise RuntimeError(f"{op} failed: nvrtcResult={code}")


def _compile_kernel_source(source: str) -> bytes:
    """Compile a CUDA source string to PTX via NVRTC. Raises with the
    compile log on failure."""
    from cuda.bindings import nvrtc

    err, prog = nvrtc.nvrtcCreateProgram(
        source.encode("utf-8"),
        b"fingerprint.cu",
        0,
        [],
        [],
    )
    _check_nvrtc(err, "nvrtcCreateProgram")
    try:
        # compute_75 (Turing, 2018) is the oldest arch still supported by
        # current CUDA toolkits and covers anything a DeckLink-equipped
        # workstation is likely to have. PTX is JIT-recompiled to the
        # device's actual SM by cuModuleLoadData.
        opts = [b"--gpu-architecture=compute_75", b"--std=c++14"]
        (err,) = nvrtc.nvrtcCompileProgram(prog, len(opts), opts)
        if getattr(err, "value", err) != 0:
            err2, log_size = nvrtc.nvrtcGetProgramLogSize(prog)
            _check_nvrtc(err2, "nvrtcGetProgramLogSize")
            log = b" " * log_size
            (err2,) = nvrtc.nvrtcGetProgramLog(prog, log)
            _check_nvrtc(err2, "nvrtcGetProgramLog")
            raise RuntimeError(
                "NVRTC compile failed:\n" + log.decode("utf-8", errors="replace")
            )
        err, ptx_size = nvrtc.nvrtcGetPTXSize(prog)
        _check_nvrtc(err, "nvrtcGetPTXSize")
        ptx = b" " * ptx_size
        (err,) = nvrtc.nvrtcGetPTX(prog, ptx)
        _check_nvrtc(err, "nvrtcGetPTX")
        return ptx
    finally:
        nvrtc.nvrtcDestroyProgram(prog)


# ---------------------------------------------------------------------------
# Output thread: encode kernel + D2H into pinned frame + schedule.
# ---------------------------------------------------------------------------


class _OutputDriver:
    """Drives the output device with fingerprinted frames at a constant
    cadence, free-running clock."""

    def __init__(
        self,
        dev: pydecklink.Device,
        encode_fn: object,
        cuda_driver: object,
        cudart: object,
        stream: object,
        staging_dptr: int,
        mode: pydecklink.DisplayMode,
    ) -> None:
        self._dev = dev
        self._encode_fn = encode_fn
        self._cuda = cuda_driver
        self._cudart = cudart
        self._stream = stream
        self._staging_dptr = staging_dptr
        duration, timescale = pydecklink.get_mode_frame_duration(mode)
        self._duration = duration
        self._timescale = timescale
        self.frame_period_us = 1_000_000.0 * duration / timescale
        self.t_playback_start_us = 0
        self._next_seq = 0
        self._lock = threading.Lock()

    def _encode_into(self, host_ptr: int, seq: int) -> None:
        """Run encode kernel and D2H 32 bytes (two v210 groups) into
        ``host_ptr``. Synchronizes the stream so the SDK can DMA the
        frame safely."""
        cuda = self._cuda
        cudart = self._cudart
        # Pack args: (uint8_t* dst, unsigned long long seq).
        dst_arg = ctypes.c_void_p(int(self._staging_dptr))
        seq_arg = ctypes.c_uint64(int(seq))
        arg_ptrs = (ctypes.c_void_p * 2)(
            ctypes.addressof(dst_arg), ctypes.addressof(seq_arg)
        )
        (err,) = cuda.cuLaunchKernel(
            self._encode_fn,
            1,
            1,
            1,  # grid
            8,
            1,
            1,  # block: 8 threads, one per fingerprint byte
            0,  # shared mem
            self._stream,
            arg_ptrs,
            0,
        )
        _check_driver(err, "cuLaunchKernel(encode)")
        D2H = cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost
        (err,) = cudart.cudaMemcpyAsync(
            host_ptr, self._staging_dptr, _FINGERPRINT_BYTES, D2H, self._stream
        )
        _check_cuda(err, "cudaMemcpyAsync(encode→host)")
        (err,) = cudart.cudaStreamSynchronize(self._stream)
        _check_cuda(err, "cudaStreamSynchronize")

    def schedule_one(self) -> int:
        """Acquire one output frame, fingerprint it on GPU, schedule.
        Returns the sequence number assigned. Thread-safe."""
        with self._lock:
            seq = self._next_seq
            self._next_seq += 1
            mf = self._dev.acquire_output_frame(timeout_ms=1000)
            host_ptr = int(mf.data.ctypes.data)
            self._encode_into(host_ptr, seq)
            self._dev.schedule_output_frame(
                mf,
                display_time=seq * self._duration,
                duration=self._duration,
                timescale=self._timescale,
            )
            return seq

    def egress_us(self, seq: int) -> float:
        """Estimated wall-clock time when frame ``seq`` hits the wire."""
        return self.t_playback_start_us + seq * self.frame_period_us


# ---------------------------------------------------------------------------
# Pipeline: GPU buffer slots + decode kernel + events.
# ---------------------------------------------------------------------------


class _Slot:
    __slots__ = ("d_ptr", "ev_done", "ev_end", "ev_start", "result_dptr", "result_host")

    def __init__(
        self,
        d_ptr: int,
        ev_start: object,
        ev_end: object,
        ev_done: object,
        result_dptr: int,
        result_host: ctypes.Array[ctypes.c_uint8],
    ) -> None:
        self.d_ptr = d_ptr
        self.ev_start = ev_start
        self.ev_end = ev_end
        self.ev_done = ev_done
        self.result_dptr = result_dptr
        self.result_host = result_host


class _CapturedFrame:
    __slots__ = ("callback_arrived_us", "cfr", "slot")

    def __init__(self, cfr: object, slot: _Slot, callback_arrived_us: int) -> None:
        self.cfr = cfr
        self.slot = slot
        self.callback_arrived_us = callback_arrived_us


class _InputPipeline:
    """Capture → H2D → decode kernel → D2H result. Two threads:
    capture submits, consumer waits and computes RTT."""

    def __init__(
        self,
        frame_bytes: int,
        depth: int,
        decode_fn: object,
        cuda_driver: object,
        cudart: object,
        output_driver: _OutputDriver,
    ) -> None:
        self._cuda = cuda_driver
        self._cudart = cudart
        self._frame_bytes = frame_bytes
        self._decode_fn = decode_fn
        self._output = output_driver
        self.rtt_us: list[float] = []
        self.kernel_us: list[float] = []
        self.frames_captured = 0
        self.frames_dropped_no_slot = 0
        self.frames_dropped_no_signal = 0
        # Stream + slot pool.
        err, stream = cudart.cudaStreamCreate()
        _check_cuda(err, "cudaStreamCreate")
        self._stream = stream
        self._slots: list[_Slot] = []
        for _ in range(depth):
            err, d_ptr = cudart.cudaMalloc(frame_bytes)
            _check_cuda(err, "cudaMalloc(frame)")
            err, result_dptr = cudart.cudaMalloc(8)
            _check_cuda(err, "cudaMalloc(result)")
            err, ev_start = cudart.cudaEventCreate()
            _check_cuda(err, "cudaEventCreate(start)")
            err, ev_end = cudart.cudaEventCreate()
            _check_cuda(err, "cudaEventCreate(end)")
            err, ev_done = cudart.cudaEventCreate()
            _check_cuda(err, "cudaEventCreate(done)")
            # 8-byte page-locked host buffer for D2H of decoded seq.
            err, h_ptr = cudart.cudaHostAlloc(8, cudart.cudaHostAllocDefault)
            _check_cuda(err, "cudaHostAlloc(result)")
            host_arr = (ctypes.c_uint8 * 8).from_address(int(h_ptr))
            self._slots.append(
                _Slot(
                    d_ptr=int(d_ptr),
                    ev_start=ev_start,
                    ev_end=ev_end,
                    ev_done=ev_done,
                    result_dptr=int(result_dptr),
                    result_host=host_arr,
                )
            )
        self.free_slots: queue.Queue[_Slot] = queue.Queue(maxsize=depth)
        for s in self._slots:
            self.free_slots.put_nowait(s)
        self.in_flight: queue.Queue[_CapturedFrame] = queue.Queue(maxsize=depth)

    def close(self) -> None:
        cudart = self._cudart
        for s in self._slots:
            cudart.cudaEventDestroy(s.ev_start)
            cudart.cudaEventDestroy(s.ev_end)
            cudart.cudaEventDestroy(s.ev_done)
            cudart.cudaFree(s.d_ptr)
            cudart.cudaFree(s.result_dptr)
            cudart.cudaFreeHost(int(ctypes.addressof(s.result_host)))
        cudart.cudaStreamDestroy(self._stream)

    def capture_loop(self, dev: pydecklink.Device, stop: threading.Event) -> None:
        cuda = self._cuda
        cudart = self._cudart
        H2D = cudart.cudaMemcpyKind.cudaMemcpyHostToDevice
        D2H = cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost
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
            host_ptr = int(cfr.data.ctypes.data)
            # Submit: H2D → record start → decode kernel → record end → D2H result.
            (err,) = cudart.cudaMemcpyAsync(
                slot.d_ptr, host_ptr, self._frame_bytes, H2D, self._stream
            )
            _check_cuda(err, "cudaMemcpyAsync(H2D)")
            (err,) = cudart.cudaEventRecord(slot.ev_start, self._stream)
            _check_cuda(err, "cudaEventRecord(start)")
            src_arg = ctypes.c_void_p(int(slot.d_ptr))
            res_arg = ctypes.c_void_p(int(slot.result_dptr))
            arg_ptrs = (ctypes.c_void_p * 2)(
                ctypes.addressof(src_arg), ctypes.addressof(res_arg)
            )
            (err,) = cuda.cuLaunchKernel(
                self._decode_fn,
                1,
                1,
                1,
                1,
                1,
                1,
                0,
                self._stream,
                arg_ptrs,
                0,
            )
            _check_driver(err, "cuLaunchKernel(decode)")
            (err,) = cudart.cudaEventRecord(slot.ev_end, self._stream)
            _check_cuda(err, "cudaEventRecord(end)")
            (err,) = cudart.cudaMemcpyAsync(
                int(ctypes.addressof(slot.result_host)),
                slot.result_dptr,
                8,
                D2H,
                self._stream,
            )
            _check_cuda(err, "cudaMemcpyAsync(D2H)")
            # ev_done fires after the result D2H completes — the consumer
            # syncs on this before reading result_host. Without it, the
            # consumer races the D2H against ev_end (kernel-done) and
            # reads stale bytes.
            (err,) = cudart.cudaEventRecord(slot.ev_done, self._stream)
            _check_cuda(err, "cudaEventRecord(done)")
            try:
                self.in_flight.put_nowait(
                    _CapturedFrame(
                        cfr=cfr,
                        slot=slot,
                        callback_arrived_us=cfr.callback_arrived_us,
                    )
                )
            except queue.Full:
                self.frames_dropped_no_slot += 1
                self.free_slots.put_nowait(slot)
                continue

    def consumer_loop(self, stop: threading.Event) -> None:
        cudart = self._cudart
        while not stop.is_set() or not self.in_flight.empty():
            try:
                frame = self.in_flight.get(timeout=0.1)
            except queue.Empty:
                continue
            # Sync on ev_done (post-D2H) so result_host is guaranteed
            # populated before we read it.
            (err,) = cudart.cudaEventSynchronize(frame.slot.ev_done)
            _check_cuda(err, "cudaEventSynchronize")
            err, kernel_ms = cudart.cudaEventElapsedTime(
                frame.slot.ev_start, frame.slot.ev_end
            )
            _check_cuda(err, "cudaEventElapsedTime")
            seq = int.from_bytes(bytes(frame.slot.result_host), "little")
            egress_us = self._output.egress_us(seq)
            rtt = float(frame.callback_arrived_us) - egress_us
            # Skip warmup frames where preroll-side egress is undefined
            # (egress_us would be earlier than playback start).
            if rtt > 0.0:
                self.rtt_us.append(rtt)
                self.kernel_us.append(float(kernel_ms) * 1000.0)
                self.frames_captured += 1
            slot = frame.slot
            frame.cfr = None
            del frame
            self.free_slots.put_nowait(slot)

    def report(self, run_seconds: float, output_status: object) -> None:
        n = self.frames_captured
        if n == 0:
            print(f"[loopback] no frames matched in {run_seconds:.1f}s.")
            return
        qs = (50.0, 95.0, 99.0)
        rtt_p = _percentiles(self.rtt_us, qs)
        kernel_p = _percentiles(self.kernel_us, qs)
        ex_kernel = [r - k for r, k in zip(self.rtt_us, self.kernel_us, strict=True)]
        ex_p = _percentiles(ex_kernel, qs)
        frame_period_us = self._output.frame_period_us
        print(
            f"[loopback] frames={n} dropped="
            f"(no_slot={self.frames_dropped_no_slot}, "
            f"no_signal={self.frames_dropped_no_signal})"
        )
        print(
            f"           run={run_seconds:.1f}s  frame_period={frame_period_us:.1f}us"
        )
        print("           min     p50     p95     p99     max     (microseconds)")
        print(
            "  rtt     "
            f" {min(self.rtt_us):>6.0f}  {rtt_p[50]:>6.0f}  "
            f"{rtt_p[95]:>6.0f}  {rtt_p[99]:>6.0f}  {max(self.rtt_us):>6.0f}"
        )
        print(
            "  kernel  "
            f" {min(self.kernel_us):>6.1f}  {kernel_p[50]:>6.1f}  "
            f"{kernel_p[95]:>6.1f}  {kernel_p[99]:>6.1f}  {max(self.kernel_us):>6.1f}"
        )
        print(
            "  ex_kern "
            f" {min(ex_kernel):>6.0f}  {ex_p[50]:>6.0f}  "
            f"{ex_p[95]:>6.0f}  {ex_p[99]:>6.0f}  {max(ex_kernel):>6.0f}"
        )
        print(
            f"  rtt(frames)  p50={rtt_p[50] / frame_period_us:.2f}  "
            f"p95={rtt_p[95] / frame_period_us:.2f}  "
            f"p99={rtt_p[99] / frame_period_us:.2f}"
        )
        print(
            f"[output]   completed={output_status.completed} "
            f"late={output_status.late} dropped={output_status.dropped} "
            f"flushed={output_status.flushed} "
            f"underrun={output_status.underrun}"
        )


# ---------------------------------------------------------------------------
# Run loop: setup, threading, GC config, teardown.
# ---------------------------------------------------------------------------


def run_loopback(
    output_device_index: int = 0,
    input_device_index: int = 2,
    mode: pydecklink.DisplayMode = _DEFAULT_MODE,
    pixel_format: pydecklink.PixelFormat = _DEFAULT_PIXEL_FORMAT,
    frame_count: int = 0,
    duration_seconds: float = 0.0,
) -> None:
    from cuda.bindings import driver as cuda
    from cuda.bindings import runtime as cudart

    if output_device_index == input_device_index:
        raise ValueError(
            "output and input device indices must differ "
            f"(both = {output_device_index})"
        )

    # Initialize the driver API context (cudart implicitly creates one,
    # but cuModuleLoadData requires a primary context held by the
    # current thread).
    (err,) = cuda.cuInit(0)
    _check_driver(err, "cuInit")
    err, dev = cuda.cuDeviceGet(0)
    _check_driver(err, "cuDeviceGet")
    err, ctx = cuda.cuDevicePrimaryCtxRetain(dev)
    _check_driver(err, "cuDevicePrimaryCtxRetain")
    (err,) = cuda.cuCtxSetCurrent(ctx)
    _check_driver(err, "cuCtxSetCurrent")
    try:
        # Compile + load kernel module.
        ptx = _compile_kernel_source(_KERNEL_SOURCE)
        err, module = cuda.cuModuleLoadData(ptx)
        _check_driver(err, "cuModuleLoadData")
        try:
            err, encode_fn = cuda.cuModuleGetFunction(module, b"encode_fingerprint")
            _check_driver(err, "cuModuleGetFunction(encode)")
            err, decode_fn = cuda.cuModuleGetFunction(module, b"decode_fingerprint")
            _check_driver(err, "cuModuleGetFunction(decode)")

            # Output staging buffer (32 bytes on device — two v210 groups).
            err, staging_dptr = cudart.cudaMalloc(_FINGERPRINT_BYTES)
            _check_cuda(err, "cudaMalloc(staging)")
            try:
                # Output stream (separate from the input pipeline stream).
                err, output_stream = cudart.cudaStreamCreate()
                _check_cuda(err, "cudaStreamCreate(output)")
                try:
                    _run_inner(
                        output_device_index=output_device_index,
                        input_device_index=input_device_index,
                        mode=mode,
                        pixel_format=pixel_format,
                        frame_count=frame_count,
                        duration_seconds=duration_seconds,
                        cuda_driver=cuda,
                        cudart=cudart,
                        encode_fn=encode_fn,
                        decode_fn=decode_fn,
                        output_stream=output_stream,
                        staging_dptr=int(staging_dptr),
                    )
                finally:
                    cudart.cudaStreamDestroy(output_stream)
            finally:
                cudart.cudaFree(staging_dptr)
        finally:
            cuda.cuModuleUnload(module)
    finally:
        cuda.cuDevicePrimaryCtxRelease(dev)


def _run_inner(
    *,
    output_device_index: int,
    input_device_index: int,
    mode: pydecklink.DisplayMode,
    pixel_format: pydecklink.PixelFormat,
    frame_count: int,
    duration_seconds: float,
    cuda_driver: object,
    cudart: object,
    encode_fn: object,
    decode_fn: object,
    output_stream: object,
    staging_dptr: int,
) -> None:
    width = pydecklink.get_mode_width(mode)
    height = pydecklink.get_mode_height(mode)
    frame_bytes = pydecklink.get_frame_bytes(mode, pixel_format)

    # CUDA pinned allocators for output (frame pool) and input (SDK
    # captures into pinned memory via VideoBufferAllocatorProvider).
    def _alloc(size: int) -> int:
        err, ptr = cudart.cudaHostAlloc(size, cudart.cudaHostAllocDefault)
        _check_cuda(err, "cudaHostAlloc")
        return int(ptr)

    def _free(ptr: int, _size: int) -> None:
        (err,) = cudart.cudaFreeHost(ptr)
        _check_cuda(err, "cudaFreeHost")

    out_dev = pydecklink.Device(index=output_device_index)
    in_dev = pydecklink.Device(index=input_device_index)

    out_dev.enable_video_output(mode)
    in_provider = pydecklink.VideoBufferAllocatorProvider(alloc=_alloc, free=_free)
    out_alloc = pydecklink.VideoBufferAllocator(frame_bytes, alloc=_alloc, free=_free)

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

        output_driver = _OutputDriver(
            dev=out_dev,
            encode_fn=encode_fn,
            cuda_driver=cuda_driver,
            cudart=cudart,
            stream=output_stream,
            staging_dptr=staging_dptr,
            mode=mode,
        )
        pipeline = _InputPipeline(
            frame_bytes=frame_bytes,
            depth=_PIPELINE_DEPTH,
            decode_fn=decode_fn,
            cuda_driver=cuda_driver,
            cudart=cudart,
            output_driver=output_driver,
        )

        # Pre-roll the output queue with sequence numbers 0..PREROLL-1.
        for _ in range(_PREROLL):
            output_driver.schedule_one()

        in_dev.start_streams()

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
            args=(in_dev, stop),
            name="decklink-capture",
            daemon=True,
        )
        consumer_thread = threading.Thread(
            target=pipeline.consumer_loop,
            args=(stop,),
            name="decklink-consumer",
            daemon=True,
        )

        # Take t_playback_start as close to the actual call as possible.
        output_driver.t_playback_start_us = pydecklink.clock_us()
        out_dev.start_scheduled_playback(
            start_time=0, timescale=output_driver._timescale
        )
        capture_thread.start()
        consumer_thread.start()

        # Output keeper: schedule one more frame each loop iteration.
        # Block on acquire when the queue is full (which is exactly the
        # SDK's own backpressure).
        started = time.monotonic()
        last_status = 0.0
        try:
            while not stop.is_set():
                now = time.monotonic()
                elapsed = now - started
                if frame_count > 0 and pipeline.frames_captured >= frame_count:
                    break
                if duration_seconds > 0 and elapsed >= duration_seconds:
                    break
                # Top up the output queue. acquire blocks until a slot is
                # free (i.e. an output frame has completed), giving us
                # natural cadence. Suppress timeouts so we loop back to
                # check the stop flag.
                with contextlib.suppress(RuntimeError):
                    output_driver.schedule_one()
                if now - last_status >= 0.5:
                    state = (
                        "running"
                        if pipeline.frames_captured > 0
                        else "waiting for signal"
                    )
                    _print_status(
                        f"{state}: {int(elapsed)}s elapsed, "
                        f"{pipeline.frames_captured} matched "
                        f"(no_slot={pipeline.frames_dropped_no_slot} "
                        f"no_signal={pipeline.frames_dropped_no_signal})"
                    )
                    last_status = now
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
        description="DeckLink CUDA loopback fingerprint latency benchmark.",
    )
    parser.add_argument(
        "--output-device",
        type=int,
        default=0,
        help="DeckLink device index for output (default 0).",
    )
    parser.add_argument(
        "--input-device",
        type=int,
        default=2,
        help="DeckLink device index for input (default 2).",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=0,
        help="Stop after N matched frames. 0 = unlimited (use --duration or Ctrl-C).",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Stop after S seconds. 0 = unlimited.",
    )
    parser.add_argument(
        "--pixel-format",
        choices=["10bit"],
        default="10bit",
        help="10-bit YUV 4:2:2 (v210). Required for the fingerprint encoding.",
    )
    args = parser.parse_args()

    if args.frames == 0 and args.duration == 0.0:
        args.duration = 30.0  # default: 30 seconds.

    devices = pydecklink.list_devices()
    for label, idx in (
        ("--output-device", args.output_device),
        ("--input-device", args.input_device),
    ):
        if idx >= len(devices):
            print(
                f"{label}={idx} out of range ({len(devices)} devices found).",
                file=sys.stderr,
            )
            sys.exit(1)

    run_loopback(
        output_device_index=args.output_device,
        input_device_index=args.input_device,
        frame_count=args.frames,
        duration_seconds=args.duration,
    )


if __name__ == "__main__":
    main()
