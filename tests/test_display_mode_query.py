"""Tests for display-mode-query bindings (§5.2).

Enum and type existence tests run without hardware.
Device method tests require hardware and are marked accordingly.
"""

import pytest

import pydecklink

pytestmark = pytest.mark.skipif(
    not getattr(pydecklink, "HAS_SDK", False),
    reason="Built without DeckLink SDK headers",
)


# --- Enum existence tests (no hardware) ---


class TestSupportedVideoModeFlags:
    """BMDSupportedVideoModeFlags enum values."""

    def test_enum_exists(self):
        assert hasattr(pydecklink, "SupportedVideoModeFlag")

    def test_default(self):
        assert pydecklink.SupportedVideoModeFlag.Default.value == 0

    def test_keying(self):
        assert pydecklink.SupportedVideoModeFlag.Keying.value == 1 << 0

    def test_dual_stream_3d(self):
        assert pydecklink.SupportedVideoModeFlag.DualStream3D.value == 1 << 1

    def test_sdi_single_link(self):
        assert pydecklink.SupportedVideoModeFlag.SDISingleLink.value == 1 << 2

    def test_sdi_dual_link(self):
        assert pydecklink.SupportedVideoModeFlag.SDIDualLink.value == 1 << 3


class TestVideoOutputConversionMode:
    """BMDVideoOutputConversionMode enum values."""

    def test_enum_exists(self):
        assert hasattr(pydecklink, "VideoOutputConversionMode")

    def test_none(self):
        assert pydecklink.VideoOutputConversionMode.NoConversion.value == 0x6E6F6E65


class TestDisplayModeInfo:
    """DisplayModeInfo struct is accessible and has expected fields."""

    def test_class_exists(self):
        assert hasattr(pydecklink, "DisplayModeInfo")


# --- Device method tests (require hardware) ---


def _has_decklink():
    try:
        return pydecklink.device_count() > 0
    except RuntimeError:
        return False


needs_hardware = pytest.mark.skipif(
    not _has_decklink(),
    reason="No DeckLink hardware available",
)


@needs_hardware
class TestGetDisplayMode:
    """device.get_display_mode() returns DisplayModeInfo."""

    def test_returns_display_mode_info(self):
        dev = pydecklink.Device(0)
        info = dev.get_display_mode(pydecklink.DisplayMode.HD1080p25)
        assert isinstance(info, pydecklink.DisplayModeInfo)

    def test_width_height(self):
        dev = pydecklink.Device(0)
        info = dev.get_display_mode(pydecklink.DisplayMode.HD1080p25)
        assert info.width == 1920
        assert info.height == 1080

    def test_frame_rate_tuple(self):
        dev = pydecklink.Device(0)
        info = dev.get_display_mode(pydecklink.DisplayMode.HD1080p25)
        assert isinstance(info.frame_rate, tuple)
        assert len(info.frame_rate) == 2
        duration, timescale = info.frame_rate
        assert timescale / duration == pytest.approx(25.0)

    def test_name_is_string(self):
        dev = pydecklink.Device(0)
        info = dev.get_display_mode(pydecklink.DisplayMode.HD1080p25)
        assert isinstance(info.name, str)
        assert len(info.name) > 0

    def test_mode_enum(self):
        dev = pydecklink.Device(0)
        info = dev.get_display_mode(pydecklink.DisplayMode.HD1080p25)
        assert info.mode == pydecklink.DisplayMode.HD1080p25

    def test_field_dominance(self):
        dev = pydecklink.Device(0)
        info = dev.get_display_mode(pydecklink.DisplayMode.HD1080p25)
        assert info.field_dominance == pydecklink.FieldDominance.ProgressiveFrame


@needs_hardware
class TestListOutputModes:
    """device.list_output_modes() returns all supported display modes."""

    def test_returns_list(self):
        dev = pydecklink.Device(0)
        modes = dev.list_output_modes()
        assert isinstance(modes, list)
        assert len(modes) > 0

    def test_elements_are_display_mode_info(self):
        dev = pydecklink.Device(0)
        modes = dev.list_output_modes()
        for m in modes:
            assert isinstance(m, pydecklink.DisplayModeInfo)

    def test_each_mode_has_valid_dimensions(self):
        dev = pydecklink.Device(0)
        modes = dev.list_output_modes()
        for m in modes:
            assert m.width > 0
            assert m.height > 0

    def test_each_mode_has_frame_rate(self):
        dev = pydecklink.Device(0)
        modes = dev.list_output_modes()
        for m in modes:
            duration, timescale = m.frame_rate
            assert duration > 0
            assert timescale > 0


@needs_hardware
class TestDoesSupportVideoMode:
    """device.does_support_video_mode() validates mode/format combos."""

    def test_returns_bool(self):
        dev = pydecklink.Device(0)
        result = dev.does_support_video_mode(
            pydecklink.VideoConnection.Unspecified,
            pydecklink.DisplayMode.HD1080p25,
            pydecklink.PixelFormat.Format8BitYUV,
        )
        assert isinstance(result, bool)

    def test_common_mode_supported(self):
        dev = pydecklink.Device(0)
        result = dev.does_support_video_mode(
            pydecklink.VideoConnection.Unspecified,
            pydecklink.DisplayMode.HD1080p25,
            pydecklink.PixelFormat.Format8BitYUV,
        )
        # Most DeckLink cards support 1080p25 8-bit YUV.
        assert result is True
