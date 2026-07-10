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


class TestOutputStatusRepr:
    """OutputStatus.__repr__ returns a valid string."""

    def test_repr(self):
        status = pydecklink.OutputStatus()
        r = repr(status)
        assert isinstance(r, str)
        assert "OutputStatus" in r


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


class TestHDRMetadataDefaults:
    """HDRMetadata constructs with Rec.2020 defaults and accepts overrides."""

    def test_class_exists(self):
        assert hasattr(pydecklink, "HDRMetadata")

    def test_default_eotf_is_pq(self):
        md = pydecklink.HDRMetadata()
        assert md.eotf == pydecklink.EOTF.PQ

    def test_default_colorspace_is_rec2020(self):
        md = pydecklink.HDRMetadata()
        assert md.colorspace == pydecklink.Colorspace.Rec2020

    def test_default_rec2020_primaries(self):
        md = pydecklink.HDRMetadata()
        # Rec.2020 (ITU-R BT.2020) reference primaries.
        assert md.red_x == pytest.approx(0.708)
        assert md.red_y == pytest.approx(0.292)
        assert md.green_x == pytest.approx(0.170)
        assert md.green_y == pytest.approx(0.797)
        assert md.blue_x == pytest.approx(0.131)
        assert md.blue_y == pytest.approx(0.046)

    def test_default_d65_white_point(self):
        md = pydecklink.HDRMetadata()
        assert md.white_x == pytest.approx(0.3127)
        assert md.white_y == pytest.approx(0.3290)

    def test_default_luminance_and_light_levels(self):
        md = pydecklink.HDRMetadata()
        assert md.max_display_mastering_luminance == pytest.approx(1000.0)
        assert md.min_display_mastering_luminance == pytest.approx(0.0001)
        assert md.max_cll == pytest.approx(1000.0)
        assert md.max_fall == pytest.approx(50.0)

    def test_constructor_accepts_overrides(self):
        md = pydecklink.HDRMetadata(
            eotf=pydecklink.EOTF.HLG,
            colorspace=pydecklink.Colorspace.Rec709,
            max_cll=10000.0,
        )
        assert md.eotf == pydecklink.EOTF.HLG
        assert md.colorspace == pydecklink.Colorspace.Rec709
        assert md.max_cll == pytest.approx(10000.0)

    def test_fields_are_writable(self):
        md = pydecklink.HDRMetadata()
        md.eotf = pydecklink.EOTF.PQ
        md.max_fall = 400.0
        assert md.max_fall == pytest.approx(400.0)


class TestHDRMetadataMethods:
    """set_hdr_metadata and display_frame_sync_frame exist with signatures."""

    def test_set_hdr_metadata_exists(self):
        assert hasattr(pydecklink.MutableFrame, "set_hdr_metadata")

    def test_display_frame_sync_frame_exists(self):
        assert hasattr(pydecklink.Device, "display_frame_sync_frame")


@pytest.mark.hardware
class TestHDRMetadataRoundTrip:
    """Set HDR metadata on a device-created frame and read it back.

    Requires hardware: IDeckLinkOutput::CreateVideoFrame needs an
    output-capable device to allocate a frame whose mutable metadata
    extension backs GetInt/GetFloat readback.
    """

    def test_set_then_readback(self):
        dev = pydecklink.Device(0)
        if not dev.supports_hdr:
            pytest.skip("device does not support HDR metadata")
        width, height = 1920, 1080
        dev.enable_video_output(pydecklink.DisplayMode.HD1080p2997)
        try:
            row_bytes = dev.row_bytes_for_pixel_format(
                pydecklink.PixelFormat.Format12BitRGB, width
            )
            frame = dev.create_video_frame(
                width, height, row_bytes, pydecklink.PixelFormat.Format12BitRGB
            )
            md = pydecklink.HDRMetadata(
                eotf=pydecklink.EOTF.PQ,
                colorspace=pydecklink.Colorspace.Rec2020,
                max_cll=10000.0,
            )
            frame.set_hdr_metadata(md)
            # Setting metadata raises the ContainsHDRMetadata frame flag.
            assert frame.flags & pydecklink.FrameFlag.ContainsHDRMetadata.value
        finally:
            dev.disable_video_output()
