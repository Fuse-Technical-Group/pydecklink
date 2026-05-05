"""Tests for the (model, profile, sub_device_index) → SDI label table.

Pure-function tests of the lookup logic — no DeckLink hardware
required. Hardware-level verification of ``Device.connector_label``
lives under ``tests/test_decklink_integration.py`` (hardware marker).
"""

from __future__ import annotations

import pytest

import pydecklink
from pydecklink._connectors import _SDI_LABEL, lookup


class TestLookup:
    """Static-table lookups."""

    def test_8k_pro_four_sub_device_transposition(self):
        # The whole point of the table: sub_device_index → SDI port
        # is non-identity on the 8K Pro in 4-sub-device mode.
        assert lookup("DeckLink 8K Pro", "FourSubDevicesHalfDuplex", 0) == "SDI 1"
        assert lookup("DeckLink 8K Pro", "FourSubDevicesHalfDuplex", 1) == "SDI 3"
        assert lookup("DeckLink 8K Pro", "FourSubDevicesHalfDuplex", 2) == "SDI 2"
        assert lookup("DeckLink 8K Pro", "FourSubDevicesHalfDuplex", 3) == "SDI 4"

    def test_8k_pro_two_sub_device_paired(self):
        assert lookup("DeckLink 8K Pro", "TwoSubDevicesFullDuplex", 0) == "SDI 1+2"
        assert lookup("DeckLink 8K Pro", "TwoSubDevicesFullDuplex", 1) == "SDI 3+4"

    def test_quad_2_eight_sub_devices(self):
        # Odd ports first, then even.
        assert lookup("DeckLink Quad 2", "TwoSubDevicesHalfDuplex", 0) == "SDI 1"
        assert lookup("DeckLink Quad 2", "TwoSubDevicesHalfDuplex", 3) == "SDI 7"
        assert lookup("DeckLink Quad 2", "TwoSubDevicesHalfDuplex", 4) == "SDI 2"
        assert lookup("DeckLink Quad 2", "TwoSubDevicesHalfDuplex", 7) == "SDI 8"

    def test_duo_2(self):
        assert lookup("DeckLink Duo 2", "TwoSubDevicesHalfDuplex", 0) == "SDI 1"
        assert lookup("DeckLink Duo 2", "TwoSubDevicesHalfDuplex", 1) == "SDI 3"

    def test_unknown_model_returns_none(self):
        assert lookup("DeckLink Mini Recorder", "OneSubDeviceFullDuplex", 0) is None

    def test_unknown_profile_returns_none(self):
        # 8K Pro in a profile not in the table.
        assert lookup("DeckLink 8K Pro", "OneSubDeviceFullDuplex", 0) is None

    def test_out_of_range_sub_index_returns_none(self):
        assert lookup("DeckLink 8K Pro", "FourSubDevicesHalfDuplex", 99) is None

    def test_model_prefix_match(self):
        # Lookup uses startswith — driver-version suffixes shouldn't break it.
        assert lookup("DeckLink 8K Pro Foo", "FourSubDevicesHalfDuplex", 0) == "SDI 1"


class TestTableShape:
    """Invariants the table itself must satisfy."""

    def test_no_duplicate_keys(self):
        # dict construction enforces this, but make it explicit.
        keys = list(_SDI_LABEL.keys())
        assert len(keys) == len(set(keys))

    @pytest.mark.parametrize("entry", list(_SDI_LABEL.items()))
    def test_label_format(self, entry):
        (_model, _profile, _idx), label = entry
        # Either single port "SDI N" or paired "SDI N+M".
        assert label.startswith("SDI ")
        rest = label[4:]
        for part in rest.split("+"):
            assert part.isdigit(), f"non-numeric port in {label}"

    @pytest.mark.parametrize("entry", list(_SDI_LABEL.items()))
    def test_profile_name_is_real(self, entry):
        (_model, profile, _idx), _label = entry
        # Profile name must be a member of pydecklink.ProfileID enum.
        assert profile in {p.name for p in pydecklink.ProfileID}


class TestModuleFunction:
    """``pydecklink.connector_label`` is wired and behaves correctly."""

    def test_function_exists(self):
        assert callable(pydecklink.connector_label)

    def test_function_has_docstring(self):
        assert pydecklink.connector_label.__doc__
        assert "SDI" in pydecklink.connector_label.__doc__
