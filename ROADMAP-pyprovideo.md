# Roadmap

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

## pydecklink

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
- **device-enumeration**: Bind `IDeckLinkIterator` to expose
  device count, names, and capabilities from Python.
- **scheduled-playback**: Replace `DisplayVideoFrameSync` with
  `ScheduleVideoFrame` + `IDeckLinkVideoOutputCallback` for
  sustained frame-rate output.
- **capture-input**: Implement capture via
  `IDeckLinkInputCallback::VideoInputFrameArrived`. Queue frames
  internally; expose as blocking pop with timeout.

## Future

- **pyprovideo**: Vendor-neutral protocol layer over pyntv2 and
  pydecklink. Deferred until both packages are stable and real
  cross-vendor usage patterns emerge. See spec section 7.
- **signal-gen-refactor**: Refactor bmd-signal-gen to consume
  pydecklink directly (then later pyprovideo). Lives in the
  bmd-signal-gen repo, not here.
- **pydeltacast**: Deltacast VideoMaster backend.
  Blocked — requires hardware and SDK access.
- **audio-streams**: Audio capture/playout.
- **ancillary-data**: Timecode, closed captions via SDI ancillary
  data.
