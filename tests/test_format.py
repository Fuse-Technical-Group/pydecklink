"""Tests for format metadata helper functions (no hardware required)."""

import pytest

from pyntv2 import (
    PixelFormat,
    VideoFormat,
    get_format_fps,
    get_format_height,
    get_format_width,
    get_frame_bytes,
)


class TestFormatMetadata:
    def test_1080i_5994_width(self):
        assert get_format_width(VideoFormat.FORMAT_1080i_5994) == 1920

    def test_1080i_5994_height(self):
        assert get_format_height(VideoFormat.FORMAT_1080i_5994) == 1080

    def test_1080i_5994_fps(self):
        fps = get_format_fps(VideoFormat.FORMAT_1080i_5994)
        assert abs(fps - 29.97) < 0.01

    def test_invalid_format_width(self):
        with pytest.raises(ValueError):
            get_format_width(VideoFormat.FORMAT_UNKNOWN)

    def test_invalid_format_height(self):
        with pytest.raises(ValueError):
            get_format_height(VideoFormat.FORMAT_UNKNOWN)


class TestGetFrameBytes:
    def test_1080i_10bit_ycbcr(self):
        """10-bit YCbCr 1080i: 1920 * 1080 * 8/3 rounded to ULWord."""
        result = get_frame_bytes(
            VideoFormat.FORMAT_1080i_5994, PixelFormat.FBF_10BIT_YCBCR
        )
        assert result > 0

    def test_1080p_8bit_ycbcr(self):
        result = get_frame_bytes(
            VideoFormat.FORMAT_1080p_2398, PixelFormat.FBF_8BIT_YCBCR
        )
        assert result > 0

    def test_1080p_argb(self):
        result = get_frame_bytes(VideoFormat.FORMAT_1080p_2398, PixelFormat.FBF_ARGB)
        # 4 bytes per pixel
        assert result == 1920 * 1080 * 4

    def test_720p_8bit_ycbcr(self):
        result = get_frame_bytes(
            VideoFormat.FORMAT_720p_5994, PixelFormat.FBF_8BIT_YCBCR
        )
        assert result > 0

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            get_frame_bytes(VideoFormat.FORMAT_UNKNOWN, PixelFormat.FBF_8BIT_YCBCR)
