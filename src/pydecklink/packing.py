"""Pack integer RGB/YUV pixel values into DeckLink in-memory layouts.

Opt-in convenience layer above the transport surface (see SPEC.md
§spec:pixel-packing). ``import pydecklink`` does not import this module;
callers opt in with ``from pydecklink.packing import pack, unpack``.

``pack(pixels, pixel_format, row_bytes)`` returns a 1-D ``uint8`` buffer
ready for ``MutableFrame.data``. ``unpack(data, pixel_format, width,
height, row_bytes)`` recovers pixel values from a raw ``CaptureFrame.data``.
``unpack(pack(x)) == x`` for every supported format.

Pixel arrays are ``(height, width, 3)`` integer ndarrays. For RGB formats
the channels are ``[R, G, B]``; the alpha channel of ARGB/BGRA is written
at peak on pack and dropped on unpack. For the 4:2:2 YUV format v210 the
channels are ``[Y, Cb, Cr]``; chroma is sampled from even columns on pack
and replicated across each pair on unpack, so round-trip identity holds
when chroma is equal within each horizontal pair.

Layouts follow the DeckLink SDK 15.3 manual section 3.4. The
implementation is NumPy; the API is backend-swappable so a native fast
path can replace it without a surface change.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from pydecklink._bindings import PixelFormat

__all__ = ["pack", "unpack"]

# Channel indices within a pixel triple.
_R, _G, _B = 0, 1, 2

# R12B big-endian nibble map (SDK 15.3 section 3.4, 8 pixels / 36 bytes).
# Each output byte is a list of placements; a placement takes ``nbits`` bits
# starting at bit ``src_lo`` of component ``(pixel, channel)`` and writes them
# at bit ``dst_lo`` of the byte. Verified: every one of the 24 components
# (8 pixels x R/G/B) contributes exactly 12 bits.
_R12B_MAP: list[list[tuple[int, int, int, int, int]]] = [
    [(0, _B, 0, 8, 0)],
    [(0, _G, 4, 8, 0)],
    [(0, _G, 0, 4, 4), (0, _R, 8, 4, 0)],
    [(0, _R, 0, 8, 0)],
    [(1, _B, 0, 4, 4), (1, _G, 8, 4, 0)],
    [(1, _G, 0, 8, 0)],
    [(1, _R, 4, 8, 0)],
    [(1, _R, 0, 4, 4), (0, _B, 8, 4, 0)],
    [(2, _G, 4, 8, 0)],
    [(2, _G, 0, 4, 4), (2, _R, 8, 4, 0)],
    [(2, _R, 0, 8, 0)],
    [(1, _B, 4, 8, 0)],
    [(3, _G, 0, 8, 0)],
    [(3, _R, 4, 8, 0)],
    [(3, _R, 0, 4, 4), (2, _B, 8, 4, 0)],
    [(2, _B, 0, 8, 0)],
    [(4, _G, 0, 4, 4), (4, _R, 8, 4, 0)],
    [(4, _R, 0, 8, 0)],
    [(3, _B, 4, 8, 0)],
    [(3, _B, 0, 4, 4), (3, _G, 8, 4, 0)],
    [(5, _R, 4, 8, 0)],
    [(5, _R, 0, 4, 4), (4, _B, 8, 4, 0)],
    [(4, _B, 0, 8, 0)],
    [(4, _G, 4, 8, 0)],
    [(6, _R, 0, 8, 0)],
    [(5, _B, 4, 8, 0)],
    [(5, _B, 0, 4, 4), (5, _G, 8, 4, 0)],
    [(5, _G, 0, 8, 0)],
    [(7, _R, 0, 4, 4), (6, _B, 8, 4, 0)],
    [(6, _B, 0, 8, 0)],
    [(6, _G, 4, 8, 0)],
    [(6, _G, 0, 4, 4), (6, _R, 8, 4, 0)],
    [(7, _B, 4, 8, 0)],
    [(7, _B, 0, 4, 4), (7, _G, 8, 4, 0)],
    [(7, _G, 0, 8, 0)],
    [(7, _R, 4, 8, 0)],
]

# (group_pixels, group_bytes) per supported format.
_GROUP = {
    "argb": (1, 4),
    "bgra": (1, 4),
    "r210": (1, 4),
    "r10b": (1, 4),
    "r10l": (1, 4),
    "v210": (6, 16),
    "r12b": (8, 36),
    "r12l": (8, 36),
}

# Bit depth per supported format (for range validation).
_BITS = {
    "argb": 8,
    "bgra": 8,
    "r210": 10,
    "r10b": 10,
    "r10l": 10,
    "v210": 10,
    "r12b": 12,
    "r12l": 12,
}

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


def _key(pixel_format: PixelFormat) -> str:
    key = _FORMATS.get(pixel_format)
    if key is None:
        raise ValueError(f"unsupported pixel format for packing: {pixel_format!r}")
    return key


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
    key = _key(pixel_format)
    arr = np.asarray(pixels)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError(f"pixels must have shape (height, width, 3), got {arr.shape}")
    height, width, _ = arr.shape

    group_px, group_bytes = _GROUP[key]
    num_groups = (width + group_px - 1) // group_px
    min_row = num_groups * group_bytes
    if row_bytes < min_row:
        raise ValueError(
            f"row_bytes={row_bytes} too small for width={width} "
            f"({pixel_format!r} needs at least {min_row})"
        )

    maxval = (1 << _BITS[key]) - 1
    if arr.size and int(arr.max()) > maxval:
        raise ValueError(
            f"pixel value exceeds {_BITS[key]}-bit range for {pixel_format!r}"
        )

    # Zero-pad width to a whole number of groups.
    padded_w = num_groups * group_px
    if padded_w != width:
        pad = np.zeros((height, padded_w - width, 3), dtype=np.uint32)
        src = np.concatenate([arr.astype(np.uint32), pad], axis=1)
    else:
        src = arr.astype(np.uint32)

    group_data = _pack_groups(
        key, src, height, num_groups
    )  # (height, num_groups*group_bytes)

    out = np.zeros((height, row_bytes), dtype=np.uint8)
    out[:, :min_row] = group_data
    return out.reshape(-1)


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
    key = _key(pixel_format)
    buf = np.asarray(data, dtype=np.uint8)
    if buf.size < height * row_bytes:
        raise ValueError(
            f"data too small: got {buf.size} bytes, need {height * row_bytes}"
        )
    rows = buf[: height * row_bytes].reshape(height, row_bytes)

    group_px, group_bytes = _GROUP[key]
    num_groups = (width + group_px - 1) // group_px
    group_data = rows[:, : num_groups * group_bytes]

    padded = _unpack_groups(
        key, group_data, height, num_groups
    )  # (height, padded_w, 3)
    result = padded[:, :width, :]

    out_dtype = np.uint8 if _BITS[key] == 8 else np.uint16
    return result.astype(out_dtype)


# --- per-format group packers ----------------------------------------------


def _pack_groups(
    key: str,
    src: NDArray[np.uint32],
    height: int,
    num_groups: int,
) -> NDArray[np.uint8]:
    if key in ("argb", "bgra"):
        return _pack_8bit(key, src)
    if key in ("r210", "r10b", "r10l"):
        return _pack_10bit_rgb(key, src)
    if key == "v210":
        return _pack_v210(src, height, num_groups)
    return _pack_12bit(key, src, height, num_groups)


def _unpack_groups(
    key: str,
    data: NDArray[np.uint8],
    height: int,
    num_groups: int,
) -> NDArray[np.uint32]:
    if key in ("argb", "bgra"):
        return _unpack_8bit(key, data)
    if key in ("r210", "r10b", "r10l"):
        return _unpack_10bit_rgb(key, data)
    if key == "v210":
        return _unpack_v210(data, height, num_groups)
    return _unpack_12bit(key, data, height, num_groups)


def _u32_to_bytes(words: NDArray[np.uint32], big_endian: bool) -> NDArray[np.uint8]:
    """Split a (..., N) uint32 array into (..., N*4) uint8, given endianness."""
    b0 = (words & 0xFF).astype(np.uint8)
    b1 = ((words >> 8) & 0xFF).astype(np.uint8)
    b2 = ((words >> 16) & 0xFF).astype(np.uint8)
    b3 = ((words >> 24) & 0xFF).astype(np.uint8)
    order = (b3, b2, b1, b0) if big_endian else (b0, b1, b2, b3)
    stacked = np.stack(order, axis=-1)
    return stacked.reshape(*words.shape[:-1], words.shape[-1] * 4)


def _bytes_to_u32(data: NDArray[np.uint8], big_endian: bool) -> NDArray[np.uint32]:
    """Combine a (..., N*4) uint8 array into (..., N) uint32, given endianness."""
    quads = data.reshape(*data.shape[:-1], data.shape[-1] // 4, 4).astype(np.uint32)
    if big_endian:
        words = (
            (quads[..., 0] << 24)
            | (quads[..., 1] << 16)
            | (quads[..., 2] << 8)
            | quads[..., 3]
        )
    else:
        words = (
            quads[..., 0]
            | (quads[..., 1] << 8)
            | (quads[..., 2] << 16)
            | (quads[..., 3] << 24)
        )
    return words.astype(np.uint32)


def _pack_8bit(key: str, src: NDArray[np.uint32]) -> NDArray[np.uint8]:
    height, width, _ = src.shape
    out = np.empty((height, width, 4), dtype=np.uint8)
    r, g, b = src[..., _R], src[..., _G], src[..., _B]
    if key == "argb":  # memory: A, R, G, B
        out[..., 0] = 0xFF
        out[..., 1] = r
        out[..., 2] = g
        out[..., 3] = b
    else:  # bgra, memory: B, G, R, A
        out[..., 0] = b
        out[..., 1] = g
        out[..., 2] = r
        out[..., 3] = 0xFF
    return out.reshape(height, width * 4)


def _unpack_8bit(key: str, data: NDArray[np.uint8]) -> NDArray[np.uint32]:
    height = data.shape[0]
    px = data.reshape(height, -1, 4).astype(np.uint32)
    out = np.empty((height, px.shape[1], 3), dtype=np.uint32)
    if key == "argb":  # A, R, G, B
        out[..., _R], out[..., _G], out[..., _B] = px[..., 1], px[..., 2], px[..., 3]
    else:  # B, G, R, A
        out[..., _R], out[..., _G], out[..., _B] = px[..., 2], px[..., 1], px[..., 0]
    return out


def _rgb10_word(key: str, src: NDArray[np.uint32]) -> NDArray[np.uint32]:
    r, g, b = src[..., _R], src[..., _G], src[..., _B]
    # r210 packs 2:10:10:10; r10b/r10l pack 10:10:10:2.
    words = (
        (r << 20) | (g << 10) | b if key == "r210" else (r << 22) | (g << 12) | (b << 2)
    )
    return words.astype(np.uint32)


def _pack_10bit_rgb(key: str, src: NDArray[np.uint32]) -> NDArray[np.uint8]:
    words = _rgb10_word(key, src)  # (height, width)
    return _u32_to_bytes(words, big_endian=key != "r10l")


def _unpack_10bit_rgb(key: str, data: NDArray[np.uint8]) -> NDArray[np.uint32]:
    height = data.shape[0]
    big = key != "r10l"
    words = _bytes_to_u32(data, big_endian=big)  # (height, width)
    out = np.empty((height, words.shape[1], 3), dtype=np.uint32)
    if key == "r210":
        out[..., _R] = (words >> 20) & 0x3FF
        out[..., _G] = (words >> 10) & 0x3FF
        out[..., _B] = words & 0x3FF
    else:
        out[..., _R] = (words >> 22) & 0x3FF
        out[..., _G] = (words >> 12) & 0x3FF
        out[..., _B] = (words >> 2) & 0x3FF
    return out


def _pack_v210(
    src: NDArray[np.uint32], height: int, num_groups: int
) -> NDArray[np.uint8]:
    g = src.reshape(height, num_groups, 6, 3)
    y = g[..., 0]  # (h, ng, 6) luma per pixel
    cb = g[..., 1]  # chroma sampled at even pixels
    cr = g[..., 2]
    words = np.empty((height, num_groups, 4), dtype=np.uint32)
    words[..., 0] = cb[..., 0] | (y[..., 0] << 10) | (cr[..., 0] << 20)
    words[..., 1] = y[..., 1] | (cb[..., 2] << 10) | (y[..., 2] << 20)
    words[..., 2] = cr[..., 2] | (y[..., 3] << 10) | (cb[..., 4] << 20)
    words[..., 3] = y[..., 4] | (cr[..., 4] << 10) | (y[..., 5] << 20)
    return _u32_to_bytes(words, big_endian=False).reshape(height, num_groups * 16)


def _unpack_v210(
    data: NDArray[np.uint8], height: int, num_groups: int
) -> NDArray[np.uint32]:
    words = _bytes_to_u32(data.reshape(height, num_groups, 16), big_endian=False)
    w0, w1, w2, w3 = words[..., 0], words[..., 1], words[..., 2], words[..., 3]
    out = np.empty((height, num_groups, 6, 3), dtype=np.uint32)
    # Luma, one per pixel.
    out[..., 0, 0] = (w0 >> 10) & 0x3FF
    out[..., 1, 0] = w1 & 0x3FF
    out[..., 2, 0] = (w1 >> 20) & 0x3FF
    out[..., 3, 0] = (w2 >> 10) & 0x3FF
    out[..., 4, 0] = w3 & 0x3FF
    out[..., 5, 0] = (w3 >> 20) & 0x3FF
    # Chroma, shared per pair, replicated to both pixels.
    cb0, cb2, cb4 = w0 & 0x3FF, (w1 >> 10) & 0x3FF, (w2 >> 20) & 0x3FF
    cr0, cr2, cr4 = (w0 >> 20) & 0x3FF, w2 & 0x3FF, (w3 >> 10) & 0x3FF
    for idx, (cb, cr) in enumerate([(cb0, cr0), (cb2, cr2), (cb4, cr4)]):
        out[..., 2 * idx, 1] = cb
        out[..., 2 * idx + 1, 1] = cb
        out[..., 2 * idx, 2] = cr
        out[..., 2 * idx + 1, 2] = cr
    return out.reshape(height, num_groups * 6, 3)


def _pack_12bit(
    key: str,
    src: NDArray[np.uint32],
    height: int,
    num_groups: int,
) -> NDArray[np.uint8]:
    g = src.reshape(height, num_groups, 8, 3)  # (h, ng, pixel, channel)
    out = np.zeros((height, num_groups, 36), dtype=np.uint32)
    for byte_idx, placements in enumerate(_R12B_MAP):
        for pixel, channel, src_lo, nbits, dst_lo in placements:
            val = g[..., pixel, channel]
            out[..., byte_idx] |= ((val >> src_lo) & ((1 << nbits) - 1)) << dst_lo
    out8 = out.astype(np.uint8)
    if key == "r12l":  # byte-reverse within each 4-byte word
        out8 = out8.reshape(height, num_groups, 9, 4)[..., ::-1].reshape(
            height, num_groups, 36
        )
    return out8.reshape(height, num_groups * 36)


def _unpack_12bit(
    key: str,
    data: NDArray[np.uint8],
    height: int,
    num_groups: int,
) -> NDArray[np.uint32]:
    grp = data.reshape(height, num_groups, 36).astype(np.uint32)
    if key == "r12l":  # undo the per-word byte reversal
        grp = grp.reshape(height, num_groups, 9, 4)[..., ::-1].reshape(
            height, num_groups, 36
        )
    out = np.zeros((height, num_groups, 8, 3), dtype=np.uint32)
    for byte_idx, placements in enumerate(_R12B_MAP):
        byte = grp[..., byte_idx]
        for pixel, channel, src_lo, nbits, dst_lo in placements:
            bits = (byte >> dst_lo) & ((1 << nbits) - 1)
            out[..., pixel, channel] |= bits << src_lo
    return out.reshape(height, num_groups * 8, 3)
