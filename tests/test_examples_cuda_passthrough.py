"""Smoke tests for ``examples/cuda_passthrough.py``.

Skips on hosts without cuda-python (the standard devcontainer). Runs
as a real test on CUDA-equipped hosts where ``pip install
pydecklink[cuda-examples]`` has been done.

Verifies the example imports without executing capture, exposes the
documented entry points, and that its bounded probes match the shape
shared with the other CUDA examples.
"""

from __future__ import annotations

import importlib.util
import inspect
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("cuda")
pytest.importorskip("cuda.bindings.runtime")

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
PASSTHROUGH_PATH = EXAMPLES_DIR / "cuda_passthrough.py"


def _load():
    spec = importlib.util.spec_from_file_location(
        PASSTHROUGH_PATH.stem, PASSTHROUGH_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# -- Existence + import + guard -----------------------------------------------


def test_example_file_exists() -> None:
    assert PASSTHROUGH_PATH.is_file(), f"missing example: {PASSTHROUGH_PATH}"


def test_module_imports() -> None:
    """Importing must not call main() or open any DeckLink device."""
    _load()


def test_main_is_guarded() -> None:
    source = PASSTHROUGH_PATH.read_text()
    assert 'if __name__ == "__main__":' in source


def test_uses_cuda_bindings_runtime() -> None:
    source = PASSTHROUGH_PATH.read_text()
    assert "from cuda.bindings import runtime" in source or (
        "import cuda.bindings.runtime" in source
    )


# -- Defaults: 4K59.94 / 10-bit YUV per §spec:canonical-gpu-passthrough -------


def test_default_mode_is_4k60() -> None:
    import pydecklink as _pdl

    mod = _load()
    assert _pdl.DisplayMode.Mode4K2160p5994 == mod._DEFAULT_MODE


def test_default_pixel_format_is_10bit_yuv() -> None:
    import pydecklink as _pdl

    mod = _load()
    assert _pdl.PixelFormat.Format10BitYUV == mod._DEFAULT_PIXEL_FORMAT


# -- Entry-point shape --------------------------------------------------------


def test_run_passthrough_function_exists() -> None:
    mod = _load()
    assert hasattr(mod, "run_passthrough"), "run_passthrough() missing"
    sig = inspect.signature(mod.run_passthrough)
    expected = {
        "input_device_index",
        "output_device_index",
        "kernel",
        "frame_count",
        "duration_seconds",
    }
    assert expected.issubset(sig.parameters.keys())


def test_kernel_type_alias_matches_documented_signature() -> None:
    """Per §spec:canonical-gpu-passthrough, the kernel callable's
    signature is ``(stream, d_input, d_output, width, height,
    frame_bytes) -> None``. The exported ``KernelFn`` type alias
    encodes that contract — six positional args, ``None`` return."""
    import typing

    mod = _load()
    assert hasattr(mod, "KernelFn"), "KernelFn type alias missing"
    args = typing.get_args(mod.KernelFn)
    # Callable[[T1, ..., T6], R] -> (T1, ..., T6, R) under get_args.
    assert len(args) == 7, f"expected 6 args + return type, got {args!r}"
    assert args[-1] is type(None), "kernel must return None"


def test_run_passthrough_default_kernel_is_none() -> None:
    """``kernel=None`` triggers the identity-kernel default at runtime
    (built inside ``run_passthrough`` once cudart is imported). Keeping
    the parameter default ``None`` avoids importing cuda-python at
    module-load time, which would break the unit-test harness on hosts
    without it."""
    mod = _load()
    sig = inspect.signature(mod.run_passthrough)
    assert sig.parameters["kernel"].default is None


def test_make_identity_kernel_returns_six_arg_callable() -> None:
    """``_make_identity_kernel(cudart)`` produces the runtime identity
    closure. Verify the returned callable's signature matches the
    documented seam — six args, no return — using a stub cudart."""

    class _StubCudart:
        class cudaMemcpyKind:
            cudaMemcpyDeviceToDevice = 3

        @staticmethod
        def cudaMemcpyAsync(*_args: object) -> tuple[int]:
            return (0,)

    mod = _load()
    fn = mod._make_identity_kernel(_StubCudart())
    fn_sig = inspect.signature(fn)
    assert {
        "stream",
        "d_input",
        "d_output",
        "width",
        "height",
        "frame_bytes",
    }.issubset(fn_sig.parameters.keys())


# -- Input signal-lock probe (shared shape with other CUDA examples) ----------


class _FakeCfr:
    __slots__ = ("has_signal",)

    def __init__(self, has_signal: bool) -> None:
        self.has_signal = has_signal


class _FakeDev:
    """Minimal stand-in for ``pydecklink.Device`` exposing only
    ``pop_capture_frame_ref``. Each call pops the next item from
    ``frames``; ``None`` simulates a pop timeout (and sleeps for
    ``timeout_ms`` so probe wall time matches reality)."""

    def __init__(self, frames: list[object | None]) -> None:
        self._frames = list(frames)
        self.calls = 0

    def pop_capture_frame_ref(self, timeout_ms: int) -> object | None:
        self.calls += 1
        if not self._frames:
            time.sleep(timeout_ms / 1000.0)
            return None
        cfr = self._frames.pop(0)
        if cfr is None:
            time.sleep(timeout_ms / 1000.0)
        return cfr


def test_wait_for_input_signal_returns_true_on_first_locked_frame() -> None:
    mod = _load()
    dev = _FakeDev([_FakeCfr(False), _FakeCfr(False), _FakeCfr(True), _FakeCfr(False)])
    assert mod._wait_for_input_signal(dev, timeout_s=2.0) is True
    assert dev.calls == 3


def test_wait_for_input_signal_returns_false_on_timeout() -> None:
    mod = _load()
    dev = _FakeDev([])
    started = time.monotonic()
    assert mod._wait_for_input_signal(dev, timeout_s=0.3) is False
    elapsed = time.monotonic() - started
    assert 0.25 <= elapsed < 1.0


def test_wait_for_input_signal_skips_unsignaled_frames() -> None:
    mod = _load()
    dev = _FakeDev([_FakeCfr(False), None, _FakeCfr(False), _FakeCfr(True)])
    assert mod._wait_for_input_signal(dev, timeout_s=2.0) is True


# -- Input mode auto-detection (bounded probe per §spec) ---------------------


class _FakeFrame:
    __slots__ = ("has_signal",)

    def __init__(self, has_signal: bool) -> None:
        self.has_signal = has_signal


class _DetectingFakeDev:
    """Stand-in for ``pydecklink.Device`` exposing the surface that
    ``_detect_input_mode`` calls: enable/start/pop/format/stop/disable.
    Records lifecycle calls so tests can assert teardown ran."""

    def __init__(
        self,
        frames: list[object | None],
        format_mode: object | None = None,
    ) -> None:
        self._frames = list(frames)
        self.calls: list[str] = []
        self._format_mode = format_mode

    def enable_video_input(
        self, mode: object, pixel_format: object, flags: object = None
    ) -> None:
        self.calls.append("enable")

    def start_streams(self) -> None:
        self.calls.append("start_streams")

    def stop_streams(self) -> None:
        self.calls.append("stop_streams")

    def disable_video_input(self) -> None:
        self.calls.append("disable")

    def pop_capture_frame(self, timeout_ms: int) -> object | None:
        self.calls.append("pop")
        if not self._frames:
            time.sleep(timeout_ms / 1000.0)
            return None
        f = self._frames.pop(0)
        if f is None:
            time.sleep(timeout_ms / 1000.0)
        return f

    @property
    def current_input_format(self) -> object | None:
        if self._format_mode is None:
            return None
        return SimpleNamespace(mode=self._format_mode)


def test_detect_input_mode_returns_format_when_signal_locks() -> None:
    import pydecklink as _pdl

    mod = _load()
    dev = _DetectingFakeDev(
        frames=[_FakeFrame(False), _FakeFrame(True)],
        format_mode=_pdl.DisplayMode.HD1080p5994,
    )
    result = mod._detect_input_mode(dev, _pdl.PixelFormat.Format10BitYUV, 2.0)
    assert result == _pdl.DisplayMode.HD1080p5994
    assert dev.calls[0] == "enable"
    assert dev.calls[1] == "start_streams"
    assert dev.calls[-2:] == ["stop_streams", "disable"]


def test_detect_input_mode_raises_on_timeout() -> None:
    import pydecklink as _pdl

    mod = _load()
    dev = _DetectingFakeDev(frames=[], format_mode=None)
    with pytest.raises(RuntimeError, match="no SDI signal"):
        mod._detect_input_mode(dev, _pdl.PixelFormat.Format10BitYUV, 0.3)
    # Teardown still runs on the timeout path.
    assert dev.calls[-2:] == ["stop_streams", "disable"]


# -- Defensive: same-device rejection, matching cuda_loopback_latency.py ------


def test_run_passthrough_rejects_same_device_for_input_and_output() -> None:
    mod = _load()
    with pytest.raises(ValueError, match="must differ"):
        mod.run_passthrough(input_device_index=2, output_device_index=2)
