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

## Phase 2 (Future)

- **audio-transfer**: Audio buffer support in `Transfer`.
- **anc-data**: Ancillary data (timecode, closed captions).
- **multi-channel**: Quad-link 4K, multi-channel ganging.
- **advanced-routing**: Multi-link, dual-stream, mixer widgets.
