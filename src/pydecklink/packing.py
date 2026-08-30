"""Pack integer RGB/YUV pixel values into DeckLink in-memory layouts.

Opt-in convenience layer above the transport surface (see SPEC.md
§spec:pixel-packing). ``import pydecklink`` does not import this module;
callers opt in with ``from pydecklink.packing import pack, unpack``.

The layouts and their codecs live in ``pypixelpack``, keyed by layout
name. This module holds the one Blackmagic-specific thing: ``_FORMATS``,
the map from ``PixelFormat`` to that name, so callers keep passing the
enum they already hold.

``pack(pixels, pixel_format, row_bytes)`` returns a 1-D ``uint8`` buffer
ready for ``MutableFrame.data``. ``unpack(data, pixel_format, width,
height, row_bytes)`` recovers pixel values from a raw ``CaptureFrame.data``.
``unpack(pack(x)) == x`` for every supported format. Array conventions
are pypixelpack's: ``(height, width, 3)`` integer arrays, ``[R, G, B]``
for RGB layouts and ``[Y, Cb, Cr]`` for v210, alpha written at peak and
dropped on unpack, chroma sampled from even columns.
"""

from __future__ import annotations

from typing import cast

import numpy as np
import pypixelpack
from numpy.typing import NDArray

from pydecklink._bindings import PixelFormat

__all__ = ["pack", "unpack"]

# PixelFormat -> pypixelpack layout name.
_FORMATS = {
    PixelFormat.Format8BitARGB: "argb",
    PixelFormat.Format8BitBGRA: "bgra",
    PixelFormat.Format10BitRGB: "r210",
    PixelFormat.Format10BitRGBX: "r10b",
    PixelFormat.Format10BitRGBXLE: "r10l",
    PixelFormat.Format10BitYUV: "v210",
    PixelFormat.Format12BitRGB: "r12b",
    PixelFormat.Format12BitRGBLE: "r12l",
}


def _layout(pixel_format: PixelFormat) -> str:
    layout = _FORMATS.get(pixel_format)
    if layout is None:
        raise ValueError(f"unsupported pixel format for packing: {pixel_format!r}")
    return layout


def pack(
    pixels: NDArray[np.integer],
    pixel_format: PixelFormat,
    row_bytes: int,
) -> NDArray[np.uint8]:
    """Pack ``(height, width, 3)`` integer pixel values into a DeckLink buffer.

    Returns a 1-D ``uint8`` array of length ``height * row_bytes`` suitable
    for ``MutableFrame.data``. ``row_bytes`` must be at least the packed
    active-line size; extra bytes are zero padding.
    """
    return cast(
        NDArray[np.uint8], pypixelpack.pack(pixels, _layout(pixel_format), row_bytes)
    )


def unpack(
    data: NDArray[np.uint8],
    pixel_format: PixelFormat,
    width: int,
    height: int,
    row_bytes: int,
) -> NDArray[np.integer]:
    """Recover ``(height, width, 3)`` pixel values from a raw DeckLink buffer.

    Inverse of :func:`pack`. Returns ``uint8`` values for 8-bit formats and
    ``uint16`` for 10/12-bit formats.
    """
    return cast(
        NDArray[np.integer],
        pypixelpack.unpack(data, _layout(pixel_format), width, height, row_bytes),
    )
