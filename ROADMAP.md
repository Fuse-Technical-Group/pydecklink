# pydecklink Roadmap

Derived from [SPEC.md](SPEC.md). Sections are in build-dependency order.

## Output path

Completed: bind-output-sync, bind-output-scheduled.

## Input path

Completed: bind-input.

## Integration

Depends on bind-output-scheduled, bind-input.

- **passthrough-example**: End-to-end capture → playout example
  in `examples/passthrough.py`. Auto-detect input format, configure
  output to match, capture loop → schedule loop. Demonstrates the
  full API surface. Modeled on pyntv2's `examples/passthrough.py`.
- **integration-tests**: Loopback data integrity test (playout →
  capture, compare buffers). Passthrough sustained streaming test
  (run N frames, assert zero drops). Signal detection test.
  Marked `pytest -m hardware`.

## Future

- **hdr-metadata**: `IDeckLinkVideoFrameMutableMetadataExtensions`
  for HDR10/HLG output. Required for bmd-signal-gen integration.
- **audio-streams**: Audio capture/playout via
  `ScheduleAudioSamples` / `IDeckLinkAudioInputPacket`.
- **ancillary-data**: Timecode, closed captions.
- **macos-support**: macOS COM model differs (CoreFoundation-based).
  Platform-conditional dispatch code.
