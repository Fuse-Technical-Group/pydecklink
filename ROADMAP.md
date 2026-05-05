# pydecklink Roadmap

Derived from [SPEC.md](SPEC.md). Sections are in build-dependency order.

## Allocator cleanup

- **split-pooled-buffer-handle**: Refactor `ManagedBuffer` into a
  pure-data `PooledBuffer` (memory + size, owned by the allocator's
  free-list) and a per-issuance `BufferHandle` (implements
  `IDeckLinkVideoBuffer`, standard COM semantics, dtor returns
  `PooledBuffer*` to the free-list). Restores standard COM
  refcount semantics — `Release()→0` destroys the handle instead
  of the current "refcount==0 still valid memory" exception that
  fights `ComPtr`. Removes `revive()`, the manual AddRef/Release
  pair in ctor/Release, and the `ManagedBuffer*` raw-owning
  free-list. Per-issuance `new BufferHandle` is a tiny heap object
  (no syscall) — the pool still amortizes the expensive `cudaHostAlloc`.
  Hardware regression: existing `TestCustomAllocatorZeroCopy` plus a
  4K59.94/10-bit loopback run. Raised in PR #110 review (#110 lands
  the recycling design as-is; this workstream closes the COM-semantics
  gap).

## Latency benchmark baseline

### §road:fingerprint-loopback

Build a CUDA loopback fingerprint benchmark in
`examples/cuda_loopback_latency.py` that stamps a sequence number into
the active video region of each output frame, recovers it from the
corresponding capture, and reports round-trip latency in microseconds
and frame periods with kernel time decomposed from ex-kernel cost via
GPU events. §spec:latency-characterization.

**Verify:** With two DeckLink devices wired in loopback (SDI device
0 → device 2) at 1080p60 8-bit YUV 4:2:2, run
`python examples/cuda_loopback_latency.py` for at least 1000 frames.
Output reports p50/p95/p99 round-trip latency in µs and frame periods,
kernel time and ex-kernel cost as separate columns, and `OutputStatus`
counters. `late + dropped + underrun` is zero across the run.

## Input-locked output

### §road:config-reference-output-mode

Add `ConfigInt.ReferenceOutputMode` to `src/pydecklink_ext/bind_enums.cpp`
and the `.pyi` stub, and an `--input-locked` flag to
`examples/cuda_loopback_latency.py` that selects the SDI input as the
output clock source. Depends on §road:fingerprint-loopback.
§spec:latency-characterization.

**Verify:** Run `python examples/cuda_loopback_latency.py
--input-locked` for at least 10 minutes against the loopback. RTT
jitter (p99 − p50 spread) is smaller than the free-running baseline
from §road:fingerprint-loopback. The run shows no monotonic frame-skip
drift between input and output streams.
`OutputStatus.late + dropped + underrun` remains zero.

## Sub-frame phase tuning

### §road:config-reference-input-timing-offset

Add `ConfigInt.ReferenceInputTimingOffset` to `bind_enums.cpp` and the
`.pyi` stub, and a `--phase-sweep` mode to
`examples/cuda_loopback_latency.py` that walks the timing offset across
one frame period in configurable steps and reports RTT at each step.
Depends on §road:config-reference-output-mode.
§spec:latency-characterization.

**Verify:** Run `python examples/cuda_loopback_latency.py
--input-locked --phase-sweep`. Output prints an offset-vs-RTT table.
The minimum RTT across the sweep occurs at a non-zero offset and is
strictly less than the integer-frame floor measured by
§road:fingerprint-loopback. Health counters remain zero at the
reported optimum.

## Headroom and preroll sweep

### §road:headroom-preroll-sweep

Add a `--sweep` mode to `examples/cuda_loopback_latency.py` that varies
headroom and preroll across configurable ranges and reports a 2D
matrix of per-cell `OutputStatus.late + dropped + underrun` over a
sustained run per cell, identifying the configuration floor. Depends
on §road:config-reference-input-timing-offset.
§spec:latency-characterization.

**Verify:** Run `python examples/cuda_loopback_latency.py
--input-locked --sweep --duration 60`. Output prints a 2D matrix
indexed by (headroom, preroll) showing per-cell health counters and
identifies the minimum stable configuration. Cells below the floor
show nonzero counters; cells at or above show zero. The benchmark
exits with a nonzero status if no stable configuration exists in the
input range.

## Future

- **hdr-metadata**: `IDeckLinkVideoFrameMutableMetadataExtensions`
  for HDR10/HLG output. Required for bmd-signal-gen integration
  (Spec §8).
- **audio-streams**: Audio capture/playout via
  `ScheduleAudioSamples` / `IDeckLinkAudioInputPacket`.
- **ancillary-data**: Timecode, closed captions.
