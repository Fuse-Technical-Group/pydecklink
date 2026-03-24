"""Hardware smoke tests — require an AJA device, no signal needed.

Run with: pytest -m hardware
"""

import mmap

import numpy as np
import pytest

from pyntv2 import (
    AudioSystem,
    Card,
    Channel,
    InputSource,
    InputXpt,
    Mode,
    OutputXpt,
    PixelFormat,
    ReferenceSource,
    VideoFormat,
    route_capture,
)

pytestmark = pytest.mark.hardware



class TestLifecycle:
    def test_open_close(self):
        card = Card()
        card.open(0)
        assert card.is_open is True
        card.close()
        assert card.is_open is False

    def test_context_manager(self):
        with Card(device_index=0) as card:
            assert card.is_open is True
        assert card.is_open is False


class TestFormatDetection:
    def test_detect_sdi_input_formats(self, card):
        """Each SDI input returns a valid VideoFormat (UNKNOWN or a real format)."""
        sdi_sources = [
            InputSource.SDI1,
            InputSource.SDI2,
            InputSource.SDI3,
            InputSource.SDI4,
        ]
        for source in sdi_sources:
            fmt = card.get_input_video_format(source)
            assert isinstance(fmt, VideoFormat), f"{source} returned {type(fmt)}"


class TestChannelConfiguration:
    def test_enable_and_set_mode(self, card):
        card.enable_channel(Channel.CH1)
        card.set_mode(Channel.CH1, Mode.CAPTURE)

    def test_set_video_format(self, card):
        card.set_video_format(VideoFormat.FORMAT_1080i_5994, channel=Channel.CH1)

    def test_set_frame_buffer_format(self, card):
        card.set_frame_buffer_format(Channel.CH1, PixelFormat.FBF_10BIT_YCBCR)

    def test_set_sdi_transmit_enable(self, card):
        card.set_sdi_transmit_enable(Channel.CH1, False)

    def test_set_reference(self, card):
        card.set_reference(ReferenceSource.FREERUN)


class TestRouting:
    def test_connect_disconnect(self, card):
        card.connect(InputXpt.FrameBuffer1Input, OutputXpt.SDIIn1)
        card.disconnect(InputXpt.FrameBuffer1Input)

    def test_clear_routing(self, card):
        card.connect(InputXpt.FrameBuffer1Input, OutputXpt.SDIIn1)
        card.clear_routing()

    def test_apply_signal_route(self, card):
        routes = route_capture(InputSource.SDI1, Channel.CH1, PixelFormat.FBF_10BIT_YCBCR)
        card.apply_signal_route(routes, replace=True)
        card.clear_routing()

    def test_connect_csc_crosspoints(self, card):
        """Verify CSC crosspoints can be connected individually."""
        card.connect(InputXpt.CSC1VidInput, OutputXpt.SDIIn1)
        card.connect(InputXpt.FrameBuffer1Input, OutputXpt.CSC1VidRGB)
        card.clear_routing()


class TestAutoCirculate:
    def test_init_status_stop(self, card):
        card.enable_channel(Channel.CH1)
        card.set_mode(Channel.CH1, Mode.CAPTURE)
        card.set_video_format(VideoFormat.FORMAT_1080i_5994)
        card.set_frame_buffer_format(Channel.CH1, PixelFormat.FBF_10BIT_YCBCR)

        # Ensure channel is stopped before init (may have residual state)
        card.autocirculate_stop(Channel.CH1, abort=True)

        card.autocirculate_init_for_input(Channel.CH1, frame_count=7)
        status = card.autocirculate_get_status(Channel.CH1)
        assert status.is_stopped is False  # init puts it in INIT state
        assert status.is_running is False

        card.autocirculate_start(Channel.CH1)

        card.autocirculate_stop(Channel.CH1, abort=True)
        status = card.autocirculate_get_status(Channel.CH1)
        assert status.is_stopped is True


class TestDmaBufferLock:
    def test_lock_unlock_numpy(self, card):
        size = 1920 * 1080 * 4
        backing = mmap.mmap(-1, size)
        buf = np.frombuffer(backing, dtype=np.uint8)
        card.dma_buffer_lock(buf)
        card.dma_buffer_unlock(buf)
        del buf
        backing.close()
