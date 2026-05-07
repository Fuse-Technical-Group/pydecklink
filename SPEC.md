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
of COM refcount. The binding opens an access window for the full
lifetime of the Python wrapper, on both directions:

- Input: `StartAccess(Read)` opens in
  `InputCallback::VideoInputFrameArrived`, closes in the
  `CaptureFrameRef` destructor.
- Output: `StartAccess(ReadAndWrite)` opens in
  `acquire_output_frame` and `create_video_frame`, closes in
  `schedule_output_frame` (when the SDK takes over) or in the
  `MutableFrame` destructor (when the wrapper is dropped without
  scheduling).

Both wrappers are move-only so the access window transfers
cleanly without aliasing. Allocators with non-trivial access
semantics (mapped GPU memory, macOS XPC-marshaled buffers, dmabuf)
implement these as real preparation/coherency operations;
`ManagedBuffer` makes them no-ops because cudaHostAlloc-backed
memory is always CPU-accessible.

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

### 5.12 Connector Labeling

*Status: complete*

Multi-sub-device DeckLinks (8K Pro, Quad 2, Duo 2) expose each
SDI connector as a distinct `IDeckLink` device. The SDK
enumerates them in a logical order — `BMDDeckLinkSubDeviceIndex`
runs 0..N-1 — that does not match the SDI port labels printed
on the card. On a DeckLink 8K Pro in
`bmdProfileFourSubDevicesHalfDuplex`, sub-device 1 maps to SDI 3
and sub-device 2 maps to SDI 2 — the two are transposed
relative to logical numbering.

The parenthesized number in `IDeckLink::GetDisplayName` (e.g.
"DeckLink 8K Pro (3)") tracks the sub-device index, *not* the
SDI port label. Naïve `display_name` parsing lands on the wrong
connector for any card whose mapping is non-identity.

The SDK provides no programmatic physical-port query. The
binding ships a static lookup table sourced from BMD's SDK 15.3
manual section 2.4.11, exposed as:

- `pydecklink.connector_label(device) → str | None` — returns
  the printed SDI port label (e.g. `"SDI 1"`, `"SDI 1+2"`) for
  known `(model, profile, sub_device_index)` tuples; returns
  `None` for unmapped cards or profiles. The function reads the
  device's current state on each call, so a runtime profile
  switch is reflected on the next call without device re-open.

A module-level function rather than a `Device` property because
the lookup is package-side data (a hand-maintained table from
BMD's manual), not an SDK-derived attribute. Keeping it
explicit avoids confusion at the call site about what the SDK
exposes versus what the binding interpolates, and avoids
monkey-patching the nanobind-generated `Device` class — which
breaks stub generation.

The system shall:

- Return the correct printed SDI port label for every device
  whose `(model_name_prefix, profile, sub_device_index)` tuple
  matches an entry in the static table.
- Return `None` (not raise) for any tuple not in the table, so
  callers can fall back to raw attributes
  (`get_attribute_int(AttributeID.SubDeviceIndex)`,
  `display_name`).
- Re-evaluate on every call so a runtime profile switch is
  reflected without device re-open.

### Why a static table

The SDK's silence on this is structural: the connector mapping
is hardware-internal, not surfaced by any attribute or interface.
Reverse-engineering it by parsing `display_name` is unsafe (the
parenthesized number is logical, not physical) and would silently
land on the wrong port for any card with non-identity mapping.

Maintenance cost is small: BMD ships at most a handful of
multi-sub-device cards per year, and additions are mechanical
(consult the manual, append a row). Returning `None` for
unmapped cards keeps the API honest — the binding never
synthesizes a guess from a partial signal.

### Scope boundaries

- `connector_label` covers SDI ports only. HDMI, optical SDI,
  and analog connectors on hybrid cards are not labeled — those
  cards are typically single-sub-device and the question does
  not arise.
- The reverse mapping (`label → device`) is left to the caller:
  `next(d for d in (Device(i) for i in range(device_count())) if connector_label(d) == "SDI 3")`.

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

## Canonical GPU Passthrough §spec:canonical-gpu-passthrough

*Status: not started*

### Problem

The headline deliverable consumers expect from pydecklink is:
SDI cable → GPU kernel → SDI cable, at frame rate, with the most
performant IO the library can provide. The library has all the
building blocks — pinned-allocator capture
(§spec:gpu-pinned-memory), scheduled playback with custom
allocators (§4), zero-copy frame relay (§5), latency floor
characterization (§spec:latency-characterization) — but no single
example ties them together as a consumer-facing recipe.

Today a consumer who wants this shape must compose pieces from
three separate examples:

- `cuda_pinned_pipelined.py` shows the capture half but has no
  playout side.
- `passthrough.py` shows the playout half but does no GPU work.
- `cuda_loopback_latency.py` shows both halves end-to-end but
  hardcodes a fingerprint-encode/decode kernel as a benchmark
  payload, not as a consumer slot.

Each composition decision a consumer makes — threading model,
preroll depth, output queue depth, format detection sequencing,
allocator wiring, GC tuning, signal-loss recovery — is independent
and easy to get wrong. Wrong choices manifest as elevated latency,
output drops, or silent stalls. The components are sufficient;
the recipe is not. Consumers should be able to drop in their CUDA
kernel and inherit the project's best IO shape, not rebuild it.

This extends the Target Workflow (§6), which described a CPU
passthrough pipeline because it predates GPU-direct DMA support.

### Behavior

A new example, `examples/cuda_passthrough.py`, ships an end-to-end
SDI → CUDA → SDI loop. The example owns every operational
decision; the consumer owns only the kernel.

- **Input**: capture from a configurable input device into pinned
  CUDA memory via `cuda_host_alloc` allocator callbacks. Mode is
  auto-detected; pixel format defaults to v210 (10-bit YUV) and is
  configurable.
- **Processing**: a Python callable invoked once per captured
  frame on a CUDA stream, with a stable signature
  `kernel(stream, d_input, d_output, width, height, frame_bytes)
  -> None`. Default implementation is identity —
  `cudaMemcpyAsync` device-to-device on the stream — producing a
  true passthrough that consumers can run unchanged to verify
  their wiring.
- **Output**: the kernel's output buffer is staged into a pinned
  output frame and scheduled for playout on a configurable output
  device. Output mode matches input mode by construction.
- **Threading**: capture, kernel-dispatch, and consumer-release on
  separate threads with bounded queues. Same shape as
  `cuda_pinned_pipelined.py`; the consumer doesn't see it.
- **Format selection**: input auto-detects with the bounded probe
  pattern (§spec:latency-characterization). Output configured to
  match. No CLI mode flag in the default invocation.
- **Failure modes**: bounded waits on signal lock and format
  detection; clear `RuntimeError` with device indices and detected
  mode on misconfiguration. No silent multi-minute spins.
- **Reporting**: per-frame end-to-end latency (input callback →
  output egress) and output health counters
  (`OutputStatus.late + dropped + underrun`) printed at exit.
- **CLI surface**:
  `python examples/cuda_passthrough.py --input <N> --output <M>
  [--pixel-format 8bit|10bit] [--frames|--duration]`. Consumers
  replace the kernel by editing the function or by importing the
  example as a module and passing their own callable to
  `run_passthrough`.

### Why an example, not a library API

Locking the recipe into the library would over-constrain
consumers who legitimately need different shapes — multi-card
configs, asymmetric in/out modes, NUMA-pinned threading,
non-CUDA frameworks. An example documents the canonical recipe
while leaving the library surface unconstrained. The
canonical-ness is editorial, not enforced by the API.

### Why a Python callable seam, not a kernel-source string

Consumer kernels arrive in many shapes — NVRTC-compiled source
strings, cupy `RawKernel` objects, numba CUDA functions,
hand-launched kernels via `cuLaunchKernel`. Wrapping the seam as
a Python callable that operates on a CUDA stream + device pointers
covers all of them with a small per-frame Python call (~µs
overhead, negligible against frame period). A kernel-source-only
seam would foreclose cupy and numba consumers; an
NVRTC-compile-and-launch seam would foreclose pre-compiled or
hand-managed launches.

### Why bidirectional in one example, not separate halves

Latency, queue depth, and preroll decisions span both halves —
splitting them invites recomposition errors of the kind §6
already warned against (CPU↔GPU copies, triple-buffer
synchronization). The headline value of the recipe is the loop,
not either half in isolation. Consumers who need only one half
already have `cuda_pinned_pipelined.py` (capture) or future
playout-only examples; they can compose their own.

### Why CUDA-only initial scope (no CPU fallback)

A CPU fallback would dilute what the example demonstrates: the
GPU-passthrough latency floor and integration shape. CPU-touching
of frame data adds 5–15ms at 4K10-bit, which would swamp the
SDI/SDK contribution and produce a different benchmark with
different audience. Consumers without CUDA already have
`passthrough.py` (zero-copy SDI → SDI, no GPU touch); the
canonical CPU recipe and canonical GPU recipe are distinct
deliverables.

HIP and Level Zero variants become reasonable once consumer
demand exists; the underlying `VideoBufferAllocator` /
`VideoBufferAllocatorProvider` surface is framework-agnostic
(§spec:gpu-pinned-memory), so they're additive examples, not API
changes.

### Tradeoffs accepted

- **Opinionated defaults.** Threading model, preroll depth, queue
  sizes, GC tuning are baked. Consumers with different operating
  points compose from lower-level CUDA examples.
- **Per-frame Python call overhead.** The kernel callable is
  invoked from Python on the hot path. Microsecond-scale; verified
  by the existing `cuda_pinned_pipelined.py` capture-loop pattern.
  Consumers with stricter latency budgets can fork the example
  and inline.
- **Single CUDA stream.** The example uses one stream end-to-end.
  Consumers wanting overlapped compute + copy across multiple
  streams compose their own from `cuda_pinned_pipelined.py`'s
  pattern.

### API surface impact

The example is purely additive — no library API changes. It
consumes the existing `VideoBufferAllocator` /
`VideoBufferAllocatorProvider` / `schedule_capture_frame` /
`create_frame_pool_pinned` surface. README's quick-start should
add a pointer alongside the existing `passthrough.py` reference;
exact wording deferred to the example PR.

## Latency Characterization §spec:latency-characterization

*Status: in progress*

### Problem

Capture-side delivery latency is instrumented
(`CaptureFrameRef.callback_arrived_us` to consumer release in
`examples/cuda_pinned_pipelined.py`), but no measurement crosses the
cable. Consumers building real-time passthrough cannot answer:

- Does the pipeline contain hidden buffering — driver queue, SDK
  input queue, output preroll — that adds frames of latency?
- How much GPU kernel time can a consumer spend before the pipeline
  forces an extra frame of headroom or starts dropping?

Without numbers, consumers over-provision headroom or accept blind
drift.

### Behavior

A CUDA loopback fingerprint benchmark
(`examples/cuda_loopback_latency.py`) operates two DeckLink devices
wired in loopback and reports:

- **Round-trip latency** in microseconds and in frame periods, by
  stamping a sequence number into the active video region of each
  output frame and recovering it from the corresponding capture.
- **Kernel time** measured separately at sub-microsecond resolution,
  decomposing total cable-to-cable cost into a fixed ex-kernel
  component (cable + DeckLink + queue + DMA) and a variable kernel
  component. A consumer's projected RTT for any kernel = ex-kernel +
  measured kernel time.
- **Output health**: `OutputStatus.completed / late / dropped /
  underrun` correlated with the active configuration.

Configurable per run:

- **Output clock source**: free-running (card crystal) or input-locked
  (output pixel clock derived from SDI input).
- **Headroom**: integer frame periods between input frame N's arrival
  and the scheduled display time of the corresponding output frame.
- **Phase offset**: sub-frame timing offset between input and output
  VBI, applied when the output clock is input-locked.
- **Preroll depth**: frames queued before `start_scheduled_playback`.

Sweep mode reports the minimum stable configuration — the smallest
(headroom, phase_offset, preroll) combination that holds zero
`late + dropped + underrun` over a sustained run.

### Why fingerprint pixels

The SDK exposes input-side timestamps but no output-side egress
timestamp — `schedule_output_frame` records queue insertion, not SDI
clock-out. Round-trip latency must be measured by stamping a known
value into output pixel data and recovering it on capture. Recovery
happens in the same pinned buffer used for H2D, with no extra device
transfers.

### Why GPU-only fingerprint touches

The CPU does not read or write framebuffers on either the output
or the input path. A real consumer pipeline runs cable → DeckLink
DMA → pinned host → CUDA H2D DMA → kernel → CUDA D2H DMA → pinned
host → DeckLink DMA → cable, with no CPU-side pixel work; the
benchmark mirrors that path so the floor it reports is meaningful
to such consumers.

- Output: a small device staging buffer holds two v210 groups
  (32 bytes) carrying the 8-byte sequence number across 8 luma
  slots. A CUDA kernel writes it; `cudaMemcpyAsync` D2H copies
  those 32 bytes into the pinned output frame at the start of
  active video. `schedule_output_frame` triggers SDK DMA
  host→wire.
- Input: SDK DMA wire→pinned host (existing path).
  `cudaMemcpyAsync` H2D copies the frame to a device pool slot.
  A decode kernel reads the fingerprint groups from the device
  pointer, extracts the 8 luma slots, and writes the recovered
  sequence number to a small result buffer. `cudaMemcpyAsync`
  D2H lifts the result back. Events bracket the decode kernel
  for sub-µs kernel-time measurement.

The decode kernel is also the timed kernel for ex-kernel
decomposition — it does real work (parse v210 bit-packing, read
8 luma values, write the recovered uint64), so `kernel_us`
reflects a genuine GPU operation rather than the event-pair
overhead floor.

### Why 10-bit YUV (v210), not 8-bit

The fingerprint is written into the luma slots of a 10-bit YUV
4:2:2 buffer in v210 packing. v210 is the standard production
capture format on this card (matches the default in
`cuda_pinned_pipelined.py`); running the latency benchmark on a
different pixel format would measure the wrong DMA path. SDI
transmission of v210 is bit-exact on the wire — no format
conversion at either the output or the input — so the 10-bit
luma values written by the encode kernel arrive intact at the
decode kernel.

Encoding: each byte of the 64-bit sequence is placed in the low
8 bits of a 10-bit luma slot OR'd with `0x100`, putting every
encoded luma value in `[256, 511]`. Spans 8 of the 12 luma slots
across 2 v210 groups (32 bytes of buffer touched, no chroma slot
disturbed). Decoding inverts: read those 8 luma slots, take the
low 8 bits of each, reassemble the uint64.

The `| 0x100` lift is required: SMPTE 425M reserves luma values
`0x000-0x003` and `0x3FC-0x3FF` as in-band sync codes, and the
DeckLink hardware silently rewrites any reserved code that
appears in active video to `0x004`. Without the lift, a sequence
byte of zero (common — every seq < 256 has seven zero bytes)
would arrive on capture as 4, corrupting the recovery for
nearly every frame.

### Why decompose kernel time from ex-kernel cost

A consumer's effective latency depends on their kernel. The fixed
ex-kernel cost is what no consumer can change; the kernel time is
what they control. With a no-op fingerprint kernel, the benchmark
measures the floor; consumers add their own measured kernel time to
project total RTT for their workload. The decomposition is what
makes the benchmark useful as a planning input rather than a single
opaque number.

### Why lock to input rather than to genlock

Genlock — locking to an external reference (REF BNC tri-level / black
burst) — synchronizes input and output to a third-party clock. The
phase between input arrival and the next output VBI is then fixed by
the genlock signal, not by the input itself. For a passthrough loop
this adds latency without adding determinism.

Locking the output clock to the input clock collapses the
input-to-output phase to a value the system controls. Combined with
sub-frame phase offset, output VBI can be placed at any phase relative
to input VBI, allowing the scheduled display time of frame N+1 to
track input frame N+1 with no clock-domain jitter.

Tradeoff: the output SDI signal is not phase-aligned to facility
genlock. Downstream gear that expects a referenced source sees this
output as free-running. Acceptable for closed-loop measurement
between paired DeckLink cards; not appropriate for facility
integration.

### Why phase adjust matters

Without sub-frame phase control, headroom is integer frame periods. A
kernel running in 0.3 frame periods still requires a full frame of
headroom in the integer model — 0.7 frames (~12ms at 60p) wasted to
alignment. With phase offset, output VBI shifts forward by the
kernel's worst-case duration plus a safety margin, recovering the
wasted phase as latency reduction.

### Why a sweep, not a fixed configuration

Preroll establishes the initial queue depth at
`start_scheduled_playback`; steady-state headroom is the gap between
current playback time and the scheduled display time of new frames.
Both contribute to latency, both have empirical floors bounded by GPU
jitter and SDK queue draining. The floor is hardware-, driver-, and
mode-specific. The sweep finds it by reducing knobs until
`late + dropped + underrun` first becomes nonzero over a sustained
run, then backing off one step. A fixed configuration would either
leave latency on the table or fail intermittently in the field.

### Why CUDA-only (initial scope)

The fingerprint approach generalizes to any GPU framework, but the
immediate consumer is the existing CUDA pinned-memory pipeline
(`examples/cuda_pinned_pipelined.py`). HIP and Level Zero variants
become reasonable when the corresponding consumer examples exist;
until then they would test paths nobody runs.

### API surface impact

The benchmark is an example, not a public API. It surfaces small
additions justified by the same need any latency-sensitive consumer
faces:

- `ConfigInt.ReferenceOutputMode` — selects input-locked output
  clock. Without it, consumers pass raw FourCC values to
  `set_config_int`.
- `ConfigInt.ReferenceInputTimingOffset` — sub-frame timing offset.
  Same justification.

Existing surface used by the benchmark:
`CaptureFrameRef.callback_arrived_us`, `OutputStatus`, `clock_us()`,
`schedule_output_frame`, `pop_capture_frame_ref`, `set_config_int`.
No helper for input-driven scheduling is added here; if the pattern
proves common a future spec section may propose one.

### Scope

- One pixel format and frame rate per run. Primary characterization
  mode: 4K UHD 59.94p 10-bit YUV 4:2:2 (`Mode4K2160p5994` /
  `Format10BitYUV` / v210). 4K59.94 + v210 is the repo-wide
  default for examples and benchmarks (see
  `cuda_pinned_pipelined.py`) and matches standard production
  capture; the latency benchmark inherits both. Other modes
  parameterized; fingerprint encoding is mode-aware.
- Two DeckLink sub-devices wired in physical loopback (BNC jumper
  between SDI ports). Sub-devices on the same card in half-duplex
  profile are valid — the SDK exposes them as independent
  `IDeckLink` interfaces, one configured for output and one for
  input. Genuine two-card configurations are also supported but
  not required.
- No HDR, audio, ancillary data. Fingerprint occupies active video
  only.
- Genlock (REF BNC) configuration is not exercised by the benchmark.
  Users who want facility-genlocked output configure it via existing
  `set_config_int`.

### Citations

- §4 Device Model — buffer recycling and queue depth context.
- §5.5 Playout — scheduled playback semantics.
- §5.7 Configuration — config-int surface this section extends.
- §5.11 Device Status — soft dependency. `ReferenceStatus.locked` is
  useful for interpreting whether input-locked output mode actually
  engaged, but the benchmark does not require §5.11 to ship.

## API Information §spec:api-information

*Status: not started*

### Problem

pydecklink loads the Blackmagic Desktop Video runtime but does not
surface which version of that runtime is loaded. Support diagnostics,
bug reports, and CI fingerprints have to ask the user to run a
separate Blackmagic CLI to recover what is already inside the
process. The SDK header version is pinned at build time (15.3,
vendored); the running driver version is opaque from Python.

### Behavior

`pydecklink.api_version() -> APIVersion` returns the running Desktop
Video runtime version, sourced from `IDeckLinkAPIInformation` via
`CreateDeckLinkAPIInformationInstance()`.

`APIVersion` exposes:

- `string -> str` — formatted version (e.g. `"15.3.0"`); also
  produced by `__str__` and `__repr__`.
- `major -> int`, `minor -> int`, `sub -> int`, `extra -> int` —
  the four bytes of the packed value, high to low.
- `packed -> int` — the raw 32-bit value as returned by the SDK.

When `CreateDeckLinkAPIInformationInstance()` returns null — Desktop
Video is not installed or its shared library cannot be loaded —
`api_version()` raises `RuntimeError` with the same install guidance
the device-enumeration path already uses.

### Why module-level, not per-device

`IDeckLinkAPIInformation` is a process-global singleton, not a
per-`IDeckLink` interface. The version reflects the loaded
`libDeckLinkAPI.so` / CoreFoundation plug-in / COM server, not any
specific device. A module-level function matches what is being
queried, mirroring `device_count()` and `list_devices()` which
expose process-global SDK state. Attaching it to `Device` would
imply the version varies per-device.

### Why a structured return, not a bare string

Diagnostic loggers want a string; consumers who later need to gate
on a threshold want the parts. Returning both views in one value
avoids forcing the caller to re-parse the version they just
received, and costs nothing — the SDK exposes both as separate
reads on the same singleton. A bare string locks future callers
out of the parts; a bare tuple is unfriendly to logs.

### Why RuntimeError on absent runtime

When Desktop Video is missing,
`CreateDeckLinkAPIInformationInstance()` returns null. Returning
`None` would conflate "we don't know the version" with "we cannot
talk to the SDK at all" — and the latter is what the caller needs
to act on. The existing device-enumeration path
(`bind_device.h`) already raises `RuntimeError` with install
guidance for the same failure; matching that shape keeps one
failure idiom across the binding.

### Scope

- Reads `BMDDeckLinkAPIVersion` only — the only attribute
  `BMDDeckLinkAPIInformationID` defines in SDK 15.3.
- The reported version is the runtime, not the vendored SDK
  headers pydecklink builds against. Detecting mismatch between
  the two is left to consumers.

### Citations

- §2 Development Environment — vendored SDK header version (15.3)
  that this surface complements at runtime.
- §5.1 Device — module-level enumeration pattern
  (`device_count()`, `list_devices()`) this function follows.
