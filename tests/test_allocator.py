"""Tests for custom video buffer allocator (no hardware required)."""

import pytest

import pydecklink

pytestmark = pytest.mark.skipif(
    not getattr(pydecklink, "HAS_SDK", False),
    reason="Built without DeckLink SDK headers",
)


class TestVideoBufferAllocatorExists:
    """VideoBufferAllocator class is importable and constructible."""

    def test_class_exists(self):
        assert hasattr(pydecklink, "VideoBufferAllocator")

    def test_construct_with_defaults(self):
        """Default allocator uses malloc/free internally."""
        alloc = pydecklink.VideoBufferAllocator(size=4096)
        assert alloc is not None

    def test_construct_with_size(self):
        alloc = pydecklink.VideoBufferAllocator(size=1920 * 1080 * 4)
        assert alloc.size == 1920 * 1080 * 4

    def test_allocate_returns_buffer(self):
        """AllocateVideoBuffer returns a buffer object with accessible bytes."""
        alloc = pydecklink.VideoBufferAllocator(size=4096)
        buf = alloc.allocate()
        assert buf is not None

    def test_allocate_buffer_has_data(self):
        """Allocated buffer exposes a numpy array of the correct size."""
        alloc = pydecklink.VideoBufferAllocator(size=4096)
        buf = alloc.allocate()
        data = buf.data
        assert len(data) == 4096

    def test_buffer_is_writable(self):
        """Buffer data is writable (needed for DMA writes)."""
        alloc = pydecklink.VideoBufferAllocator(size=4096)
        buf = alloc.allocate()
        data = buf.data
        data[0] = 42
        assert data[0] == 42

    def test_multiple_allocations(self):
        """Allocator can produce multiple independent buffers."""
        alloc = pydecklink.VideoBufferAllocator(size=4096)
        buf1 = alloc.allocate()
        buf2 = alloc.allocate()
        buf1.data[0] = 1
        buf2.data[0] = 2
        assert buf1.data[0] == 1
        assert buf2.data[0] == 2

    def test_pool_count(self):
        """`allocated_count` tracks fresh allocations from the
        underlying alloc_fn — recycled buffers do not increment it.
        Holding two buffers simultaneously forces two distinct
        allocations."""
        alloc = pydecklink.VideoBufferAllocator(size=4096)
        assert alloc.allocated_count == 0
        b1 = alloc.allocate()
        assert alloc.allocated_count == 1
        b2 = alloc.allocate()
        assert alloc.allocated_count == 2
        # Hold references so the free-list stays empty.
        assert b1 is not None and b2 is not None


class TestVideoBufferAllocatorRepr:
    """VideoBufferAllocator.__repr__ returns a valid string."""

    def test_repr(self):
        alloc = pydecklink.VideoBufferAllocator(size=4096)
        r = repr(alloc)
        assert isinstance(r, str)
        assert "VideoBufferAllocator" in r


class TestManagedBufferRepr:
    """ManagedBuffer.__repr__ returns a valid string."""

    def test_repr(self):
        alloc = pydecklink.VideoBufferAllocator(size=256)
        buf = alloc.allocate()
        r = repr(buf)
        assert isinstance(r, str)
        assert "ManagedBuffer" in r


class TestVideoBufferAllocatorProviderExists:
    """VideoBufferAllocatorProvider class is importable."""

    def test_class_exists(self):
        assert hasattr(pydecklink, "VideoBufferAllocatorProvider")

    def test_construct(self):
        provider = pydecklink.VideoBufferAllocatorProvider()
        assert provider is not None

    def test_get_allocator(self):
        """Provider returns an allocator for the given buffer parameters."""
        provider = pydecklink.VideoBufferAllocatorProvider()
        alloc = provider.get_allocator(
            buffer_size=4096,
            width=1920,
            height=1080,
            row_bytes=1920 * 4,
            pixel_format=pydecklink.PixelFormat.Format8BitBGRA,
        )
        assert alloc is not None
        assert alloc.size == 4096

    def test_get_allocator_cache_hit_does_not_leak_refs(self):
        """Repeated cache-hit calls must not grow the cached allocator's refcount."""
        provider = pydecklink.VideoBufferAllocatorProvider()
        args = dict(
            buffer_size=4096,
            width=1920,
            height=1080,
            row_bytes=1920 * 4,
            pixel_format=pydecklink.PixelFormat.Format8BitBGRA,
        )
        first = provider.get_allocator(**args)
        baseline = first._refcount  # cache(+1) + this handle(+1) == 2
        for _ in range(50):
            alloc = provider.get_allocator(**args)
            assert alloc is not None
        del alloc
        assert first._refcount == baseline, (
            f"refcount grew from {baseline} to {first._refcount} - leak"
        )


class TestDeviceAllocatorMethods:
    """Device has allocator-related methods."""

    def test_enable_video_input_with_allocator_exists(self):
        assert hasattr(pydecklink.Device, "enable_video_input_with_allocator")


class TestManagedBufferExists:
    """ManagedBuffer class exists and has expected attributes."""

    def test_class_exists(self):
        assert hasattr(pydecklink, "ManagedBuffer")

    def test_has_data_property(self):
        alloc = pydecklink.VideoBufferAllocator(size=256)
        buf = alloc.allocate()
        assert hasattr(buf, "data")

    def test_has_size_property(self):
        alloc = pydecklink.VideoBufferAllocator(size=256)
        buf = alloc.allocate()
        assert hasattr(buf, "size")
        assert buf.size == 256


class _LoggingAllocator:
    """Allocator/free helpers that log call counts.

    Simulates a GPU-pinned allocator where alloc/free are expensive and
    must not run at frame rate. Uses bytearrays as backing storage so
    the test does not require a real C allocator wrapper.
    """

    def __init__(self) -> None:
        self.alloc_calls: list[int] = []  # sizes
        self.free_calls: list[tuple[int, int]] = []  # (ptr, size)
        # Hold backing bytearrays so the memory stays valid until free().
        self._live: dict[int, bytearray] = {}

    def alloc(self, size: int) -> int:
        ba = bytearray(size)
        ptr = _ptr_of(ba)
        self._live[ptr] = ba
        self.alloc_calls.append(size)
        return ptr

    def free(self, ptr: int, size: int) -> None:
        self.free_calls.append((ptr, size))
        self._live.pop(ptr, None)


def _ptr_of(buf: bytearray) -> int:
    """Return the address of a bytearray's data, via numpy."""
    import numpy as np

    arr = np.frombuffer(buf, dtype=np.uint8)
    return int(arr.ctypes.data)


class TestRecycledCountProperty:
    """`recycled_count` exposes the number of free-list pops."""

    def test_recycled_count_starts_at_zero(self):
        alloc = pydecklink.VideoBufferAllocator(size=256)
        assert alloc.recycled_count == 0

    def test_recycled_count_unchanged_when_buffer_held(self):
        """A buffer that is still alive is not on the free-list."""
        alloc = pydecklink.VideoBufferAllocator(size=256)
        _buf = alloc.allocate()
        assert alloc.recycled_count == 0
        # Keep buf alive so this read is meaningful.
        assert _buf is not None


class TestBufferRecycling:
    """Buffers return to the allocator free-list on Release; the next
    AllocateVideoBuffer pops a recycled buffer instead of calling alloc."""

    def test_release_does_not_call_free_fn(self):
        """Dropping a buffer must not invoke the user free callable —
        the buffer goes onto the free-list."""
        log = _LoggingAllocator()
        alloc = pydecklink.VideoBufferAllocator(
            size=256, alloc=log.alloc, free=log.free
        )
        buf = alloc.allocate()
        assert len(log.alloc_calls) == 1
        del buf  # COM Release → free-list (NOT free_fn)
        assert len(log.free_calls) == 0

    def test_recycled_count_grows_on_release(self):
        """`recycled_count` advances each time a buffer hits the free-list."""
        alloc = pydecklink.VideoBufferAllocator(size=256)
        buf = alloc.allocate()
        del buf
        assert alloc.recycled_count == 1
        buf2 = alloc.allocate()
        # Popped from free-list; counter unchanged on pop.
        assert alloc.recycled_count == 1
        del buf2
        assert alloc.recycled_count == 2

    def test_allocate_reuses_freed_buffer(self):
        """The next allocate() after a release returns the recycled
        buffer — alloc_fn is NOT called again."""
        log = _LoggingAllocator()
        alloc = pydecklink.VideoBufferAllocator(
            size=256, alloc=log.alloc, free=log.free
        )
        buf1 = alloc.allocate()
        ptr1 = buf1.data.ctypes.data
        del buf1
        # First allocation invoked alloc once.
        assert len(log.alloc_calls) == 1

        buf2 = alloc.allocate()
        ptr2 = buf2.data.ctypes.data
        # Recycled — same backing memory, no new alloc call.
        assert ptr2 == ptr1
        assert len(log.alloc_calls) == 1
        assert len(log.free_calls) == 0

    def test_alloc_called_n_times_at_high_watermark(self):
        """alloc fires only when the free-list is empty. Holding N
        buffers concurrently forces N alloc calls."""
        log = _LoggingAllocator()
        alloc = pydecklink.VideoBufferAllocator(
            size=256, alloc=log.alloc, free=log.free
        )
        bufs = [alloc.allocate() for _ in range(4)]
        assert len(log.alloc_calls) == 4
        # Drop all → free-list grows to 4.
        del bufs
        assert alloc.recycled_count == 4
        assert len(log.free_calls) == 0
        # Re-acquire 4 — all from free-list, no new allocs.
        bufs2 = [alloc.allocate() for _ in range(4)]
        assert len(log.alloc_calls) == 4
        assert bufs2 is not None

    def test_free_called_n_times_at_shutdown(self):
        """When the allocator is destroyed, free fires once per buffer
        on the free-list (plus any still-live buffers when they release)."""
        log = _LoggingAllocator()
        alloc = pydecklink.VideoBufferAllocator(
            size=256, alloc=log.alloc, free=log.free
        )
        bufs = [alloc.allocate() for _ in range(3)]
        del bufs
        assert len(log.free_calls) == 0
        assert alloc.recycled_count == 3
        # Drop the last reference to the allocator.
        del alloc
        # All 3 buffers now drained from the free-list and freed.
        assert len(log.free_calls) == 3

    def test_capture_lifecycle_alloc_free_counts(self):
        """End-to-end verify (matches ROADMAP.md verify block):

        - alloc called N times at startup
        - free never called during capture (every Release recycles)
        - free called N times at shutdown
        - recycled_count confirms reuse
        """
        log = _LoggingAllocator()
        alloc = pydecklink.VideoBufferAllocator(
            size=2048, alloc=log.alloc, free=log.free
        )

        N = 4  # peak in-flight buffer count
        # Startup: peak fill — N distinct allocations.
        peak = [alloc.allocate() for _ in range(N)]
        assert len(log.alloc_calls) == N
        assert len(log.free_calls) == 0

        # Capture: cycle one buffer at a time many times. Each cycle is
        # release-then-allocate, so the free-list always has one entry.
        for _ in range(20):
            peak[0] = None  # release
            peak[0] = alloc.allocate()  # recycled

        # Steady-state during capture: alloc never called again, free
        # never called.
        assert len(log.alloc_calls) == N
        assert len(log.free_calls) == 0
        # recycled_count went up by 20 (one release per cycle).
        assert alloc.recycled_count == 20

        # Shutdown.
        peak.clear()
        del alloc
        assert len(log.free_calls) == N
