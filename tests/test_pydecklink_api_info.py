"""Tests for pydecklink.api_version — Desktop Video runtime version.

The binding exposes ``IDeckLinkAPIInformation::GetInt(BMDDeckLinkAPIVersion)``
as a structured ``APIVersion`` value. The packed 32-bit field encodes
four byte-sized parts (major.minor.sub.extra, high to low). When
Desktop Video is not installed, ``api_version()`` raises
``RuntimeError``; that path is covered by the install-guidance string in
``bind_api_info.cpp`` but is not faked here — every host that runs the
populated-path tests has the runtime loaded, and CI without the SDK
skips the whole module.
"""

import pytest

import pydecklink

pytestmark = pytest.mark.skipif(
    not getattr(pydecklink, "HAS_SDK", False),
    reason="Built without DeckLink SDK headers",
)


class TestAPIVersion:
    """``api_version()`` returns a populated APIVersion when the runtime loads."""

    def test_function_exists(self):
        assert callable(pydecklink.api_version)

    def test_returns_api_version_instance(self):
        v = pydecklink.api_version()
        assert isinstance(v, pydecklink.APIVersion)

    def test_parts_are_bytes(self):
        v = pydecklink.api_version()
        for part_name in ("major", "minor", "sub", "extra"):
            part = getattr(v, part_name)
            assert isinstance(part, int)
            assert 0 <= part <= 255, f"{part_name}={part} outside [0, 255]"

    def test_parts_compose_to_packed(self):
        v = pydecklink.api_version()
        recomposed = (v.major << 24) | (v.minor << 16) | (v.sub << 8) | v.extra
        assert recomposed == v.packed & 0xFFFFFFFF

    def test_string_is_non_empty(self):
        v = pydecklink.api_version()
        assert isinstance(v.string, str)
        assert v.string

    def test_str_returns_string_field(self):
        v = pydecklink.api_version()
        assert str(v) == v.string

    def test_repr_includes_string(self):
        v = pydecklink.api_version()
        assert v.string in repr(v)
