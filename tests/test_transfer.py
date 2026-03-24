"""Tests for Transfer and Status class bindings (no hardware required)."""

import numpy as np
import pytest

from pyntv2 import Status, Transfer


class TestTransferConstruction:
    def test_default_constructor(self):
        t = Transfer()
        assert t is not None

    def test_set_video_buffer_numpy(self):
        t = Transfer()
        buf = np.zeros(1920 * 1080 * 4, dtype=np.uint8)
        t.set_video_buffer(buf)

    def test_captured_audio_byte_count(self):
        t = Transfer()
        assert t.captured_audio_byte_count == 0

    def test_captured_anc_byte_count(self):
        t = Transfer()
        assert t.captured_anc_byte_count == 0

    def test_transferred_frame(self):
        t = Transfer()
        assert isinstance(t.transferred_frame, int)


class TestBufferValidation:
    """Verify set_video_buffer rejects non-contiguous buffers."""

    def test_non_contiguous_slice_raises(self):
        arr = np.zeros((10, 10), dtype=np.uint8)
        sliced = arr[:, ::2]  # non-contiguous
        assert not sliced.flags["C_CONTIGUOUS"]
        t = Transfer()
        with pytest.raises(ValueError, match="C-contiguous"):
            t.set_video_buffer(sliced)

    def test_transposed_raises(self):
        arr = np.zeros((4, 8), dtype=np.uint8)
        transposed = arr.T  # Fortran-contiguous, not C-contiguous
        assert not transposed.flags["C_CONTIGUOUS"]
        t = Transfer()
        with pytest.raises(ValueError, match="C-contiguous"):
            t.set_video_buffer(transposed)

    def test_contiguous_copy_succeeds(self):
        arr = np.zeros((10, 10), dtype=np.uint8)
        sliced = np.ascontiguousarray(arr[:, ::2])
        t = Transfer()
        t.set_video_buffer(sliced)  # should not raise


class TestStatusProperties:
    """Status is not user-constructable, but we verify the class exists
    and has the expected property descriptors."""

    def test_class_exists(self):
        assert Status is not None

    def test_property_descriptors(self):
        props = [
            "is_running",
            "is_stopped",
            "has_available_input_frame",
            "can_accept_more_output_frames",
            "dropped_frame_count",
            "buffer_level",
            "with_audio",
            "with_custom_anc",
        ]
        for prop in props:
            assert hasattr(Status, prop), f"Status missing property: {prop}"
