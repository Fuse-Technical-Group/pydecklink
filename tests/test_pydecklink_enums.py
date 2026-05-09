"""Tests for pydecklink enum bindings."""

import pytest

import pydecklink

pytestmark = pytest.mark.skipif(
    not getattr(pydecklink, "HAS_SDK", False),
    reason="Built without DeckLink SDK headers",
)


class TestDisplayMode:
    """BMDDisplayMode enum values exist and are usable."""

    def test_enum_exists(self):
        assert hasattr(pydecklink, "DisplayMode")

    def test_sd_modes(self):
        assert pydecklink.DisplayMode.NTSC.value == 0x6E747363
        assert pydecklink.DisplayMode.PAL.value == 0x70616C20

    def test_hd_1080_modes(self):
        assert pydecklink.DisplayMode.HD1080p2398.value == 0x32337073
        assert pydecklink.DisplayMode.HD1080p25.value == 0x48703235
        assert pydecklink.DisplayMode.HD1080i50.value == 0x48693530

    def test_hd_720_modes(self):
        assert pydecklink.DisplayMode.HD720p50.value == 0x68703530

    def test_4k_modes(self):
        assert pydecklink.DisplayMode.Mode4K2160p25.value == 0x346B3235

    def test_8k_modes(self):
        assert pydecklink.DisplayMode.Mode8K4320p25.value == 0x386B3235

    def test_unknown_mode(self):
        assert pydecklink.DisplayMode.Unknown.value == 0x69756E6B

    def test_repr_readable(self):
        r = repr(pydecklink.DisplayMode.HD1080p25)
        assert "HD1080p25" in r

    def test_comparison(self):
        a = pydecklink.DisplayMode.HD1080p25
        b = pydecklink.DisplayMode.HD1080p25
        assert a == b
        assert a != pydecklink.DisplayMode.PAL


class TestPixelFormat:
    """BMDPixelFormat enum values exist and are usable."""

    def test_enum_exists(self):
        assert hasattr(pydecklink, "PixelFormat")

    def test_yuv_formats(self):
        assert pydecklink.PixelFormat.Format8BitYUV.value == 0x32767579
        assert pydecklink.PixelFormat.Format10BitYUV.value == 0x76323130

    def test_rgb_formats(self):
        assert pydecklink.PixelFormat.Format8BitARGB.value == 32
        assert pydecklink.PixelFormat.Format8BitBGRA.value == 0x42475241
        assert pydecklink.PixelFormat.Format10BitRGB.value == 0x72323130

    def test_repr_readable(self):
        r = repr(pydecklink.PixelFormat.Format8BitYUV)
        assert "Format8BitYUV" in r


class TestFieldDominance:
    """BMDFieldDominance enum values."""

    def test_enum_exists(self):
        assert hasattr(pydecklink, "FieldDominance")

    def test_values(self):
        assert pydecklink.FieldDominance.Unknown.value == 0
        assert pydecklink.FieldDominance.LowerFieldFirst.value == 0x6C6F7772
        assert pydecklink.FieldDominance.UpperFieldFirst.value == 0x75707072
        assert pydecklink.FieldDominance.ProgressiveFrame.value == 0x70726F67
        assert pydecklink.FieldDominance.ProgressiveSegmentedFrame.value == 0x70736620


class TestVideoInputFlags:
    """BMDVideoInputFlags enum values."""

    def test_enum_exists(self):
        assert hasattr(pydecklink, "VideoInputFlag")

    def test_values(self):
        assert pydecklink.VideoInputFlag.Default.value == 0
        assert pydecklink.VideoInputFlag.EnableFormatDetection.value == 1 << 0


class TestVideoOutputFlags:
    """BMDVideoOutputFlags enum values."""

    def test_enum_exists(self):
        assert hasattr(pydecklink, "VideoOutputFlag")

    def test_values(self):
        assert pydecklink.VideoOutputFlag.Default.value == 0
        assert pydecklink.VideoOutputFlag.VANC.value == 1 << 0
        assert pydecklink.VideoOutputFlag.RP188.value == 1 << 2


class TestFrameFlags:
    """BMDFrameFlags enum values."""

    def test_enum_exists(self):
        assert hasattr(pydecklink, "FrameFlag")

    def test_values(self):
        assert pydecklink.FrameFlag.Default.value == 0
        assert pydecklink.FrameFlag.FlipVertical.value == 1 << 0
        # 1 << 31 = 0x80000000 which is -2147483648 as signed int32
        assert pydecklink.FrameFlag.HasNoInputSource.value == -2147483648


class TestDetectedVideoInputFormatFlags:
    """BMDDetectedVideoInputFormatFlags enum values."""

    def test_enum_exists(self):
        assert hasattr(pydecklink, "DetectedInputFormat")

    def test_values(self):
        assert pydecklink.DetectedInputFormat.YCbCr422.value == 1 << 0
        assert pydecklink.DetectedInputFormat.RGB444.value == 1 << 1
        assert pydecklink.DetectedInputFormat.Depth8Bit.value == 1 << 5
        assert pydecklink.DetectedInputFormat.Depth10Bit.value == 1 << 4
        assert pydecklink.DetectedInputFormat.Depth12Bit.value == 1 << 3


class TestOutputFrameCompletionResult:
    """BMDOutputFrameCompletionResult enum values."""

    def test_enum_exists(self):
        assert hasattr(pydecklink, "OutputFrameResult")

    def test_values(self):
        assert pydecklink.OutputFrameResult.Completed.value == 0
        assert pydecklink.OutputFrameResult.DisplayedLate.value == 1
        assert pydecklink.OutputFrameResult.Dropped.value == 2
        assert pydecklink.OutputFrameResult.Flushed.value == 3


class TestVideoIOSupport:
    """BMDVideoIOSupport enum values."""

    def test_enum_exists(self):
        assert hasattr(pydecklink, "VideoIOSupport")

    def test_values(self):
        assert pydecklink.VideoIOSupport.Capture.value == 1 << 0
        assert pydecklink.VideoIOSupport.Playback.value == 1 << 1


class TestConfigurationID:
    """BMDDeckLinkConfigurationID enum values (subset)."""

    def test_enum_exists(self):
        assert hasattr(pydecklink, "ConfigurationID")

    def test_flag_values(self):
        assert pydecklink.ConfigurationID.Config444SDIVideoOutput.value == 0x3434346F

    def test_integer_values(self):
        cfg = pydecklink.ConfigurationID
        assert cfg.ConfigVideoOutputConnection.value == 0x766F636E

    def test_playback_group_value(self):
        # bmdDeckLinkConfigPlaybackGroup ('plgr') — int config used to
        # assign outputs to a shared sync group.
        # §spec:synchronized-output-fanout.
        assert pydecklink.ConfigurationID.PlaybackGroup.value == 0x706C6772


class TestAttributeID:
    """BMDDeckLinkAttributeID enum values (subset)."""

    def test_enum_exists(self):
        assert hasattr(pydecklink, "AttributeID")

    def test_flag_values(self):
        assert pydecklink.AttributeID.SupportsInputFormatDetection.value == 0x696E6664
        assert pydecklink.AttributeID.SupportsHDRMetadata.value == 0x6864726D

    def test_integer_values(self):
        assert pydecklink.AttributeID.VideoIOSupport.value == 0x76696F73
        assert pydecklink.AttributeID.MinimumPrerollFrames.value == 0x6D707266
        assert pydecklink.AttributeID.Duplex.value == 0x64757078

    def test_supports_synchronize_to_playback_group_value(self):
        # BMDDeckLinkSupportsSynchronizeToPlaybackGroup ('stpg') — flag
        # capability queried before assigning a device to a sync group.
        # §spec:synchronized-output-fanout.
        assert (
            pydecklink.AttributeID.SupportsSynchronizeToPlaybackGroup.value
            == 0x73747067
        )
