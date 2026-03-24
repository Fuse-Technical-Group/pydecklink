# Professional Video I/O Mono-repo

## 1. Problem Statement

*Status: not started*

Professional video I/O in Python is fragmented by vendor. Each SDK
(AJA NTV2, Blackmagic DeckLink, Deltacast VideoMaster) has its own
device model, frame lifecycle, and DMA semantics. Applications that
need to support multiple vendors must write and maintain separate
integration code for each.

This project co-locates Python bindings for AJA (pyntv2) and
Blackmagic (pydecklink) in a shared mono-repo. Each package exposes
its vendor's SDK directly — no premature abstraction layer. A
vendor-neutral wrapper (pyprovideo) is a future goal, deferred
until both packages are stable and real usage patterns emerge.

### Target pipeline

Capture a live SDI signal via AJA hardware, DMA the frame to GPU
memory, process it (ML inference, color correction, compositing),
and output the result via Blackmagic DeckLink — all from Python, at
frame rate, without unnecessary memory copies.

## 2. Architecture

*Status: not started*

### Mono-repo with independent packages

```text
pyntv2/                  # existing repo — renamed after migration
  packages/
    pyntv2/              # AJA NTV2 backend (nanobind, existing)
    pydecklink/          # Blackmagic DeckLink backend (nanobind, new)
  pyproject.toml         # uv workspace root
```

Each package publishes independently to PyPI. Applications import
the vendor package they need directly (`import pyntv2`,
`import pydecklink`).

### Why a mono-repo

- Shared build infrastructure: nanobind version, scikit-build-core
  config, Python version matrix, linting rules.
- Cross-package changes land in one PR, one review.
- Per-package publishing preserves install-time independence. Users
  who need only AJA install only `pyntv2`.

### Why separate packages (not one fat package)

- Install-time independence. Users install only the vendor they have
  hardware for. A Blackmagic user has no reason to pull in libajantv2.
- Per-package versioning. A pydecklink bugfix ships without rebuilding
  pyntv2.

### Testing model

CI has no access to video hardware. CI runs linting, type checking,
pure-Python unit tests, and wheel builds. All hardware integration
tests run locally on a dev machine with the relevant capture cards
installed. The dev machine currently has an AJA card; a Blackmagic
card will be added for cross-vendor testing.

### Migration from pyntv2 repo

The existing pyntv2 repository becomes the mono-repo root. Existing
code moves to `packages/pyntv2/`. New packages are added alongside.
The repo is renamed after pyntv2 is stable in its new location.

pydecklink is extracted from bmd-signal-gen. The DeckLink hardware
interface (`cpp/`, `bmd_sg/decklink/`) is copied into
`packages/pydecklink/` and rewritten with nanobind. Signal
generation code stays in the bmd-signal-gen repo. Git history for
the original DeckLink wrapper lives in the bmd-signal-gen repo.

## 3. pyntv2 (AJA)

*Status: not started*

Existing package. Nanobind bindings over AJA NTV2 SDK. Exposes
`Card`, `Channel`, `AutoCirculate`, signal routing, and format
enums. Moves from repo root to `packages/pyntv2/` — no API changes.

AJA-specific features (full crosspoint routing, explicit buffer
locking, VBI sync) are exposed directly. No abstraction layer.

## 4. pydecklink (Blackmagic)

*Status: not started*

Nanobind rewrite of the C++ wrapper from bmd-signal-gen. Replaces
the `extern "C"` shim + ctypes with direct class binding.

### Scope

- Device enumeration via `IDeckLinkIterator`.
- Output via scheduled playback (`ScheduleVideoFrame` +
  `IDeckLinkVideoOutputCallback`). Replaces single-frame
  `DisplayVideoFrameSync` for sustained streaming.
- Capture via `IDeckLinkInputCallback::VideoInputFrameArrived`.
  Queues frames internally; exposes as blocking pop with timeout.
- Linux support (currently macOS only). Replace `CoreFoundation` /
  `CFStringRef` string handling with platform-conditional code.

### Signal loss

The DeckLink SDK delivers frames with `bmdFrameHasNoInputSource`
on signal loss — callbacks continue but frame data is invalid.
pydecklink surfaces this as a flag on returned frame metadata.

### Output underrun

`ScheduledFrameCompleted` callback reports
`bmdOutputFrameDisplayedLate` and `bmdOutputFrameDropped`. If the
buffer empties completely, `ScheduledPlaybackHasStopped` fires.
pydecklink exposes dropped frame counts and underrun state.

## 5. DMA and GPU Interop

*Status: not started*

### DMA paths by vendor

| Vendor | CPU DMA | GPU RDMA (NVIDIA) | Notes |
|---|---|---|---|
| AJA NTV2 | AutoCirculate transfer | `nvidia_p2p_*` in kernel driver | Zero-copy GPU-card. Requires same PCIe bridge. |
| Blackmagic | Scheduled playback / sync display | Not supported by SDK | GPU frames must copy to host first. |

### Cross-vendor GPU pipeline

The target pipeline — AJA capture to GPU, process, Blackmagic
output — involves an asymmetric DMA path:

```text
AJA card ──RDMA──▶ GPU memory ──process──▶ GPU memory
                                              │
                                         cudaMemcpy
                                              │
                                              ▼
                                        Host buffer
                                              │
                                           DMA
                                              ▼
                                        BMD card
```

The GPU-to-host copy on the output side is unavoidable given current
Blackmagic SDK constraints. Each vendor package handles GPU buffer
staging internally (including `cudaMemcpy` when needed).

## 6. Explicit Non-Goals (current phase)

*Status: not started*

- **Vendor-neutral wrapper (pyprovideo).** Deferred until both
  packages are stable and real cross-vendor usage patterns emerge.
  Designing the abstraction before understanding the common surface
  area would be premature.
- **Audio.** Deferred.
- **Ancillary data.** Timecode, closed captions — deferred.
- **Windows.** Linux first. macOS where vendor SDKs support it.
- **Deltacast.** Requires hardware and SDK access.
- **Real-time scheduling.** Thread priority, CPU affinity,
  SCHED_FIFO — application concern.
- **Video processing.** No color conversion, scaling, or compositing.
  These packages move frames. Processing belongs in the application.

## 7. Future — pyprovideo wrapper

When both pyntv2 and pydecklink are stable and at least one
application uses both in a real pipeline, a vendor-neutral protocol
layer becomes viable. Design notes from early exploration are
preserved here as a starting point.

### Design direction

- `typing.Protocol` based (structural subtyping, not inheritance).
- Entry-point discovery for backends.
- `VideoFormat` as a dataclass, not an enum — the format space is
  too large for fixed enumeration.
- `PixelFormat` baseline subset (YCBCR_8, YCBCR_10, RGB_8, RGB_10)
  that all backends must support; optional formats advertised per
  device.
- Stream state machine: IDLE → CONFIGURED → RUNNING.
- Pure Python — GPU interop logic stays in vendor packages.
- Signal routing stays vendor-specific. AJA's crosspoint matrix
  cannot be meaningfully abstracted.

### Open questions (to resolve from usage)

- Whether `acquire_frame` should be pull-based (caller supplies
  buffer) or callback-based (backend pushes). AJA is naturally
  pull; BMD is naturally push.
- Whether a common `FrameMetadata` type is useful or whether each
  vendor's metadata is too different to unify.
- Thread safety contract for streams.
- Error model — common exceptions vs vendor-specific.
- HDR metadata handling — ignore on unsupported backends, or
  query capability first.
