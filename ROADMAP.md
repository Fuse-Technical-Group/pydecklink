# pydecklink Roadmap

Derived from [SPEC.md](SPEC.md). Sections are in build-dependency order.

## Sub-frame phase tuning §road:config-reference-input-timing-offset

Add `ConfigInt.ReferenceInputTimingOffset` to `bind_enums.cpp` and the
`.pyi` stub, and a `--phase-sweep` mode to
`examples/cuda_loopback_latency.py` that walks the timing offset across
one frame period in configurable steps and reports RTT at each step.
Requires REF IN wired to an external reference for the sweep to have
an anchor; the SDK does not expose locking the output PLL to the SDI
input clock. §spec:latency-characterization.

**Verify:** With REF IN connected to an external reference shared with
the upstream source, run `python examples/cuda_loopback_latency.py
--ref-locked --phase-sweep`. Output prints an offset-vs-RTT table.
The minimum RTT across the sweep occurs at a non-zero offset and is
strictly less than the integer-frame floor of the free-running run.
Health counters remain zero at the reported optimum.

## Headroom and preroll sweep §road:headroom-preroll-sweep

Add a `--sweep` mode to `examples/cuda_loopback_latency.py` that varies
headroom and preroll across configurable ranges and reports a 2D
matrix of per-cell `OutputStatus.late + dropped + underrun` over a
sustained run per cell, identifying the configuration floor. Depends
on §road:config-reference-input-timing-offset.
§spec:latency-characterization.

**Verify:** Run `python examples/cuda_loopback_latency.py --sweep
--duration 60`. Output prints a 2D matrix indexed by (headroom,
preroll) showing per-cell health counters and identifies the minimum
stable configuration. Cells below the floor show nonzero counters;
cells at or above show zero. The benchmark exits with a nonzero
status if no stable configuration exists in the input range.

## HDR metadata output §road:hdr-metadata

Expose HDR10 static metadata on output frames. Add an `EOTF` enum to
`bind_enums.cpp` and the `.pyi` stub (reuse the existing `Colorspace`
values). Add `MutableFrame.set_hdr_metadata(HDRMetadata)` in
`bind_output.cpp`: query
`IID_IDeckLinkVideoFrameMutableMetadataExtensions` off the frame,
`SetInt`/`SetFloat` the mastering-display, white-point, and content
light-level IDs, then `SetFlags(flags | bmdFrameContainsHDRMetadata)`.
Add `device.display_frame_sync_frame(mutable_frame)` so a caller-built
frame carries metadata through the synchronous `DisplayVideoFrameSync`
path. Defaults: Rec.2020 primaries and white point; PQ and HLG EOTF
selectable. Ports bmd-signal-gen's `SetHDRMetadata`
(`cpp/decklink_wrapper.cpp`), which drives the identical SDK
interface. §spec:hdr-metadata. Closes #194.

**Verify:** Build the extension. On a device where `supports_hdr` is
true, create a 12-bit RGB frame, call `set_hdr_metadata` with
`EOTF.PQ`, `Colorspace.Rec2020`, `max_cll=10000`, then
`display_frame_sync_frame`. A downstream HDR display or analyzer
reports the signalled EOTF, colorspace, and MaxCLL. Without hardware:
read the values back through the frame's metadata extension
(`GetInt`/`GetFloat` return what was set) and assert
`FrameFlag.ContainsHDRMetadata` is present in the frame flags.

## HDR metadata capture §road:hdr-metadata-capture

Expose received HDR10 static metadata on captured frames, mirroring the
output write surface. Add `hdr_metadata → HDRMetadata | None` to
`CaptureFrame` and `CaptureFrameRef` in `bind_input.{h,cpp}`: query
`IID_IDeckLinkVideoFrameMetadataExtensions` (the read interface) off the
captured `IDeckLinkVideoInputFrame`, read the mastering-display,
white-point, and content-light-level IDs plus the EOTF/colorspace, and
return `None` when `FrameFlag.ContainsHDRMetadata` is absent. Reuse the
`HDRMetadata` / `EOTF` / `Colorspace` types from the output surface.
§spec:hdr-metadata-capture. Builds on the output HDR surface
(§spec:hdr-metadata / PR #198).

**Verify:** With an HDMI OUT → IN loopback on an `supports_hdr` device,
build a frame, `set_hdr_metadata(EOTF.PQ, Colorspace.Rec2020,
max_cll=10000)`, display it, capture it back, and assert
`frame.hdr_metadata` reports the same EOTF, colorspace, and MaxCLL.
Without hardware: assert `hdr_metadata` returns `None` for a plain SDR
capture and that the accessor exists on both `CaptureFrame` and
`CaptureFrameRef`.

## Future §road:future

- **audio-streams**: Audio capture/playout via
  `ScheduleAudioSamples` / `IDeckLinkAudioInputPacket`.
- **ancillary-data**: Timecode, closed captions.
- **status-change-notifications**: Push-based status updates via
  `IDeckLinkNotification::Subscribe(bmdStatusChanged)` —
  `device.subscribe_status_changes() → StatusChangeQueue` per
  §spec:device-status. Deferred until a long-running monitor surface
  exists to consume it; the synchronous status getter already
  covers one-shot diagnostics.
