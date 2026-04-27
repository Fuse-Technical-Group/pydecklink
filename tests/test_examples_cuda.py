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
