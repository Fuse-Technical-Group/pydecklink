"""Tests for pydecklink input bindings (no hardware required)."""

import pytest

import pydecklink

pytestmark = pytest.mark.skipif(
    not getattr(pydecklink, "HAS_SDK", False),
    reason="Built without DeckLink SDK headers",
)


class TestCaptureFrameExists:
    """CaptureFrame class is importable and has expected attributes."""

    def test_capture_frame_class_exists(self):
        assert hasattr(pydecklink, "CaptureFrame")


class TestDeviceInputMethods:
    """Device has input-related methods."""

    def test_enable_video_input_exists(self):
        assert hasattr(pydecklink.Device, "enable_video_input")

    def test_disable_video_input_exists(self):
        assert hasattr(pydecklink.Device, "disable_video_input")

    def test_start_streams_exists(self):
        assert hasattr(pydecklink.Device, "start_streams")

    def test_stop_streams_exists(self):
        assert hasattr(pydecklink.Device, "stop_streams")

    def test_pop_capture_frame_exists(self):
        assert hasattr(pydecklink.Device, "pop_capture_frame")

    def test_current_input_format_exists(self):
        assert hasattr(pydecklink.Device, "current_input_format")


class TestCaptureFrameMetadata:
    """Captured frames expose the colorimetry and HDR metadata that arrived."""

    @pytest.mark.parametrize("frame_cls", ["CaptureFrame", "CaptureFrameRef"])
    @pytest.mark.parametrize("prop", ["flags", "colorspace", "eotf", "hdr_metadata"])
    def test_metadata_property_exists(self, frame_cls, prop):
        assert hasattr(getattr(pydecklink, frame_cls), prop)
