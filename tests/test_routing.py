"""Tests for routing helper functions (no hardware required)."""

import pytest

from pyntv2 import (
    Channel,
    InputSource,
    InputXpt,
    OutputDest,
    OutputXpt,
    PixelFormat,
    route_capture,
    route_playout,
)


class TestRouteCapture:
    def test_sdi_ycbcr_no_csc(self):
        """SDI input + YCbCr pixel format: direct connection, no CSC."""
        routes = route_capture(InputSource.SDI1, Channel.CH1, PixelFormat.FBF_10BIT_YCBCR)
        assert routes == {InputXpt.FrameBuffer1Input: OutputXpt.SDIIn1}

    def test_sdi_rgb_with_csc(self):
        """SDI input + RGB pixel format: route through CSC."""
        routes = route_capture(InputSource.SDI1, Channel.CH1, PixelFormat.FBF_ARGB)
        assert routes == {
            InputXpt.CSC1VidInput: OutputXpt.SDIIn1,
            InputXpt.FrameBuffer1Input: OutputXpt.CSC1VidRGB,
        }

    def test_sdi2_ch2_rgb(self):
        """SDI2 -> CH2 with RGB: uses CSC2."""
        routes = route_capture(InputSource.SDI2, Channel.CH2, PixelFormat.FBF_RGBA)
        assert routes == {
            InputXpt.CSC2VidInput: OutputXpt.SDIIn2,
            InputXpt.FrameBuffer2Input: OutputXpt.CSC2VidRGB,
        }

    def test_hdmi_ycbcr_no_csc(self):
        """HDMI input + YCbCr: direct connection (HDMI not in _YCBCR_INPUT_SOURCES)."""
        routes = route_capture(InputSource.HDMI1, Channel.CH1, PixelFormat.FBF_8BIT_YCBCR)
        assert routes == {InputXpt.FrameBuffer1Input: OutputXpt.HDMIIn1}

    def test_hdmi_rgb_no_csc(self):
        """HDMI input + RGB: direct connection (HDMI assumed to handle RGB natively)."""
        routes = route_capture(InputSource.HDMI1, Channel.CH1, PixelFormat.FBF_ARGB)
        assert routes == {InputXpt.FrameBuffer1Input: OutputXpt.HDMIIn1}


class TestRouteCaptureAllChannels:
    """Verify route_capture succeeds for every valid Channel (CH1-CH8)."""

    @pytest.mark.parametrize("channel", [
        Channel.CH1, Channel.CH2, Channel.CH3, Channel.CH4,
        Channel.CH5, Channel.CH6, Channel.CH7, Channel.CH8,
    ])
    def test_all_channels_ycbcr(self, channel):
        routes = route_capture(InputSource.SDI1, channel, PixelFormat.FBF_10BIT_YCBCR)
        assert len(routes) == 1

    @pytest.mark.parametrize("channel", [
        Channel.CH1, Channel.CH2, Channel.CH3, Channel.CH4,
        Channel.CH5, Channel.CH6, Channel.CH7, Channel.CH8,
    ])
    def test_all_channels_rgb(self, channel):
        routes = route_capture(InputSource.SDI1, channel, PixelFormat.FBF_ARGB)
        assert len(routes) == 2  # CSC path


class TestRouteCaptureNegative:
    """Verify unsupported inputs raise ValueError."""

    def test_analog_source_raises(self):
        with pytest.raises(ValueError, match="unsupported source"):
            route_capture(InputSource.ANALOG1, Channel.CH1, PixelFormat.FBF_8BIT_YCBCR)

    def test_invalid_source_raises(self):
        with pytest.raises(ValueError, match="unsupported source"):
            route_capture(InputSource.INVALID, Channel.CH1, PixelFormat.FBF_8BIT_YCBCR)

    def test_invalid_channel_raises(self):
        with pytest.raises(ValueError, match="unsupported channel"):
            route_capture(InputSource.SDI1, Channel.INVALID, PixelFormat.FBF_8BIT_YCBCR)


class TestRoutePlayout:
    def test_sdi_ycbcr_no_csc(self):
        """YCbCr pixel format -> SDI: direct connection."""
        routes = route_playout(Channel.CH1, OutputDest.SDI1, PixelFormat.FBF_10BIT_YCBCR)
        assert routes == {InputXpt.SDIOut1Input: OutputXpt.FrameBuffer1YUV}

    def test_sdi_rgb_with_csc(self):
        """RGB pixel format -> SDI: route through CSC to convert to YCbCr."""
        routes = route_playout(Channel.CH1, OutputDest.SDI1, PixelFormat.FBF_ARGB)
        assert routes == {
            InputXpt.CSC1VidInput: OutputXpt.FrameBuffer1RGB,
            InputXpt.SDIOut1Input: OutputXpt.CSC1VidYUV,
        }

    def test_sdi3_ch3_rgb(self):
        """CH3 -> SDI3 with RGB: uses CSC3."""
        routes = route_playout(Channel.CH3, OutputDest.SDI3, PixelFormat.FBF_10BIT_RGB)
        assert routes == {
            InputXpt.CSC3VidInput: OutputXpt.FrameBuffer3RGB,
            InputXpt.SDIOut3Input: OutputXpt.CSC3VidYUV,
        }

    def test_hdmi_rgb_no_csc(self):
        """RGB -> HDMI: direct connection (HDMI carries RGB natively)."""
        routes = route_playout(Channel.CH1, OutputDest.HDMI1, PixelFormat.FBF_ARGB)
        assert routes == {InputXpt.HDMIOutQ1Input: OutputXpt.FrameBuffer1RGB}

    def test_hdmi_ycbcr_no_csc(self):
        """YCbCr -> HDMI: direct connection."""
        routes = route_playout(Channel.CH1, OutputDest.HDMI1, PixelFormat.FBF_8BIT_YCBCR)
        assert routes == {InputXpt.HDMIOutQ1Input: OutputXpt.FrameBuffer1YUV}


class TestRoutePlayoutAllSDIOutputs:
    """Verify all 8 SDI output destinations produce valid routes."""

    _SDI_OUTPUTS = [
        OutputDest.SDI1, OutputDest.SDI2, OutputDest.SDI3, OutputDest.SDI4,
        OutputDest.SDI5, OutputDest.SDI6, OutputDest.SDI7, OutputDest.SDI8,
    ]

    @pytest.mark.parametrize("output", _SDI_OUTPUTS)
    def test_sdi_ycbcr(self, output):
        routes = route_playout(Channel.CH1, output, PixelFormat.FBF_10BIT_YCBCR)
        assert len(routes) == 1

    @pytest.mark.parametrize("output", _SDI_OUTPUTS)
    def test_sdi_rgb(self, output):
        routes = route_playout(Channel.CH1, output, PixelFormat.FBF_ARGB)
        assert len(routes) == 2  # CSC path


class TestRoutePlayoutAllChannels:
    """Verify route_playout succeeds for every valid Channel (CH1-CH8)."""

    @pytest.mark.parametrize("channel", [
        Channel.CH1, Channel.CH2, Channel.CH3, Channel.CH4,
        Channel.CH5, Channel.CH6, Channel.CH7, Channel.CH8,
    ])
    def test_all_channels_ycbcr(self, channel):
        routes = route_playout(channel, OutputDest.SDI1, PixelFormat.FBF_10BIT_YCBCR)
        assert len(routes) == 1

    @pytest.mark.parametrize("channel", [
        Channel.CH1, Channel.CH2, Channel.CH3, Channel.CH4,
        Channel.CH5, Channel.CH6, Channel.CH7, Channel.CH8,
    ])
    def test_all_channels_rgb(self, channel):
        routes = route_playout(channel, OutputDest.SDI1, PixelFormat.FBF_ARGB)
        assert len(routes) == 2  # CSC path


class TestRoutePlayoutNegative:
    """Verify unsupported outputs raise ValueError."""

    def test_analog_output_raises(self):
        with pytest.raises(ValueError, match="unsupported output"):
            route_playout(Channel.CH1, OutputDest.ANALOG1, PixelFormat.FBF_8BIT_YCBCR)

    def test_invalid_output_raises(self):
        with pytest.raises(ValueError, match="unsupported output"):
            route_playout(Channel.CH1, OutputDest.INVALID, PixelFormat.FBF_8BIT_YCBCR)

    def test_invalid_channel_raises(self):
        with pytest.raises(ValueError, match="unsupported channel"):
            route_playout(Channel.INVALID, OutputDest.SDI1, PixelFormat.FBF_8BIT_YCBCR)
