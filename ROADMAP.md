# pydecklink Roadmap

Derived from [SPEC.md](SPEC.md). Sections are in build-dependency order.

## GPU DMA

### §road:allocator-buffer-recycling

Add free-list to `VideoBufferAllocator` so `ManagedBuffer`
instances recycle on COM refcount drop to zero — from SDK
`Release` or Python GC of a `ComPtr<ManagedBuffer>` — instead of
calling `free_fn`. Add `ComPtr<VideoBufferAllocator>` back-reference
on `ManagedBuffer` so the allocator outlives outstanding buffers.
Touches `allocator.h` and `bind_allocator.cpp`. §spec:gpu-pinned-memory

### §road:cuda-host-register-example

Example script showing `cudaHostRegister` (pin SDK-allocated
buffers on first sight) and allocator-based (`cudaHostAlloc`)
capture patterns. New file `examples/cuda_pinned_capture.py`.
Depends on §road:allocator-buffer-recycling. §spec:gpu-pinned-memory

**Verify:** custom alloc/free callables that log calls show: alloc
called N times at startup, free never called during capture, free
called N times at shutdown. `recycled_count` property confirms
buffer reuse.

## Future

- **hdr-metadata**: `IDeckLinkVideoFrameMutableMetadataExtensions`
  for HDR10/HLG output. Required for bmd-signal-gen integration
  (Spec §8).
- **audio-streams**: Audio capture/playout via
  `ScheduleAudioSamples` / `IDeckLinkAudioInputPacket`.
- **ancillary-data**: Timecode, closed captions.
