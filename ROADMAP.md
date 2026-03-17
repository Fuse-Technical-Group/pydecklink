# pyntv2 Roadmap

Derived from [SPEC.md](SPEC.md). Sections are in build-dependency order.

## Enum Bindings

- **core-enums**: Bind `NTV2Channel`, `NTV2AudioSystem`,
  `NTV2VideoFormat`, `NTV2FrameBufferFormat`, `NTV2InputSource`,
  `NTV2OutputDestination`, `NTV2InputCrosspointID`,
  `NTV2OutputCrosspointID`, `NTV2Mode`, `NTV2ReferenceSource`.
  Expose with Pythonic names (`Channel`, `PixelFormat`, etc.).

## Card Wrapper

- **card-open-close**: Bind `CNTV2Card` open/close lifecycle. Context
  manager support (`__enter__`/`__exit__`).

## Format Detection and Configuration

- **format-detect**: Bind `GetInputVideoFormat`. Return `VideoFormat`
  enum.
- **format-config**: Bind `SetVideoFormat`, `SetFrameBufferFormat`,
  `EnableChannel`, `SetMode`, `SetSDITransmitEnable`, `SetReference`.

## Signal Routing

- **routing-core**: Bind `Connect`, `Disconnect`, `ClearRouting`,
  `ApplySignalRoute`. Expose `InputXpt` and `OutputXpt` enums.
- **routing-helpers**: Implement `route_capture()` and
  `route_playout()` convenience functions. Insert CSC widget when
  input color space differs from framebuffer pixel format.

## AutoCirculate

- **autocirculate-init**: Bind `AutoCirculateInitForInput`,
  `AutoCirculateInitForOutput`. Bool-to-exception translation.
- **autocirculate-start-stop**: Bind `AutoCirculateStart`,
  `AutoCirculateStop`.
- **autocirculate-status**: Bind `AutoCirculateGetStatus`. Return
  `Status` dataclass.
- **transfer-class**: Bind `AUTOCIRCULATE_TRANSFER` as `Transfer`
  class. `set_video_buffer()` accepts `nb::ndarray<>`.
- **autocirculate-transfer**: Bind `AutoCirculateTransfer`. Accepts
  `Channel` and `Transfer`.
- **wait-for-vbi**: Bind `WaitForInputVerticalInterrupt`.

## Buffer Management

- **dma-buffer-lock**: Bind `DMABufferLock`/`DMABufferUnlock`. Detect
  CPU vs CUDA device from `nb::ndarray<>` device tag. Set `rdma` flag
  accordingly.

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
