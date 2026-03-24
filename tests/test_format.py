"""Tests for format metadata helper functions (no hardware required)."""

import pytest

from pyntv2 import VideoFormat, get_format_fps, get_format_height, get_format_width


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
