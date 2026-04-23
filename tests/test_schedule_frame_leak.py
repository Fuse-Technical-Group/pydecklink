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
The leak only manifests when scheduled playback is *running*: without
playback the SDK queues frames internally and growth looks identical
between branches. With playback paced at frame rate, completed frames
should be dropped by the SDK — and any host-side over-reference shows
up as 4 MiB/iter RSS growth, plus eventual ``CreateVideoFrame failed``
once the SDK's allocator can't satisfy a new frame.

Observed on main (pre-fix): ~3.2 MiB/iter, crashes within ~30 iters.
Observed on fix/mem-leak:    bounded growth, completes all iterations.

The threshold below is set well above fix-branch noise (~325 KiB/iter
asymptotic from DMA warm-up) and well below the buggy branch's
~3.2 MiB/iter, so it cleanly distinguishes the two.
"""

from __future__ import annotations

import contextlib
import time

import psutil
import pytest

import pydecklink

_HAS_SDK = getattr(pydecklink, "HAS_SDK", False)

pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers"),
]

MODE = pydecklink.DisplayMode.HD1080p25 if _HAS_SDK else None
PIXEL_FORMAT = pydecklink.PixelFormat.Format8BitYUV if _HAS_SDK else None
ITERATIONS = 100
PREROLL = 4
# Per-iter RSS budget. Buggy branch leaks ~3.2 MiB/iter (one full frame).
# Fixed branch settles around ~325 KiB/iter from one-time DMA buffer
# warm-up. 1.0 MiB/iter is comfortably between the two.
PER_ITER_BUDGET_BYTES = 1024 * 1024


def test_schedule_frame_does_not_leak_per_call():
    assert MODE
    assert PIXEL_FORMAT

    width = pydecklink.get_mode_width(MODE)
    height = pydecklink.get_mode_height(MODE)
    row_bytes = width * 2  # 8-bit YUV
    fps = pydecklink.get_mode_fps(MODE)
    timescale = 10_000_000
    frame_duration = round(timescale / fps)

    pool_size = PREROLL + 5

    dev = pydecklink.Device(index=0)
    dev.enable_video_output(MODE)
    try:
        dev.create_frame_pool(pool_size, width, height, row_bytes, PIXEL_FORMAT)

        def schedule_pattern(display_time: int) -> None:
            mf = dev.acquire_output_frame(timeout_ms=1000)
            mf.data[:] = 0
            dev.schedule_output_frame(
                mf,
                display_time=display_time,
                duration=frame_duration,
                timescale=timescale,
            )

        # Pre-roll a few frames before starting playback.
        for i in range(PREROLL):
            schedule_pattern(i * frame_duration)
        dev.start_scheduled_playback(0, timescale, 1.0)

        proc = psutil.Process()
        baseline = proc.memory_info().rss

        # Pace at slightly under frame rate so the SDK has time to
        # complete (and release) frames between schedules.
        period = 0.9 / fps
        for i in range(PREROLL, PREROLL + ITERATIONS):
            time.sleep(period)
            schedule_pattern(i * frame_duration)

        delta = proc.memory_info().rss - baseline
        per_iter = delta / ITERATIONS
        assert per_iter < PER_ITER_BUDGET_BYTES, (
            f"schedule_frame leaked: RSS grew {delta} bytes over {ITERATIONS} "
            f"calls = {per_iter:.0f} B/call (budget {PER_ITER_BUDGET_BYTES})"
        )
    finally:
        with contextlib.suppress(RuntimeError):
            dev.stop_scheduled_playback()
        with contextlib.suppress(RuntimeError):
            dev.disable_video_output()
