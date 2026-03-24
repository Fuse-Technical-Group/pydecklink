# pyprovideo — Vendor-Neutral Professional Video I/O for Python

## 1. Problem Statement

*Status: not started*

Professional video I/O in Python is fragmented by vendor. Each SDK
(AJA NTV2, Blackmagic DeckLink, Deltacast VideoMaster) has its own
device model, frame lifecycle, and DMA semantics. Applications that
need to support multiple vendors — or use two vendors in the same
pipeline (e.g., capture on AJA, output on Blackmagic) — must write
and maintain separate integration code for each.

pyprovideo provides a vendor-neutral protocol layer over per-vendor
Python bindings. It unifies device discovery, stream lifecycle, and
frame transfer behind a common interface. Vendor-specific features
(AJA crosspoint routing, Blackmagic HDR InfoFrame metadata) remain
accessible through each backend's native API.

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
    pyprovideo/          # vendor-neutral protocols + device discovery
    pyntv2/              # AJA NTV2 backend (nanobind, existing)
    pydecklink/          # Blackmagic DeckLink backend (nanobind, new)
    pydeltacast/         # Deltacast VideoMaster backend (future)
  pyproject.toml         # uv workspace root
```

Each package publishes independently to PyPI. `pyprovideo` has no
vendor SDK dependencies. Installing a backend (e.g., `pip install
pyntv2`) makes it available to pyprovideo via entry-point discovery.

### Why a mono-repo

- Shared build infrastructure: nanobind version, scikit-build-core
  config, Python version matrix, linting rules.
- Protocol changes and backend updates land in one PR, one review.
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
generation code stays in the bmd-signal-gen repo and becomes a
pyprovideo consumer. Git history for the original DeckLink wrapper
lives in the bmd-signal-gen repo.

## 3. Device Discovery

*Status: not started*

`pyprovideo.enumerate_devices()` returns all devices across all
installed backends as a flat list. Each device carries vendor and
model metadata.

```python
devices = pyprovideo.enumerate_devices()
# [
#   Device(vendor="aja", model="Corvid 44 12G", index=0),
#   Device(vendor="aja", model="Corvid 44 12G", index=1),
#   Device(vendor="blackmagic", model="DeckLink 8K Pro", index=0),
# ]
```

### Backend registration

Backends register via Python entry points:

```toml
# pyntv2/pyproject.toml
[project.entry-points."pyprovideo.backends"]
aja = "pyntv2:AjaBackend"
```

pyprovideo lazy-loads backends on the first `enumerate_devices()`
call. A backend whose SDK or driver is missing raises `ImportError`
at load time; pyprovideo catches it, logs a warning, and skips that
backend. No application crash.

### Explicit override

When the caller knows which backend it wants, it can skip discovery:

```python
devices = pyprovideo.enumerate_devices(backends=["aja"])
```

Or register a backend directly without entry points:

```python
from pyntv2 import AjaBackend
pyprovideo.register_backend(AjaBackend())
devices = pyprovideo.enumerate_devices()
```

### Multi-card

Multiple cards from the same vendor appear as separate `Device`
instances. Multiple cards from different vendors appear in the same
list. The caller selects devices by vendor, model, index, or any
combination. There is no implicit "default device" — the caller
always chooses.

## 4. Stream Protocols

*Status: not started*

pyprovideo defines `OutputStream` and `InputStream` as Python
`Protocol` classes (structural subtyping). Backends implement them;
applications program against them.

### OutputStream

```python
FrameBuffer = Union[numpy.ndarray, "cupy.ndarray", "torch.Tensor", Any]
# Any object supporting the buffer protocol or DLPack.

class OutputStream(Protocol):
    def configure(self, fmt: VideoFormat, pix: PixelFormat) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def submit_frame(self, frame: FrameBuffer) -> None: ...
    def status(self) -> StreamStatus: ...
```

`submit_frame` accepts any object implementing the buffer protocol
or DLPack (numpy, CuPy, PyTorch). The backend determines from the
buffer's device tag whether DMA, RDMA, or a host-memory copy is
needed.

### InputStream

```python
class InputStream(Protocol):
    def configure(self, fmt: VideoFormat, pix: PixelFormat) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def acquire_frame(
        self, buffer: FrameBuffer, timeout: float | None = None,
    ) -> FrameMetadata: ...
    def detected_format(self) -> VideoFormat | None: ...
    def status(self) -> StreamStatus: ...
```

`acquire_frame` writes into a caller-supplied buffer. The buffer
may be CPU or GPU memory. The backend handles DMA targeting.

`timeout` is seconds. `None` blocks until the next frame. On
timeout, raises `TimeoutError`. Each backend translates to its
native wait mechanism — AJA polls `has_available_input_frame` per
VBI; Blackmagic pops from an internal callback queue.

`FrameMetadata` includes a `signal_present: bool` field. On signal
loss, AJA returns no frames (timeout); Blackmagic delivers frames
with `bmdFrameHasNoInputSource` (signal_present=False, frame data
invalid). Callers check `signal_present` rather than branching on
vendor.

### StreamStatus

Read-only snapshot of stream health:

```python
@dataclass(frozen=True)
class StreamStatus:
    is_running: bool
    dropped_frame_count: int
    buffer_level: int
```

### Stream state machine

Both `InputStream` and `OutputStream` enforce the same external
state contract. Each backend owns its internal init/teardown
sequence but must map to these transitions:

```text
IDLE ──configure()──▶ CONFIGURED ──start()──▶ RUNNING ──stop()──▶ CONFIGURED
                         ▲                                           │
                         └───────────────configure()─────────────────┘
```

- `start()` from IDLE raises `RuntimeError`.
- `configure()` while RUNNING raises `RuntimeError` (must stop first).
- `stop()` from IDLE or CONFIGURED is a no-op.
- `close()` (context manager exit) calls `stop()` then releases
  hardware resources. The stream is not reusable after close.

### Stream acquisition

```python
with device.open_output(connector="SDI1") as out:
    out.configure(fmt, pix)
    out.start()
    out.submit_frame(frame)
```

The `connector` parameter names the physical connector. Each
backend maps connector names to its internal channel/stream model:

| Connector name | AJA mapping | BMD mapping | Deltacast mapping |
|---|---|---|---|
| `"SDI1"` | CH1 + route_playout | Sub-device 0 output | Board 0, TX0 |
| `"HDMI1"` | CH1 + HDMI route | Sub-device HDMI output | Board 0, HDMI TX |

If a connector name is ambiguous or unsupported, the backend raises
`ValueError` with available options.

## 5. Format Model

*Status: not started*

### VideoFormat

A vendor-neutral video format descriptor. Not an enum — the format
space is too large and vendor-specific for a fixed enumeration.

```python
@dataclass(frozen=True)
class VideoFormat:
    width: int
    height: int
    rate: Fraction         # exact frame rate, e.g. Fraction(30000, 1001)
    interlaced: bool
    name: str              # human-readable, e.g. "1080p29.97"
```

Each backend maps its native format enum to/from `VideoFormat`.
Round-tripping is lossless for formats the backend supports.

### PixelFormat

The enum defines a baseline that all backends must support, plus
optional formats that backends may advertise.

```python
class PixelFormat(Enum):
    # Baseline — every backend must support these four.
    YCBCR_8   = auto()
    YCBCR_10  = auto()
    RGB_8     = auto()
    RGB_10    = auto()

    # Optional — backends advertise support via
    # Device.supported_pixel_formats().
    RGB_12    = auto()
    RGBA_8    = auto()
    RGBA_10   = auto()
```

`Device.supported_pixel_formats()` returns the set of `PixelFormat`
values the device handles natively. The baseline four are always
present. Callers targeting cross-vendor compatibility should stick
to the baseline. Backends that receive an unsupported format raise
`ValueError`.

### HDRMetadata

```python
@dataclass
class HDRMetadata:
    eotf: EOTF                             # SDR, PQ, HLG
    primaries: tuple[float, ...]           # CIE 1931 xy, 8 values (RGBW)
    max_display_luminance: float           # cd/m², ST 2086
    min_display_luminance: float           # cd/m², ST 2086
    max_cll: float                         # cd/m², CEA-861.3
    max_fall: float                        # cd/m², CEA-861.3
```

Backends that support HDR metadata (Blackmagic InfoFrame, AJA
ancillary data injection) consume this structure. Backends that
don't silently ignore it.

## 6. DMA and GPU Interop

*Status: not started*

### DMA paths by vendor

| Vendor | CPU DMA | GPU RDMA (NVIDIA) | Notes |
|---|---|---|---|
| AJA NTV2 | AutoCirculate transfer | `nvidia_p2p_*` in kernel driver | Zero-copy GPU↔card. Requires same PCIe bridge. |
| Blackmagic | Scheduled playback / sync display | Not supported by SDK | GPU frames must copy to host first. |
| Deltacast | Slot lock/unlock | Not supported by SDK | GPU frames must copy to host first. |

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

The GPU→host copy on the output side is unavoidable given current
Blackmagic SDK constraints. Each backend handles this internally:
when `submit_frame` receives a GPU buffer and the backend lacks
RDMA, the backend copies to a pinned host staging buffer before
DMA. pyprovideo remains pure Python — GPU interop logic (including
`cudaMemcpy`) lives in the vendor package that needs it. The caller
does not branch on vendor.

### Buffer lifecycle

Each backend manages DMA buffer pinning internally. The pyprovideo
protocol operates on buffer objects (numpy/CuPy/PyTorch arrays).
Backends that benefit from pre-pinned buffers (AJA's
`dma_buffer_lock`) expose a buffer allocator:

```python
buf = stream.allocate_buffer()  # returns pinned, page-aligned array
```

Callers who supply their own buffers accept that the backend may
need to pin/unpin per frame.

## 7. Backend Requirements

*Status: not started*

Each backend package must:

1. Implement `Backend` protocol: `enumerate_devices() → list[Device]`.
2. `Device` must support `open_input(connector)` and
   `open_output(connector)`.
3. Returned streams must implement `InputStream` or `OutputStream`.
4. Register via `[project.entry-points."pyprovideo.backends"]`.
5. Handle missing SDK/driver gracefully — `ImportError` at module
   load, not segfault.
6. Map the vendor-neutral `VideoFormat` and `PixelFormat` to native
   enums without data loss for the common subset.

### pyntv2 backend (AJA)

Already exists. Shim layer maps `open_output("SDI1")` to
`Card.set_mode(CH1, DISPLAY)` + `route_playout(CH1, SDI1, fmt)` +
AutoCirculate init/start. `submit_frame` calls
`autocirculate_transfer`.

AJA-specific features (full crosspoint routing, explicit buffer
locking, VBI sync) remain accessible by dropping to the `pyntv2`
API directly.

### pydecklink backend (Blackmagic)

Nanobind rewrite of the C++ wrapper from bmd-signal-gen. Replaces
the `extern "C"` shim + ctypes with direct class binding.

Adds:
- Scheduled playback (output frame queue) — replaces single-frame
  `DisplayVideoFrameSync` for sustained streaming.
- Capture via `IDeckLinkInputCallback` — adapted to pull-based
  `acquire_frame` by queuing frames internally and blocking on pop.
- Linux support (currently macOS only).
- Device enumeration via `IDeckLinkIterator`.

### pydeltacast backend (Deltacast)

Future. The VideoMaster flat C API (`VHD_*` functions) wraps
naturally with nanobind or ctypes. Board/stream/slot model maps
directly to Device/Stream/Frame.

## 8. Signal Routing

*Status: not started*

### Why routing is not in the protocol

Signal routing describes how on-card processing blocks (frame
stores, color space converters, LUTs, mixers) are wired together.

AJA exposes a full crosspoint matrix: 120+ input crosspoints,
100+ output crosspoints, user-controlled wiring. Applications
build a routing graph: physical inputs → processing → frame
stores → processing → physical outputs.

Blackmagic and Deltacast do not expose internal routing. Opening
a stream implicitly wires frame store → physical connector.

A vendor-neutral routing abstraction would be either too simple
(already what `open_input(connector)` does) or too complex
(AJA's crosspoint matrix that other vendors can't use).

### What pyprovideo provides instead

`open_input(connector)` and `open_output(connector)` handle
routing implicitly. The AJA backend calls `route_capture()` /
`route_playout()` with automatic CSC insertion when needed.

Users who need AJA's full routing — dual-link, multi-stream,
mixer keying, LUT insertion — use `pyntv2.Card` directly:

```python
device = pyprovideo.enumerate_devices(backends=["aja"])[0]
card = device.native  # pyntv2.Card instance
card.apply_signal_route(custom_routes)
```

## 9. Explicit Non-Goals

*Status: not started*

- **Audio.** Deferred. The stream protocol can extend to audio
  later without breaking changes.
- **Ancillary data.** Timecode, closed captions — deferred.
- **Windows.** Linux first. macOS where vendor SDKs support it.
  Windows is not blocked but not prioritized.
- **Matrox, Bluefish444.** The protocol doesn't prevent additional
  backends, but only AJA, Blackmagic, and Deltacast are planned.
- **Real-time scheduling.** pyprovideo does not manage thread
  priority, CPU affinity, or SCHED_FIFO. Applications handle this.
- **Video processing.** No color conversion, scaling, or compositing
  in pyprovideo. It moves frames. Processing belongs in the
  application (or a library like OpenCV, colour-science, or a GPU
  shader).
- **Signal routing abstraction.** Vendor-internal routing (AJA
  crosspoints) stays in the vendor API. pyprovideo routes implicitly
  via connector names.
