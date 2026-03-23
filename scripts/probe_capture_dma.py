"""Probe capture DMA on CH1/SDI1 (live signal).

Mirrors scripts/test_capture_minimal.cpp to validate the Python binding
against the same code path that the static C++ binary exercises.

    sudo /path/to/.venv/bin/python3 scripts/probe_capture_dma.py
"""

from __future__ import annotations

import os

import numpy as np

from pyntv2 import (
    Card,
    Channel,
    InputSource,
    Mode,
    PixelFormat,
    ReferenceSource,
    Transfer,
    route_capture,
)

CH = Channel.CH1
SRC = InputSource.SDI1
PIXEL_FORMAT = PixelFormat.FBF_10BIT_YCBCR
FRAME_BYTES = 1920 * 1080 * 4  # 8 MB, matches the C++ test

_NTV2_OEM_TASKS = 2
_APP_SIG = 0x54455354  # NTV2_FOURCC('T','E','S','T')

with Card(device_index=0) as card:
    # Acquire ownership and set OEM task mode (matches C++ test)
    card.acquire_stream_for_application(_APP_SIG, os.getpid())
    saved_mode = card.get_every_frame_services()
    card.set_every_frame_services(_NTV2_OEM_TASKS)

    # Detect input format
    vf = card.get_input_video_format(SRC)
    print(f"Detected input format: {vf}")

    # Configure CH1 for capture
    card.set_sdi_transmit_enable(CH, False)
    card.enable_channel(CH)
    card.set_mode(CH, Mode.CAPTURE)
    card.set_video_format(vf, channel=CH)
    card.set_frame_buffer_format(CH, PIXEL_FORMAT)
    card.set_reference(ReferenceSource.FREERUN)

    # Route SDI1 → FB1
    card.clear_routing()
    routes = route_capture(SRC, CH, PIXEL_FORMAT)
    card.apply_signal_route(routes, replace=False)

    # Pre-lock the DMA buffer (page-aligned, matches C++ posix_memalign)
    import mmap
    _backing = mmap.mmap(-1, FRAME_BYTES)  # anonymous, page-aligned
    buf = np.frombuffer(_backing, dtype=np.uint8)
    print(f"Buffer ptr=0x{buf.ctypes.data:X}  size={FRAME_BYTES}  "
          f"page_aligned={buf.ctypes.data % 4096 == 0}")
    card.dma_buffer_lock(buf)

    # AutoCirculate
    card.autocirculate_stop(CH, abort=True)
    card.autocirculate_init_for_input(CH)
    card.autocirculate_start(CH)

    for i in range(60):
        card.wait_for_input_vertical_interrupt(CH)
        s = card.autocirculate_get_status(CH)
        if s.has_available_input_frame:
            print(f"Frame available after {i + 1} VBIs, bufLevel={s.buffer_level}")
            break
    else:
        card.autocirculate_stop(CH, abort=True)
        raise SystemExit("FAIL: no capture frame after 60 VBIs")

    xfer = Transfer()
    xfer.set_video_buffer(buf)
    card.autocirculate_transfer(CH, xfer)
    nonzero = np.count_nonzero(buf)
    print(f"PASS: capture DMA OK, non-zero={nonzero} / {FRAME_BYTES}")

    # Transfer 9 more frames
    ok = 0
    for _ in range(9):
        card.wait_for_input_vertical_interrupt(CH)
        s = card.autocirculate_get_status(CH)
        if not s.has_available_input_frame:
            continue
        buf[:] = 0
        xfer.set_video_buffer(buf)
        card.autocirculate_transfer(CH, xfer)
        ok += 1
    print(f"9 more frames: {ok} ok")

    card.autocirculate_stop(CH, abort=True)
    card.dma_buffer_unlock(buf)
    card.clear_routing()
    card.set_every_frame_services(saved_mode)
    card.release_stream_for_application(_APP_SIG, os.getpid())
