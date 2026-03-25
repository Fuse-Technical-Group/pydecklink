"""Tests for pydecklink output bindings (no hardware required)."""

import pytest

import pydecklink

pytestmark = pytest.mark.skipif(
    not getattr(pydecklink, "HAS_SDK", False),
    reason="Built without DeckLink SDK headers",
)


class TestOutputStatusExists:
    """OutputStatus class is importable and has expected attributes."""

    def test_output_status_class_exists(self):
        assert hasattr(pydecklink, "OutputStatus")

    def test_output_status_fields(self):
        status = pydecklink.OutputStatus()
        assert hasattr(status, "completed")
        assert hasattr(status, "late")
        assert hasattr(status, "dropped")
        assert hasattr(status, "flushed")
        assert hasattr(status, "underrun")

    def test_output_status_defaults(self):
        status = pydecklink.OutputStatus()
        assert status.completed == 0
        assert status.late == 0
        assert status.dropped == 0
        assert status.flushed == 0
        assert status.underrun is False


class TestMutableFrameExists:
    """MutableFrame class is importable."""

    def test_mutable_frame_class_exists(self):
        assert hasattr(pydecklink, "MutableFrame")


class TestDeviceOutputMethods:
    """Device has output-related methods."""

    def test_enable_video_output_exists(self):
        assert hasattr(pydecklink.Device, "enable_video_output")

    def test_disable_video_output_exists(self):
        assert hasattr(pydecklink.Device, "disable_video_output")

    def test_display_frame_sync_exists(self):
        assert hasattr(pydecklink.Device, "display_frame_sync")

    def test_create_video_frame_exists(self):
        assert hasattr(pydecklink.Device, "create_video_frame")

    def test_schedule_frame_exists(self):
        assert hasattr(pydecklink.Device, "schedule_frame")

    def test_start_scheduled_playback_exists(self):
        assert hasattr(pydecklink.Device, "start_scheduled_playback")

    def test_stop_scheduled_playback_exists(self):
        assert hasattr(pydecklink.Device, "stop_scheduled_playback")

    def test_is_scheduled_playback_running_exists(self):
        assert hasattr(pydecklink.Device, "is_scheduled_playback_running")

    def test_output_status_exists(self):
        assert hasattr(pydecklink.Device, "output_status")


class TestDeviceConfigMethods:
    """Device has configuration methods."""

    def test_set_config_flag_exists(self):
        assert hasattr(pydecklink.Device, "set_config_flag")

    def test_get_config_flag_exists(self):
        assert hasattr(pydecklink.Device, "get_config_flag")

    def test_set_config_int_exists(self):
        assert hasattr(pydecklink.Device, "set_config_int")

    def test_get_config_int_exists(self):
        assert hasattr(pydecklink.Device, "get_config_int")
