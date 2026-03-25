"""Tests for pydecklink device bindings (no hardware required)."""

import pydecklink


class TestDeviceClassExists:
    """Device class is importable and has expected attributes."""

    def test_device_class_exists(self):
        assert hasattr(pydecklink, "Device")

    def test_device_count_exists(self):
        assert callable(pydecklink.device_count)

    def test_list_devices_exists(self):
        assert callable(pydecklink.list_devices)


class TestDeviceCountNoHardware:
    """device_count returns 0 when no DeckLink hardware is present."""

    def test_device_count_returns_int(self):
        # May return 0 (no hardware) or raise RuntimeError (no driver).
        # Both are acceptable in CI.
        try:
            count = pydecklink.device_count()
            assert isinstance(count, int)
            assert count >= 0
        except RuntimeError:
            # No DeckLink driver installed — acceptable in CI.
            pass


class TestListDevicesNoHardware:
    """list_devices returns empty list when no DeckLink hardware is present."""

    def test_list_devices_returns_list(self):
        try:
            devices = pydecklink.list_devices()
            assert isinstance(devices, list)
        except RuntimeError:
            pass


class TestDeviceInfo:
    """DeviceInfo is importable."""

    def test_device_info_exists(self):
        assert hasattr(pydecklink, "DeviceInfo")
