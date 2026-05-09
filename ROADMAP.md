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

## Synchronized output fanout

### §road:bindings-playback-group

Add `ConfigurationID.PlaybackGroup` (wraps
`bmdDeckLinkConfigPlaybackGroup`) and
`AttributeID.SupportsSynchronizeToPlaybackGroup` (wraps
`BMDDeckLinkSupportsSynchronizeToPlaybackGroup`) to
`src/pydecklink_ext/bind_enums.cpp` and the `.pyi` stub. Both are
additive; no signature changes elsewhere.
§spec:synchronized-output-fanout.

### §road:cuda-passthrough-fanout

Refactor `examples/cuda_passthrough.py` to auto-discover non-input
sub-devices, configure them into a shared playback group via
`device.set_config_int(ConfigurationID.PlaybackGroup, group_id)` plus
`enable_video_output(mode, VideoOutputFlag.SynchronizeToPlaybackGroup)`,
and fan the kernel result out to all of them with N D2H copies on
the CUDA stream into N pinned output pools. Drop the `--output` CLI
flag (outputs are auto-discovered). Add the stderr WARNING on first
sync-group starvation event and the `[anomaly]` block in the final
report. Update `tests/test_examples_cuda_passthrough.py` for the
changed CLI shape and the new auto-discovery logic. Depends on
§road:bindings-playback-group. §spec:synchronized-output-fanout.

**Verify:** On a host with a 4-sub-device DeckLink card and an SDI
source feeding `--input 2`, run
`uv run examples/cuda_passthrough.py --input 2 --duration 30`. The
example logs the discovered output indices (e.g. `[fanout]
outputs=[0, 1, 3]`) at startup, runs at frame rate with the identity
kernel, and prints `[anomaly] sync-group starvation events: 0` in
the final report. Per-output `OutputStatus.late + dropped +
underrun = 0` on every output. Routing the three SDI outputs to a
multi-viewer (or fingerprinting them per the
`cuda_loopback_latency.py` pattern and confirming matching sequence
numbers across outputs every frame) shows all three present the
same frame at the same wall-clock instant. Re-run with `--input 0`
and confirm the discovered outputs become `[1, 2, 3]`.

## Future

- **hdr-metadata**: `IDeckLinkVideoFrameMutableMetadataExtensions`
  for HDR10/HLG output. Required for bmd-signal-gen integration
  (Spec §8).
- **audio-streams**: Audio capture/playout via
  `ScheduleAudioSamples` / `IDeckLinkAudioInputPacket`.
- **ancillary-data**: Timecode, closed captions.
