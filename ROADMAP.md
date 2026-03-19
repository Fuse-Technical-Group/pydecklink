# pyntv2 Roadmap

Derived from [SPEC.md](SPEC.md). Sections are in build-dependency order.

## Integration Testing

Hardware: CH3↔CH4 SDI loopback cable.

- **cpu-loopback**: Playout known patterns on CH3, capture on CH4,
  bitwise compare. numpy buffers. Validates DMA data integrity.
- **gpu-loopback**: Same as cpu-loopback but with CuPy buffers and
  RDMA. Requires NVIDIA GPU on same PCIe bridge.
- **cpu-passthrough**: Capture CH4 → numpy buffer → playout CH3.
  Sustained AutoCirculate pump. Assert zero dropped frames over N
  frames.
- **gpu-passthrough**: Same as cpu-passthrough but with CuPy buffers.
  Validates RDMA round-trip at frame rate without touching system
  memory.

## Phase 2 (Future)

- **audio-transfer**: Audio buffer support in `Transfer`.
- **anc-data**: Ancillary data (timecode, closed captions).
- **multi-channel**: Quad-link 4K, multi-channel ganging.
- **advanced-routing**: Multi-link, dual-stream, mixer widgets.
