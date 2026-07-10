"""Pixel packing tests for pydecklink.packing.

Byte-exact golden vectors are hand-computed from the DeckLink SDK 15.3
section 3.4 pixel-format layout tables. Each format is also checked for
``unpack(pack(x)) == x`` round-trip identity. The 12-bit R12B / R12L
formats are exercised across the 8-pixel / 36-byte group boundary
(the historically error-prone case).

These tests are pure NumPy and require no DeckLink hardware.
"""

from __future__ import annotations

import subprocess
import sys

import numpy as np
import pytest

from pydecklink import PixelFormat
from pydecklink.packing import pack, unpack

# --- Import isolation -------------------------------------------------------


def test_pack_unpack_importable() -> None:
    """The documented entry points are importable from pydecklink.packing."""
    assert callable(pack)
    assert callable(unpack)


def test_import_pydecklink_pulls_in_no_packing() -> None:
    """``import pydecklink`` alone must not import packing or expose its symbols."""
    code = (
        "import sys, pydecklink;"
        "assert 'pydecklink.packing' not in sys.modules, 'packing imported eagerly';"
        "assert not hasattr(pydecklink, 'pack'), 'pack leaked into pydecklink';"
        "assert not hasattr(pydecklink, 'unpack'), 'unpack leaked into pydecklink';"
        "print('ok')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


# --- 8-bit RGB golden vectors ----------------------------------------------


def test_argb_byte_exact() -> None:
    """ARGB memory order is A, R, G, B with alpha at peak (SDK 3.4)."""
    px = np.array([[[0x12, 0x34, 0x56]]], dtype=np.uint8)  # R, G, B
    out = pack(px, PixelFormat.Format8BitARGB, row_bytes=4)
    assert out.tolist() == [0xFF, 0x12, 0x34, 0x56]


def test_bgra_byte_exact() -> None:
    """BGRA memory order is B, G, R, A with alpha at peak (SDK 3.4)."""
    px = np.array([[[0x12, 0x34, 0x56]]], dtype=np.uint8)  # R, G, B
    out = pack(px, PixelFormat.Format8BitBGRA, row_bytes=4)
    assert out.tolist() == [0x56, 0x34, 0x12, 0xFF]


# --- 10-bit RGB golden vectors ---------------------------------------------

_RGB10 = np.array([[[768, 512, 256]]], dtype=np.uint16)  # R, G, B


def test_r210_byte_exact() -> None:
    """r210: word = (R<<20)|(G<<10)|B, big-endian (SDK 3.4)."""
    out = pack(_RGB10, PixelFormat.Format10BitRGB, row_bytes=4)
    assert out.tolist() == [0x30, 0x08, 0x01, 0x00]


def test_r10b_byte_exact() -> None:
    """R10b: word = (R<<22)|(G<<12)|(B<<2), big-endian (SDK 3.4)."""
    out = pack(_RGB10, PixelFormat.Format10BitRGBX, row_bytes=4)
    assert out.tolist() == [0xC0, 0x20, 0x04, 0x00]


def test_r10l_byte_exact() -> None:
    """R10l: same word as R10b, little-endian (SDK 3.4)."""
    out = pack(_RGB10, PixelFormat.Format10BitRGBXLE, row_bytes=4)
    assert out.tolist() == [0x00, 0x04, 0x20, 0xC0]


# --- 10-bit YUV (v210) golden vector ---------------------------------------


def test_v210_byte_exact() -> None:
    """v210: 6 pixels in 4 little-endian words; chroma from even pixels (SDK 3.4)."""
    y = [64, 65, 66, 67, 68, 69]
    cb = [100, 0, 101, 0, 102, 0]  # sampled at even pixels 0, 2, 4
    cr = [200, 0, 201, 0, 202, 0]
    px = np.array([[[y[i], cb[i], cr[i]] for i in range(6)]], dtype=np.uint16)
    out = pack(px, PixelFormat.Format10BitYUV, row_bytes=16)
    assert out.tolist() == [
        0x64,
        0x00,
        0x81,
        0x0C,
        0x41,
        0x94,
        0x21,
        0x04,
        0xC9,
        0x0C,
        0x61,
        0x06,
        0x44,
        0x28,
        0x53,
        0x04,
    ]


# --- 12-bit RGB golden vectors ---------------------------------------------


def _group_pixels_first_only() -> np.ndarray:
    """One 8-pixel group: pixel 0 distinctive, pixels 1-7 zero."""
    px = np.zeros((1, 8, 3), dtype=np.uint16)
    px[0, 0] = [0xABC, 0xDEF, 0x123]  # R, G, B
    return px


def test_r12b_byte_exact() -> None:
    """R12B big-endian nibble packing for pixel 0 (SDK 3.4 table)."""
    out = pack(_group_pixels_first_only(), PixelFormat.Format12BitRGB, row_bytes=36)
    expected = [0x00] * 36
    expected[0:4] = [0x23, 0xDE, 0xFA, 0xBC]
    expected[7] = 0x01  # B0[11:8] in low nibble of byte 7
    assert out.tolist() == expected


def test_r12l_byte_exact() -> None:
    """R12L == R12B with each 4-byte word byte-reversed (SDK 3.4)."""
    out = pack(_group_pixels_first_only(), PixelFormat.Format12BitRGBLE, row_bytes=36)
    expected = [0x00] * 36
    expected[0:4] = [0xBC, 0xFA, 0xDE, 0x23]
    expected[4:8] = [0x01, 0x00, 0x00, 0x00]
    assert out.tolist() == expected


# --- Round-trip identity ----------------------------------------------------

_RGB_FORMATS = [
    (PixelFormat.Format8BitARGB, 4, 8),
    (PixelFormat.Format8BitBGRA, 4, 8),
    (PixelFormat.Format10BitRGB, 4, 10),
    (PixelFormat.Format10BitRGBX, 4, 10),
    (PixelFormat.Format10BitRGBXLE, 4, 10),
    (PixelFormat.Format12BitRGB, 36, 12),
    (PixelFormat.Format12BitRGBLE, 36, 12),
]


def _row_bytes(fmt: PixelFormat, width: int) -> int:
    if fmt in (PixelFormat.Format12BitRGB, PixelFormat.Format12BitRGBLE):
        return ((width + 7) // 8) * 36
    if fmt is PixelFormat.Format10BitYUV:
        return ((width + 5) // 6) * 16
    return width * 4


@pytest.mark.parametrize("fmt,bpp_group,bits", _RGB_FORMATS)
def test_rgb_round_trip(fmt: PixelFormat, bpp_group: int, bits: int) -> None:
    """unpack(pack(x)) == x for every RGB format over a random frame."""
    rng = np.random.default_rng(1234)
    height, width = 5, 17  # non-multiple-of-8 width
    maxval = (1 << bits) - 1
    dtype = np.uint8 if bits == 8 else np.uint16
    px = rng.integers(0, maxval + 1, size=(height, width, 3)).astype(dtype)
    rb = _row_bytes(fmt, width)
    packed = pack(px, fmt, row_bytes=rb)
    assert packed.dtype == np.uint8
    assert packed.shape == (height * rb,)
    out = unpack(packed, fmt, width=width, height=height, row_bytes=rb)
    np.testing.assert_array_equal(out, px)


def test_v210_round_trip() -> None:
    """unpack(pack(x)) == x for v210 with chroma replicated across each pair."""
    rng = np.random.default_rng(99)
    height, width = 3, 12
    y = rng.integers(0, 1024, size=(height, width))
    cb = rng.integers(0, 1024, size=(height, width // 2))
    cr = rng.integers(0, 1024, size=(height, width // 2))
    px = np.zeros((height, width, 3), dtype=np.uint16)
    px[:, :, 0] = y
    px[:, :, 1] = np.repeat(cb, 2, axis=1)  # replicate chroma to both pixels
    px[:, :, 2] = np.repeat(cr, 2, axis=1)
    rb = _row_bytes(PixelFormat.Format10BitYUV, width)
    packed = pack(px, PixelFormat.Format10BitYUV, row_bytes=rb)
    out = unpack(
        packed, PixelFormat.Format10BitYUV, width=width, height=height, row_bytes=rb
    )
    np.testing.assert_array_equal(out, px)


# --- 12-bit group-boundary stress ------------------------------------------


@pytest.mark.parametrize(
    "fmt", [PixelFormat.Format12BitRGB, PixelFormat.Format12BitRGBLE]
)
@pytest.mark.parametrize("width", [9, 15, 17, 23])  # span >= 2 groups, non-mult-of-8
def test_r12_group_boundary_round_trip(fmt: PixelFormat, width: int) -> None:
    """R12B / R12L round-trip across the 8-pixel / 36-byte group boundary."""
    rng = np.random.default_rng(width)
    height = 2
    px = rng.integers(0, 4096, size=(height, width, 3)).astype(np.uint16)
    rb = _row_bytes(fmt, width)
    packed = pack(px, fmt, row_bytes=rb)
    out = unpack(packed, fmt, width=width, height=height, row_bytes=rb)
    np.testing.assert_array_equal(out, px)


# --- Error handling ---------------------------------------------------------


def test_unsupported_format_raises() -> None:
    with pytest.raises(ValueError):
        pack(np.zeros((1, 1, 3), np.uint8), PixelFormat.Format8BitYUV, row_bytes=4)


def test_row_bytes_too_small_raises() -> None:
    with pytest.raises(ValueError):
        pack(np.zeros((1, 4, 3), np.uint8), PixelFormat.Format8BitARGB, row_bytes=4)


def test_value_out_of_range_raises() -> None:
    px = np.array([[[4096, 0, 0]]], dtype=np.uint16)  # exceeds 12-bit range
    with pytest.raises(ValueError):
        pack(px, PixelFormat.Format12BitRGB, row_bytes=36)
