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
    # ``output_device_index`` is gone — outputs are auto-discovered per
    # §spec:synchronized-output-fanout. ``output_device_indices`` (plural,
    # optional override) replaces it for programmatic callers.
    expected = {
        "input_device_index",
        "output_device_indices",
        "kernel",
        "frame_count",
        "duration_seconds",
    }
    assert expected.issubset(sig.parameters.keys())
    assert "output_device_index" not in sig.parameters


def test_main_cli_drops_output_flag() -> None:
    """The CLI must not accept ``--output`` per §spec — outputs are
    auto-discovered. A leftover flag would silently trump auto-discovery
    and reintroduce the single-output behavior."""
    source = PASSTHROUGH_PATH.read_text()
    assert '"--output"' not in source, "CLI must not accept --output"


def test_kernel_type_alias_matches_documented_signature() -> None:
    """Per §spec:canonical-gpu-passthrough, the kernel callable's
    signature is ``(stream, d_input, d_output, width, height,
    frame_bytes) -> None``. The exported ``KernelFn`` type alias
    encodes that contract — six positional args, ``None`` return."""
    import typing

    mod = _load()
    assert hasattr(mod, "KernelFn"), "KernelFn type alias missing"
    # typing.get_args(Callable[[T1..Tn], R]) -> ([T1..Tn], R): a 2-tuple
    # of (arg-type list, return type).
    arg_types, return_type = typing.get_args(mod.KernelFn)
    assert len(arg_types) == 6, f"expected 6 arg types, got {arg_types!r}"
    # ``get_args`` may report the return type as the literal ``None`` or
    # as ``type(None)`` depending on the Python version; accept either.
    assert return_type in (None, type(None)), "kernel must return None"


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


# -- Output auto-discovery (§spec:synchronized-output-fanout) -----------------


class _FakeDeviceInfo:
    """Stand-in for ``pydecklink.DeviceInfo`` exposing ``index``."""

    def __init__(self, index: int) -> None:
        self.index = index


class _FakeOutputDevice:
    """Stand-in for ``pydecklink.Device`` covering only the surface
    ``_discover_output_indices`` exercises: ``supports_playback`` plus
    the context-manager protocol."""

    def __init__(self, supports_playback: bool) -> None:
        self.supports_playback = supports_playback

    def __enter__(self) -> _FakeOutputDevice:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def test_discover_output_indices_excludes_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On a 4-sub-device card with --input 2, outputs must be [0, 1, 3]."""
    import pydecklink as _pdl

    mod = _load()
    monkeypatch.setattr(
        _pdl, "list_devices", lambda: [_FakeDeviceInfo(i) for i in range(4)]
    )
    monkeypatch.setattr(_pdl, "Device", lambda index: _FakeOutputDevice(True))
    assert mod._discover_output_indices(input_device_index=2) == [0, 1, 3]


def test_discover_output_indices_with_input_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On a 4-sub-device card with --input 0, outputs must be [1, 2, 3].
    Re-running with the input on the other end of the topology must
    pick up the rest, per the §road:cuda-passthrough-fanout verify
    step."""
    import pydecklink as _pdl

    mod = _load()
    monkeypatch.setattr(
        _pdl, "list_devices", lambda: [_FakeDeviceInfo(i) for i in range(4)]
    )
    monkeypatch.setattr(_pdl, "Device", lambda index: _FakeOutputDevice(True))
    assert mod._discover_output_indices(input_device_index=0) == [1, 2, 3]


def test_discover_output_indices_skips_capture_only_devices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Devices without playback capability cannot participate in the
    fanout — they're dropped silently from the discovered list."""
    import pydecklink as _pdl

    mod = _load()
    monkeypatch.setattr(
        _pdl, "list_devices", lambda: [_FakeDeviceInfo(i) for i in range(4)]
    )

    def _device(index: int) -> _FakeOutputDevice:
        # Index 1 is capture-only; 0/2/3 are playback-capable.
        return _FakeOutputDevice(supports_playback=(index != 1))

    monkeypatch.setattr(_pdl, "Device", _device)
    # input=2 -> exclude 2; from {0, 1, 3}, drop 1 (capture-only) -> [0, 3].
    assert mod._discover_output_indices(input_device_index=2) == [0, 3]


def test_discover_output_indices_rejects_out_of_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pydecklink as _pdl

    mod = _load()
    monkeypatch.setattr(
        _pdl, "list_devices", lambda: [_FakeDeviceInfo(i) for i in range(2)]
    )
    monkeypatch.setattr(_pdl, "Device", lambda index: _FakeOutputDevice(True))
    with pytest.raises(ValueError, match="out of range"):
        mod._discover_output_indices(input_device_index=5)


# -- Sync-group configuration (§spec:synchronized-output-fanout) --------------


class _SyncGroupFakeDevice:
    """Stand-in for ``pydecklink.Device`` covering the surface
    ``_configure_sync_group`` calls: ``get_attribute_flag``,
    ``set_config_int``, ``enable_video_output``, plus a ``display_name``
    used in error messages."""

    def __init__(self, supports_sync: bool = True, name: str = "DeckLink") -> None:
        self.supports_sync = supports_sync
        self.display_name = name
        self.config_calls: list[tuple[object, int]] = []
        self.enable_calls: list[tuple[object, int]] = []

    def get_attribute_flag(self, attr_id: object) -> bool:
        return self.supports_sync

    def set_config_int(self, setting: object, value: int) -> None:
        self.config_calls.append((setting, value))

    def enable_video_output(self, mode: object, flags: int = 0) -> None:
        self.enable_calls.append((mode, flags))


def test_configure_sync_group_assigns_group_id_to_every_output() -> None:
    import pydecklink as _pdl

    mod = _load()
    devs = [_SyncGroupFakeDevice() for _ in range(3)]
    mod._configure_sync_group(devs, _pdl.DisplayMode.Mode4K2160p5994, group_id=42)
    for d in devs:
        # PlaybackGroup config set first, then enable_video_output with
        # the SynchronizeToPlaybackGroup flag.
        assert d.config_calls == [(_pdl.ConfigurationID.PlaybackGroup, 42)]
        assert len(d.enable_calls) == 1
        mode, flags = d.enable_calls[0]
        assert mode == _pdl.DisplayMode.Mode4K2160p5994
        assert flags & int(_pdl.VideoOutputFlag.SynchronizeToPlaybackGroup)


def test_configure_sync_group_raises_on_unsupported_device() -> None:
    """If any output lacks SupportsSynchronizeToPlaybackGroup, the
    function must raise BEFORE assigning any group ID — fail fast on
    misconfigured hardware rather than discover it as silent drift."""
    import pydecklink as _pdl

    mod = _load()
    devs = [
        _SyncGroupFakeDevice(supports_sync=True, name="OK"),
        _SyncGroupFakeDevice(supports_sync=False, name="NoSync"),
    ]
    with pytest.raises(RuntimeError, match="SynchronizeToPlaybackGroup"):
        mod._configure_sync_group(devs, _pdl.DisplayMode.Mode4K2160p5994, 42)
    # The capability check runs over every device first; no device gets
    # set_config_int or enable_video_output called.
    for d in devs:
        assert d.config_calls == []
        assert d.enable_calls == []


def test_group_id_mask_fits_int64_signed_range() -> None:
    """The SDK ``int64_t`` range is the bound the example must respect.
    A negative or oversized group ID would either underflow the SDK or
    collide with an unrelated process's group."""
    mod = _load()
    assert mod._GROUP_ID_MASK == (1 << 63) - 1


# -- Sync-group starvation accounting (§spec:synchronized-output-fanout) ------


class _StarvingPoolDev:
    """Stand-in for ``pydecklink.Device`` exposing the bare minimum the
    pipeline acquires from output devices: ``acquire_output_frame`` plus
    a ``display_name`` for the warning message."""

    def __init__(self, frames: int, name: str = "out") -> None:
        self._frames = frames
        self.display_name = name
        self.acquire_calls = 0

    def acquire_output_frame(self, timeout_ms: int) -> object:
        self.acquire_calls += 1
        if self._frames <= 0:
            raise RuntimeError("pool empty")
        self._frames -= 1
        return SimpleNamespace(data=SimpleNamespace(ctypes=SimpleNamespace(data=0)))


def _make_pipeline_for_starvation_test(mod: object) -> object:
    """Build a ``_Pipeline`` instance bypassing CUDA — only the
    starvation accounting paths are exercised."""

    class _StubCudart:
        class cudaMemcpyKind:
            cudaMemcpyDeviceToDevice = 3
            cudaMemcpyHostToDevice = 1
            cudaMemcpyDeviceToHost = 2

        @staticmethod
        def cudaStreamCreate() -> tuple[int, int]:
            return (0, 0)

        @staticmethod
        def cudaMalloc(size: int) -> tuple[int, int]:
            return (0, 0)

        @staticmethod
        def cudaEventCreate() -> tuple[int, int]:
            return (0, 0)

    return mod._Pipeline(
        frame_bytes=1024,
        depth=2,
        kernel=lambda *_: None,
        cudart=_StubCudart(),
        width=1920,
        height=1080,
    )


def test_acquire_all_outputs_returns_mfs_when_all_pools_have_frames() -> None:
    mod = _load()
    pipeline = _make_pipeline_for_starvation_test(mod)
    devs = [_StarvingPoolDev(frames=3) for _ in range(3)]
    result = pipeline._acquire_all_outputs(devs)
    assert result is not None
    assert len(result) == 3
    assert pipeline.sync_group_starvations == 0


def test_acquire_all_outputs_records_starvation_on_partial_acquire(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When the second output's pool is empty but the first's is not,
    the function must return ``None``, increment the starvation
    counter, and emit the WARNING to stderr — once."""
    mod = _load()
    pipeline = _make_pipeline_for_starvation_test(mod)
    devs = [
        _StarvingPoolDev(frames=3, name="primary"),
        _StarvingPoolDev(frames=0, name="starved"),
        _StarvingPoolDev(frames=3, name="tertiary"),
    ]
    assert pipeline._acquire_all_outputs(devs) is None
    assert pipeline.sync_group_starvations == 1
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "starved" in captured.err

    # A second starvation event must increment the counter without
    # re-emitting the warning to stderr.
    devs2 = [
        _StarvingPoolDev(frames=3, name="primary"),
        _StarvingPoolDev(frames=0, name="starved"),
        _StarvingPoolDev(frames=3, name="tertiary"),
    ]
    assert pipeline._acquire_all_outputs(devs2) is None
    assert pipeline.sync_group_starvations == 2
    captured2 = capsys.readouterr()
    assert "WARNING" not in captured2.err


def test_acquire_all_outputs_no_starvation_when_all_pools_empty() -> None:
    """Every pool empty is plain consumer-behind, not sync-group
    starvation. Returns ``None`` without incrementing the counter."""
    mod = _load()
    pipeline = _make_pipeline_for_starvation_test(mod)
    devs = [_StarvingPoolDev(frames=0) for _ in range(3)]
    assert pipeline._acquire_all_outputs(devs) is None
    assert pipeline.sync_group_starvations == 0


def test_acquire_all_outputs_first_dev_starved_others_have_frames() -> None:
    """The first output starved while later outputs have frames is
    sync-group starvation — the asymmetry is what makes it an anomaly,
    not which output happens to be empty."""
    mod = _load()
    pipeline = _make_pipeline_for_starvation_test(mod)
    devs = [
        _StarvingPoolDev(frames=0, name="primary"),
        _StarvingPoolDev(frames=3, name="other"),
    ]
    assert pipeline._acquire_all_outputs(devs) is None
    assert pipeline.sync_group_starvations == 1
