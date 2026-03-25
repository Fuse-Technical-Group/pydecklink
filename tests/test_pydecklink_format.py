"""Tests for pydecklink format metadata helpers."""

import pytest

import pydecklink

pytestmark = pytest.mark.skipif(
    not getattr(pydecklink, "HAS_SDK", False),
    reason="Built without DeckLink SDK headers",
)


class TestGetModeWidth:
    """get_mode_width returns correct widths for known modes."""

    def test_function_exists(self):
        assert callable(pydecklink.get_mode_width)

    def test_hd1080(self):
        assert pydecklink.get_mode_width(pydecklink.DisplayMode.HD1080p25) == 1920

    def test_hd720(self):
        assert pydecklink.get_mode_width(pydecklink.DisplayMode.HD720p50) == 1280

    def test_4k(self):
        assert pydecklink.get_mode_width(pydecklink.DisplayMode.Mode4K2160p25) == 3840

    def test_ntsc(self):
        assert pydecklink.get_mode_width(pydecklink.DisplayMode.NTSC) == 720

    def test_pal(self):
        assert pydecklink.get_mode_width(pydecklink.DisplayMode.PAL) == 720


class TestGetModeHeight:
    """get_mode_height returns correct heights for known modes."""

    def test_function_exists(self):
        assert callable(pydecklink.get_mode_height)

    def test_hd1080(self):
        assert pydecklink.get_mode_height(pydecklink.DisplayMode.HD1080p25) == 1080

    def test_hd720(self):
        assert pydecklink.get_mode_height(pydecklink.DisplayMode.HD720p50) == 720

    def test_4k(self):
        assert pydecklink.get_mode_height(pydecklink.DisplayMode.Mode4K2160p25) == 2160

    def test_ntsc(self):
        assert pydecklink.get_mode_height(pydecklink.DisplayMode.NTSC) == 486

    def test_pal(self):
        assert pydecklink.get_mode_height(pydecklink.DisplayMode.PAL) == 576


class TestGetModeFps:
    """get_mode_fps returns approximate frame rate."""

    def test_function_exists(self):
        assert callable(pydecklink.get_mode_fps)

    def test_hd1080p25(self):
        fps = pydecklink.get_mode_fps(pydecklink.DisplayMode.HD1080p25)
        assert abs(fps - 25.0) < 0.01

    def test_hd1080p2997(self):
        fps = pydecklink.get_mode_fps(pydecklink.DisplayMode.HD1080p2997)
        assert abs(fps - 29.97) < 0.01

    def test_pal(self):
        fps = pydecklink.get_mode_fps(pydecklink.DisplayMode.PAL)
        assert abs(fps - 25.0) < 0.01


class TestGetModeFrameDuration:
    """get_mode_frame_duration returns (duration, timescale) tuples."""

    def test_function_exists(self):
        assert callable(pydecklink.get_mode_frame_duration)

    def test_5994_mode(self):
        duration, timescale = pydecklink.get_mode_frame_duration(
            pydecklink.DisplayMode.Mode4K2160p5994,
        )
        assert duration == 1001
        assert timescale == 60000

    def test_25_mode(self):
        duration, timescale = pydecklink.get_mode_frame_duration(
            pydecklink.DisplayMode.HD1080p25,
        )
        assert duration == 1000
        assert timescale == 25000

    def test_pal(self):
        duration, timescale = pydecklink.get_mode_frame_duration(
            pydecklink.DisplayMode.PAL,
        )
        assert duration == 1000
        assert timescale == 25000

    def test_ntsc(self):
        duration, timescale = pydecklink.get_mode_frame_duration(
            pydecklink.DisplayMode.NTSC,
        )
        assert duration == 1001
        assert timescale == 30000

    def test_consistent_with_fps(self):
        """timescale/duration should equal get_mode_fps."""
        mode = pydecklink.DisplayMode.HD1080p5994
        duration, timescale = pydecklink.get_mode_frame_duration(mode)
        fps = pydecklink.get_mode_fps(mode)
        assert abs(timescale / duration - fps) < 0.001


class TestGetFrameBytes:
    """get_frame_bytes returns correct byte counts."""

    def test_function_exists(self):
        assert callable(pydecklink.get_frame_bytes)

    def test_hd1080_8bit_yuv(self):
        # 1920 * 1080 * 2 (UYVY = 2 bytes/pixel)
        size = pydecklink.get_frame_bytes(
            pydecklink.DisplayMode.HD1080p25,
            pydecklink.PixelFormat.Format8BitYUV,
        )
        assert size == 1920 * 1080 * 2

    def test_hd1080_8bit_bgra(self):
        # 1920 * 1080 * 4 (BGRA = 4 bytes/pixel)
        size = pydecklink.get_frame_bytes(
            pydecklink.DisplayMode.HD1080p25,
            pydecklink.PixelFormat.Format8BitBGRA,
        )
        assert size == 1920 * 1080 * 4
