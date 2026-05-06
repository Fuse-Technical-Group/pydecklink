"""Smoke tests for examples/cuda_pinned_pipelined.py and
examples/cuda_register_pinned.py.

Skips on hosts without cuda-python (the standard devcontainer). Runs
as a real test on CUDA-equipped hosts where ``pip install
pydecklink[cuda-examples]`` has been done.

Verifies the example modules import without executing capture and
expose the documented entry-point functions.
"""

from __future__ import annotations

import importlib.util
import inspect
import time
from pathlib import Path

import pytest

# Skip if cuda-python is not installed. This is the expected outcome on
# the standard devcontainer; the test only runs on CUDA hosts.
pytest.importorskip("cuda")
pytest.importorskip("cuda.bindings.runtime")

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
PIPELINED_PATH = EXAMPLES_DIR / "cuda_pinned_pipelined.py"
REGISTER_PATH = EXAMPLES_DIR / "cuda_register_pinned.py"


def _load(path: Path):
    """Load an example as a module without executing main()."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# -- Existence + import + guard checks for both examples ----------------------


@pytest.mark.parametrize("path", [PIPELINED_PATH, REGISTER_PATH])
def test_example_file_exists(path: Path) -> None:
    assert path.is_file(), f"missing example: {path}"


@pytest.mark.parametrize("path", [PIPELINED_PATH, REGISTER_PATH])
def test_module_imports(path: Path) -> None:
    """Importing must not call main() or open any DeckLink device."""
    _load(path)


@pytest.mark.parametrize("path", [PIPELINED_PATH, REGISTER_PATH])
def test_main_is_guarded(path: Path) -> None:
    source = path.read_text()
    assert 'if __name__ == "__main__":' in source


@pytest.mark.parametrize("path", [PIPELINED_PATH, REGISTER_PATH])
def test_uses_cuda_bindings_runtime(path: Path) -> None:
    """Examples must use ``cuda.bindings.runtime``, not the legacy
    ``cuda.cudart`` shim."""
    source = path.read_text()
    assert "from cuda.bindings import runtime" in source or (
        "import cuda.bindings.runtime" in source
    ), f"{path.name} must import cuda.bindings.runtime"


# -- Entry-point function shape ----------------------------------------------


def test_pipelined_run_function_exists() -> None:
    mod = _load(PIPELINED_PATH)
    assert hasattr(mod, "run_pipelined"), "run_pipelined() missing"
    sig = inspect.signature(mod.run_pipelined)
    assert {"device_index", "frame_count", "duration_seconds"}.issubset(
        sig.parameters.keys()
    )


def test_register_run_function_exists() -> None:
    mod = _load(REGISTER_PATH)
    assert hasattr(mod, "run_register"), "run_register() missing"
    sig = inspect.signature(mod.run_register)
    assert {"device_index", "frame_count"}.issubset(sig.parameters.keys())


# -- Input signal-lock probe (shared shape across both examples) -------------


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


@pytest.mark.parametrize("path", [PIPELINED_PATH, REGISTER_PATH])
def test_wait_for_input_signal_returns_true_on_first_locked_frame(
    path: Path,
) -> None:
    mod = _load(path)
    dev = _FakeDev([_FakeCfr(False), _FakeCfr(False), _FakeCfr(True), _FakeCfr(False)])
    assert mod._wait_for_input_signal(dev, timeout_s=2.0) is True
    assert dev.calls == 3


@pytest.mark.parametrize("path", [PIPELINED_PATH, REGISTER_PATH])
def test_wait_for_input_signal_returns_false_on_timeout(path: Path) -> None:
    mod = _load(path)
    dev = _FakeDev([])
    started = time.monotonic()
    assert mod._wait_for_input_signal(dev, timeout_s=0.3) is False
    elapsed = time.monotonic() - started
    assert 0.25 <= elapsed < 1.0


@pytest.mark.parametrize("path", [PIPELINED_PATH, REGISTER_PATH])
def test_wait_for_input_signal_skips_unsignaled_frames(path: Path) -> None:
    mod = _load(path)
    dev = _FakeDev([_FakeCfr(False), None, _FakeCfr(False), _FakeCfr(True)])
    assert mod._wait_for_input_signal(dev, timeout_s=2.0) is True


# -- Input mode auto-detection (shared shape across both examples) -----------


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

        class _Fmt:
            mode = self._format_mode

        return _Fmt()


@pytest.mark.parametrize("path", [PIPELINED_PATH, REGISTER_PATH])
def test_detect_input_mode_returns_format_when_signal_locks(path: Path) -> None:
    import pydecklink as _pdl

    mod = _load(path)
    dev = _DetectingFakeDev(
        frames=[_FakeFrame(False), _FakeFrame(True)],
        format_mode=_pdl.DisplayMode.HD1080p5994,
    )
    result = mod._detect_input_mode(dev, _pdl.PixelFormat.Format10BitYUV, 2.0)
    assert result == _pdl.DisplayMode.HD1080p5994
    # Lifecycle ran in order: enable → start → pop... → stop → disable.
    assert dev.calls[0] == "enable"
    assert dev.calls[1] == "start_streams"
    assert dev.calls[-2:] == ["stop_streams", "disable"]


@pytest.mark.parametrize("path", [PIPELINED_PATH, REGISTER_PATH])
def test_detect_input_mode_raises_on_timeout(path: Path) -> None:
    import pydecklink as _pdl

    mod = _load(path)
    dev = _DetectingFakeDev(frames=[], format_mode=None)
    with pytest.raises(RuntimeError, match="no SDI signal"):
        mod._detect_input_mode(dev, _pdl.PixelFormat.Format10BitYUV, 0.3)
    # Teardown still runs on the timeout path.
    assert dev.calls[-2:] == ["stop_streams", "disable"]


# -- _SelfSource lifecycle (only in the pipelined example) -------------------


def test_self_source_defers_playback_until_explicit_start() -> None:
    """``_SelfSource.__enter__`` must enable output and create the pool
    only — playback must wait for an explicit ``start_playback()``.

    Why: the integration tests show the input device must be listening
    before output starts, otherwise the input fails to lock to the
    signal. If ``__enter__`` started playback, callers couldn't sequence
    "enable output, then enable+start input, then start output" as a
    single ``with`` block.

    Contract: enter → enable + pool, no schedule, no playback.
    ``start_playback()`` → preroll frames + start playback.
    ``schedule_next()`` → one more frame each call. exit → stop + disable.
    """
    import pydecklink as _pdl

    mod = _load(PIPELINED_PATH)

    class _FakeManagedFrame:
        class _Data:
            def __setitem__(self, key: object, value: object) -> None:
                pass

        data = _Data()

    class _FakeOutputDev:
        def __init__(self) -> None:
            self.calls: list[tuple[object, ...]] = []

        def enable_video_output(self, mode: object) -> None:
            self.calls.append(("enable_video_output", mode))

        def row_bytes_for_pixel_format(self, pf: object, width: int) -> int:
            return width * 2

        def create_frame_pool(self, *args: object) -> None:
            self.calls.append(("create_frame_pool", *args))

        def acquire_output_frame(self, timeout_ms: int) -> _FakeManagedFrame:
            self.calls.append(("acquire_output_frame", timeout_ms))
            return _FakeManagedFrame()

        def schedule_output_frame(
            self,
            mf: object,
            display_time: int,
            duration: int,
            timescale: int,
        ) -> None:
            self.calls.append(("schedule_output_frame", display_time))

        def start_scheduled_playback(self, start_time: int, timescale: int) -> None:
            self.calls.append(("start_scheduled_playback", start_time, timescale))

        def stop_scheduled_playback(self) -> None:
            self.calls.append(("stop_scheduled_playback",))

        def disable_video_output(self) -> None:
            self.calls.append(("disable_video_output",))

    fake = _FakeOutputDev()
    mode = _pdl.DisplayMode.HD1080p25
    pf = _pdl.PixelFormat.Format8BitYUV

    with mod._SelfSource(fake, mode, pf) as src:
        assert any(c[0] == "enable_video_output" for c in fake.calls)
        assert any(c[0] == "create_frame_pool" for c in fake.calls)
        assert not any(c[0] == "schedule_output_frame" for c in fake.calls), (
            "frames scheduled before start_playback() — preroll must wait"
        )
        assert not any(c[0] == "start_scheduled_playback" for c in fake.calls), (
            "playback started in __enter__ — must defer to start_playback()"
        )

        src.start_playback()
        scheduled = [c for c in fake.calls if c[0] == "schedule_output_frame"]
        assert len(scheduled) == mod._SelfSource.PREROLL, "preroll count wrong"
        assert any(c[0] == "start_scheduled_playback" for c in fake.calls)

        src.schedule_next()
        scheduled_after = [c for c in fake.calls if c[0] == "schedule_output_frame"]
        assert len(scheduled_after) == mod._SelfSource.PREROLL + 1

    assert any(c[0] == "stop_scheduled_playback" for c in fake.calls), (
        "stop_scheduled_playback not called on exit"
    )
    assert any(c[0] == "disable_video_output" for c in fake.calls), (
        "disable_video_output not called on exit"
    )
