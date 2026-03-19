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

libajantv2 installs headers and a shared library to system paths.
Containing the build avoids polluting the host and pins the SDK
version, compiler, and Python version for reproducibility.

### Constraints

- The Dockerfile's pinned SDK tag must match the host's loaded AJA
  kernel driver version. AJA documents compatible pairs in their
  release notes.
- The container runs as a non-root user. The host's AJA device node
  (`/dev/ajantv20`) is passed through via `--device`.
- GPU passthrough (NVIDIA Container Toolkit) is deferred to Phase 2.

## 3. Binding Technology

*Status: in progress*

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

*Status: not started*

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

*Status: in progress*

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

## 7. Explicit Non-Goals (Phase 1)

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
