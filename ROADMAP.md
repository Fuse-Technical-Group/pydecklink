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

## Future §road:future

- **hdr-metadata**: `IDeckLinkVideoFrameMutableMetadataExtensions`
  for HDR10/HLG output. Required for bmd-signal-gen integration
  (§spec:test-pattern-generation).
- **audio-streams**: Audio capture/playout via
  `ScheduleAudioSamples` / `IDeckLinkAudioInputPacket`.
- **ancillary-data**: Timecode, closed captions.
- **status-change-notifications**: Push-based status updates via
  `IDeckLinkNotification::Subscribe(bmdStatusChanged)` —
  `device.subscribe_status_changes() → StatusChangeQueue` per
  §spec:device-status. Deferred until a long-running monitor surface
  exists to consume it; the synchronous status getter already
  covers one-shot diagnostics.
