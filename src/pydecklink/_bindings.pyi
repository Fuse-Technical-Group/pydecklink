"""pydecklink: Python bindings for Blackmagic DeckLink SDK"""

from collections.abc import Callable
import enum
from typing import Annotated

import numpy
from numpy.typing import NDArray


HAS_SDK: bool = True

class DisplayMode(enum.Enum):
    NTSC = 1853125475

    NTSC2398 = 1853108787

    PAL = 1885432864

    NTSCp = 1853125488

    PALp = 1885432944

    HD1080p2398 = 842231923

    HD1080p24 = 842297459

    HD1080p25 = 1215312437

    HD1080p2997 = 1215312441

    HD1080p30 = 1215312688

    HD1080p4795 = 1215312951

    HD1080p48 = 1215312952

    HD1080p50 = 1215313200

    HD1080p5994 = 1215313209

    HD1080p6000 = 1215313456

    HD1080p9590 = 1215314229

    HD1080p96 = 1215314230

    HD1080p100 = 1215312176

    HD1080p11988 = 1215312177

    HD1080p120 = 1215312178

    HD1080i50 = 1214854448

    HD1080i5994 = 1214854457

    HD1080i6000 = 1214854704

    HD720p50 = 1752184112

    HD720p5994 = 1752184121

    HD720p60 = 1752184368

    Mode2k2398 = 845886003

    Mode2k24 = 845886004

    Mode2k25 = 845886005

    Mode2kDCI2398 = 845427251

    Mode2kDCI24 = 845427252

    Mode2kDCI25 = 845427253

    Mode2kDCI2997 = 845427257

    Mode2kDCI30 = 845427504

    Mode2kDCI4795 = 845427767

    Mode2kDCI48 = 845427768

    Mode2kDCI50 = 845428016

    Mode2kDCI5994 = 845428025

    Mode2kDCI60 = 845428272

    Mode2kDCI9590 = 845429045

    Mode2kDCI96 = 845429046

    Mode2kDCI100 = 845426992

    Mode2kDCI11988 = 845426993

    Mode2kDCI120 = 845426994

    Mode4K2160p2398 = 879440435

    Mode4K2160p24 = 879440436

    Mode4K2160p25 = 879440437

    Mode4K2160p2997 = 879440441

    Mode4K2160p30 = 879440688

    Mode4K2160p4795 = 879440951

    Mode4K2160p48 = 879440952

    Mode4K2160p50 = 879441200

    Mode4K2160p5994 = 879441209

    Mode4K2160p60 = 879441456

    Mode4K2160p9590 = 879442229

    Mode4K2160p96 = 879442230

    Mode4K2160p100 = 879440176

    Mode4K2160p11988 = 879440177

    Mode4K2160p120 = 879440178

    Mode4kDCI2398 = 878981683

    Mode4kDCI24 = 878981684

    Mode4kDCI25 = 878981685

    Mode4kDCI2997 = 878981689

    Mode4kDCI30 = 878981936

    Mode4kDCI4795 = 878982199

    Mode4kDCI48 = 878982200

    Mode4kDCI50 = 878982448

    Mode4kDCI5994 = 878982457

    Mode4kDCI60 = 878982704

    Mode4kDCI9590 = 878983477

    Mode4kDCI96 = 878983478

    Mode4kDCI100 = 878981424

    Mode4kDCI11988 = 878981425

    Mode4kDCI120 = 878981426

    Mode8K4320p2398 = 946549299

    Mode8K4320p24 = 946549300

    Mode8K4320p25 = 946549301

    Mode8K4320p2997 = 946549305

    Mode8K4320p30 = 946549552

    Mode8K4320p4795 = 946549815

    Mode8K4320p48 = 946549816

    Mode8K4320p50 = 946550064

    Mode8K4320p5994 = 946550073

    Mode8K4320p60 = 946550320

    Mode8kDCI2398 = 946090547

    Mode8kDCI24 = 946090548

    Mode8kDCI25 = 946090549

    Mode8kDCI2997 = 946090553

    Mode8kDCI30 = 946090800

    Mode8kDCI4795 = 946091063

    Mode8kDCI48 = 946091064

    Mode8kDCI50 = 946091312

    Mode8kDCI5994 = 946091321

    Mode8kDCI60 = 946091568

    Mode640x480p60 = 1986486582

    Mode1920x1200p60 = 2004187190

    Unknown = 1769303659

class PixelFormat(enum.Enum):
    Unspecified = 0

    Format8BitYUV = 846624121

    Format10BitYUV = 1983000880

    Format10BitYUVA = 1098461488

    Format8BitARGB = 32

    Format8BitBGRA = 1111970369

    Format10BitRGB = 1915892016

    Format12BitRGB = 1378955842

    Format12BitRGBLE = 1378955852

    Format10BitRGBXLE = 1378955372

    Format10BitRGBX = 1378955362

    FormatH265 = 1751479857

    FormatDNxHR = 1096180840

class FieldDominance(enum.Enum):
    Unknown = 0

    LowerFieldFirst = 1819244402

    UpperFieldFirst = 1970303090

    ProgressiveFrame = 1886547815

    ProgressiveSegmentedFrame = 1886610976

class VideoInputFlag(enum.Enum):
    Default = 0

    EnableFormatDetection = 1

    DualStream3D = 2

    SynchronizeToCaptureGroup = 4

class VideoOutputFlag(enum.IntEnum):
    Default = 0

    VANC = 1

    VITC = 2

    RP188 = 4

    DualStream3D = 16

    SynchronizeToPlaybackGroup = 64

    DolbyVision = 128

class FrameFlag(enum.Enum):
    Default = 0

    FlipVertical = 1

    MonitorOutOnly = 8

    ContainsHDRMetadata = 2

    ContainsDolbyVisionMetadata = 16

    CapturedAsPsF = 1073741824

    HasNoInputSource = -2147483648

class DetectedInputFormat(enum.Enum):
    YCbCr422 = 1

    RGB444 = 2

    DualStream3D = 4

    Depth12Bit = 8

    Depth10Bit = 16

    Depth8Bit = 32

class OutputFrameResult(enum.Enum):
    Completed = 0

    DisplayedLate = 1

    Dropped = 2

    Flushed = 3

class VideoIOSupport(enum.Enum):
    Capture = 1

    Playback = 2

class ConfigurationID(enum.Enum):
    Config444SDIVideoOutput = 875836527

    ConfigLowLatencyVideoOutput = 1819047535

    ConfigSMPTELevelAOutput = 1936553057

    ConfigRec2020Output = 1919247154

    ConfigOutput1080pAsPsF = 1885761650

    ConfigVideoOutputConnection = 1987011438

    ConfigVideoOutputConversionMode = 1987011437

    ConfigVideoOutputIdleOperation = 1987012975

    ConfigSDIOutputLinkConfiguration = 1936682083

    ConfigReferenceInputTimingOffset = 1735159668

    PlaybackGroup = 1886152562

    ConfigUseDedicatedLTCInput = 1684829283

    ConfigCapture1080pAsPsF = 1667657842

    ConfigVideoInputConnection = 1986618222

    ConfigCapturePassThroughMode = 1668314221

    ConfigSwapSerialRxTx = 1936945780

class AttributeID(enum.Enum):
    SupportsInternalKeying = 1801812329

    SupportsExternalKeying = 1801812325

    SupportsInputFormatDetection = 1768842852

    HasReferenceInput = 1752328558

    SupportsHDRMetadata = 1751413357

    SupportsColorspaceMetadata = 1668113780

    SupportsIdleOutput = 1768189813

    SupportsSMPTELevelAOutput = 1819700321

    SupportsSynchronizeToPlaybackGroup = 1937010791

    SupportsFullFrameReferenceInputTimingOffset = 1718774126

    MaximumAudioChannels = 1835098984

    NumberOfSubDevices = 1853055588

    SubDeviceIndex = 1937072745

    PersistentID = 1885694308

    VideoOutputConnections = 1987011438

    VideoInputConnections = 1986618222

    VideoIOSupport = 1986621299

    DeviceInterface = 1684174195

    Duplex = 1685418104

    MinimumPrerollFrames = 1836085862

    ProfileID = 1886546276

    VendorName = 1986946162

    DisplayName = 1685287022

    ModelName = 1835297902

    DeviceHandle = 1684371048

class DisplayModeFlag(enum.Enum):
    Supports3D = 1

    ColorspaceRec601 = 2

    ColorspaceRec709 = 4

    ColorspaceRec2020 = 8

class VideoConnection(enum.Enum):
    Unspecified = 0

    SDI = 1

    HDMI = 2

    OpticalSDI = 4

    Component = 8

    Composite = 16

    SVideo = 32

    Ethernet = 64

    OpticalEthernet = 128

    Internal = 256

class DuplexMode(enum.Enum):
    Full = 1685612149

    Half = 1685612641

    Simplex = 1685615472

    Inactive = 1685612910

class SupportedVideoModeFlag(enum.Enum):
    Default = 0

    Keying = 1

    DualStream3D = 2

    SDISingleLink = 4

    SDIDualLink = 8

class VideoOutputConversionMode(enum.Enum):
    NoConversion = 1852796517

    LetterboxDownconversion = 1819566712

    AnamorphicDownconversion = 1634562152

    HD720toHD1080 = 926036067

    HardwareLetterboxDownconversion = 1213688930

    HardwareAnamorphicDownconversion = 1213686125

    HardwareCenterCutDownconversion = 1213686627

    Hardware720p1080pCrossconversion = 2019778928

    HardwareAnamorphic720pUpconversion = 1969305456

class ProfileID(enum.Enum):
    OneSubDeviceFullDuplex = 828663396

    OneSubDeviceHalfDuplex = 828663908

    TwoSubDevicesFullDuplex = 845440612

    TwoSubDevicesHalfDuplex = 845441124

    FourSubDevicesHalfDuplex = 878995556

class DeviceInfo:
    @property
    def model_name(self) -> str: ...

    @property
    def display_name(self) -> str: ...

    @property
    def index(self) -> int: ...

    def __repr__(self) -> str: ...

def device_count() -> int:
    """Return the number of DeckLink devices present."""

def list_devices() -> list[DeviceInfo]:
    """Return a list of DeviceInfo for each DeckLink device."""

class Device:
    def __init__(self, index: int = 0) -> None: ...

    @property
    def model_name(self) -> str: ...

    @property
    def display_name(self) -> str: ...

    @property
    def supports_capture(self) -> bool: ...

    @property
    def supports_playback(self) -> bool: ...

    @property
    def supports_input_format_detection(self) -> bool: ...

    @property
    def supports_hdr(self) -> bool: ...

    def __repr__(self) -> str: ...

    def __enter__(self) -> object: ...

    def __exit__(self, *args) -> None: ...

    def get_attribute_int(self, attr_id: AttributeID) -> int:
        """Get an integer profile attribute."""

    def active_profile(self) -> ProfileID:
        """Return the active profile ID for this device."""

    def set_profile(self, profile_id: ProfileID) -> None:
        """Activate a connector profile. Affects all sub-devices on this card."""

    def get_attribute_flag(self, attr_id: AttributeID) -> bool:
        """Get a boolean profile attribute."""

    def get_display_mode(self, mode: DisplayMode) -> DisplayModeInfo:
        """Get display mode properties for a given BMDDisplayMode."""

    def list_output_modes(self) -> list[DisplayModeInfo]:
        """List all output display modes supported by the device."""

    def does_support_video_mode(self, connection: VideoConnection, mode: DisplayMode, pixel_format: PixelFormat, conversion_mode: VideoOutputConversionMode = VideoOutputConversionMode.NoConversion, flags: SupportedVideoModeFlag = SupportedVideoModeFlag.Default) -> bool:
        """
        Check whether the device supports a given video mode, pixel format, and connection.
        """

    def enable_video_output(self, mode: DisplayMode, flags: int = 0) -> None:
        """Enable video output for the given display mode."""

    def row_bytes_for_pixel_format(self, pixel_format: PixelFormat, width: int) -> int:
        """Get the row bytes for a given pixel format and width."""

    def create_frame_pool(self, count: int, width: int, height: int, row_bytes: int, pixel_format: PixelFormat) -> None:
        """
        Pre-allocate a pool of output frames. Completed frames return to the pool automatically.
        """

    def acquire_output_frame(self, timeout_ms: int = 1000) -> MutableFrame:
        """
        Acquire a pre-allocated output frame from the pool. Blocks until one is available.
        """

    def schedule_output_frame(self, frame: MutableFrame, display_time: int, duration: int, timescale: int) -> None:
        """Schedule a pre-allocated output frame. No allocation, no copy."""

    @property
    def pool_available(self) -> int:
        """Number of output frames available in the pool."""

    def disable_video_output(self) -> None:
        """Disable video output."""

    def create_video_frame(self, width: int, height: int, row_bytes: int, pixel_format: PixelFormat) -> MutableFrame:
        """Create a mutable video frame for output."""

    def display_frame_sync(self, buffer: Annotated[NDArray[numpy.uint8], dict(shape=(None,))], width: int, height: int, row_bytes: int, pixel_format: PixelFormat) -> None:
        """
        Display a frame synchronously (blocking). Copies buffer into a new frame.
        """

    def schedule_capture_frame(self, capture_frame: CaptureFrameRef, display_time: int, duration: int, timescale: int) -> None:
        """Schedule a zero-copy captured frame for playback. No memcpy."""

    def start_scheduled_playback(self, start_time: int, timescale: int, speed: float = 1.0) -> None:
        """Start scheduled playback."""

    def stop_scheduled_playback(self) -> None:
        """Stop scheduled playback."""

    @property
    def is_scheduled_playback_running(self) -> bool:
        """True if scheduled playback is currently running."""

    @property
    def output_status(self) -> OutputStatus:
        """Current output frame completion statistics."""

    def set_config_flag(self, flag: ConfigurationID, value: bool) -> None:
        """Set a boolean configuration flag."""

    def get_config_flag(self, flag: ConfigurationID) -> bool:
        """Get a boolean configuration flag."""

    def set_config_int(self, setting: ConfigurationID, value: int) -> None:
        """Set an integer configuration value."""

    def get_config_int(self, setting: ConfigurationID) -> int:
        """Get an integer configuration value."""

    def write_config(self) -> None:
        """Persist configuration changes to preferences."""

    def enable_video_input(self, mode: DisplayMode, pixel_format: PixelFormat, flags: VideoInputFlag = VideoInputFlag.Default, zero_copy: bool = False, input_queue_depth: int = 1) -> None:
        """
        Enable video input for the given display mode and pixel format. ``input_queue_depth`` bounds the internal C++ queue between the SDK input thread (producer) and the Python consumer; on overflow the oldest frame is dropped. Default 1 (real-time: drop late frames, never lag); raise for recorder-style consumers that need to absorb consumer-side jitter.
        """

    def disable_video_input(self) -> None:
        """Disable video input."""

    def start_streams(self) -> None:
        """Start capture streams."""

    def stop_streams(self) -> None:
        """Stop capture streams."""

    def pop_capture_frame(self, timeout_ms: int = 1000) -> CaptureFrame | None:
        """Pop a captured frame from the queue, or None on timeout."""

    def pop_capture_frame_ref(self, timeout_ms: int = 1000) -> CaptureFrameRef | None:
        """Pop a zero-copy captured frame reference, or None on timeout."""

    @property
    def current_input_format(self) -> InputFormatInfo | None:
        """Current detected input format, or None if input is not enabled."""

    def enable_video_input_with_allocator(self, mode: DisplayMode, pixel_format: PixelFormat, flags: VideoInputFlag, allocator_provider: VideoBufferAllocatorProvider, zero_copy: bool = True, input_queue_depth: int = 1) -> None:
        """
        Enable video input using a custom buffer allocator provider. The SDK will call the provider to obtain allocators for DMA buffers, enabling host pinned memory for the H2D path. ``input_queue_depth`` bounds the internal frame queue (default 1 = real-time, drop late frames); each queued frame in zero-copy mode holds an AddRef on a ManagedBuffer, keeping it off the allocator's free-list, so a deep queue puts buffer-pool pressure on the SDK.
        """

    def create_frame_pool_pinned(self, count: int, width: int, height: int, row_bytes: int, pixel_format: PixelFormat, allocator: VideoBufferAllocator) -> None:
        """
        Create a frame pool backed by pinned (allocator-managed) buffers. Each frame uses CreateVideoFrameWithBuffer. For GPU DMA, pass an allocator using CUDA pinned memory.
        """

    @property
    def profile_manager(self) -> ProfileManager | None:
        """
        Return the device's ``ProfileManager``, or ``None`` if the device is single-profile.
        """

class DisplayModeInfo:
    @property
    def mode(self) -> DisplayMode: ...

    @property
    def name(self) -> str: ...

    @property
    def width(self) -> int: ...

    @property
    def height(self) -> int: ...

    @property
    def frame_rate(self) -> tuple[int, int]: ...

    @property
    def field_dominance(self) -> FieldDominance: ...

    @property
    def flags(self) -> int: ...

    def __repr__(self) -> str: ...

def get_mode_width(mode: DisplayMode) -> int:
    """Return the raster width in pixels for a display mode."""

def get_mode_height(mode: DisplayMode) -> int:
    """Return the raster height in pixels for a display mode."""

def get_mode_fps(mode: DisplayMode) -> float:
    """Return the frames per second for a display mode."""

def get_mode_frame_duration(mode: DisplayMode) -> tuple[int, int]:
    """Return (duration, timescale) for a display mode."""

def get_frame_bytes(mode: DisplayMode, pixel_format: PixelFormat) -> int:
    """Return the total frame byte count for a display mode and pixel format."""

def get_row_bytes(pixel_format: PixelFormat, width: int) -> int:
    """Return the row byte count for a pixel format and width."""

class OutputStatus:
    def __init__(self) -> None: ...

    @property
    def completed(self) -> int: ...

    @completed.setter
    def completed(self, arg: int, /) -> None: ...

    @property
    def late(self) -> int: ...

    @late.setter
    def late(self, arg: int, /) -> None: ...

    @property
    def dropped(self) -> int: ...

    @dropped.setter
    def dropped(self, arg: int, /) -> None: ...

    @property
    def flushed(self) -> int: ...

    @flushed.setter
    def flushed(self, arg: int, /) -> None: ...

    @property
    def underrun(self) -> bool: ...

    @underrun.setter
    def underrun(self, arg: bool, /) -> None: ...

    def __repr__(self) -> str: ...

class MutableFrame:
    @property
    def width(self) -> int: ...

    @property
    def height(self) -> int: ...

    @property
    def row_bytes(self) -> int: ...

    @property
    def data(self) -> Annotated[NDArray[numpy.uint8], dict(shape=(None,))]:
        """Writeable numpy uint8 view of the frame buffer."""

def clock_us() -> int:
    """Return monotonic time in microseconds."""

class CaptureFrame:
    @property
    def data(self) -> Annotated[NDArray[numpy.uint8], dict(shape=(None,))]:
        """Frame pixel data as numpy uint8 array."""

    @property
    def width(self) -> int: ...

    @property
    def height(self) -> int: ...

    @property
    def row_bytes(self) -> int: ...

    @property
    def pixel_format(self) -> PixelFormat: ...

    @property
    def stream_time(self) -> tuple[int, int]:
        """Stream time as (time, duration) tuple."""

    @property
    def hardware_reference_timestamp(self) -> int: ...

    @property
    def has_signal(self) -> bool: ...

    def __repr__(self) -> str: ...

class CaptureFrameRef:
    @property
    def data(self) -> Annotated[NDArray[numpy.uint8], dict(shape=(None,))]:
        """
        Read-only numpy view of the SDK frame buffer. The CaptureFrameRef must outlive the array.
        """

    @property
    def width(self) -> int: ...

    @property
    def height(self) -> int: ...

    @property
    def row_bytes(self) -> int: ...

    @property
    def pixel_format(self) -> PixelFormat: ...

    @property
    def has_signal(self) -> bool: ...

    @property
    def hardware_reference_timestamp(self) -> int: ...

    @property
    def callback_arrived_us(self) -> int:
        """CLOCK_MONOTONIC_RAW time (microseconds) when the callback fired."""

    @property
    def stream_time(self) -> tuple[int, int]:
        """Stream time as (time, duration) tuple."""

    def __repr__(self) -> str: ...

class InputFormatInfo:
    @property
    def mode(self) -> DisplayMode: ...

    @property
    def pixel_format(self) -> PixelFormat: ...

    def __repr__(self) -> str: ...

class ManagedBuffer:
    @property
    def size(self) -> int:
        """Buffer size in bytes."""

    @property
    def data(self) -> Annotated[NDArray[numpy.uint8], dict(shape=(None,))]:
        """Writeable numpy uint8 view of the buffer."""

    def __repr__(self) -> str: ...

class VideoBufferAllocator:
    def __init__(self, size: int, alloc: Callable | None = None, free: Callable | None = None) -> None:
        """
        Create a buffer allocator for the given buffer size.

        Args:
          size: Buffer size in bytes.
          alloc: Optional callable(size: int) -> int returning a pointer.
                 Defaults to malloc.
          free: Optional callable(ptr: int, size: int) -> None.
                Defaults to free.

        For CUDA pinned memory, pass cudaHostAlloc/cudaFreeHost wrappers.

        Note on lifecycle: when ``alloc`` and ``free`` are top-level
        module functions, a reference cycle forms via
        ``func.__globals__`` that Python's GC cannot break (it
        passes through C++). Wrap your setup in a function so the
        allocator and its callbacks are local variables and the
        cycle is reclaimed when that function returns. Both
        examples (``cuda_passthrough.py``,
        ``cuda_register_pinned.py``) follow this pattern.
        """

    @property
    def size(self) -> int:
        """Buffer size that this allocator produces."""

    @property
    def allocated_count(self) -> int:
        """Number of buffers allocated so far."""

    @property
    def recycled_count(self) -> int:
        """
        Number of times a buffer has been returned to the free-list. Each release of a ManagedBuffer increments this counter; the next AllocateVideoBuffer reuses the recycled memory.
        """

    def allocate(self) -> ManagedBuffer:
        """Allocate a new ManagedBuffer."""

    def prefill(self, count: int) -> None:
        """
        Pre-allocate ``count`` buffers and seat them on the free-list. Use this before ``start_streams`` when the allocator wraps a Python callback (e.g. cudaHostAlloc): each SLOW-path allocation pays a GIL+Python round-trip, which the SDK input pipeline cannot tolerate at signal rate. Pre-filling moves all that cost to the calling thread; runtime allocations take the FAST path.
        """

    def __repr__(self) -> str: ...

class VideoBufferAllocatorProvider:
    def __init__(self, alloc: Callable | None = None, free: Callable | None = None) -> None:
        """
        Create a buffer allocator provider.

        Args:
          alloc: Optional callable(size: int) -> int returning a pointer.
          free: Optional callable(ptr: int, size: int) -> None.

        Allocators are cached by buffer size. Custom alloc/free are
        propagated to each VideoBufferAllocator created by the provider.

        Note on lifecycle: when ``alloc`` and ``free`` are top-level
        module functions, a reference cycle forms via
        ``func.__globals__`` that Python's GC cannot break (it
        passes through C++). Wrap your setup in a function so the
        provider and its callbacks are local variables and the
        cycle is reclaimed when that function returns. The passthrough
        example (``cuda_passthrough.py``) follows this pattern.
        """

    def get_allocator(self, buffer_size: int, width: int, height: int, row_bytes: int, pixel_format: PixelFormat) -> VideoBufferAllocator:
        """Get or create a VideoBufferAllocator for the given parameters."""

    def __repr__(self) -> str: ...

class APIVersion:
    @property
    def string(self) -> str:
        """Formatted version string reported by the SDK (e.g. "15.3.0")."""

    @property
    def packed(self) -> int:
        """Raw 32-bit packed version as returned by the SDK."""

    @property
    def major(self) -> int:
        """Major version (high byte of packed)."""

    @property
    def minor(self) -> int:
        """Minor version (second byte of packed)."""

    @property
    def sub(self) -> int:
        """Sub version (third byte of packed)."""

    @property
    def extra(self) -> int:
        """Extra version (low byte of packed)."""

    def __str__(self) -> str: ...

    def __repr__(self) -> str: ...

def api_version() -> APIVersion:
    """
    Return the running Desktop Video runtime version. Raises RuntimeError if Desktop Video is not installed.
    """

class ProfileCallback:
    """
    Base class for profile-change callbacks. Subclass and override ``profile_changing`` and/or ``profile_activated``. The SDK invokes both synchronously on an internal thread; the binding acquires the GIL before dispatching into Python.
    """

    def __init__(self) -> None: ...

    def profile_changing(self, profile: object, streams_will_be_forced_to_stop: bool) -> None:
        """
        Called before firmware reconfiguration. The SDK waits for this method to return before proceeding. Release I/O interfaces here when ``streams_will_be_forced_to_stop`` is True.
        """

    def profile_activated(self, profile: object) -> None:
        """Called after firmware reconfiguration completes."""

class Profile:
    """
    Wraps ``IDeckLinkProfile``. A handle to one of a card's connector profiles.
    """

    @property
    def id(self) -> ProfileID:
        """The profile's identifier."""

    @property
    def is_active(self) -> bool:
        """True if this profile is currently active on the card."""

    def set_active(self) -> None:
        """
        Request activation of this profile. Returns immediately; activation completes asynchronously and is signalled via the registered ``ProfileCallback``.
        """

    def get_peers(self) -> list[Profile]:
        """
        Return profiles of peer sub-devices that activate together when this profile becomes active.
        """

    def __repr__(self) -> str: ...

class ProfileManager:
    """
    Wraps ``IDeckLinkProfileManager``. Created on demand via ``Device.profile_manager``; one per ``IDeckLink``.
    """

    def get_profiles(self) -> list[Profile]:
        """Return all profiles available on this device."""

    def get_profile(self, profile_id: ProfileID) -> Profile:
        """Look up a specific profile by its identifier."""

    def set_callback(self, callback: object | None) -> None:
        """
        Register a ``ProfileCallback``. Pass ``None`` to clear. The SDK accepts one callback per manager; subsequent calls replace prior registrations.
        """

    def __repr__(self) -> str: ...
