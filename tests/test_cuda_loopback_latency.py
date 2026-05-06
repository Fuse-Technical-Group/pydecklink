"""Smoke tests + pure-Python correctness tests for
``examples/cuda_loopback_latency.py``.

Skips on hosts without cuda-python (the standard devcontainer). Runs
as a real test on CUDA-equipped hosts where ``pip install
pydecklink[cuda-examples]`` has been done.

The unit-testable surface: pure-Python reference implementations of
the fingerprint encode/decode used to validate the CUDA kernels at
review time. Hardware-level RTT verification (1000 frames at 4K59.94
with zero late/dropped/underrun) is the §road:fingerprint-loopback
manual test, not exercised here.
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("cuda")
pytest.importorskip("cuda.bindings.runtime")

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
LATENCY_PATH = EXAMPLES_DIR / "cuda_loopback_latency.py"


def _load():
    spec = importlib.util.spec_from_file_location(LATENCY_PATH.stem, LATENCY_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# -- Existence + import + guard -----------------------------------------------


def test_example_file_exists() -> None:
    assert LATENCY_PATH.is_file(), f"missing example: {LATENCY_PATH}"


def test_module_imports() -> None:
    """Importing must not call main() or open any DeckLink device."""
    _load()


def test_main_is_guarded() -> None:
    source = LATENCY_PATH.read_text()
    assert 'if __name__ == "__main__":' in source


def test_uses_cuda_bindings_runtime() -> None:
    source = LATENCY_PATH.read_text()
    assert "from cuda.bindings import runtime" in source or (
        "import cuda.bindings.runtime" in source
    )


# -- Entry-point shape --------------------------------------------------------


def test_run_loopback_function_exists() -> None:
    mod = _load()
    assert hasattr(mod, "run_loopback")
    sig = inspect.signature(mod.run_loopback)
    expected = {
        "output_device_index",
        "input_device_index",
        "frame_count",
        "duration_seconds",
    }
    assert expected.issubset(sig.parameters.keys())


def test_default_mode_is_4k60() -> None:
    """SPEC §spec:latency-characterization.Scope: primary mode is 4K59.94."""
    import pydecklink as _pdl

    mod = _load()
    assert _pdl.DisplayMode.Mode4K2160p5994 == mod._DEFAULT_MODE


def test_default_pixel_format_is_10bit_yuv() -> None:
    """SPEC §spec:latency-characterization."Why 10-bit YUV (v210),
    not 8-bit": v210 is the standard production capture format and the
    repo-wide default."""
    import pydecklink as _pdl

    mod = _load()
    assert _pdl.PixelFormat.Format10BitYUV == mod._DEFAULT_PIXEL_FORMAT


# -- v210 packing helpers -----------------------------------------------------


def test_v210_pack_unpack_roundtrip() -> None:
    mod = _load()
    word = mod._v210_pack(0x123, 0x2AB, 0x3FF)
    c0, c1, c2 = mod._v210_unpack(word)
    assert (c0, c1, c2) == (0x123, 0x2AB, 0x3FF)


def test_v210_pack_masks_to_10_bits() -> None:
    """Components above 0x3FF are silently truncated to fit 10 bits."""
    mod = _load()
    word = mod._v210_pack(0xFFFF, 0xFFFF, 0xFFFF)
    c0, c1, c2 = mod._v210_unpack(word)
    assert (c0, c1, c2) == (0x3FF, 0x3FF, 0x3FF)


def test_v210_word_top_two_bits_zero() -> None:
    """v210 reserves the top 2 bits of each 32-bit word."""
    mod = _load()
    word = mod._v210_pack(0x3FF, 0x3FF, 0x3FF)
    assert word & 0xC0000000 == 0


# -- Fingerprint encode / decode (pure-Python reference) ----------------------


def test_encode_writes_seq_into_v210_luma_slots() -> None:
    """Each byte of a 64-bit little-endian sequence number lands in the
    low 8 bits of one of the first 8 v210 luma slots, spread across
    two 16-byte v210 groups. Chroma slots stay at neutral 0x200.
    """
    mod = _load()
    buf = bytearray(64)  # initialized to zero
    seq = 0x0807060504030201
    mod._encode_fingerprint_cpu(buf, seq)
    # Decode the 8 v210 words and check luma slot positions.
    words = [int.from_bytes(buf[4 * i : 4 * i + 4], "little") for i in range(8)]
    cb0, y0, cr0 = mod._v210_unpack(words[0])
    y1, cb2, y2 = mod._v210_unpack(words[1])
    cr2, y3, cb4 = mod._v210_unpack(words[2])
    y4, cr4, y5 = mod._v210_unpack(words[3])
    expected = seq.to_bytes(8, "little")
    assert (y0 & 0xFF, y1 & 0xFF, y2 & 0xFF, y3 & 0xFF, y4 & 0xFF, y5 & 0xFF) == (
        expected[0],
        expected[1],
        expected[2],
        expected[3],
        expected[4],
        expected[5],
    )
    # Group 1 luma 0/1 hold seq[6]/seq[7].
    cb0g1, y6, cr0g1 = mod._v210_unpack(words[4])
    y7, cb2g1, _y_unused = mod._v210_unpack(words[5])
    assert (y6 & 0xFF, y7 & 0xFF) == (expected[6], expected[7])
    # Chroma slots are neutral.
    for c in (cb0, cr0, cb2, cr2, cb4, cr4, cb0g1, cr0g1, cb2g1):
        assert c == 0x200, f"chroma slot not neutral: {c:#x}"
    # Bytes after offset 32 are untouched.
    assert all(b == 0 for b in buf[32:])


def test_decode_recovers_encoded_seq() -> None:
    mod = _load()
    seq = 0xDEADBEEFCAFEBABE
    buf = bytearray(64)
    mod._encode_fingerprint_cpu(buf, seq)
    assert mod._decode_fingerprint_cpu(buf) == seq


def test_encode_decode_roundtrip_many() -> None:
    mod = _load()
    rng = np.random.default_rng(0xC0FFEE)
    samples = rng.integers(0, 2**64, size=100, dtype=np.uint64)
    for seq in samples:
        buf = bytearray(32)
        mod._encode_fingerprint_cpu(buf, int(seq))
        assert mod._decode_fingerprint_cpu(buf) == int(seq)


def test_decode_handles_zero_seq() -> None:
    mod = _load()
    buf = bytearray(32)
    mod._encode_fingerprint_cpu(buf, 0)
    assert mod._decode_fingerprint_cpu(buf) == 0


def test_decode_handles_max_seq() -> None:
    mod = _load()
    buf = bytearray(32)
    mod._encode_fingerprint_cpu(buf, 2**64 - 1)
    assert mod._decode_fingerprint_cpu(buf) == 2**64 - 1


# -- Stats ---------------------------------------------------------------------


def test_percentiles_handles_empty() -> None:
    mod = _load()
    out = mod._percentiles([], (50.0, 95.0, 99.0))
    assert out == {50.0: 0.0, 95.0: 0.0, 99.0: 0.0}


def test_percentiles_known_distribution() -> None:
    mod = _load()
    samples = list(range(100))  # 0..99
    out = mod._percentiles(samples, (50.0, 95.0, 99.0))
    # Nearest-rank style percentile (matches cuda_pinned_pipelined helper).
    assert out[50.0] == pytest.approx(49.5, abs=1.0)
    assert out[95.0] == pytest.approx(94.05, abs=1.0)
    assert out[99.0] == pytest.approx(98.01, abs=1.0)


# -- NVRTC kernels -------------------------------------------------------------


def test_kernel_source_compiles() -> None:
    """The embedded CUDA source must compile via NVRTC. A failure here
    means the kernel is malformed before any device launch."""
    pytest.importorskip("cuda.bindings.nvrtc")
    mod = _load()
    assert hasattr(mod, "_KERNEL_SOURCE")
    assert "encode" in mod._KERNEL_SOURCE
    assert "decode" in mod._KERNEL_SOURCE
    # Compile via NVRTC; the helper raises on compile failure.
    ptx = mod._compile_kernel_source(mod._KERNEL_SOURCE)
    assert isinstance(ptx, bytes)
    assert len(ptx) > 0
