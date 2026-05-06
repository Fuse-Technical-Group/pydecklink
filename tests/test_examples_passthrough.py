"""Smoke tests for ``examples/passthrough.py``.

Covers the bounded format-detection probe and the public entry shape.
The example is non-CUDA, so this test runs everywhere.
"""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path
from types import SimpleNamespace

EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "examples" / "passthrough.py"


def _load():
    spec = importlib.util.spec_from_file_location(EXAMPLE_PATH.stem, EXAMPLE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# -- Existence + import + guard -----------------------------------------------


def test_example_file_exists() -> None:
    assert EXAMPLE_PATH.is_file(), f"missing example: {EXAMPLE_PATH}"


def test_module_imports() -> None:
    """Importing must not call main() or open any DeckLink device."""
    _load()


def test_main_is_guarded() -> None:
    source = EXAMPLE_PATH.read_text()
    assert 'if __name__ == "__main__":' in source


# -- _poll_for_format_detection ------------------------------------------------


class _FakeFrame:
    __slots__ = ("has_signal",)

    def __init__(self, has_signal: bool) -> None:
        self.has_signal = has_signal


class _FakeDev:
    """Stand-in for ``pydecklink.Device`` exposing only
    ``pop_capture_frame`` and ``current_input_format``. Each call to
    ``pop_capture_frame`` pops the next item from ``frames``; ``None``
    simulates a pop timeout (and sleeps for ``timeout_ms``)."""

    def __init__(
        self,
        frames: list[object | None],
        format_mode: object | None = None,
    ) -> None:
        self._frames = list(frames)
        self.calls = 0
        self._format_mode = format_mode

    def pop_capture_frame(self, timeout_ms: int) -> object | None:
        self.calls += 1
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


def test_poll_returns_mode_when_signal_and_format_known() -> None:
    import pydecklink as _pdl

    mod = _load()
    dev = _FakeDev(
        frames=[_FakeFrame(False), _FakeFrame(True)],
        format_mode=_pdl.DisplayMode.HD1080p5994,
    )
    result = mod._poll_for_format_detection(dev, timeout_s=2.0)
    assert result == _pdl.DisplayMode.HD1080p5994


def test_poll_returns_none_on_timeout() -> None:
    mod = _load()
    dev = _FakeDev(frames=[], format_mode=None)
    started = time.monotonic()
    assert mod._poll_for_format_detection(dev, timeout_s=0.3) is None
    elapsed = time.monotonic() - started
    assert 0.25 <= elapsed < 1.0


# -- _preroll_capture_to_output -----------------------------------------------


class _FakeCapDev:
    """Stand-in for ``pydecklink.Device`` exposing only
    ``pop_capture_frame_ref``."""

    def __init__(self, frames: list[object | None]) -> None:
        self._frames = list(frames)

    def pop_capture_frame_ref(self, timeout_ms: int) -> object | None:
        if not self._frames:
            time.sleep(timeout_ms / 1000.0)
            return None
        f = self._frames.pop(0)
        if f is None:
            time.sleep(timeout_ms / 1000.0)
        return f


class _FakeOutDev:
    """Stand-in for ``pydecklink.Device`` exposing only
    ``schedule_capture_frame``. Records each call."""

    def __init__(self) -> None:
        self.scheduled: list[tuple[int, int, int]] = []

    def schedule_capture_frame(
        self,
        frame: object,
        display_time: int,
        duration: int,
        timescale: int,
    ) -> None:
        self.scheduled.append((display_time, duration, timescale))


def test_preroll_schedules_count_frames_at_consecutive_times() -> None:
    mod = _load()
    cap = _FakeCapDev(frames=[_FakeFrame(True), _FakeFrame(True), _FakeFrame(True)])
    out = _FakeOutDev()
    mod._preroll_capture_to_output(
        cap_dev=cap,
        out_dev=out,
        preroll_count=3,
        frame_duration=1000,
        frame_timescale=60000,
        timeout_s=2.0,
    )
    assert out.scheduled == [
        (0, 1000, 60000),
        (1000, 1000, 60000),
        (2000, 1000, 60000),
    ]


def test_preroll_skips_unsignaled_frames() -> None:
    mod = _load()
    cap = _FakeCapDev(
        frames=[
            _FakeFrame(False),
            None,
            _FakeFrame(False),
            _FakeFrame(True),
            _FakeFrame(True),
        ]
    )
    out = _FakeOutDev()
    mod._preroll_capture_to_output(
        cap_dev=cap,
        out_dev=out,
        preroll_count=2,
        frame_duration=1000,
        frame_timescale=60000,
        timeout_s=2.0,
    )
    assert len(out.scheduled) == 2


def test_preroll_raises_on_timeout() -> None:
    mod = _load()
    cap = _FakeCapDev(frames=[])  # nothing ever arrives
    out = _FakeOutDev()
    started = time.monotonic()
    try:
        mod._preroll_capture_to_output(
            cap_dev=cap,
            out_dev=out,
            preroll_count=3,
            frame_duration=1000,
            frame_timescale=60000,
            timeout_s=0.3,
        )
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "0/3 frames" in str(exc)
    elapsed = time.monotonic() - started
    assert 0.25 <= elapsed < 1.0
    assert out.scheduled == []


def test_poll_skips_unknown_format_until_known_arrives() -> None:
    """A signaled frame whose ``current_input_format.mode`` is Unknown
    is not enough — keep polling until format detection completes."""
    import pydecklink as _pdl

    mod = _load()

    class _DriftingDev(_FakeDev):
        def __init__(self) -> None:
            super().__init__(
                frames=[_FakeFrame(True), _FakeFrame(True)],
                format_mode=_pdl.DisplayMode.Unknown,
            )

        @property
        def current_input_format(self) -> object | None:
            # First call: Unknown; subsequent calls: a known mode.
            if self.calls <= 1:
                return SimpleNamespace(mode=_pdl.DisplayMode.Unknown)
            return SimpleNamespace(mode=_pdl.DisplayMode.HD1080p5994)

    dev = _DriftingDev()
    result = mod._poll_for_format_detection(dev, timeout_s=2.0)
    assert result == _pdl.DisplayMode.HD1080p5994
