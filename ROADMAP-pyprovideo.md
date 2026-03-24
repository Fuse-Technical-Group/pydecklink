# pyprovideo Roadmap

Derived from [SPEC-pyprovideo.md](SPEC-pyprovideo.md). Sections are
in build-dependency order.

## Mono-repo scaffold

Restructure the pyntv2 repository into a uv workspace mono-repo.
Move existing pyntv2 code to `packages/pyntv2/`. Create workspace
root `pyproject.toml`. Verify pyntv2 builds and tests pass from
the new location.

- **workspace-init**: Create `packages/` layout, workspace
  `pyproject.toml`, move pyntv2 source and build config. Preserve
  git history with `git mv`.
- **ci-migrate**: Update CI workflows for the new path structure.
  CI covers linting, type checks, and wheel builds — no hardware.

## pydecklink (nanobind rewrite)

Copy DeckLink wrapper code from bmd-signal-gen into
`packages/pydecklink/`. Rewrite the binding layer from
`extern "C"` + ctypes to nanobind. Add Linux support.

- **copy-bmd-wrapper**: Copy `cpp/decklink_wrapper.cpp`,
  `cpp/decklink_wrapper.h`, `cpp/pixel_packing.cpp`, and
  `bmd_sg/decklink/` into `packages/pydecklink/`. Strip
  signal-gen dependencies. This is a snapshot — not a submodule.
- **nanobind-binding**: Replace the 19 `extern "C"` functions
  with a nanobind module that binds `DeckLinkSignalGen` directly.
  Drop all ctypes code from the Python side. Wire up
  scikit-build-core + CMake.
- **linux-support**: Replace `CoreFoundation` / `CFStringRef`
  string handling with platform-conditional code. Link against
  the DeckLink SDK's Linux shared library. Test on Linux.
- **scheduled-playback**: Replace `DisplayVideoFrameSync` with
  `ScheduleVideoFrame` + `IDeckLinkVideoOutputCallback` for
  sustained frame-rate output. This is required for the
  pyprovideo `OutputStream` contract.
- **capture-input**: Implement capture via
  `IDeckLinkInputCallback::VideoInputFrameArrived`. Queue frames
  internally; expose as blocking `acquire_frame()`. Required for
  the pyprovideo `InputStream` contract.
- **device-enumeration**: Bind `IDeckLinkIterator` to expose
  device count, names, and capabilities from Python.

## pyprovideo protocol layer

Create the `packages/pyprovideo/` package. Pure Python — no
compiled extensions. Defines protocols, format model, and
backend discovery.

Depends on: mono-repo scaffold (for workspace structure).

- **protocols**: Define `Device`, `Backend`, `InputStream`,
  `OutputStream`, `StreamStatus` as `typing.Protocol` classes.
  Define `VideoFormat`, `PixelFormat`, `HDRMetadata`, `EOTF`
  data types.
- **discovery**: Implement `enumerate_devices()` with entry-point
  based backend loading. Lazy-load, graceful `ImportError`
  handling, optional `backends=` filter.
- **format-mapping**: Utility for backends to register
  bidirectional mappings between native format enums and
  pyprovideo's `VideoFormat` / `PixelFormat`.

## Backend shims

Wire pyntv2 and pydecklink into pyprovideo's backend protocol.

Depends on: pyprovideo protocol layer, pydecklink nanobind rewrite.

- **pyntv2-backend**: Add `AjaBackend` class to pyntv2 that
  implements the `Backend` protocol. Map `open_input` /
  `open_output` to Card + routing + AutoCirculate. Register
  entry point in `pyproject.toml`.
- **pydecklink-backend**: Add `DeckLinkBackend` class to
  pydecklink that implements the `Backend` protocol. Map
  `open_input` / `open_output` to the nanobind-bound device.
  Register entry point.
- **cross-backend-test**: Integration test: enumerate devices
  from both backends in one `enumerate_devices()` call. Runs
  locally on dev machine with both cards installed.

## GPU DMA pipeline

End-to-end: AJA RDMA capture to GPU, GPU processing, output via
Blackmagic DMA.

Depends on: backend shims, pyntv2 GPU RDMA (existing Phase 2 work).

- **gpu-staging**: When `submit_frame` receives a CUDA buffer and
  the backend lacks RDMA, automatically `cudaMemcpy` to a pinned
  host staging buffer before DMA. Transparent to the caller.
- **buffer-allocator**: `stream.allocate_buffer()` returns a
  pre-pinned, page-aligned buffer appropriate for the backend.
  AJA returns mmap'd + `dma_buffer_lock`'d memory. Blackmagic
  returns pinned host memory.
- **cross-vendor-passthrough**: Integration test: AJA capture →
  CuPy buffer → identity transform → Blackmagic output. Verify
  zero dropped frames over N seconds.

## signal-gen refactor

Refactor bmd-signal-gen to use pyprovideo for device output.
Separate concern — lives in the bmd-signal-gen / signal-gen repo,
not in this mono-repo.

Depends on: backend shims.

- **strip-decklink-dep**: Replace direct `BMDDeckLink` usage in
  CLI commands and API server with `pyprovideo.enumerate_devices()`
  + `OutputStream.submit_frame()`. Remove `bmd_sg/decklink/`
  directory.
- **vendor-neutral-cli**: CLI device selection flag accepts vendor
  and index (e.g., `--device aja:0`, `--device blackmagic:0`).
  Default: first available device.

## Future

- **pydeltacast**: Deltacast VideoMaster backend. Wrap `VHD_*`
  flat C API with nanobind. Board/stream/slot → Device/Stream/Frame.
  Blocked — requires Deltacast hardware and SDK access.
- **audio-streams**: Extend pyprovideo protocols with audio
  capture/playout. Requires spec work on buffer format, sample
  rate negotiation, and A/V sync.
- **ancillary-data**: Timecode, closed captions via SDI ancillary
  data.
