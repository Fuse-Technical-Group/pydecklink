"""Tests for NTV2 enum bindings."""

import pytest

from pyntv2 import (
    AudioSystem,
    Channel,
    InputSource,
    InputXpt,
    Mode,
    OutputDest,
    OutputXpt,
    PixelFormat,
    ReferenceSource,
    VideoFormat,
)


class TestChannel:
    def test_known_values(self):
        assert Channel.CH1.value == 0
        assert Channel.CH4.value == 3
        assert Channel.CH8.value == 7

    def test_invalid_sentinel(self):
        assert Channel.INVALID.value == 8

    def test_member_count(self):
        members = [m for m in Channel]
        assert len(members) == 9  # CH1-CH8 + INVALID

    def test_int_conversion(self):
        assert Channel(0) == Channel.CH1
        assert Channel(7) == Channel.CH8


class TestAudioSystem:
    def test_known_values(self):
        assert AudioSystem.SYSTEM_1.value == 0
        assert AudioSystem.SYSTEM_4.value == 3
        assert AudioSystem.SYSTEM_8.value == 7

    def test_none_sentinel(self):
        assert AudioSystem.NONE.value == 8

    def test_member_count(self):
        members = [m for m in AudioSystem]
        assert len(members) == 9  # SYSTEM_1-8 + NONE

    def test_int_conversion(self):
        assert AudioSystem(0) == AudioSystem.SYSTEM_1
        assert AudioSystem(7) == AudioSystem.SYSTEM_8


class TestVideoFormat:
    def test_known_values(self):
        assert VideoFormat.FORMAT_UNKNOWN.value == 0
        assert VideoFormat.FORMAT_1080i_5000.value == 1
        assert VideoFormat.FORMAT_1080i_5994.value == 2
        assert VideoFormat.FORMAT_720p_5994.value == 4
        assert VideoFormat.FORMAT_1080p_2398.value == 11
        assert VideoFormat.FORMAT_525_5994.value == 32
        assert VideoFormat.FORMAT_625_5000.value == 33

    def test_4k_formats(self):
        assert VideoFormat.FORMAT_4x1920x1080p_2398.value == 83
        assert VideoFormat.FORMAT_4x2048x1080p_6000.value == 105

    def test_uhd_tsi_formats(self):
        assert VideoFormat.FORMAT_3840x2160p_2398.value == 203
        assert VideoFormat.FORMAT_3840x2160p_6000.value == 212

    def test_member_count(self):
        members = [m for m in VideoFormat]
        assert len(members) >= 150  # many format values

    def test_int_conversion(self):
        assert VideoFormat(0) == VideoFormat.FORMAT_UNKNOWN
        assert VideoFormat(1) == VideoFormat.FORMAT_1080i_5000


class TestPixelFormat:
    def test_known_values(self):
        assert PixelFormat.FBF_10BIT_YCBCR.value == 0
        assert PixelFormat.FBF_8BIT_YCBCR.value == 1
        assert PixelFormat.FBF_ARGB.value == 2
        assert PixelFormat.FBF_RGBA.value == 3
        assert PixelFormat.FBF_10BIT_RGB.value == 4

    def test_invalid_sentinel(self):
        assert PixelFormat.INVALID.value == 32

    def test_member_count(self):
        members = [m for m in PixelFormat]
        assert len(members) == 33  # 32 formats + INVALID

    def test_int_conversion(self):
        assert PixelFormat(0) == PixelFormat.FBF_10BIT_YCBCR
        assert PixelFormat(3) == PixelFormat.FBF_RGBA


class TestInputSource:
    def test_known_values(self):
        assert InputSource.ANALOG1.value == 0
        assert InputSource.HDMI1.value == 1
        assert InputSource.HDMI4.value == 4
        assert InputSource.SDI1.value == 5
        assert InputSource.SDI8.value == 12

    def test_invalid_sentinel(self):
        assert InputSource.INVALID.value == 13

    def test_member_count(self):
        members = [m for m in InputSource]
        assert len(members) == 14  # ANALOG1 + HDMI1-4 + SDI1-8 + INVALID

    def test_int_conversion(self):
        assert InputSource(0) == InputSource.ANALOG1
        assert InputSource(5) == InputSource.SDI1


class TestOutputDest:
    def test_known_values(self):
        assert OutputDest.ANALOG1.value == 0
        assert OutputDest.HDMI1.value == 1
        assert OutputDest.SDI1.value == 2
        assert OutputDest.SDI8.value == 9

    def test_invalid_sentinel(self):
        assert OutputDest.INVALID.value == 10

    def test_member_count(self):
        members = [m for m in OutputDest]
        assert len(members) == 11  # ANALOG1 + HDMI1 + SDI1-8 + INVALID

    def test_int_conversion(self):
        assert OutputDest(0) == OutputDest.ANALOG1
        assert OutputDest(2) == OutputDest.SDI1


class TestInputXpt:
    def test_known_values(self):
        assert int(InputXpt.FrameBuffer1Input) == 0x00
        assert int(InputXpt.FrameBuffer2Input) == 0x02
        assert int(InputXpt.CSC1VidInput) == 0x10
        assert int(InputXpt.LUT1Input) == 0x20
        assert int(InputXpt.SDIOut1Input) == 0x2C
        assert int(InputXpt.HDMIOutQ1Input) == 0x64

    def test_invalid_sentinel(self):
        assert int(InputXpt.INVALID) == 0xFFFFFFFF

    def test_member_count(self):
        members = [m for m in InputXpt]
        assert len(members) >= 120

    def test_int_conversion(self):
        assert InputXpt(0x00) == InputXpt.FrameBuffer1Input
        assert InputXpt(0x10) == InputXpt.CSC1VidInput


class TestOutputXpt:
    def test_known_values(self):
        assert int(OutputXpt.Black) == 0x00
        assert int(OutputXpt.SDIIn1) == 0x01
        assert int(OutputXpt.SDIIn2) == 0x02
        assert int(OutputXpt.CSC1VidYUV) == 0x05
        assert int(OutputXpt.CSC1VidRGB) == 0x85
        assert int(OutputXpt.FrameBuffer1YUV) == 0x08
        assert int(OutputXpt.FrameBuffer1RGB) == 0x88

    def test_invalid_sentinel(self):
        assert int(OutputXpt.INVALID) == 0xFF

    def test_member_count(self):
        members = [m for m in OutputXpt]
        assert len(members) >= 100

    def test_int_conversion(self):
        assert OutputXpt(0x00) == OutputXpt.Black
        assert OutputXpt(0x05) == OutputXpt.CSC1VidYUV


class TestMode:
    def test_known_values(self):
        assert Mode.DISPLAY.value == 0
        assert Mode.CAPTURE.value == 1

    def test_invalid_sentinel(self):
        assert Mode.INVALID.value == 2

    def test_member_count(self):
        members = [m for m in Mode]
        assert len(members) == 3  # DISPLAY, CAPTURE, INVALID

    def test_int_conversion(self):
        assert Mode(0) == Mode.DISPLAY
        assert Mode(1) == Mode.CAPTURE


class TestReferenceSource:
    def test_known_values(self):
        assert ReferenceSource.EXTERNAL.value == 0
        assert ReferenceSource.INPUT1.value == 1
        assert ReferenceSource.INPUT2.value == 2
        assert ReferenceSource.FREERUN.value == 3
        assert ReferenceSource.ANALOG_INPUT1.value == 4
        assert ReferenceSource.HDMI_INPUT1.value == 5
        assert ReferenceSource.SFP1_PTP.value == 12

    def test_invalid_sentinel(self):
        assert ReferenceSource.INVALID.value == 19

    def test_member_count(self):
        members = [m for m in ReferenceSource]
        assert len(members) == 20  # 19 sources + INVALID

    def test_int_conversion(self):
        assert ReferenceSource(0) == ReferenceSource.EXTERNAL
        assert ReferenceSource(3) == ReferenceSource.FREERUN
