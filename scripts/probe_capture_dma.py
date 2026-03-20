"""Probe capture DMA on the CH3→SDI3→SDI4→CH4 loopback path.

Run on the host (outside the container) to isolate container security
issues from driver/hardware problems.

    uv run python scripts/probe_capture_dma.py
"""

from __future__ import annotations

import numpy as np

from pyntv2 import (
    Card,
    Channel,
    InputSource,
    Mode,
    OutputDest,
    PixelFormat,
    ReferenceSource,
    Transfer,
    VideoFormat,
    route_capture,
    route_playout,
)

VIDEO_FORMAT = VideoFormat.FORMAT_1080i_5994
PIXEL_FORMAT = PixelFormat.FBF_10BIT_YCBCR
MAX_FRAME_BYTES = 3840 * 2160 * 4

with Card(device_index=0) as card:
    # -- playout (CH3 → SDI3) --
    card.set_sdi_transmit_enable(Channel.CH3, True)
    card.enable_channel(Channel.CH3)
    card.set_mode(Channel.CH3, Mode.DISPLAY)
    card.set_video_format(VIDEO_FORMAT, channel=Channel.CH3)
    card.set_frame_buffer_format(Channel.CH3, PIXEL_FORMAT)

    # -- capture (SDI4 → CH4) --
    card.set_sdi_transmit_enable(Channel.CH4, False)
    card.enable_channel(Channel.CH4)
    card.set_mode(Channel.CH4, Mode.CAPTURE)
    card.set_video_format(VIDEO_FORMAT, channel=Channel.CH4)
    card.set_frame_buffer_format(Channel.CH4, PIXEL_FORMAT)

    # -- routing --
    card.set_reference(ReferenceSource.FREERUN)
    card.clear_routing()
    card.apply_signal_route(
        route_playout(Channel.CH3, OutputDest.SDI3, PIXEL_FORMAT), replace=False
    )
    card.apply_signal_route(
        route_capture(InputSource.SDI4, Channel.CH4, PIXEL_FORMAT), replace=False
    )

    card.autocirculate_stop(Channel.CH3, abort=True)
    card.autocirculate_stop(Channel.CH4, abort=True)

    # -- playout: push frames so loopback cable carries signal --
    card.autocirculate_init_for_output(Channel.CH3)
    card.autocirculate_start(Channel.CH3)

    blank = np.zeros(MAX_FRAME_BYTES, dtype=np.uint8)
    xfer = Transfer()
    xfer.set_video_buffer(blank)
    for _ in range(10):
        card.wait_for_input_vertical_interrupt(Channel.CH3)
        s = card.autocirculate_get_status(Channel.CH3)
        if s.can_accept_more_output_frames:
            card.autocirculate_transfer(Channel.CH3, xfer)

    # -- capture: wait for a frame then attempt DMA --
    card.autocirculate_init_for_input(Channel.CH4)
    card.autocirculate_start(Channel.CH4)

    for i in range(30):
        card.wait_for_input_vertical_interrupt(Channel.CH4)
        s = card.autocirculate_get_status(Channel.CH4)
        if s.has_available_input_frame:
            buf = np.zeros(MAX_FRAME_BYTES, dtype=np.uint8)
            cx = Transfer()
            cx.set_video_buffer(buf)
            card.autocirculate_transfer(Channel.CH4, cx)
            print(f"PASS: capture DMA at VBI {i}, non-zero={np.count_nonzero(buf)}")
            break
    else:
        print("FAIL: no capture frame after 30 VBIs")

    card.autocirculate_stop(Channel.CH3, abort=True)
    card.autocirculate_stop(Channel.CH4, abort=True)
    card.clear_routing()
