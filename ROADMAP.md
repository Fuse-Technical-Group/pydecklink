# pydecklink Roadmap

Derived from [SPEC.md](SPEC.md). Sections are in build-dependency order.

## GPU DMA (Phase 2)

- **cuda-pinned-alloc**: Wire CUDA `cudaHostAlloc`/`cudaFreeHost` as
  the allocation functions for `VideoBufferAllocator`. Requires CUDA
  toolkit in the devcontainer. The allocator infrastructure
  (**custom-allocator**, **gpu-output-pool**) is complete; this
  workstream adds the CUDA-specific backend.

## macOS Support

- **macos-build**: Add macOS path to `platform.h` and CMakeLists.txt.
  Mac SDK headers are already vendored. macOS uses CoreFoundation-based
  COM (`CFPlugIn`) rather than `dlopen` dispatch (Linux) or Windows COM.
  Extend `platform.h` with macOS type aliases and
  `CreateDeckLinkIteratorInstance`. Add CI workflow for macOS.

## Future

- **hdr-metadata**: `IDeckLinkVideoFrameMutableMetadataExtensions`
  for HDR10/HLG output. Required for bmd-signal-gen integration
  (Spec §8).
- **audio-streams**: Audio capture/playout via
  `ScheduleAudioSamples` / `IDeckLinkAudioInputPacket`.
- **ancillary-data**: Timecode, closed captions.
