"""Regression test for the schedule_frame ComPtr ref leak.

Background
----------
Before fix/mem-leak, ``Device.schedule_frame`` called ``ComPtr::release()``
on its local frame after ``ScheduleVideoFrame`` returned. The intent was
"give up our reference, the SDK now holds one." But ``release()`` had
``unique_ptr``-style semantics (return raw pointer + null-out, *without*
calling COM ``Release()``), so the host-side reference was never
dropped. Net effect: every ``schedule_frame()`` call leaked one full
``IDeckLinkMutableVideoFrame`` — a ~4 MiB buffer at HD1080p25 8-bit YUV.

The fix removed the bogus ``release()`` call so the local ``ComPtr``
destructor releases the reference correctly. The misnamed method was
renamed to ``detach()`` to match its actual semantics.

Detection strategy
------------------
``TrackedFramePtr`` wraps each frame created by ``schedule_frame`` and
maintains an atomic counter (``g_host_frame_refs``).  The counter
increments after ``CreateVideoFrame`` succeeds and decrements in the
destructor only when the inner ``ComPtr`` still holds a live pointer
(i.e. ``Release()`` will fire).  After all calls return, the counter
must be zero — any non-zero value means a host-side ref was leaked.
"""

from __future__ import annotations

import contextlib
import time

import numpy as np
import pytest

import pydecklink
from pydecklink._bindings import _host_frame_refs

_HAS_SDK = getattr(pydecklink, "HAS_SDK", False)

pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers"),
]

MODE = pydecklink.DisplayMode.HD1080p25 if _HAS_SDK else None
PIXEL_FORMAT = pydecklink.PixelFormat.Format8BitYUV if _HAS_SDK else None
ITERATIONS = 100
PREROLL = 4


def test_schedule_frame_does_not_leak_per_call():
    width = pydecklink.get_mode_width(MODE)
    height = pydecklink.get_mode_height(MODE)
    row_bytes = width * 2  # 8-bit YUV
    fps = pydecklink.get_mode_fps(MODE)
    timescale = 10_000_000
    frame_duration = round(timescale / fps)

    dev = pydecklink.Device(index=0)
    dev.enable_video_output(MODE)
    try:
        buf = np.zeros(row_bytes * height, dtype=np.uint8)

        # Pre-roll a few frames before starting playback.
        for i in range(PREROLL):
            dev.schedule_frame(
                buf,
                width,
                height,
                row_bytes,
                PIXEL_FORMAT,
                i * frame_duration,
                frame_duration,
                timescale,
            )
        dev.start_scheduled_playback(0, timescale, 1.0)

        # Pace at slightly under frame rate so the SDK has time to
        # complete (and release) frames between schedules.
        period = 0.9 / fps
        for i in range(PREROLL, PREROLL + ITERATIONS):
            time.sleep(period)
            dev.schedule_frame(
                buf,
                width,
                height,
                row_bytes,
                PIXEL_FORMAT,
                i * frame_duration,
                frame_duration,
                timescale,
            )

        # Every host-side frame ref should have been released by the
        # ComPtr destructor at schedule_frame scope exit.
        leaked_refs = _host_frame_refs()
        assert leaked_refs == 0, (
            f"schedule_frame leaked {leaked_refs} host-side frame refs"
        )
    finally:
        with contextlib.suppress(RuntimeError):
            dev.stop_scheduled_playback()
        with contextlib.suppress(RuntimeError):
            dev.disable_video_output()
