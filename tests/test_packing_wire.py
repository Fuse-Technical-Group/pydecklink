"""Over-the-wire validation for pydecklink.packing — requires DeckLink hardware.

The in-memory tests (test_packing.py) prove pack/unpack are byte-exact
against the SDK layout tables and self-inverse. This test closes the loop:
pack a known pattern, play it out over SDI, capture it back, unpack, and
confirm the pixel values survive the real output → cable → input path.

Uses v210 (10-bit YUV 4:2:2) at HD1080p25. That format fits single-link
1.5G HD-SDI and is bit-exact on the wire. 4:4:4 RGB is deliberately not
exercised here: it exceeds 1.5G link bandwidth (needs 3G or dual-link),
so an RGB round-trip at this rate drops colour — a transport limit, not a
packing one.

Run with: pytest -m hardware tests/test_packing_wire.py

Requires an SDI OUT → IN loopback (see test_decklink_integration.py for
topology and the PYDECKLINK_LOOPBACK_* overrides).
"""

from __future__ import annotations

import contextlib
import os

import numpy as np
import pytest

import pydecklink

_HAS_SDK = getattr(pydecklink, "HAS_SDK", False)

_OUTPUT_INDEX = int(os.environ.get("PYDECKLINK_LOOPBACK_OUTPUT", "0"))
_INPUT_INDEX = int(os.environ.get("PYDECKLINK_LOOPBACK_INPUT", str(_OUTPUT_INDEX)))

pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(not _HAS_SDK, reason="Built without DeckLink SDK headers"),
]

if _HAS_SDK:
    MODE = pydecklink.DisplayMode.HD1080p25
    PIXEL_FORMAT = pydecklink.PixelFormat.Format10BitYUV  # v210
    WIDTH = pydecklink.get_mode_width(MODE)
    HEIGHT = pydecklink.get_mode_height(MODE)
    ROW_BYTES = pydecklink.get_row_bytes(PIXEL_FORMAT, WIDTH)
    TIMESCALE = 10_000_000
    FRAME_DURATION = round(TIMESCALE / pydecklink.get_mode_fps(MODE))
else:
    MODE = PIXEL_FORMAT = None  # type: ignore[assignment]
    WIDTH = HEIGHT = ROW_BYTES = 0
    TIMESCALE = FRAME_DURATION = 0


def _band_pattern() -> np.ndarray:
    """Four horizontal bands of distinct [Y, Cb, Cr] triples.

    Chroma is constant across each row so the 4:2:2 pairing is consistent
    (v210 subsamples chroma horizontally), and all components sit in
    [0x040, 0x3C0] to avoid the SMPTE reserved codes the hardware rewrites.
    """
    bands = [
        (0x200, 0x180, 0x280),
        (0x100, 0x200, 0x100),
        (0x340, 0x0C0, 0x200),
        (0x080, 0x300, 0x140),
    ]
    frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint16)
    for i, triple in enumerate(bands):
        frame[i * HEIGHT // 4 : (i + 1) * HEIGHT // 4] = triple
    return frame


def test_v210_packing_round_trips_over_sdi():
    """A v210-packed pattern survives output → SDI → capture → unpack.

    Exercises pydecklink.packing.pack and .unpack against real hardware:
    the recovered pixels must match what was packed, bit-for-bit across the
    active picture (excluding the band-boundary rows, where SDI line timing
    makes a one-row transition).
    """
    from pydecklink.packing import pack, unpack

    if pydecklink.device_count() <= max(_OUTPUT_INDEX, _INPUT_INDEX):
        pytest.skip("Loopback device index not present")

    out_dev = pydecklink.Device(index=_OUTPUT_INDEX)
    # Self-loopback shares one handle; distinct indices get their own.
    if _INPUT_INDEX == _OUTPUT_INDEX:
        in_dev = out_dev
    else:
        in_dev = pydecklink.Device(index=_INPUT_INDEX)

    c444 = pydecklink.ConfigurationID.Config444SDIVideoOutput
    try:
        original_444 = out_dev.get_config_flag(c444)
        out_dev.set_config_flag(c444, False)  # 4:2:2 YCbCr so v210 rides the wire
    except RuntimeError:
        original_444 = None

    original = _band_pattern()
    buf = pack(original, PIXEL_FORMAT, ROW_BYTES)

    out_dev.enable_video_output(MODE)
    in_dev.enable_video_input(MODE, PIXEL_FORMAT)  # fixed mode matches the wire
    in_dev.start_streams()
    try:
        preroll = 15
        out_dev.create_frame_pool(preroll + 5, WIDTH, HEIGHT, ROW_BYTES, PIXEL_FORMAT)

        def schedule(display_time: int) -> None:
            mf = out_dev.acquire_output_frame(timeout_ms=1000)
            mf.data[:] = buf
            out_dev.schedule_output_frame(
                mf,
                display_time=display_time,
                duration=FRAME_DURATION,
                timescale=TIMESCALE,
            )

        for i in range(preroll):
            schedule(i * FRAME_DURATION)
        out_dev.start_scheduled_playback(start_time=0, timescale=TIMESCALE)
        display_time = preroll * FRAME_DURATION

        frame = None
        for _ in range(200):
            f = in_dev.pop_capture_frame(timeout_ms=1000)
            with contextlib.suppress(RuntimeError):
                schedule(display_time)
                display_time += FRAME_DURATION
            if f is not None and f.has_signal:
                frame = f
                break

        if frame is None:
            pytest.skip("No SDI signal on loopback input — check OUT→IN cabling")

        assert frame.pixel_format == PIXEL_FORMAT
        cap = np.array(frame.data)
        recovered = unpack(
            cap,
            frame.pixel_format,
            frame.width,
            frame.height,
            len(cap) // frame.height,
        )

        equal = np.all(recovered == original, axis=2)
        # Exclude the band-boundary rows (±1): SDI carries a one-line
        # transition there, not a packing artifact.
        interior = np.ones(HEIGHT, dtype=bool)
        for boundary in (i * HEIGHT // 4 for i in range(4)):
            interior[max(0, boundary - 1) : boundary + 1] = False
        match = equal[interior].mean()
        assert match == 1.0, (
            f"v210 loopback not bit-exact: {match:.5f} of interior pixels match "
            f"(pack → SDI → capture → unpack should be lossless for 4:2:2)"
        )
    finally:
        if original_444 is not None:
            with contextlib.suppress(RuntimeError):
                out_dev.set_config_flag(c444, original_444)
        for step in (
            out_dev.stop_scheduled_playback,
            in_dev.stop_streams,
            in_dev.disable_video_input,
            out_dev.disable_video_output,
        ):
            with contextlib.suppress(RuntimeError):
                step()
