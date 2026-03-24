# pyntv2 — Python Bindings for libajantv2

## 1. Problem Statement

*Status: complete*

AJA provides no Python interface to their NTV2 SDK. Users who want to
capture or play out video via AJA hardware from Python must either shell
out to CLI tools or write C++. This blocks adoption in Python-centric
video pipelines (ML inference, QC, monitoring, live production tooling).

pyntv2 exposes the AutoCirculate API — AJA's high-performance
frame-accurate capture/playout engine — as a Python module. It uses
CPU buffers (numpy) for DMA transfers.

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
- The container runs as the base image's default non-root user
  (`ubuntu:1000` on `ubuntu:24.04`). `--userns=keep-id` maps the
  host user's UID 1000 to container UID 1000, so files created
  inside the container on bind-mounted volumes are owned by the
  host user. This allows a single `.venv` shared between host and
  container with no ownership conflicts. The host's AJA device
  node (`/dev/ajantv20`) is passed through via `--device`.
- Common developer tools (sudo, GitHub CLI, fish shell) are installed
  via devcontainer features, not manual Dockerfile steps. This keeps
  the Dockerfile focused on project-specific build dependencies
  (libajantv2, uv, Claude Code).
- GPU passthrough (NVIDIA Container Toolkit) is not needed — see §4
  for why GPU RDMA is infeasible with this hardware.

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

- `nb::ndarray<>` provides a uniform buffer interface for numpy,
  CuPy, and PyTorch arrays without manual buffer-protocol handling.
- 2.7–4.4× faster compile times than pybind11. The NTV2 SDK has
  hundreds of enums; compile time compounds.
- ~3–10× lower call overhead. AutoCirculate runs at frame rate
  (≤16.7 ms at 60 fps); dispatch cost matters.
- Built-in `.pyi` stub generation via `nanobind_add_stub()`.

### Build system

- [scikit-build-core](https://github.com/scikit-build/scikit-build-core)
  drives the Python packaging. Requires Python ≥3.12.
- CMake finds libajantv2 via `find_package` or a vendored copy.
- nanobind is fetched via `find_package(nanobind)` (pip-installed) or
  CMake `FetchContent`. Python ≥3.12 enables nanobind's Stable ABI
  support for cross-version binary compatibility.

## 4. Device Model

*Status: complete*

pyntv2 uses CPU buffers (numpy) for all DMA transfers. The binding
accepts any `nb::ndarray<>`-compatible object, but only CPU-resident
buffers produce correct DMA transfers.

| Buffer source | DMABufferLock | Platform |
|---|---|---|
| numpy array | `rdma=false` | Linux, macOS, Windows |
| PyTorch CPU tensor | `rdma=false` | Linux, macOS, Windows |

### 32-bit DMA constraint

The AJA NTV2 DMA engine is 32-bit addressable. The kernel driver
sets `DMA_BIT_MASK(32)` during probe (`ntv2driver.c`); some firmware
revisions upgrade to 64-bit, but the cards in use here do not.

On x86_64 systems, physical memory above 4 GB is not directly
addressable by the DMA engine. The kernel's SWIOTLB bounce-buffer
layer translates high-address pages into the 32-bit range
transparently. This works for CPU buffers allocated via
`get_user_pages`.

`iommu=pt` (IOMMU passthrough) must be disabled. In passthrough
mode the kernel bypasses SWIOTLB, and DMA to high-address pages
fails silently or returns errors. Use `iommu=soft` or remove
`iommu=pt` from kernel parameters.

### Why GPU RDMA is not feasible

The AJA driver's RDMA path (`ntv2rdma.c`) calls NVIDIA's
`nvidia_p2p_get_pages()` to pin GPU memory and obtain physical
addresses for scatter-gather DMA. These addresses correspond to GPU
BAR windows, which modern systems map above 4 GB. The
`nvidia_p2p_*` API provides no mechanism to constrain returned
addresses below 4 GB.

The 32-bit DMA engine cannot address GPU BAR memory. SWIOTLB does
not intercede for `nvidia_p2p_*` mappings — those bypass the kernel
DMA allocator entirely. The result is truncated addresses and DMA
failures.

This is a hardware limitation of the DMA engine, not a software
issue. GPU frames must pass through CPU memory (capture → CPU →
GPU copy, or GPU → CPU copy → playout).

## 5. Python API (Phase 1)

*Status: in progress*

The API is a thin 1:1 mapping of `CNTV2Card` methods to Python. Each
C++ method that returns `bool` raises `RuntimeError` on failure.
Naming follows Python convention: `AutoCirculateStart` →
`autocirculate_start`.

### 5.1 Card

Wraps `CNTV2Card`. Opens the device on construction or via `open()`.
Supports context manager protocol for deterministic cleanup.

Device identity is available after opening:

- `device_id → int` — the `NTV2DeviceID` value identifying the card
  model (e.g. Corvid 44 12G, Kona 5). Read-only property.
- `display_name → str` — human-readable device name returned by the
  SDK. Read-only property.

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
  transfer using a `Transfer` object. Releases the GIL during the
  blocking DMA call so other Python threads can run concurrently.

### 5.5 Transfer

Wraps `AUTOCIRCULATE_TRANSFER`. The caller creates a `Transfer`,
sets the video buffer via `set_video_buffer()`, and reuses it across
frames. This maps 1:1 to the C++ usage pattern.

`set_video_buffer` accepts any `nb::ndarray<>`-compatible object
(numpy, PyTorch CPU tensors). It extracts the raw pointer and byte
size from the array. Only CPU-resident buffers are supported (see §4).

After a capture transfer, `captured_audio_byte_count` and
`captured_anc_byte_count` properties report transfer metadata.

### 5.6 Buffer Locking

`dma_buffer_lock(buffer)` and `dma_buffer_unlock(buffer)` pre-lock
buffer pages for DMA. Buffers must be page-aligned (4096 bytes);
use `mmap.mmap(-1, size)` + `numpy.frombuffer()` instead of
`numpy.zeros()`. Optional but recommended for sustained streaming —
avoids per-frame page pinning overhead.

### 5.7 Frame Sync

- `wait_for_input_vertical_interrupt(channel, repeat_count=1)` —
  blocks until the next input vertical blanking interval.
- `wait_for_output_vertical_interrupt(channel, repeat_count=1)` —
  blocks until the next output vertical blanking interval. Needed
  for playout pacing.

Both calls release the GIL during the blocking wait.

### 5.8 Status

Read-only snapshot from `AUTOCIRCULATE_STATUS`. Fields:
`is_running`, `is_stopped`, `has_available_input_frame`,
`can_accept_more_output_frames`, `dropped_frame_count`,
`buffer_level`, `with_audio`, `with_custom_anc`.

### 5.9 Transfer Status

After `autocirculate_transfer()` completes, the `Transfer` object
exposes `transferred_frame` — the on-device frame index used for
the transfer. Read from `acTransferStatus.acTransferFrame`.
Debugging aid for correlating DMA transfers with hardware state.

### 5.10 Format Metadata

Module-level helpers extract video format properties from
`NTV2FormatDescriptor`:

- `get_frame_bytes(video_format, pixel_format) → int` — total frame
  byte count. Used for allocating page-aligned DMA buffers.
- `get_format_width(video_format) → int` — raster width in pixels.
- `get_format_height(video_format) → int` — raster height in lines.
- `get_format_fps(video_format) → float` — frame rate in Hz.

These allow a consuming application to satisfy `FrameSource` protocol
properties (resolution, frame rate) without hardcoding format tables.

### 5.11 Enums

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
live SDI/HDMI signal on one channel, process frames on CPU, and play
out the result on another channel at the same format.

The input video format is auto-detected from the signal. The output
channel is configured to match. Both channels use the same pixel
format. Frames transfer between the AJA card and CPU memory via DMA.
GPU processing requires an explicit CPU↔GPU copy step (see §4 for
why direct GPU RDMA is infeasible).

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

Exercises the CPU DMA path with numpy buffers.

### 7.2 Passthrough (frame-rate transfer)

Capture on CH4, DMA to CPU memory, DMA back out on CH3.
Exercises the sustained AutoCirculate pump: init → start → transfer
loop → stop. The loopback cable feeds CH3's output back to CH4's
input, creating a closed loop.

Verification: run for N frames, assert zero dropped frames and
stable buffer levels. Data integrity is already covered by 7.1;
this test validates timing and flow control. Uses numpy buffers
with a single-buffer round-trip.

### 7.3 DMA Throughput Benchmark

Measures per-frame DMA transfer time on the CH3↔CH4 loopback path
at 3840×2160p59.94 (single-link 12G-SDI). The card is a Corvid 44
12G — each SDI port carries 12G, so 4K/60 fits a single link without
quad-link ganging.

The benchmark runs the same capture→playout loop as §7.2 but
instruments each `autocirculate_transfer` call with
`time.perf_counter`. It reports min, max, mean, and p99 DMA times
for both capture and playout directions.

Frame size: 22,118,400 bytes (21.1 MB) at 10-bit YCbCr. Frame
budget: 16.68 ms. The two-hop round trip (capture + playout DMA)
must complete within one frame period. SWIOTLB bounce-buffer
overhead is included in the measurement — this is the real-world
path, not a synthetic DMA-only test.

The benchmark is a pytest test marked `hardware` and `benchmark`.
It asserts zero dropped frames as a pass/fail gate but primarily
exists to produce timing data for capacity planning.

## 8. Secondary Use Case: Test Pattern Generation

*Status: not started*

The primary use case is the CPU DMA passthrough pipeline (Section 6).
A secondary use case is CPU-buffer playout of static test patterns for
display
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

The passthrough pipeline operates at frame rate with locked buffers
and sustained AutoCirculate. Test pattern output sends one frame and
holds — no continuous transfer loop, no latency constraints. The API
surface overlaps but the performance envelope is different.

## 9. Reliability Engineering

*Status: complete*

The codebase has no static analysis, no Python linting, and CI does
not run the existing unit tests. Buffer validation in the C++ layer
is incomplete — non-contiguous or read-only arrays can cause silent
data corruption or segfaults. One method pair accepts and returns raw
`int` where a typed enum exists. Error messages from the generic
`check()` helper lack argument context, making failures hard to
diagnose without a debugger.

This section specifies hardening work that reduces the surface area
for development errors without adding features.

### 9.1 Static Analysis in CI

The CI pipeline shall run ruff (lint + format check) and mypy
(strict mode) on all Python source and test files. The nanobind-
generated `.pyi` stubs provide the type surface for mypy. ruff
catches unused imports, unreachable code, shadowed names, and style
drift.

### 9.2 Unit Tests in CI

The CI pipeline shall run all no-hardware unit tests
(`test_enums`, `test_routing`, `test_card`, `test_transfer`,
`test_format`) after the build step. These tests require no AJA
device and run on any GitHub-hosted runner. The current CI only
verifies that `import pyntv2` succeeds.

### 9.3 Buffer Validation

`Transfer.set_video_buffer()` and `Card.dma_read_frame()` /
`Card.dma_write_frame()` shall validate buffers before extracting
raw pointers:

- **Contiguity**: the buffer must be C-contiguous. A sliced or
  transposed numpy array has non-contiguous memory; passing its
  `.data` pointer with `.nbytes` to the DMA engine reads/writes
  wrong addresses. Raise `ValueError` if not contiguous.
- **Writability** (capture only): `dma_read_frame()` and
  `set_video_buffer()` used for capture write into the buffer. A
  read-only buffer (e.g. `array.flags.writeable = False`) would
  cause undefined behavior. Raise `ValueError` if the buffer is
  read-only and the operation writes into it.

### 9.4 Typed Enum for EveryFrameServices

`get_every_frame_services()` and `set_every_frame_services()` shall
use a bound `TaskMode` enum (`NTV2EveryFrameTaskMode`) instead of
raw `int`. This prevents passing arbitrary integers to the SDK and
makes the valid values discoverable in Python.

### 9.5 Routing Input Validation

`route_capture()` and `route_playout()` shall raise `ValueError`
with a descriptive message when passed an unsupported enum member
(e.g. `InputSource.ANALOG1`, `InputSource.INVALID`,
`Channel.INVALID`). The current behavior is an unadorned `KeyError`
from the lookup dict.

### 9.6 Richer Error Messages in check()

The `check()` utility in `bind_common.h` shall accept a
`std::string` (not just `const char*`) so callers can include
argument values in the error message. Methods that take enum
arguments shall format those values into the error string.

Why: the existing `autocirculate_transfer` error handler proves the
value of rich diagnostics — channel, state, buffer level, DMA
pointer, and errno. The simpler methods produce only
`"Card.set_mode failed"` with no indication of which channel or
mode was requested.

AutoCirculate state-transition methods (`autocirculate_start`,
`autocirculate_stop`, `autocirculate_init_for_input`,
`autocirculate_init_for_output`) shall query
`autocirculate_get_status` on failure and include the current
`acState` in the error message. Calling `start` on a channel that
was never initialized or is already running produces a silent
`false` from the SDK — the error message must say what state the
channel was actually in.

### 9.7 Expanded Unit Test Coverage

New no-hardware unit tests shall cover:

- `get_frame_bytes()` for valid and invalid format combinations.
- Routing functions with every valid `Channel` (CH1–CH8) to
  catch lookup table drift when enum members are added.
- Routing functions with invalid/unsupported inputs to verify
  `ValueError` is raised (after §9.5 lands).
- `autocirculate_init_for_input` / `_for_output` with
  `frame_count < 3` to verify `InvalidArgumentError`.
- `Transfer.set_video_buffer` with non-contiguous and read-only
  buffers to verify `ValueError` (after §9.3 lands).
- All 8 SDI output destinations in `route_playout` (currently
  only SDI1 and SDI3 are tested).

### 9.8 Public API Surface Control

`__init__.py` shall define `__all__` listing every public name.
The wildcard re-export (`from _bindings import *`) currently leaks
any internal symbol nanobind generates. `__all__` makes the public
API explicit and prevents accidental breakage when nanobind
internals change.

### 9.9 Script Retirement

The `scripts/` directory contains exploration code written before
the Python bindings and test suite existed:

- `test_capture_minimal.cpp` + `CMakeLists.txt` — standalone C++
  capture test. Superseded by `tests/test_integration.py` (loopback
  probe, data integrity, passthrough) and `examples/passthrough.py`.
- `probe_capture_dma.py` — single-channel Python capture probe.
  Superseded by `_probe_capture_dma()` in `test_integration.py` and
  by `examples/passthrough.py`.

These shall be deleted. Their diagnostic value is fully covered by
the test suite and example code.

`reset_card.sh` shall remain. It performs PCI function-level reset
and driver reload after a DMA timeout — an operational recovery
procedure that cannot be replaced by Python-level code.

The `.gitignore` in `scripts/` shall be simplified to cover only
`reset_card.sh`'s concerns (no build artifacts from removed C++).

## 10. Explicit Non-Goals (Phase 1)

- **GPU RDMA.** The 32-bit DMA engine cannot address GPU BAR memory
  (see §4). GPU frames require explicit CPU↔GPU copies.
- **Apple-specific features.** CPU path works on macOS.
- **Audio capture/playout.** `AudioSystem` param exists but audio
  buffer transfer is deferred.
- **Ancillary data.** SDI ancillary data (closed captions, timecode
  metadata) is deferred.
- **Multi-channel / quad-link 4K.** Single-channel only in Phase 1.
- **Advanced routing.** The full crosspoint widget graph is accessible
  via `connect()`/`disconnect()`, but only simple single-link
  capture and playout routes are provided as convenience functions.
