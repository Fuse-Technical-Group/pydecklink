"""Tests for pydecklink.api_version — Desktop Video runtime version.

The binding exposes ``IDeckLinkAPIInformation::GetInt(BMDDeckLinkAPIVersion)``
as a structured ``APIVersion`` value. The packed 32-bit field encodes
four byte-sized parts (major.minor.sub.extra, high to low). When
Desktop Video is not installed, ``api_version()`` raises
``RuntimeError``; that path is covered by the install-guidance string in
``bind_api_info.cpp`` but is not faked here — every host that runs the
populated-path tests has the runtime loaded.

The whole module is gated on actual runtime availability, not the
build-time ``HAS_SDK`` flag. Hosted CI runners build *with* the SDK
headers (vendored) but *without* Desktop Video installed — exactly
the case where ``api_version()`` raises by design — so a HAS_SDK
gate would let the populated-path tests run on a host that cannot
satisfy them.
"""

import pytest

import pydecklink

try:
    pydecklink.api_version()
    _RUNTIME_AVAILABLE = True
except (RuntimeError, AttributeError):
    # RuntimeError: Desktop Video runtime not installed.
    # AttributeError: built without SDK headers — api_version absent.
    _RUNTIME_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _RUNTIME_AVAILABLE,
    reason="Desktop Video runtime not installed",
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
