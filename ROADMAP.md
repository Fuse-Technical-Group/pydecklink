# pydecklink Roadmap

Derived from [SPEC.md](SPEC.md). Sections are in build-dependency order.

## GPU DMA (Phase 2)

- **allocator-buffer-recycling**: Add buffer pool to
  `VideoBufferAllocator`. When the SDK releases a `ManagedBuffer`
  (ref count → 0), return it to a free pool instead of calling the
  free function. `AllocateVideoBuffer` returns a recycled buffer
  when available. Fixes the hang when using `cudaHostAlloc` (which
  is too expensive to call per-frame). Requires changing
  `ManagedBuffer::Release` to recycle via a back-pointer to the
  parent allocator, and fixing the nanobind destructor to call
  `Release()` instead of `delete`. Touches `allocator.h` and
  `bind_allocator.cpp`.
- **cuda-host-register-path**: Add `cudaHostRegister`-based
  alternative that pins SDK-allocated (malloc) buffers on first
  sight in the capture callback. Avoids the custom allocator
  entirely — pin once, unpin on shutdown. Simpler integration
  for consumers who don't want to manage allocators. Touches
  `bind_input.cpp` (or a new helper). Depends on CUDA toolkit
  in the consumer's environment, not in pydecklink itself.
  Document as a usage pattern, not a built-in feature.

## Future

- **hdr-metadata**: `IDeckLinkVideoFrameMutableMetadataExtensions`
  for HDR10/HLG output. Required for bmd-signal-gen integration
  (Spec §8).
- **audio-streams**: Audio capture/playout via
  `ScheduleAudioSamples` / `IDeckLinkAudioInputPacket`.
- **ancillary-data**: Timecode, closed captions.
- **macos-support**: macOS COM model differs (CoreFoundation-based).
  Platform-conditional dispatch code.
