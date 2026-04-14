# pydecklink — Python Bindings for Blackmagic DeckLink

## 1. Problem Statement

*Status: complete*

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
(committed — Blackmagic's header license permits redistribution).

### Why a devcontainer

Pins the compiler, Python version, and build toolchain for
reproducibility.

### SDK integration

SDK headers are vendored in `vendor/` at a pinned version (15.3).
The build system detects the platform and uses the appropriate SDK
artefacts:

| | Linux | Windows |
|---|---|---|
| SDK artefacts | C++ headers + dispatch source | IDL files → MIDL-generated headers + COM stubs |
| Runtime library | `libDeckLinkAPI.so` via `dlopen` | COM interfaces via `CoCreateInstance` |
| Build toolchain | C++ compiler, CMake | MSVC, Windows SDK (MIDL), CMake |

A platform abstraction layer (`platform.h`) provides type aliases
(`dlstring_t`, `dlbool_t`) and helpers (`DeckLinkStringToStd`,
`CreateDeckLinkIteratorInstance`) that hide platform differences
from all binding code.

CMake conditionally includes SDK sources when present, allowing CI
to build without the SDK on any platform.

### Constraints

- SDK header version should match installed Desktop Video version.
- Linux container runs as `ubuntu:1000` with `--userns=keep-id`.
  Host DeckLink device nodes (`/dev/blackmagic/*`) passed via
  `--device`. `libDeckLinkAPI.so` bind-mounted from host.
- Windows requires Visual Studio with the Desktop development with
  C++ workload (MSVC + Windows SDK for MIDL).

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

### Why CPU buffers (Phase 1)

The SDK ships deprecated DVP headers for GPU direct (`NVIDIA_GPUDirect/`)
but no maintained GPU RDMA path. Phase 1 uses CPU memory for all
frame transfers. A zero-copy path (`CaptureFrameRef`) avoids memcpy
by holding the SDK's DMA buffer by reference. A pre-allocated output
frame pool avoids per-frame allocation. Together these reduce the
per-frame CPU overhead to ~4.7ms at 4K 59.94 10-bit YUV, leaving
~10ms for processing.

### Custom buffer allocators

The SDK v15.3 provides `IDeckLinkVideoBufferAllocator` and
`IDeckLinkVideoBufferAllocatorProvider` to control how DMA buffers
are allocated. The binding exposes these as `VideoBufferAllocator`
and `VideoBufferAllocatorProvider`, backed by `ManagedBuffer`
(an `IDeckLinkVideoBuffer` implementation).

By default, allocators use malloc/free. Users can supply custom
Python callables for alloc/free at construction time. The allocator
provider caches allocators by buffer size so the SDK reuses them
across format changes.

**Capture path**: `enable_video_input_with_allocator()` calls
`IDeckLinkInput::EnableVideoInputWithAllocatorProvider`, directing
the DeckLink DMA engine to write into user-allocated buffers.

**Output path**: `create_frame_pool_pinned()` creates frames via
`IDeckLinkOutput::CreateVideoFrameWithBuffer`, each backed by a
`ManagedBuffer` from the allocator. These frames enter the existing
output pool and are recycled via `ScheduledFrameCompleted`.

This infrastructure is allocator-agnostic. CUDA pinned memory,
HIP pinned memory, or any other page-locked allocator is a
configuration choice, not a code change.

#### Buffer recycling

The SDK treats capture buffers as disposable: allocate via
`AllocateVideoBuffer`, DMA-fill, deliver via callback, `Release`
when done. With malloc this is nanoseconds. With GPU pinned
allocators (`cudaHostAlloc`, `hipHostMalloc`, `zeMemAllocHost`)
it is fatal — these are kernel page-table operations (~1ms each)
that cannot sustain frame-rate alloc/free cycles.

The allocator maintains a free-list. When a `ManagedBuffer`'s COM
refcount drops to zero — from SDK `Release` of a delivered capture
buffer or Python GC of a `ComPtr<ManagedBuffer>` — the buffer
returns to its parent allocator's free-list instead of calling the
free function. The next `AllocateVideoBuffer` call returns a
recycled buffer. The free function runs only when the allocator
itself is destroyed and drains the free-list.

Each `ManagedBuffer` holds a `ComPtr<VideoBufferAllocator>` to its
parent. Without this back-reference a buffer outliving its
allocator would return to a freed free-list.

Capture buffers cycle at frame rate. Output-pool buffers held by
`IDeckLinkMutableVideoFrame` (AddRef'd in `CreateVideoFrameWithBuffer`)
visit the free-list only when the pool is destroyed; frame-level
reuse during sustained playback happens via `ScheduledFrameCompleted`,
not the buffer free-list.

### GPU pinned memory integration §spec:gpu-pinned-memory

GPU pinned memory (`cudaHostAlloc`, `hipHostMalloc`,
`zeMemAllocHost`) produces page-locked system RAM mapped into both
CPU and GPU address spaces. Any PCIe device — including DeckLink —
can DMA to/from it. The GPU runtime has no awareness of third-party
DMA; coherency is the application's responsibility.

#### Why pydecklink is allocator-agnostic

Every GPU framework follows "allocator allocates, allocator frees":

| Framework | Allocate | Free |
|---|---|---|
| CUDA | `cudaHostAlloc` | `cudaFreeHost` |
| HIP (AMD) | `hipHostMalloc` | `hipHostFree` |
| Intel Level Zero | `zeMemAllocHost` | `zeMemFree` |

The `alloc(size) → ptr` / `free(ptr, size)` callable interface
accommodates all of them. pydecklink never imports a GPU toolkit.

CUDA and HIP also offer a "register existing memory" path
(`cudaHostRegister` / `hipHostRegister`) that pins malloc'd
buffers after allocation. Intel Level Zero has no equivalent.
The register path is a consumer-side pattern that requires no
pydecklink changes — see `examples/cuda_pinned_capture.py`.

#### Synchronization contract

DeckLink DMA and GPU copies must not overlap on the same buffer:

- Do not `cudaMemcpyAsync` from a buffer while DeckLink is
  writing to it. Wait for the frame callback.
- Do not let DeckLink reuse a buffer while a GPU copy is in
  flight. Hold the `CaptureFrameRef` until the CUDA stream
  completes.
- Triple-buffer pattern: DeckLink writes buffer N, GPU copies
  buffer N-1, GPU processes buffer N-2.

#### cudaHostAlloc flags

`cudaHostAllocWriteCombined` bypasses CPU cache — optimal for
frames the CPU does not read (GPU-only processing).
`cudaHostAllocDefault` uses normal caching — required if the CPU
also inspects frame data (metadata extraction, overlay compositing).
HIP provides `hipHostMallocWriteCombined` with identical semantics.

### Why C++ callback queues

SDK callbacks (`VideoInputFrameArrived`, `ScheduledFrameCompleted`)
run on internal SDK threads. Acquiring the GIL at frame rate would
block the SDK thread if Python is slow. Instead, C++ callbacks enqueue
frames into bounded thread-safe queues; Python consumes via blocking
pop. The queue drops oldest frames on overflow, matching hardware
behavior. In zero-copy mode, the callback AddRefs the SDK frame and
enqueues a lightweight reference — no pixel copy.

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
- `Device.active_profile() → ProfileID`
- `Device.set_profile(profile_id)` — activates a connector profile.
- `Device.get_attribute_int(attr_id) → int`
- `Device.get_attribute_flag(attr_id) → bool`

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

Frame retrieval (copy mode):

- `device.pop_capture_frame(timeout_ms=1000) → CaptureFrame | None`

`CaptureFrame` exposes:

- `data → numpy.ndarray` — frame pixels (uint8 view of raw bytes).
- `width, height → int`
- `pixel_format → PixelFormat`
- `stream_time → tuple[int, int]` — (time, duration) at input
  timescale.
- `hardware_reference_timestamp → int`
- `has_signal → bool` — `False` when `bmdFrameHasNoInputSource`.

Frame retrieval (zero-copy mode, `zero_copy=True` on
`enable_video_input`):

- `device.pop_capture_frame_ref(timeout_ms=1000)
  → CaptureFrameRef | None`

`CaptureFrameRef` holds the SDK's `IDeckLinkVideoInputFrame` by
reference (AddRef, no pixel copy). Same metadata as `CaptureFrame`
plus `callback_arrived_us` for latency profiling. Can be passed
directly to `schedule_capture_frame` for zero-copy passthrough.

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
- `device.schedule_output_frame(mutable_frame, display_time,
  duration, timescale)` — schedules a pre-allocated pool frame
  (see frame pool below).
- `device.schedule_capture_frame(capture_frame_ref, display_time,
  duration, timescale)` — zero-copy: passes the SDK input frame
  directly to `ScheduleVideoFrame`.
- `device.start_scheduled_playback(start_time, timescale, speed=1.0)`
- `device.stop_scheduled_playback()`
- `device.is_scheduled_playback_running → bool`

#### Output frame pool

Pre-allocated frames avoid per-frame `CreateVideoFrame` overhead:

- `device.create_frame_pool(count, width, height, row_bytes,
  pixel_format)` — allocates `count` frames up front.
- `device.acquire_output_frame(timeout_ms) → MutableFrame` — blocks
  until a frame is returned by `ScheduledFrameCompleted`.
- `device.pool_available → int` — frames currently available.

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

For the common case (display a single numpy buffer synchronously),
`display_frame_sync` accepts a numpy array directly and handles frame
creation internally. Scheduled playback uses the pool API
(`create_frame_pool` + `acquire_output_frame` +
`schedule_output_frame`).

### 5.7 Configuration

Wraps `IDeckLinkConfiguration`:

- `device.set_config_flag(flag, value)`
- `device.get_config_flag(flag) → bool`
- `device.set_config_int(setting, value)`
- `device.get_config_int(setting) → int`
- `device.write_config()` — persists changes via
  `WriteConfigurationToPreferences`.

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
| `ProfileID` | `BMDProfileID` | Connector profile selection |
| `DuplexMode` | `BMDDuplexMode` | Full, half, simplex, inactive |

### 5.9 Format Metadata

Module-level helpers (derived from display mode properties):

- `get_frame_bytes(mode, pixel_format) → int` — total frame size.
  Computed from `width × height × bytes_per_pixel` using SDK row
  bytes.
- `get_mode_width(mode) → int`
- `get_mode_height(mode) → int`
- `get_mode_fps(mode) → float`
- `clock_us() → int` — `CLOCK_MONOTONIC_RAW` in microseconds, for
  latency profiling against `CaptureFrameRef.callback_arrived_us`.
- `device.row_bytes_for_pixel_format(pixel_format, width) → int` —
  queries the output device's expected row stride.

## 6. Target Workflow

*Status: complete*

Same goal as pyntv2: an ML inference passthrough pipeline. Capture a
live SDI signal, process frames on CPU, play out the result — all
from Python, at frame rate.

The input format is auto-detected. The output is configured to match.
Frames transfer between the DeckLink card and CPU memory. GPU
processing requires explicit CPU↔GPU copies (see §4).

## 7. Integration Testing

*Status: complete*

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

### 5.10 Custom Buffer Allocators

Wraps `IDeckLinkVideoBufferAllocator`, `IDeckLinkVideoBufferAllocatorProvider`,
and `IDeckLinkVideoBuffer` for user-controlled DMA buffer allocation.

- `VideoBufferAllocator(size)` — allocator producing buffers of
  `size` bytes. Uses malloc/free by default.
- `VideoBufferAllocator.allocate() → ManagedBuffer`
- `VideoBufferAllocator.size → int`
- `VideoBufferAllocator.allocated_count → int`
- `VideoBufferAllocatorProvider()` — creates allocators on demand,
  caching by buffer size.
- `VideoBufferAllocatorProvider.get_allocator(buffer_size, width,
  height, row_bytes, pixel_format) → VideoBufferAllocator`
- `ManagedBuffer.data → numpy.ndarray` — writeable uint8 view.
- `ManagedBuffer.size → int`
- `device.enable_video_input_with_allocator(mode, pixel_format,
  flags, allocator_provider, zero_copy=True)` — capture with
  custom-allocated DMA buffers.
- `device.create_frame_pool_pinned(count, width, height, row_bytes,
  pixel_format, allocator)` — output pool backed by
  allocator-managed buffers via `CreateVideoFrameWithBuffer`.

### 5.11 Device Status and Reference Input

*Status: not started*

Wraps `IDeckLinkStatus` so Python can observe runtime hardware state
that the existing `IDeckLinkProfileAttributes` surface (static
capabilities) does not cover. The motivating use case is detecting
whether the analog tri-level / black-burst reference input is locked
and to what video mode — needed for any tool that wants to report
genlock health alongside SDI signal status (e.g.
`examples/detect_signals.py`).

Generic accessors mirror the existing attribute surface:

- `device.get_status_flag(status_id) → bool`
- `device.get_status_int(status_id) → int`
- `StatusID` enum bound from `BMDDeckLinkStatusID`.

Narrow convenience for the reference input:

- `device.reference_status → ReferenceStatus` — snapshot of current
  reference-signal state. Raises `RuntimeError` if the device's
  `HasReferenceInput` attribute is false (no physical REF BNC).
- `ReferenceStatus.locked → bool` — from
  `bmdDeckLinkStatusReferenceSignalLocked`.
- `ReferenceStatus.mode → DisplayMode | None` — `BMDDisplayMode` from
  `bmdDeckLinkStatusReferenceSignalMode`, mapped to the existing
  `DisplayMode` enum. `None` when not locked or mode is
  `bmdModeUnknown`.
- `ReferenceStatus.flags → int` — raw
  `bmdDeckLinkStatusReferenceSignalFlags` (e.g. dual-link).

Push notifications mirror the SDK's `IDeckLinkNotificationCallback`:

- `device.subscribe_status_changes() → StatusChangeQueue` — registers
  a C++ callback against `IDeckLinkNotification::Subscribe(bmdStatusChanged)`
  and enqueues `(status_id, value)` events into a bounded queue.
- `StatusChangeQueue.pop(timeout_ms=1000) → StatusChange | None`
- `StatusChangeQueue.close()` — unsubscribes and drains.
- `StatusChange.id → StatusID`
- `StatusChange.kind → "flag" | "int"`
- `StatusChange.flag_value → bool` (if `kind == "flag"`)
- `StatusChange.int_value → int` (if `kind == "int"`)

The synchronous getter and the notification queue are independent:
consumers may use either or both.

#### Why mirror the SDK's push shape

The SDK is push-driven for status changes
(`IDeckLinkNotificationCallback`). The capture path is
poll-from-Python because acquiring the GIL on the SDK's frame-rate
thread would stall the SDK; that argument does not apply to status
events, which fire on the order of seconds. Matching the SDK's
native shape avoids the latency floor of polling and lets a UI react
to a genlock drop without a polling loop. The synchronous getter is
retained for one-shot diagnostics where setting up a subscription is
overkill.

#### Why generic + narrow

The generic `get_status_flag` / `get_status_int` accessors mirror the
existing `get_attribute_int` / `get_attribute_flag` pattern, give
Python access to the rest of `IDeckLinkStatus` (PCIe link width, busy
state, current input video mode, fan/temperature where supported)
without further binding work, and keep `ReferenceStatus` as a
narrowly-typed convenience on the most common path.

#### Why per-`IDeckLink`, not per-physical-card

`IDeckLinkStatus` is queried per `IDeckLink` interface. On
multi-sub-device cards (e.g. DeckLink 8K Pro with four sub-devices)
all sub-devices belonging to the same physical card report identical
reference-signal status, because they share one REF BNC. The binding
does not de-duplicate this — that is consumer policy. Consumers that
want one row per physical card can group sub-devices by
`get_attribute_int(AttributeID.TopologicalID)`, which the SDK
guarantees is constant across sub-devices of the same card while
`PersistentID` varies.

#### Capability gating

`device.reference_status` checks `HasReferenceInput` before issuing
the underlying `GetFlag` call and raises `RuntimeError` with a
descriptive message when the device has no reference port. The
generic `get_status_flag` / `get_status_int` accessors do not gate;
they surface the SDK's `HRESULT` failure as `RuntimeError`, matching
how `get_attribute_int` already behaves.

## 9. Explicit Non-Goals (Phase 1)

- **GPU RDMA.** The allocator infrastructure and buffer recycling
  design support GPU pinned memory (§spec:gpu-pinned-memory).
  Wiring a specific GPU allocator is a consumer configuration step,
  not a pydecklink code change.
- **Audio.** Deferred. The SDK supports audio scheduling; the binding
  does not expose it yet.
- **Ancillary data.** Timecode, closed captions — deferred.
- **HDR metadata.** The SDK supports it via frame metadata extensions.
  Deferred to Phase 2 (bmd-signal-gen integration needs it).
- **Deck control.** `IDeckLinkDeckControl` (tape transport) is not
  bound.
- **Reference signal generation.** Capture/playback DeckLinks have
  no reference-output role — the REF BNC is input-only (genlock /
  tri-level sync in). Reference-generator products (Mini Sync
  Generator, Sync Generator 4K) are out of scope; only reference
  *input* status is exposed (§5.11).
- **Video conversion.** No color space conversion, scaling. The SDK
  has some hardware conversion modes; exposing them is deferred.
