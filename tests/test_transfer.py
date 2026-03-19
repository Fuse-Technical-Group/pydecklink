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
