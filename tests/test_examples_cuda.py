"""Smoke test for examples/cuda_pinned_capture.py.

Skips on hosts without cuda-python (the devcontainer). Runs as a real
test on CUDA-equipped hosts where `pip install pydecklink[cuda-examples]`
has been done.

Verifies the example module imports without executing capture and
exposes the documented pattern functions.
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

import pytest

# Skip if cuda-python is not installed. This is the expected outcome on
# the standard devcontainer; the test only runs on CUDA hosts.
pytest.importorskip("cuda")
pytest.importorskip("cuda.bindings.runtime")

EXAMPLE_PATH = (
    Path(__file__).resolve().parent.parent / "examples" / "cuda_pinned_capture.py"
)


def _load_example():
    """Load the example file as a module without executing main()."""
    spec = importlib.util.spec_from_file_location(
        "cuda_pinned_capture", EXAMPLE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_example_file_exists() -> None:
    assert EXAMPLE_PATH.is_file(), f"missing example: {EXAMPLE_PATH}"


def test_module_imports() -> None:
    """Importing must not call main() or open any DeckLink device."""
    _load_example()


def test_alloc_pattern_function_exists() -> None:
    mod = _load_example()
    assert hasattr(mod, "run_alloc_mode"), "run_alloc_mode() missing"
    sig = inspect.signature(mod.run_alloc_mode)
    # Expected parameters: device_index, mode, pixel_format, frame_count.
    assert {"device_index", "frame_count"}.issubset(sig.parameters.keys())


def test_register_pattern_function_exists() -> None:
    mod = _load_example()
    assert hasattr(mod, "run_register_mode"), "run_register_mode() missing"
    sig = inspect.signature(mod.run_register_mode)
    assert {"device_index", "frame_count"}.issubset(sig.parameters.keys())


def test_uses_cuda_bindings_runtime() -> None:
    """The example must import cuda.bindings.runtime (not the legacy
    `cuda.cudart` shim)."""
    source = EXAMPLE_PATH.read_text()
    assert "from cuda.bindings import runtime" in source or (
        "import cuda.bindings.runtime" in source
    ), "example must import cuda.bindings.runtime"


def test_main_is_guarded() -> None:
    """main() must not run at import time."""
    source = EXAMPLE_PATH.read_text()
    assert 'if __name__ == "__main__":' in source


def test_self_source_defers_playback_until_explicit_start() -> None:
    """``_SelfSource.__enter__`` must enable output and create the pool
    only — playback must wait for an explicit ``start_playback()``.

    Why: the integration tests show the input device must be listening
    before output starts, otherwise the input fails to lock to the
    signal. If ``__enter__`` started playback, callers couldn't sequence
    "enable output, then enable+start input, then start output" as a
    single ``with`` block.

    Contract verified here: enter → enable + pool, no schedule, no
    playback. ``start_playback()`` → preroll frames + start playback.
    ``schedule_next()`` → one more frame each call. exit → stop + disable.
    """
    import pydecklink as _pdl

    mod = _load_example()

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

        def start_scheduled_playback(
            self, start_time: int, timescale: int
        ) -> None:
            self.calls.append(("start_scheduled_playback", start_time, timescale))

        def stop_scheduled_playback(self) -> None:
            self.calls.append(("stop_scheduled_playback",))

        def disable_video_output(self) -> None:
            self.calls.append(("disable_video_output",))

    fake = _FakeOutputDev()
    mode = _pdl.DisplayMode.HD1080p25
    pf = _pdl.PixelFormat.Format8BitYUV

    with mod._SelfSource(fake, mode, pf) as src:
        # On enter: output enabled and pool created, but NO frames
        # scheduled and NO playback started yet.
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


def test_capture_with_progress_counts_only_valid_frames() -> None:
    """`_capture_with_progress` must skip None and no-signal frames and
    invoke the on_frame callback only for valid frames. Without this,
    the example's main loop has no observable progress when the input
    signal is missing — it appears hung.
    """
    mod = _load_example()

    class _FakeFrame:
        def __init__(self, has_signal: bool) -> None:
            self.has_signal = has_signal

    class _FakeDev:
        def __init__(self) -> None:
            # Two no-signal returns, then two valid frames.
            self._frames = [
                None,
                _FakeFrame(has_signal=False),
                _FakeFrame(has_signal=True),
                _FakeFrame(has_signal=True),
            ]
            self._idx = 0

        def pop_capture_frame_ref(self, timeout_ms: int):
            if self._idx >= len(self._frames):
                return None
            f = self._frames[self._idx]
            self._idx += 1
            return f

    import signal

    prev_handler = signal.getsignal(signal.SIGINT)
    seen: list[object] = []
    try:
        captured, interrupted = mod._capture_with_progress(
            _FakeDev(), frame_count=2, on_frame=seen.append
        )
    finally:
        signal.signal(signal.SIGINT, prev_handler)
    assert captured == 2
    assert interrupted is False
    assert len(seen) == 2
    assert all(getattr(f, "has_signal", False) for f in seen)
