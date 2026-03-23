# pyntv2 — Python Bindings for libajantv2

## 1. Problem Statement

*Status: complete*

AJA provides no Python interface to their NTV2 SDK. Users who want to
capture or play out video via AJA hardware from Python must either shell
out to CLI tools or write C++. This blocks adoption in Python-centric
video pipelines (ML inference, QC, monitoring, live production tooling).

pyntv2 exposes the AutoCirculate API — AJA's high-performance
frame-accurate capture/playout engine — as a Python module. It supports
both CPU buffers (numpy) and NVIDIA GPU buffers (CuPy/PyTorch) for
RDMA-enabled zero-copy streaming.

## 2. Development Environment

*Status: complete*

Development uses a VS Code devcontainer that builds libajantv2 from
source at a pinned release tag and installs it to `/usr/local`. No
host-side SDK installation is required.

### Why a devcontainer

libajantv2 installs headers and a static library to system paths.
Containing the build avoids polluting the host and pins the SDK
version, compiler, and Python version for reproducibility.

The SDK defaults to a static build (`AJANTV2_BUILD_SHARED=OFF`).
The static archive links into consumers (the Python extension, host
diagnostic tools) at build time. No runtime `.so` dependency. This
is correct for both use cases: a Python C extension is itself a
`.so` but statically links its dependencies; standalone binaries
avoid `LD_LIBRARY_PATH` and work with `setcap` file capabilities.

### Constraints

- The Dockerfile's pinned SDK tag must match the host's loaded AJA
  kernel driver version. AJA documents compatible pairs in their
  release notes.
- The container runs as a non-root user via `--userns=keep-id`. The
  host's AJA device node (`/dev/ajantv20`) is passed through via
  `--device`.
- GPU passthrough (NVIDIA Container Toolkit) is deferred to Phase 2.

### Container device access

The NTV2 kernel driver has no Linux capability checks. All
operations — register I/O, DMA buffer locking, AutoCirculate
transfers (both directions) — use standard ioctl on the device
node. The only requirements are:

- Read/write access to `/dev/ajantv20` (the driver creates it
  mode 666).
- Sufficient `RLIMIT_MEMLOCK` for DMA page pinning (the driver
  calls `get_user_pages` without accounting against the limit,
  but user-space `mlock` may still need headroom).

The devcontainer runs rootless Podman with `--userns=keep-id`,
which maps the host user's UID 1:1 into the container. The host
user's permissions on the device node pass through unchanged.
`--security-opt=label=disable` prevents SELinux from relabeling
the device node inside the container. No `--privileged`, no
`--cap-add` flags are needed.

## 3. Binding Technology

*Status: complete*

The module uses [nanobind](https://github.com/wjakob/nanobind) (not
pybind11).

### Why nanobind

- `nb::ndarray<>` dispatches on device tags (`nb::device::cpu`,
  `nb::device::cuda`). One C++ binding handles both CPU and GPU
  buffers; the device determines whether `DMABufferLock` uses RDMA.
- 2.7–4.4× faster compile times than pybind11. The NTV2 SDK has
  hundreds of enums; compile time compounds.
- ~3–10× lower call overhead. AutoCirculate runs at frame rate
  (≤16.7 ms at 60 fps); dispatch cost matters.
- Built-in `.pyi` stub generation via `nanobind_add_stub()`.
- Production-proven for GPU bindings (JAX, Apple MLX, XLA).

### Build system

- [scikit-build-core](https://github.com/scikit-build/scikit-build-core)
  drives the Python packaging. Requires Python ≥3.12.
- CMake finds libajantv2 via `find_package` or a vendored copy.
- nanobind is fetched via `find_package(nanobind)` (pip-installed) or
  CMake `FetchContent`. Python ≥3.12 enables nanobind's Stable ABI
  support for cross-version binary compatibility.

## 4. Device Model

*Status: complete*

pyntv2 accepts any array-like object that implements the buffer protocol
or DLPack. nanobind's `nb::ndarray<>` inspects the device at dispatch
time.

| Buffer source | Device tag | DMABufferLock | Platform |
|---|---|---|---|
| numpy array | `nb::device::cpu` | `rdma=false` | Linux, macOS, Windows |
| CuPy array | `nb::device::cuda` | `rdma=true` | Linux only |
| PyTorch CPU tensor | `nb::device::cpu` | `rdma=false` | Linux, macOS, Windows |
| PyTorch CUDA tensor | `nb::device::cuda` | `rdma=true` | Linux only |

### Why this design

The AJA kernel driver's RDMA path calls NVIDIA's `nvidia_p2p_*` APIs
directly. No user-space GPU interop is needed — the driver pins GPU
pages and builds scatter-gather lists internally. From the wrapper's
perspective, the only difference between CPU and GPU is the `rdma` flag
on `DMABufferLock`.

The driver's RDMA interface is pluggable (`struct ntv2_page_fops`), but
only NVIDIA callbacks exist today. If AMD ROCm support lands in the AJA
driver, `nb::ndarray<nb::device::rocm>` tensors would work without
wrapper changes.

## 5. Python API (Phase 1)

*Status: complete*

The API is a thin 1:1 mapping of `CNTV2Card` methods to Python. Each
C++ method that returns `bool` raises `RuntimeError` on failure.
Naming follows Python convention: `AutoCirculateStart` →
`autocirculate_start`.

### 5.1 Card

Wraps `CNTV2Card`. Opens the device on construction or via `open()`.
Supports context manager protocol for deterministic cleanup.

### 5.2 Format Detection and Configuration

The module exposes format detection and card configuration methods
that map 1:1 to their C++ counterparts:

- `get_input_video_format(source) → VideoFormat` — queries hardware
  for the signal present on the given input. Returns
  `VideoFormat.UNKNOWN` when no signal is detected.
- `set_video_format(format, channel)` — applies resolution/rate.
- `set_frame_buffer_format(channel, pixel_format)` — sets pixel
  format for framebuffer read/write.
- `enable_channel(channel)` — activates a FrameStore.
- `set_mode(channel, mode)` — sets capture or playout mode.
- `set_sdi_transmit_enable(channel, enable)` — switches SDI
  connector between transmit and receive.
- `set_reference(source)` — sets clock reference.

### 5.3 Signal Routing

The crosspoint routing API is exposed directly:

- `connect(sink, source)` — connects one widget output to a widget
  input.
- `disconnect(sink)` — breaks a connection.
- `clear_routing()` — breaks all crosspoint connections.
- `apply_signal_route(connections, clear_first=True)` — batch-applies
  a routing table from a `dict[InputXpt, OutputXpt]`.

Two module-level convenience functions build common routes:

- `route_capture(source, channel, pixel_format)` — returns a
  connection dict for single-link capture. Inserts a CSC widget when
  the input color space (YCbCr for SDI) differs from the framebuffer
  pixel format (RGB).
- `route_playout(channel, output, pixel_format)` — returns a
  connection dict for single-link playout. Inserts CSC when needed.

These return data (a dict), not side effects. The caller applies the
route via `card.apply_signal_route()`.

### 5.4 AutoCirculate

- `autocirculate_init_for_input(channel, frame_count=7,
  audio_system=AudioSystem.NONE, option_flags=0)` — allocates
  on-device frame buffers for capture.
- `autocirculate_init_for_output(...)` — same, for playout.
- `autocirculate_start(channel)` — begins hardware-driven frame
  circulation.
- `autocirculate_stop(channel, abort=False)` — stops circulation.
- `autocirculate_get_status(channel) → Status` — returns a read-only
  snapshot of circulation state.
- `autocirculate_transfer(channel, transfer)` — executes a DMA
  transfer using a `Transfer` object.

### 5.5 Transfer

Wraps `AUTOCIRCULATE_TRANSFER`. The caller creates a `Transfer`,
sets the video buffer via `set_video_buffer()`, and reuses it across
frames. This maps 1:1 to the C++ usage pattern.

`set_video_buffer` accepts any `nb::ndarray<>`-compatible object
(numpy, CuPy, PyTorch). It extracts the raw pointer and byte size
from the array.

After a capture transfer, `captured_audio_byte_count` and
`captured_anc_byte_count` properties report transfer metadata.

### 5.6 Buffer Locking

`dma_buffer_lock(buffer)` and `dma_buffer_unlock(buffer)` pre-lock
buffer pages for DMA. The device tag on the array determines whether
RDMA is used. Optional but recommended for sustained streaming —
avoids per-frame page pinning overhead.

### 5.7 Frame Sync

`wait_for_input_vertical_interrupt(channel, repeat_count=1)` blocks
until the next vertical blanking interval.

### 5.8 Status

Read-only snapshot from `AUTOCIRCULATE_STATUS`. Fields:
`is_running`, `is_stopped`, `has_available_input_frame`,
`can_accept_more_output_frames`, `dropped_frame_count`,
`buffer_level`, `with_audio`, `with_custom_anc`.

### 5.9 Enums

Bound from NTV2 C++ enums via `nb::enum_<>`:

| Python name | C++ enum | Notes |
|---|---|---|
| `Channel` | `NTV2Channel` | CH1–CH8 |
| `AudioSystem` | `NTV2AudioSystem` | NONE, SYSTEM_1–8 |
| `VideoFormat` | `NTV2VideoFormat` | All SDK values |
| `PixelFormat` | `NTV2FrameBufferFormat` | All SDK values |
| `InputSource` | `NTV2InputSource` | SDI1–8, HDMI1–4 |
| `OutputDest` | `NTV2OutputDestination` | SDI1–8, HDMI |
| `InputXpt` | `NTV2InputCrosspointID` | All SDK values |
| `OutputXpt` | `NTV2OutputCrosspointID` | All SDK values |
| `Mode` | `NTV2Mode` | CAPTURE, OUTPUT |
| `ReferenceSource` | `NTV2ReferenceSource` | FREERUN, INPUT1, EXTERNAL, etc. |

## 6. Target Workflow

*Status: not started*

The system supports an ML inference passthrough pipeline: capture a
live SDI/HDMI signal on one channel, process frames on GPU (or CPU),
and play out the result on another channel at the same format.

The input video format is auto-detected from the signal. The output
channel is configured to match. Both channels use the same pixel
format. Frames transfer directly between the AJA card and GPU memory
via RDMA, bypassing system memory entirely.

## 7. Integration Testing

*Status: in progress*

Integration tests require AJA hardware. CH3 and CH4 are connected
via SDI loopback cable. Tests run locally with `pytest -m hardware`
and on dedicated CI runners with AJA cards installed.

### 7.1 Loopback (data integrity)

Generate a known test pattern in memory, playout on CH3, capture on
CH4, and compare buffers. Verifies DMA write → wire → DMA read
preserves data byte-for-byte.

Test patterns: all zeros, incrementing ramp, random noise,
checkerboard (0xAA/0x55). Each catches a different class of
corruption (stuck bits, byte swaps, stride misalignment, adjacent-bit
crosstalk).

Two variants exercise the same path with different buffer types:

- **CPU loopback**: numpy buffers, `rdma=false`.
- **GPU loopback**: CuPy buffers, `rdma=true`. Requires NVIDIA GPU +
  AJA card on the same PCIe bridge.

### 7.2 Passthrough (frame-rate transfer)

Capture on CH4, DMA to host/GPU memory, DMA back out on CH3.
Exercises the sustained AutoCirculate pump: init → start → transfer
loop → stop. The loopback cable feeds CH3's output back to CH4's
input, creating a closed loop.

Verification: run for N frames, assert zero dropped frames and
stable buffer levels. Data integrity is already covered by 7.1;
this test validates timing and flow control.

Two variants:

- **CPU passthrough**: numpy buffer, single-buffer round-trip.
- **GPU passthrough**: CuPy buffer, RDMA both directions. Validates
  that frames never touch system memory.

## 8. Secondary Use Case: Test Pattern Generation

*Status: not started*

The primary use case is GPU RDMA streaming (Section 6). A secondary
use case is CPU-buffer playout of static test patterns for display
measurement, integrating with
[OLE-Toolset](https://github.com/OpenLEDEval/OLE-Toolset) via
[bmd-signal-gen](https://github.com/OpenLEDEval/bmd-signal-gen).

bmd-signal-gen currently targets Blackmagic DeckLink hardware. Its
pattern generation (solids, checkerboards, HDR metadata) is
device-agnostic — it produces numpy buffers. The device output layer
is BMD-specific.

### Integration path

A narrow `FrameOutput` protocol (configure, present, stop) would let
signal-gen drive either a DeckLink or AJA backend. pyntv2 provides
the AJA implementation. The protocol belongs in signal-gen (the
consumer), not here. pyntv2's existing API (`set_video_format`,
`autocirculate_*`, `Transfer.set_video_buffer`) is sufficient to
implement it without changes.

### Why this is secondary

GPU RDMA streaming operates at frame rate with locked buffers and
sustained AutoCirculate. Test pattern output sends one frame and
holds — no continuous transfer loop, no GPU memory, no latency
constraints. The API surface overlaps but the performance envelope
is different.

## 9. Explicit Non-Goals (Phase 1)

- **AMD GPU RDMA.** No AJA driver support exists. The architecture
  doesn't block it if support arrives.
- **Apple-specific features.** CPU path works on macOS. No RDMA.
- **Audio capture/playout.** `AudioSystem` param exists but audio
  buffer transfer is deferred.
- **Ancillary data.** SDI ancillary data (closed captions, timecode
  metadata) is deferred.
- **Multi-channel / quad-link 4K.** Single-channel only in Phase 1.
- **Advanced routing.** The full crosspoint widget graph is accessible
  via `connect()`/`disconnect()`, but only simple single-link
  capture and playout routes are provided as convenience functions.
