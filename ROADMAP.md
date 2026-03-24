# pyntv2 Roadmap

Derived from [SPEC.md](SPEC.md). Sections are in build-dependency order.

## Device identity

Spec §5.1. Needed by the benchmark to log which card model is under
test, and generally useful for any multi-card or diagnostic workflow.

- **device-identity**: Bind `CNTV2Card::GetDeviceID()` as
  `device_id` (read-only int property) and
  `CNTV2Card::GetDisplayName()` as `display_name` (read-only str
  property) in `src/bind_card.cpp`. Add method-existence tests in
  `tests/test_card.py`. Verify on hardware that the Corvid 44 12G
  returns a non-zero ID and non-empty name.

## DMA throughput benchmark

Spec §7.3. Validates that the two-hop capture→playout DMA path fits
within the 16.68 ms frame budget at 3840×2160p59.94 (21.1 MB/frame,
single-link 12G-SDI on CH3↔CH4 loopback). Depends on
**device-identity** (logs card model in output).

- **benchmark-4k60-dma**: Add `tests/test_benchmark.py` with a
  pytest test marked `hardware` and `benchmark`. Runs the
  `TestCpuPassthrough` loop (same helpers from `test_integration.py`)
  at `FORMAT_3840x2160p_5994` / `FBF_10BIT_YCBCR`, timing each
  `autocirculate_transfer` via `time.perf_counter`. Reports min,
  max, mean, p99 for capture and playout DMA. Asserts zero dropped
  frames as pass/fail gate. Prints timing summary to stdout
  (captured by `pytest -s`).

## Phase 2 (Future)

- **audio-transfer**: Audio buffer support in `Transfer`.
- **anc-data**: Ancillary data (timecode, closed captions).
- **multi-channel**: Quad-link 4K, multi-channel ganging.
- **advanced-routing**: Multi-link, dual-stream, mixer widgets.
