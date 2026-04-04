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
        """Track how many buffers have been allocated."""
        alloc = pydecklink.VideoBufferAllocator(size=4096)
        assert alloc.allocated_count == 0
        alloc.allocate()
        assert alloc.allocated_count == 1
        alloc.allocate()
        assert alloc.allocated_count == 2


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
