# pydecklink Roadmap

Derived from [SPEC.md](SPEC.md). Sections are in build-dependency order.

## GPU DMA

### §road:cuda-host-register-example

Example script showing `cudaHostRegister` (pin SDK-allocated
buffers on first sight) and allocator-based (`cudaHostAlloc`)
capture patterns. New file `examples/cuda_pinned_capture.py`.
§spec:gpu-pinned-memory

**Verify:** capture runs against pinned buffers; no per-frame
`cudaHostAlloc` calls during steady state.

## Future

- **hdr-metadata**: `IDeckLinkVideoFrameMutableMetadataExtensions`
  for HDR10/HLG output. Required for bmd-signal-gen integration
  (Spec §8).
- **audio-streams**: Audio capture/playout via
  `ScheduleAudioSamples` / `IDeckLinkAudioInputPacket`.
- **ancillary-data**: Timecode, closed captions.
