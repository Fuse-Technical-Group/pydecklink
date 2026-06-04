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

| | Linux | macOS | Windows |
|---|---|---|---|
| SDK artefacts | C++ headers + dispatch source | C++ headers + dispatch source | IDL files → MIDL-generated headers + COM stubs |
| Runtime library | `libDeckLinkAPI.so` via `dlopen` | CoreFoundation `CFPlugIn` | COM interfaces via `CoCreateInstance` |
| Build toolchain | C++ compiler, CMake | Xcode / Apple Clang, CMake | MSVC, Windows SDK (MIDL), CMake |

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
and `VideoBufferAllocatorProvider`. Each `AllocateVideoBuffer` call
returns a `ManagedBuffer` — a per-issuance `IDeckLinkVideoBuffer`
handle wrapping a pooled memory chunk owned by the allocator's
free-list.

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
configuration choice, not a code change to pydecklink.

#### COM contract

The handle (`ManagedBuffer`), `VideoBufferAllocator`, and
`VideoBufferAllocatorProvider` all implement `IUnknown::QueryInterface`
to return the correct interface pointer for `IID_IUnknown` and for
the implementing type's own IID, with `AddRef` on success. The SDK
relies on this to wrap our buffers into its internal video-frame
objects. Returning `E_NOINTERFACE` for the type's own IID is a
contract violation that stalls the SDK input pipeline at the
no-signal → signal-locked transition.

#### Buffer recycling

The SDK treats capture buffers as disposable: allocate via
`AllocateVideoBuffer`, DMA-fill, deliver via callback, `Release`
when done. With malloc this is nanoseconds. With GPU pinned
allocators (`cudaHostAlloc`, `hipHostMalloc`, `zeMemAllocHost`)
it is fatal — these are kernel page-table operations (~1 ms each)
that cannot sustain frame-rate alloc/free cycles.

The allocator separates per-issuance lifetime from memory lifetime
to keep COM semantics standard while still pooling the expensive
allocation:

- A *pooled buffer* — the raw memory chunk + size — is owned by
  the allocator's free-list. Created once via the user-supplied
  alloc function; freed via the user-supplied free function only
  when the allocator itself is destroyed.
- A *handle* (`ManagedBuffer` in Python) is a per-issuance COM
  object implementing `IDeckLinkVideoBuffer`. Each
  `AllocateVideoBuffer` returns a fresh handle wrapping a pooled
  buffer popped from the free-list (or freshly allocated when the
  list is empty). When the handle's COM refcount reaches zero,
  the handle destructs (standard COM) and its destructor returns
  the underlying pooled buffer to the free-list. The next
  `AllocateVideoBuffer` reuses that pooled buffer in a fresh
  handle.

This split keeps `Release()→0 → delete this` true for the COM
object, while the pooled memory amortizes across many issuances.
The handle's own heap allocation is a few dozen bytes — negligible
versus the page-locking syscalls the pool exists to avoid.

This recycling is internal to the SDK's COM `Release` path.
Python-owned buffers (created via `allocator.allocate()` for the
output frame pool) are unaffected — those buffers live for the
duration of the pool and recycle at the frame level via
`ScheduledFrameCompleted`.

#### Pre-fill for slow allocators

Recycling closes the loop in steady state but doesn't cover the
no-signal → signal-locked transition: the SDK requests fresh
buffers when its internal pipeline reconfigures, and a Python
allocator callback (which acquires the GIL and dispatches into
Python) takes ~1–10 ms — far longer than the SDK input thread can
tolerate. The thread blocks, no callbacks fire, the pipeline
stalls.

`VideoBufferAllocator.prefill(count)` runs the slow path on the
calling thread before `start_streams`, seating `count` buffers on
the free-list. Mid-stream allocations then take the FAST path
(free-list pop) with no Python involvement. Empirically 2 buffers
cover the transition with `input_queue_depth=1`; 4 is a small
safety margin. Default-malloc allocators don't need pre-fill
because their slow path is microseconds.

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
pydecklink changes — see `examples/cuda_register_pinned.py`.

`examples/cuda_pinned_pipelined.py` is the production-shaped
recipe for the allocator path: capture and consumer on separate
threads, GPU buffer pool, GC tuned for the hot loop, end-to-end
delivery latency reported.

#### Synchronization contract

DeckLink DMA and GPU copies must not overlap on the same buffer:

- Do not `cudaMemcpyAsync` from a buffer while DeckLink is
  writing to it. Wait for the frame callback.
- Do not let DeckLink reuse a buffer while a GPU copy is in
  flight. Hold the `CaptureFrameRef` until the CUDA stream
  completes.
- Triple-buffer pattern: DeckLink writes buffer N, GPU copies
  buffer N-1, GPU processes buffer N-2.

The SDK exposes `IDeckLinkVideoBuffer::StartAccess` /
`EndAccess` as the access-synchronization primitive — independent
of COM refcount. The binding opens a read access window on each
delivered frame's `ManagedBuffer` in `InputCallback::VideoInputFrameArrived`
and closes it in the `CaptureFrameRef` destructor. Allocators
with non-trivial access semantics (mapped GPU memory, macOS
XPC-marshaled buffers, dmabuf) implement these as real
preparation/coherency operations; `ManagedBuffer` makes them
no-ops because cudaHostAlloc-backed memory is always
CPU-accessible.

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

The bounded depth is exposed as `input_queue_depth` on
`enable_video_input` and `enable_video_input_with_allocator`,
defaulting to 1 — the right cap for real-time consumers (drop
late frames, never lag). Recorder-style consumers can raise it
to absorb consumer-side jitter at the cost of latency and (in
zero-copy mode) buffer-pool pressure: each queued frame holds an
AddRef on a `ManagedBuffer`, keeping it off the allocator's
free-list.

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

- `device.enable_video_input(mode, pixel_format, flags=0,
  zero_copy=False, input_queue_depth=1)`
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

### 7.6 Custom-allocator + zero-copy + signal-locked recycling

Streams signal-locked frames through a custom allocator (Python
`libc.malloc` / `libc.free` callbacks via ctypes), zero-copy
delivery, `prefill(4)`. Asserts:

- frames are delivered (input thread didn't stall);
- `recycled_count > 0` (free-list cycle is closed at runtime);
- `allocated_count` stable after prefill (no SLOW path during
  streaming).

Each assertion guards a distinct failure mode of the recycling
path: stall on slow allocator, broken Release-to-free-list cycle,
SLOW-path growth on the SDK input thread.

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

- `VideoBufferAllocator(size, alloc=None, free=None)` — allocator
  producing buffers of `size` bytes. Optional Python callables
  override the default malloc/free.
- `VideoBufferAllocator.allocate() → ManagedBuffer`
- `VideoBufferAllocator.prefill(count) → None` — pre-allocate
  `count` buffers and seat them on the free-list. Required before
  `start_streams` whenever `alloc` is a Python callable; see §4
  buffer recycling for why.
- `VideoBufferAllocator.size → int`
- `VideoBufferAllocator.allocated_count → int`
- `VideoBufferAllocator.recycled_count → int` — number of times
  a `ManagedBuffer` has been pushed back onto the free-list.
- `VideoBufferAllocatorProvider(alloc=None, free=None)` — creates
  allocators on demand, caching by buffer size.
- `VideoBufferAllocatorProvider.get_allocator(buffer_size, width,
  height, row_bytes, pixel_format) → VideoBufferAllocator`
- `ManagedBuffer.data → numpy.ndarray` — writeable uint8 view.
- `ManagedBuffer.size → int`
- `device.enable_video_input_with_allocator(mode, pixel_format,
  flags, allocator_provider, zero_copy=True, input_queue_depth=1)`
  — capture with custom-allocated DMA buffers.
- `device.create_frame_pool_pinned(count, width, height, row_bytes,
  pixel_format, allocator)` — output pool backed by
  allocator-managed buffers via `CreateVideoFrameWithBuffer`.

When `alloc` and `free` are top-level module functions, a reference
cycle forms via the function's `__globals__` that Python's GC
cannot break (the cycle passes through C++). Callers wrap setup
in a function so the allocator and its callbacks are local
variables; the cycle is reclaimed when that function returns.
Both CUDA examples follow this pattern.

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

- **GPU RDMA.** The allocator infrastructure, free-list recycling,
  and `prefill` API support GPU pinned memory
  (§spec:gpu-pinned-memory). Wiring a specific GPU allocator (CUDA,
  HIP, Level Zero) is a consumer step; pydecklink imports no GPU
  toolkit. True GPU RDMA — DMA from PCIe direct into GPU VRAM,
  bypassing host memory — is not implemented; the SDK's deprecated
  DVP / GPUDirect headers have no maintained path.
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

## 10. Supply Chain Security

*Status: not started*

The build pulls in third-party code from two ecosystems: PyPI
(numpy, scikit-build-core, nanobind, dev/test tooling) and the
GitHub Actions marketplace (seven external actions across six
workflows). Both are mutable dependency surfaces with documented
real-world compromises (tj-actions/changed-files, March 2025,
~23k repos; multiple PyPI typosquat campaigns annually). Without
ongoing surveillance, advisories published *after* a dep has been
adopted are invisible until they break something.

The system shall:

- Fail PR CI when a pull request introduces a dependency
  (PyPI package or GitHub Action) with a known advisory at the
  configured severity threshold or higher.
- Report — without failing CI — advisories newly published against
  already-adopted dependencies, on a recurring schedule. Reports
  surface as GitHub Security tab entries, not silent logs.
- Allow individual advisories to be suppressed only via a tracked
  allowlist file with an expiry date and a one-line justification.
  An expired suppression re-fails CI; a suppression without a date
  is rejected by the scanner config.
- Reject any pull request whose `.github/workflows/**` introduces
  an external Action reference (`uses: owner/repo@ref`) not pinned
  by 40-character commit SHA, with a `# vX.Y.Z` point-version
  comment trailing the SHA for human review. Floating major tags
  (`@v4`), branch refs, and missing or non-point version comments
  are rejected. Local workflow references (`uses: ./...`) are not
  external and are unaffected.

### Why scanning, in addition to bumping

GitHub's Dependabot already opens version-bump and security-update
PRs, but it operates at the level of "version X.Y.Z is available"
or "version X.Y.Z fixes CVE-N." It does not gate merges. A PR can
land a known-vulnerable transitive dependency, or a freshly forked
GitHub Action that has no advisory but minimal hygiene, before
Dependabot has anything to say about it. Scanning closes that gap
by gating *introduction*; bumping covers *response*. The two are
complementary, not redundant.

### Why one scanner across both ecosystems

`osv-scanner` (Google, Apache-2.0) consults the OSV.dev advisory
database, which federates GitHub Security Advisories, PyPA, and
the GitHub Actions ecosystem in a single feed. Using one tool
across both ecosystems avoids divergent severity definitions, two
sets of suppression files, and two code paths in CI. The
alternatives (`pip-audit` for PyPI only; `actions/dependency-review`
for Actions delta only) are narrower and would require a second
tool for the surface they don't cover.

`actions/dependency-review-action` runs in addition to
`osv-scanner` on pull-request events specifically — it surfaces
the *delta* introduced by the PR (new package vs. existing
package) directly in the PR review UI, which is more actionable
for reviewers than a full scan diff. It does not replace
`osv-scanner`, which still gates the full closure.

### Why pin severity threshold at HIGH

The system shall block merges on advisories of severity HIGH or
CRITICAL, and report (without blocking) advisories of MEDIUM or
LOW. Two reasons:

- **Signal-to-noise.** PyPI and the Actions ecosystem accumulate
  LOW/MEDIUM advisories continuously; gating on those produces
  daily CI failures unrelated to anything the PR author touched,
  trains reviewers to ignore the gate, and erodes its value
  against the failures that matter.
- **Severity calibration.** OSV.dev severity scores derive from
  CVSS where available. CVSS HIGH/CRITICAL maps to "remote code
  execution," "privilege escalation," or "credential exposure" —
  outcomes worth blocking a merge for. MEDIUM/LOW typically maps
  to "information disclosure under specific conditions" or
  "denial of service against the affected component" — worth
  reporting but not worth a hard gate.

Threshold is configured in one place (the scanner config) and
referenced from both the PR-time gate and the scheduled audit so
the two stay in sync.

### Why SHA-pin shape, in addition to vulnerability scanning

The Actions marketplace has no registry-level integrity layer.
`uses: owner/repo@ref` resolves to a Git ref, and tags are
mutable by default. A maintainer (or compromised account) can
`git tag -f v4.2.2 && git push --force --tags`, and every
consumer pinned to `@v4.2.2` silently picks up new bytes on the
next workflow run. PyPI, npm, and crates.io refuse re-publishes
under an existing version; the Actions marketplace does not. SHA
pinning encodes bit-exact provenance directly into the workflow
YAML — the workflow file *is* the lockfile.

Vulnerability scanning catches *known* CVEs against parsed
version strings. It does not catch a maintainer compromise that
ships malicious code under an existing tag before any advisory
is written, and it depends on the OSV.dev feed having coverage
for the action in question. Pin-shape enforcement catches the
structural defect regardless of whether an advisory exists, runs
offline, and fails on the same PR that introduced the regression.

GitHub's "immutable releases" feature would close this at the
registry level once universally adopted, but adoption is partial
(of the actions used here, only `astral-sh/setup-uv` has opted
in), the feature only freezes point-release tags — floating
major tags like `@v4` are not Release objects and remain mutable
by design — and attestation proves the maintainer published the
bytes, not that the bytes are safe. SHA-pinning is the durable
defense; attestation, where available, layers on as a sanity
check at bump time.

The trailing `# vX.Y.Z` comment is mandatory because a 40-char
hex string carries no human-readable signal at review time. The
comment lets a reviewer assess whether a bump is plausibly
intentional ("v6.0.2 → v7.0.1, breaking change check the
release notes") without resolving the SHA.

### Why allowlist suppressions must expire

Permanent suppressions silently rot. A suppression added because
"the vulnerable code path isn't reachable in our usage" stops
being true the moment someone refactors. An expiring suppression
forces a re-check on the calendar boundary the reviewer chose, at
which point either the upstream has shipped a fix, or the
maintainer reaffirms the analysis with fresh evidence. The
mechanism is `osv-scanner`'s native `osv-scanner.toml` ignore
list, with `expires` field required by repo policy.

### Why scheduled scans, in addition to PR-time

Most advisories affecting a repo are published *after* the
vulnerable dep is already merged. PR-time gating only catches
*new* introductions. A weekly scheduled scan against the current
main branch's full closure surfaces advisories that dropped
during the week so they're triaged on a regular cadence rather
than discovered when something breaks.

### Why Dependabot is enabled alongside

Dependabot is the bumping mechanism: it opens PRs for outdated
deps and for deps that gain a security advisory after merge.
Scanning is the gating mechanism: it blocks new introductions
and surfaces advisories on the existing closure. They cover
different points in the dep lifecycle. The system shall include
a `.github/dependabot.yml` covering the `pip` and
`github-actions` ecosystems on a weekly cadence, grouping
patch/minor updates to keep PR volume manageable.

### Why self-scorecard is in scope, separately

`ossf/scorecard-action` runs the OpenSSF Scorecard checks
against this repository on a schedule and reports findings to
the GitHub Security tab. It answers "is *pydecklink* a
well-hardened consumer of OSS?" — a different question from
"are pydecklink's deps vulnerable?" Worth running because the
checks (branch protection, signed releases, token permissions,
pinned dependencies) catch hygiene regressions in our own
workflows, and the score is visible to downstream consumers
deciding whether to depend on pydecklink. Lower priority than
the scanning itself; see roadmap sequencing.

### Release integrity (outbound)

The subsections above harden the *inbound* supply chain — code
pydecklink consumes. Releases are the *outbound* surface: pydecklink
ships per-platform wheels (Linux, macOS, Windows) as GitHub Release
assets that downstream users install directly. A published release
whose assets can be altered after publication, or that ships before
every platform's wheel is present, is an integrity risk for those
installs.

The system shall:

- Publish releases as **immutable** GitHub Releases — once published,
  a release's tag and assets cannot be added, replaced, or removed.
- Publish a release only after every per-platform wheel has been built
  and attached, so a published release is never missing a platform's
  wheel and no asset can be swapped after the fact.

Why: consumers install wheels straight from the release assets, so the
published set must be both complete and bit-stable. Immutability gives
the same post-publish tamper-resistance a package index (PyPI) provides
through filename burn; distributing via an index is a possible future
alternative but is out of scope — the package is not currently indexed.

Because GitHub freezes a release's assets at publication, the release
tool must build and attach all wheels *before* publishing: cut the
release as a draft, attach wheels, and promote to published only once
every platform succeeds; a failed build leaves a draft for remediation
rather than shipping an incomplete release. This draft → attach →
promote ordering is a hard requirement on whatever tool cuts releases,
and gates the release-automation migration tracked in the roadmap.

### Constraints

- **PR-time scan budget.** The PR-time scan shall complete in
  under 30 seconds on the hot path. `osv-scanner` against the
  Python lockfile and `.github/workflows/` finishes in single
  digits of seconds in practice (the bottleneck is action
  startup, not scan work). It runs as a parallel job in
  `ci-linux.yml`, not serialized with the build/test jobs.
- **No paid services.** All scanners and feeds shall be
  free-tier. OSV.dev, OpenSSF Scorecard, GHSA, and Dependabot
  satisfy this. Snyk, Socket.dev (paid tiers), and Mend.io are
  rejected on this constraint.
- **Actionable output.** A CI failure shall name a specific
  advisory ID (e.g., `GHSA-xxxx-yyyy-zzzz` or `CVE-N`), the
  affected package, and the fixed version. "Something is
  vulnerable" without a pointer is rejected.

### Scope boundaries

- System packages installed via `apt-get`/`brew` (cmake,
  ninja-build, build-essential) are out of scope. Their
  vulnerability surface belongs to the runner image's
  maintainer, not this project.
- Vendored DeckLink SDK headers are out of scope. The vendor
  ships them under a header license that permits redistribution;
  no advisory feed covers them and updates ride the SDK release
  cycle.
- The C++ extension's link-time deps (`libDeckLinkAPI.so`) are
  out of scope. They're host-installed at runtime; advisories
  against them are the host operator's concern.
