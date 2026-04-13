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
``ComPtr`` maintains a global atomic counter (``g_comptr_live``) of all
live instances holding a non-null COM pointer.  The counter increments
on acquisition (constructor or deferred via ``put()``) and decrements
on release (destructor, move-assignment, or ``put()`` overwrite).
Between ``schedule_frame`` calls, all scope-local ``ComPtr`` objects
are destroyed, so the counter must return to its baseline — any drift
means a ref was leaked.
"""

from __future__ import annotations

import contextlib
import time

import numpy as np
import pytest

import pydecklink
from pydecklink._bindings import _comptr_live

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

        # Snapshot after pre-roll — all scope-local ComPtrs from
        # pre-roll calls are already destroyed.
        baseline = _comptr_live()

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

        # All scope-local ComPtrs from schedule_frame should be
        # destroyed.  Any counter drift means a ref was leaked.
        leaked = _comptr_live() - baseline
        assert leaked == 0, (
            f"schedule_frame leaked {leaked} ComPtr refs over {ITERATIONS} calls"
        )
    finally:
        with contextlib.suppress(RuntimeError):
            dev.stop_scheduled_playback()
        with contextlib.suppress(RuntimeError):
            dev.disable_video_output()
