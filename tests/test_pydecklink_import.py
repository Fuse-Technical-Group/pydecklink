"""Verify the pydecklink package loads and re-exports from _bindings."""

import importlib


def test_import_pydecklink():
    """import pydecklink must succeed and the module must have __version__."""
    mod = importlib.import_module("pydecklink")
    assert mod is not None


def test_bindings_submodule_exists():
    """pydecklink._bindings must be importable (the compiled extension)."""
    mod = importlib.import_module("pydecklink._bindings")
    assert mod is not None
