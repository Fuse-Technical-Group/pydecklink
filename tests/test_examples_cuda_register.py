"""Smoke tests for ``examples/cuda_register_pinned.py``.

Skips on hosts without cuda-python (the standard devcontainer). Runs
as a real test on CUDA-equipped hosts where ``pip install
pydecklink[cuda-examples]`` has been done.

Verifies the example imports without executing capture, exposes the
documented entry-point, and that its bounded probes match the shape
shared with ``cuda_passthrough.py``.
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
REGISTER_PATH = EXAMPLES_DIR / "cuda_register_pinned.py"


def _load():
    spec = importlib.util.spec_from_file_location(REGISTER_PATH.stem, REGISTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# -- Existence + import + guard -----------------------------------------------


def test_example_file_exists() -> None:
    assert REGISTER_PATH.is_file(), f"missing example: {REGISTER_PATH}"


def test_module_imports() -> None:
    """Importing must not call main() or open any DeckLink device."""
    _load()


def test_main_is_guarded() -> None:
    source = REGISTER_PATH.read_text()
    assert 'if __name__ == "__main__":' in source


def test_uses_cuda_bindings_runtime() -> None:
    source = REGISTER_PATH.read_text()
    assert "from cuda.bindings import runtime" in source or (
        "import cuda.bindings.runtime" in source
    )


# -- Entry-point shape --------------------------------------------------------


def test_run_register_function_exists() -> None:
    mod = _load()
    assert hasattr(mod, "run_register"), "run_register() missing"
    sig = inspect.signature(mod.run_register)
    assert {"device_index", "frame_count"}.issubset(sig.parameters.keys())


# -- Input signal-lock probe (shared shape with cuda_passthrough.py) ----------


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


# -- Input mode auto-detection (bounded probe) -------------------------------


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
