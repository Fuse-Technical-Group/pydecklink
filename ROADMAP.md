# pydecklink Roadmap

Derived from [SPEC.md](SPEC.md). Sections are in build-dependency order.

## Enum and device layer

Completed: bind-enums, bind-device.

## Output path

Depends on bind-device.

- **bind-output-sync**: Synchronous output in `bind_output.cpp`.
  `IDeckLinkOutput::EnableVideoOutput`, `DisableVideoOutput`,
  `CreateVideoFrame`. Frame buffer access via
  `IDeckLinkVideoBuffer` → numpy. `display_frame_sync(buffer)` —
  creates frame, copies data, calls `DisplayVideoFrameSync`.
  Configuration: `IDeckLinkConfiguration::SetFlag` for SDI 4:4:4
  mode (must be set before `EnableVideoOutput`). Hardware test:
  display a solid color frame, verify no errors.
- **bind-output-scheduled**: Scheduled playback in `bind_output.cpp`.
  `ScheduleVideoFrame`, `StartScheduledPlayback`,
  `StopScheduledPlayback`. C++ `IDeckLinkVideoOutputCallback`
  implementation tracking completion results (completed, late,
  dropped, flushed). Preroll management respecting
  `BMDDeckLinkMinimumPrerollFrames`. `OutputStatus` exposing
  dropped/late counts. Hardware test: schedule N frames at frame
  rate, verify zero dropped.

## Input path

Depends on bind-device.

- **bind-input**: Capture in `bind_input.cpp`. `IDeckLinkInput`:
  `EnableVideoInput`, `DisableVideoInput`, `StartStreams`,
  `StopStreams`. C++ `IDeckLinkInputCallback` implementation:
  `VideoInputFrameArrived` copies frame data into bounded
  thread-safe queue. `pop_capture_frame(timeout_ms)` returns
  `CaptureFrame` (numpy data, dimensions, stream time, signal
  flag). `VideoInputFormatChanged` handler: auto-reconfigure on
  signal change when format detection is enabled. GIL released
  during queue wait. Hardware test: capture frames from live
  signal, verify timestamps, signal flag, data non-zero.

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

## Format metadata helpers

Completed: format-helpers.

## Future

- **hdr-metadata**: `IDeckLinkVideoFrameMutableMetadataExtensions`
  for HDR10/HLG output. Required for bmd-signal-gen integration.
- **audio-streams**: Audio capture/playout via
  `ScheduleAudioSamples` / `IDeckLinkAudioInputPacket`.
- **ancillary-data**: Timecode, closed captions.
- **macos-support**: macOS COM model differs (CoreFoundation-based).
  Platform-conditional dispatch code.
