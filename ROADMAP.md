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

## API version surfacing

### §road:api-version

Add `pydecklink.api_version() -> APIVersion` by wrapping
`IDeckLinkAPIInformation` in a new
`src/pydecklink_ext/bind_api_info.cpp` (hooked from `bindings.cpp`),
updating the `src/pydecklink/_bindings.pyi` stub, and adding
`tests/test_pydecklink_api_info.py` covering the populated-runtime
and absent-runtime paths. §spec:api-information.

**Verify:** On a host with Desktop Video installed,
`uv run python -c "import pydecklink; v = pydecklink.api_version();
print(v.string, v.major, v.minor, v.sub, v.extra, hex(v.packed))"`
prints a populated version (e.g. `15.3.0 15 3 0 0 0xf030000`) whose
`major.minor.sub` matches the version reported by the Blackmagic
Desktop Video control panel and whose four parts compose to `packed`.
On a host without Desktop Video, the same invocation raises
`RuntimeError` with the install guidance string.

## Future

- **hdr-metadata**: `IDeckLinkVideoFrameMutableMetadataExtensions`
  for HDR10/HLG output. Required for bmd-signal-gen integration
  (Spec §8).
- **audio-streams**: Audio capture/playout via
  `ScheduleAudioSamples` / `IDeckLinkAudioInputPacket`.
- **ancillary-data**: Timecode, closed captions.
