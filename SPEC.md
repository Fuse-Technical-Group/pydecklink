# pydecklink — Python Bindings for Blackmagic DeckLink

## 1. Problem Statement

*Status: not started*

Blackmagic provides no Python interface to the DeckLink SDK. Users who
want to capture or play out video via DeckLink hardware from Python
must shell out to CLI tools, use ctypes against a C wrapper, or write
C++. This blocks adoption in Python-centric video pipelines (ML
inference, QC, monitoring, live production tooling).

pydecklink exposes DeckLink's capture and scheduled playback APIs as a
Python module. It uses CPU buffers (numpy) for frame transfers.

### Prior art

[bmd-signal-gen](https://github.com/OpenLEDEval/bmd-signal-gen)
wraps a subset of the DeckLink SDK (synchronous single-frame output)
via `extern "C"` + ctypes. It targets macOS only and is not designed
for sustained frame-rate streaming. pydecklink replaces that approach
with nanobind, scheduled playback, capture input, and Linux support.

## 2. Development Environment

*Status: complete*

VS Code devcontainer based on `ubuntu:24.04` with devcontainer
features (cmake, ninja, uv). DeckLink SDK headers vendored locally
(gitignored — Blackmagic's license prohibits redistribution).

### Why a devcontainer

Pins the compiler, Python version, and build toolchain for
reproducibility.

### SDK integration

- **Headers** — vendored in `vendor/` at a pinned version (15.3).
  Header-only on Linux.
- **Dispatch source** (`DeckLinkAPIDispatch.cpp`) — compiled into the
  extension. Uses `dlopen` to load `libDeckLinkAPI.so` at runtime.
  CMake conditionally includes it when the vendor directory exists,
  allowing CI to build without the SDK.
- **Runtime library** (`libDeckLinkAPI.so`) — host-installed via
  Desktop Video. No link-time dependency; `dlopen` at import time.

### Constraints

- SDK header version should match installed Desktop Video version.
- Container runs as `ubuntu:1000` with `--userns=keep-id`. Host
  DeckLink device nodes (`/dev/blackmagic/*`) passed via `--device`.
- `libDeckLinkAPI.so` bind-mounted from host into container.

## 3. Binding Technology

*Status: complete*

[nanobind](https://github.com/wjakob/nanobind) with
[scikit-build-core](https://github.com/scikit-build/scikit-build-core).

### Why nanobind

- `nb::ndarray<>` for zero-copy numpy buffer integration.
- Low call overhead for frame-rate callbacks.
- Built-in `.pyi` stub generation.
- Stable ABI (abi3) for cross-version binary compatibility.

### Build system

scikit-build-core drives Python packaging (Python ≥3.12). CMake
finds nanobind via `find_package`, conditionally includes vendored
SDK sources when present. CI builds without the SDK; the extension
compiles but has no DeckLink functionality until the SDK is available.

## 4. Device Model

*Status: complete*

### Why COM lifetime is hidden

The DeckLink SDK uses COM (`AddRef`/`Release`) on all platforms. The
binding manages COM lifetimes via RAII `ComPtr<T>` — Python never
calls `AddRef` or `Release`. This prevents leaks and use-after-free
from Python's non-deterministic GC.

### Why CPU buffers only

The SDK provides no GPU RDMA path (`NVIDIA_GPUDirect/` contains only
deprecated DVP headers). All frame data passes through CPU memory as
numpy arrays. GPU processing requires explicit copies.

### Why C++ callback queues

SDK callbacks (`VideoInputFrameArrived`, `ScheduledFrameCompleted`)
run on internal SDK threads. Acquiring the GIL at frame rate would
block the SDK thread if Python is slow. Instead, C++ callbacks copy
frame data into bounded thread-safe queues; Python consumes via
blocking pop. The queue drops oldest frames on overflow, matching
hardware behavior.

## 5. Python API

*Status: in progress*

### 5.1 Device

Wraps `IDeckLink`. Created via enumeration or by device index.
Supports context manager protocol.

- `Device(index=0)` — open device by index.
- `Device.model_name → str` — hardware model.
- `Device.display_name → str` — user-visible name.
- `Device.supports_capture → bool` — via `BMDDeckLinkVideoIOSupport`.
- `Device.supports_playback → bool` — via `BMDDeckLinkVideoIOSupport`.
- `Device.supports_input_format_detection → bool`
- `Device.supports_hdr → bool`

Module-level enumeration:

- `device_count() → int`
- `list_devices() → list[DeviceInfo]` — lightweight metadata without
  opening devices.

### 5.2 Display Modes

`IDeckLinkDisplayMode` properties exposed as a Python object:

- `DisplayMode.mode → DisplayModeEnum` — the `BMDDisplayMode` value.
- `DisplayMode.name → str`
- `DisplayMode.width → int`
- `DisplayMode.height → int`
- `DisplayMode.frame_rate → tuple[int, int]` — (duration, timescale).
- `DisplayMode.field_dominance → FieldDominance`

Device-level queries:

- `device.get_display_mode_iterator() → Iterator[DisplayMode]`
- `device.does_support_video_mode(mode, pixel_format, direction) → bool`

### 5.3 Capture

The binding implements `IDeckLinkInputCallback` in C++. Captured
frames are copied into a bounded queue. Python consumes frames via
blocking pop.

Setup:

- `device.enable_video_input(mode, pixel_format, flags=0)`
- `device.start_streams()`
- `device.stop_streams()`
- `device.disable_video_input()`

Frame retrieval:

- `device.pop_capture_frame(timeout_ms=1000) → CaptureFrame | None`

`CaptureFrame` exposes:

- `data → numpy.ndarray` — frame pixels (uint8 view of raw bytes).
- `width, height → int`
- `pixel_format → PixelFormat`
- `stream_time → tuple[int, int]` — (time, duration) at input
  timescale.
- `hardware_reference_timestamp → int`
- `has_signal → bool` — `False` when `bmdFrameHasNoInputSource`.

### Why internal queue (not Python callbacks)

Exposing `VideoInputFrameArrived` as a Python callback requires
acquiring the GIL on the SDK's thread at frame rate. If the Python
callback is slow, it blocks the SDK thread, which stalls all
callbacks for that device. A C++ queue with Python pop decouples the
SDK thread from Python execution. The queue drops oldest frames on
overflow, matching hardware behavior.

### 5.4 Format Detection

When `bmdVideoInputEnableFormatDetection` is passed to
`enable_video_input`, the SDK calls `VideoInputFormatChanged` on
signal changes. The binding handles this by:

1. Stopping streams internally.
2. Reconfiguring with the new mode and pixel format.
3. Restarting streams.
4. Exposing the new format via `device.current_input_format`.

This matches pyntv2's auto-detection pattern but is handled
internally because DeckLink's callback-driven model requires it.

### 5.5 Playout

Two output modes: synchronous (simple, blocking) and scheduled
(sustained frame-rate streaming).

#### Synchronous (for test patterns, stills)

- `device.enable_video_output(mode, flags=0)`
- `device.display_frame_sync(buffer)` — creates a frame, copies
  buffer data, calls `DisplayVideoFrameSync`. Blocks until displayed.
- `device.disable_video_output()`

#### Scheduled (for sustained streaming)

- `device.enable_video_output(mode, flags=0)`
- `device.schedule_frame(buffer, display_time, duration, timescale)`
- `device.start_scheduled_playback(start_time, timescale, speed=1.0)`
- `device.stop_scheduled_playback()`
- `device.is_scheduled_playback_running → bool`

The binding implements `IDeckLinkVideoOutputCallback` in C++. Frame
completion results (completed, late, dropped, flushed) are tracked
internally and exposed via:

- `device.output_status → OutputStatus` — dropped count, late count,
  underrun flag.

### 5.6 Frame Creation

- `device.create_video_frame(width, height, row_bytes, pixel_format)
  → MutableFrame` — wraps `IDeckLinkOutput::CreateVideoFrame`.
- `MutableFrame.data → numpy.ndarray` — writeable buffer via
  `IDeckLinkVideoBuffer`.

For the common case (schedule a numpy buffer), `schedule_frame` and
`display_frame_sync` accept a numpy array directly and handle frame
creation internally.

### 5.7 Configuration

Wraps `IDeckLinkConfiguration`:

- `device.set_config_flag(flag, value)`
- `device.get_config_flag(flag) → bool`
- `device.set_config_int(setting, value)`
- `device.get_config_int(setting) → int`

Used for SDI mode selection (4:4:4 vs 4:2:2), connector mapping, etc.

### 5.8 Enums

Bound from DeckLink SDK types via `nb::enum_<>`:

| Python name | SDK type | Notes |
|---|---|---|
| `DisplayModeEnum` | `BMDDisplayMode` | SD through 8K |
| `PixelFormat` | `BMDPixelFormat` | YUV 8/10-bit, RGB 8/10/12-bit |
| `VideoInputFlag` | `BMDVideoInputFlags` | Format detection, etc. |
| `VideoOutputFlag` | `BMDVideoOutputFlags` | VANC, RP188, etc. |
| `FieldDominance` | `BMDFieldDominance` | Progressive, upper, lower |
| `FrameFlag` | `BMDFrameFlags` | HDR, colorspace, no signal |
| `DetectedInputFormat` | `BMDDetectedVideoInputFormatFlags` | YCbCr/RGB, bit depth |
| `OutputFrameResult` | `BMDOutputFrameCompletionResult` | Completed, late, dropped |
| `ConfigFlag` | `BMDDeckLinkConfigurationID` | Flag-type config IDs |
| `ConfigInt` | `BMDDeckLinkConfigurationID` | Int-type config IDs |
| `DeviceAttribute` | `BMDDeckLinkAttributeID` | Capability query IDs |

### 5.9 Format Metadata

Module-level helpers (derived from display mode properties):

- `get_frame_bytes(mode, pixel_format) → int` — total frame size.
  Computed from `width × height × bytes_per_pixel` using SDK row
  bytes.
- `get_mode_width(mode) → int`
- `get_mode_height(mode) → int`
- `get_mode_fps(mode) → float`

## 6. Target Workflow

*Status: not started*

Same goal as pyntv2: an ML inference passthrough pipeline. Capture a
live SDI signal, process frames on CPU, play out the result — all
from Python, at frame rate.

The input format is auto-detected. The output is configured to match.
Frames transfer between the DeckLink card and CPU memory. GPU
processing requires explicit CPU↔GPU copies (see §4).

## 7. Integration Testing

*Status: not started*

Integration tests require DeckLink hardware. Tests run locally with
`pytest -m hardware`.

### 7.1 Device enumeration

Verify at least one device is found. Check model name, display name,
capability flags.

### 7.2 Signal detection

Connect an SDI source. Verify `enable_video_input` with format
detection resolves the correct mode and pixel format.

### 7.3 Capture

Capture N frames, verify frame data is non-zero, timestamps are
monotonically increasing, no dropped frames.

### 7.4 Playout

Schedule N frames of a known pattern, verify zero dropped frames and
stable output status.

### 7.5 Passthrough (loopback)

Capture on one sub-device, play out on another (requires a card with
both input and output, or two cards). Verify frame data integrity
end-to-end.

## 8. Secondary Use Case: Test Pattern Generation

*Status: not started*

bmd-signal-gen currently uses a ctypes wrapper for DeckLink output.
pydecklink replaces that wrapper. Signal-gen's pattern generation
(solids, gradients, HDR metadata) produces numpy buffers that
pydecklink can output directly via `display_frame_sync`.

The integration path is the same as pyntv2's §8: a narrow
`FrameOutput` protocol in signal-gen that either backend can satisfy.

## 9. Explicit Non-Goals (Phase 1)

- **GPU RDMA.** DeckLink SDK provides no GPU direct path. GPU frames
  require CPU copies.
- **Audio.** Deferred. The SDK supports audio scheduling; the binding
  does not expose it yet.
- **Ancillary data.** Timecode, closed captions — deferred.
- **HDR metadata.** The SDK supports it via frame metadata extensions.
  Deferred to Phase 2 (bmd-signal-gen integration needs it).
- **Windows / macOS.** Linux first. macOS is a future goal (the SDK
  supports it, but COM differs).
- **Deck control.** `IDeckLinkDeckControl` (tape transport) is not
  bound.
- **Video conversion.** No color space conversion, scaling. The SDK
  has some hardware conversion modes; exposing them is deferred.
