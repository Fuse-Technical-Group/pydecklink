"""Smoke tests for ``examples/detect_signals.py``.

Covers the ``ref=`` formatting helper (`_reference_info`) and the
module's import/guard shape. The reference-lock surface (SPEC §5.11,
§road:detect-signals-report-reference-status) needs physical hardware
to exercise end-to-end; these tests drive the formatting logic with a
fake device so the three reportable states — ``locked@<mode>``,
``unlocked``, ``n/a`` — are verifiable on any host.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pydecklink

EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "examples" / "detect_signals.py"


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


# -- _reference_info ----------------------------------------------------------


class _FakeDev:
    """Stand-in for ``pydecklink.Device`` exposing only the attribute
    surface ``_reference_info`` touches: ``get_attribute_flag`` (for
    HasReferenceInput) and the ``reference_status`` property."""

    def __init__(self, has_ref: bool, ref_status: object) -> None:
        self._has_ref = has_ref
        self._ref_status = ref_status

    def get_attribute_flag(self, attr_id: object) -> bool:
        assert attr_id == pydecklink.AttributeID.HasReferenceInput
        return self._has_ref

    @property
    def reference_status(self) -> object:
        if not self._has_ref:
            raise RuntimeError("Device has no reference input")
        return self._ref_status


def test_reference_info_no_ref_input() -> None:
    mod = _load()
    dev = _FakeDev(has_ref=False, ref_status=None)
    assert mod._reference_info(dev) == "n/a"


def test_reference_info_unlocked() -> None:
    mod = _load()
    status = SimpleNamespace(locked=False, mode=None, flags=0)
    dev = _FakeDev(has_ref=True, ref_status=status)
    assert mod._reference_info(dev) == "unlocked"


def test_reference_info_locked_with_mode() -> None:
    mod = _load()
    status = SimpleNamespace(
        locked=True, mode=pydecklink.DisplayMode.HD1080p25, flags=0
    )
    dev = _FakeDev(has_ref=True, ref_status=status)
    assert mod._reference_info(dev) == "locked@HD1080p25"


def test_reference_info_locked_mode_unknown_reports_unlocked() -> None:
    """A locked status whose mode maps to None (bmdModeUnknown) reports
    ``unlocked`` — there is no resolvable reference mode to show."""
    mod = _load()
    status = SimpleNamespace(locked=True, mode=None, flags=0)
    dev = _FakeDev(has_ref=True, ref_status=status)
    assert mod._reference_info(dev) == "unlocked"
