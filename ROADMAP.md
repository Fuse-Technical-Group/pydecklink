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

## Future

- **hdr-metadata**: `IDeckLinkVideoFrameMutableMetadataExtensions`
  for HDR10/HLG output. Required for bmd-signal-gen integration
  (Spec §8).
- **audio-streams**: Audio capture/playout via
  `ScheduleAudioSamples` / `IDeckLinkAudioInputPacket`.
- **ancillary-data**: Timecode, closed captions.
