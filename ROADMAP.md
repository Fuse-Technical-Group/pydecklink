# pydecklink Roadmap

Derived from [SPEC.md](SPEC.md). Sections are in build-dependency order.

## Input-locked output

### §road:config-reference-output-mode

Add `ConfigInt.ReferenceOutputMode` to `src/pydecklink_ext/bind_enums.cpp`
and the `.pyi` stub, and an `--input-locked` flag to
`examples/cuda_loopback_latency.py` that selects the SDI input as the
output clock source. §spec:latency-characterization.

**Verify:** Run `python examples/cuda_loopback_latency.py
--input-locked` for at least 10 minutes against the loopback. RTT
jitter (p99 − p50 spread) is smaller than the free-running baseline
(default invocation, no `--input-locked`). The run shows no monotonic
frame-skip drift between input and output streams.
`OutputStatus.late + dropped + underrun` remains zero.

## Sub-frame phase tuning

### §road:config-reference-input-timing-offset

Add `ConfigInt.ReferenceInputTimingOffset` to `bind_enums.cpp` and the
`.pyi` stub, and a `--phase-sweep` mode to
`examples/cuda_loopback_latency.py` that walks the timing offset across
one frame period in configurable steps and reports RTT at each step.
Depends on §road:config-reference-output-mode.
§spec:latency-characterization.

**Verify:** Run `python examples/cuda_loopback_latency.py
--input-locked --phase-sweep`. Output prints an offset-vs-RTT table.
The minimum RTT across the sweep occurs at a non-zero offset and is
strictly less than the integer-frame floor of the free-running run.
Health counters remain zero at the reported optimum.

## Headroom and preroll sweep

### §road:headroom-preroll-sweep

Add a `--sweep` mode to `examples/cuda_loopback_latency.py` that varies
headroom and preroll across configurable ranges and reports a 2D
matrix of per-cell `OutputStatus.late + dropped + underrun` over a
sustained run per cell, identifying the configuration floor. Depends
on §road:config-reference-input-timing-offset.
§spec:latency-characterization.

**Verify:** Run `python examples/cuda_loopback_latency.py
--input-locked --sweep --duration 60`. Output prints a 2D matrix
indexed by (headroom, preroll) showing per-cell health counters and
identifies the minimum stable configuration. Cells below the floor
show nonzero counters; cells at or above show zero. The benchmark
exits with a nonzero status if no stable configuration exists in the
input range.

## Reference input status query

### §road:bind-decklink-status

Bind the `StatusID` enum members for reference-signal status,
`Device.get_status_flag` / `Device.get_status_int`, and the
`Device.reference_status → ReferenceStatus` convenience (with
`HasReferenceInput` gating) in `src/pydecklink_ext/bind_enums.cpp`,
`src/pydecklink_ext/bind_device.cpp`, and
`src/pydecklink/_bindings.pyi`. SPEC §5.11.

### §road:detect-signals-report-reference-status

Extend `examples/detect_signals.py` to print per-device reference
lock state and detected reference mode alongside the existing SDI
signal row, skipping devices whose `HasReferenceInput` attribute is
false. Depends on §road:bind-decklink-status. SPEC §5.11.

**Verify:** With at least one device's REF IN connected to an
external reference, run `python examples/detect_signals.py`. The
output shows a `ref=` field on each row: `locked@<DisplayMode>` for
the referenced device, `unlocked` for devices with a REF BNC but no
reference applied, and `n/a` for devices without a REF BNC.
Disconnecting the reference between runs flips the corresponding
row from `locked@…` to `unlocked`.

## Future

- **hdr-metadata**: `IDeckLinkVideoFrameMutableMetadataExtensions`
  for HDR10/HLG output. Required for bmd-signal-gen integration
  (Spec §8).
- **audio-streams**: Audio capture/playout via
  `ScheduleAudioSamples` / `IDeckLinkAudioInputPacket`.
- **ancillary-data**: Timecode, closed captions.
- **status-change-notifications**: Push-based status updates via
  `IDeckLinkNotification::Subscribe(bmdStatusChanged)` —
  `device.subscribe_status_changes() → StatusChangeQueue` per
  SPEC §5.11. Deferred until a long-running monitor surface
  exists to consume it; the synchronous getter in
  §road:bind-decklink-status covers one-shot diagnostics.
