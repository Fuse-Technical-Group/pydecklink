# pydecklink Roadmap

Derived from [SPEC.md](SPEC.md). Sections are in build-dependency order.

## Build foundation

- **repo-scaffold**: Replace pyntv2 build config with pydecklink.
  New `pyproject.toml` (package name `pydecklink`, scikit-build-core).
  New `CMakeLists.txt` finding vendored DeckLink SDK headers, compiling
  `DeckLinkAPIDispatch.cpp` into the nanobind module. `src/bindings.cpp`
  with empty `NB_MODULE`. `src/pydecklink/__init__.py` re-exporting
  from `_bindings`. Verify `import pydecklink` succeeds (module loads,
  `dlopen` finds `libDeckLinkAPI.so`). Existing pyntv2 `src/` files
  are removed from the build but left on disk until the repo is
  restructured for the mono-repo (see ROADMAP-pyprovideo.md).
- **devcontainer-decklink**: Devcontainer config for DeckLink
  development. Dockerfile based on `ubuntu:24.04`, installs build
  tools (cmake, ninja, uv). SDK headers are vendored locally (not
  in the image). Device passthrough for `/dev/blackmagic/*`.
  `libDeckLinkAPI.so` accessed via bind-mount from host or installed
  in container. Same `--userns=keep-id` pattern as pyntv2.

## Enum and device layer

Depends on repo-scaffold.

- **bind-enums**: Bind core SDK enums in `bind_enums.cpp`.
  `BMDDisplayMode` (SD through 8K), `BMDPixelFormat` (YUV/RGB
  variants), `BMDVideoInputFlags`, `BMDVideoOutputFlags`,
  `BMDFieldDominance`, `BMDFrameFlags`,
  `BMDDetectedVideoInputFormatFlags`,
  `BMDOutputFrameCompletionResult`, configuration and attribute IDs.
  Unit tests: enum values exist, can compare, repr is readable.
- **bind-device**: Device enumeration and properties in
  `bind_device.cpp`. Wrap `IDeckLinkIterator` for discovery.
  `Device` class with context manager, model/display name,
  capability queries via `IDeckLinkProfileAttributes` (duplex mode,
  I/O support, format detection, min preroll frames). Module-level
  `device_count()` and `list_devices()`. Unit tests: construction,
  type validation. Hardware tests: enumerate real devices, check
  properties.

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

Depends on bind-enums.

- **format-helpers**: Module-level `get_frame_bytes(mode,
  pixel_format)`, `get_mode_width(mode)`, `get_mode_height(mode)`,
  `get_mode_fps(mode)`. Implemented by querying
  `IDeckLinkDisplayMode` properties from the SDK's mode iterator.
  Unit tests for known formats.

## Future

- **hdr-metadata**: `IDeckLinkVideoFrameMutableMetadataExtensions`
  for HDR10/HLG output. Required for bmd-signal-gen integration.
- **audio-streams**: Audio capture/playout via
  `ScheduleAudioSamples` / `IDeckLinkAudioInputPacket`.
- **ancillary-data**: Timecode, closed captions.
- **macos-support**: macOS COM model differs (CoreFoundation-based).
  Platform-conditional dispatch code.
