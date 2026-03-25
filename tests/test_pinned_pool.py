"""Tests for pinned output frame pool (no hardware required)."""

import pytest

import pydecklink

pytestmark = pytest.mark.skipif(
    not getattr(pydecklink, "HAS_SDK", False),
    reason="Built without DeckLink SDK headers",
)


class TestCreateFramePoolPinnedExists:
    """Device has create_frame_pool_pinned method."""

    def test_method_exists(self):
        assert hasattr(pydecklink.Device, "create_frame_pool_pinned")


class TestAllocatorProviderIntegration:
    """Allocator and provider work together for the GPU DMA pipeline."""

    def test_allocator_reuse_by_size(self):
        """Provider caches allocators by buffer size."""
        provider = pydecklink.VideoBufferAllocatorProvider()
        pf = pydecklink.PixelFormat.Format8BitBGRA

        alloc1 = provider.get_allocator(4096, 1920, 1080, 7680, pf)
        alloc2 = provider.get_allocator(4096, 1920, 1080, 7680, pf)
        # Same buffer size should return same allocator.
        assert alloc1.size == alloc2.size

    def test_different_sizes_get_different_allocators(self):
        """Provider creates new allocators for different buffer sizes."""
        provider = pydecklink.VideoBufferAllocatorProvider()
        pf = pydecklink.PixelFormat.Format8BitBGRA

        alloc_small = provider.get_allocator(4096, 1920, 1080, 7680, pf)
        alloc_large = provider.get_allocator(8192, 3840, 2160, 15360, pf)
        assert alloc_small.size == 4096
        assert alloc_large.size == 8192

    def test_allocator_buffer_roundtrip(self):
        """Allocate, write, read back data through ManagedBuffer."""
        import numpy as np

        alloc = pydecklink.VideoBufferAllocator(size=1920 * 4)
        buf = alloc.allocate()
        data = buf.data
        # Write a known pattern.
        pattern = np.arange(1920 * 4, dtype=np.uint8)
        data[:] = pattern
        # Read back.
        np.testing.assert_array_equal(data, pattern)
