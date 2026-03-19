# pyntv2 Roadmap

Derived from [SPEC.md](SPEC.md). Sections are in build-dependency order.

## Integration Testing

- **loopback-test**: End-to-end test with AJA hardware in loopback
  mode (output Ch1 → input Ch2). Requires hardware; runs manually or
  on a dedicated CI runner.
- **gpu-rdma-test**: Same as loopback but with CuPy GPU buffers.
  Validates RDMA path. Requires NVIDIA GPU + AJA card on same PCIe
  bridge.

## Phase 2 (Future)

- **audio-transfer**: Audio buffer support in `Transfer`.
- **anc-data**: Ancillary data (timecode, closed captions).
- **multi-channel**: Quad-link 4K, multi-channel ganging.
- **advanced-routing**: Multi-link, dual-stream, mixer widgets.
