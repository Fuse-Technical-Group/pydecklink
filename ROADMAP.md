# pydecklink Roadmap

Derived from [SPEC.md](SPEC.md). Sections are in build-dependency order.

## GPU DMA (Phase 2)

- **cuda-pinned-alloc**: Wire CUDA `cudaHostAlloc`/`cudaFreeHost` as
  the allocation functions for `VideoBufferAllocator`. Requires CUDA
  toolkit in the devcontainer. The allocator infrastructure
  (**custom-allocator**, **gpu-output-pool**) is complete; this
  workstream adds the CUDA-specific backend.

## Future

- **hdr-metadata**: `IDeckLinkVideoFrameMutableMetadataExtensions`
  for HDR10/HLG output. Required for bmd-signal-gen integration
  (Spec §8).
- **audio-streams**: Audio capture/playout via
  `ScheduleAudioSamples` / `IDeckLinkAudioInputPacket`.
- **ancillary-data**: Timecode, closed captions.
- **macos-support**: macOS COM model differs (CoreFoundation-based).
  Platform-conditional dispatch code.
