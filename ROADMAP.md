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

## macOS wheel deployment target §road:macos-deployment-target

Pin `MACOSX_DEPLOYMENT_TARGET` to 14.0 for the macOS wheel build in
`.github/workflows/build-wheels.yml`, so the published platform tag is
chosen rather than inherited from the `macos-latest` runner image.
Pinning the runner to a dated `macos-N` label instead re-couples the
floor to a label that rolls over again. Blocks §spec:test-pattern-generation:
bmd-signal-gen is macOS-targeted and cannot consume a macOS-26-only
wheel. §spec:distribution. Reported in #208.

**Verify:** A macOS wheel from a tagged build lists `macosx_14_0_arm64`
in its filename (`python -m zipfile -l`, or the release artifact
listing), not `macosx_26_0_arm64`. On macOS 14 or 15, `uv add
pydecklink` resolves to the newest release rather than 0.3.3. The
extension imports and `api_version()` returns on a machine at the floor.

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
