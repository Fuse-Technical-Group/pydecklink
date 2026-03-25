# pydecklink Roadmap

Derived from [SPEC.md](SPEC.md). Sections are in build-dependency order.

## Type stubs and API completeness

- **type-stubs**: Generate `.pyi` stubs for `pydecklink._bindings`.
  nanobind supports stub generation via `nanobind.stubgen`. Current
  stubs are near-empty (`HAS_SDK: bool = False`), blocking downstream
  type checking.
- **display-mode-query**: Bind `IDeckLinkOutput::GetDisplayMode` and
  `DoesSupportVideoMode`. Spec §5.2 describes these but they are not
  implemented. Needed for runtime mode validation.

## GPU DMA (Phase 2)

- **custom-allocator**: Implement `IDeckLinkMemoryAllocator` that
  allocates CUDA pinned memory (or accepts externally pinned buffers).
  Register with `IDeckLinkInput::SetVideoInputFrameMemoryAllocator`
  so the DeckLink DMA engine writes directly into GPU-accessible
  memory. Depends on CUDA toolkit in the devcontainer.
- **gpu-output-pool**: Extend the output frame pool to use
  CUDA-pinned backing buffers, so GPU→DeckLink output is also a
  single DMA hop. Depends on **custom-allocator**.

## Future

- **hdr-metadata**: `IDeckLinkVideoFrameMutableMetadataExtensions`
  for HDR10/HLG output. Required for bmd-signal-gen integration
  (Spec §8).
- **audio-streams**: Audio capture/playout via
  `ScheduleAudioSamples` / `IDeckLinkAudioInputPacket`.
- **ancillary-data**: Timecode, closed captions.
- **macos-support**: macOS COM model differs (CoreFoundation-based).
  Platform-conditional dispatch code.
