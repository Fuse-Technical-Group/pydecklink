"""Tests for profile-change-notification bindings.

Two layers:

* Shape tests (no hardware): class existence, subclassability, base-method
  no-op behaviour, ``Device.profile_manager`` reachable on a constructed
  ``Device`` (skipped if no device present).
* Hardware test (``@pytest.mark.hardware``): drives a real profile
  switch on a multi-profile DeckLink card (8K Pro is canonical) and
  asserts ``profile_changing`` and ``profile_activated`` both fire.
"""

from __future__ import annotations

import threading

import pytest

import pydecklink

pytestmark = pytest.mark.skipif(
    not getattr(pydecklink, "HAS_SDK", False),
    reason="Built without DeckLink SDK headers",
)


# ---- shape tests -----------------------------------------------------------


class TestSurfaceExists:
    """The new classes are importable from the package."""

    def test_profile_class_exists(self) -> None:
        assert hasattr(pydecklink, "Profile")

    def test_profile_manager_class_exists(self) -> None:
        assert hasattr(pydecklink, "ProfileManager")

    def test_profile_callback_class_exists(self) -> None:
        assert hasattr(pydecklink, "ProfileCallback")


class TestProfileCallbackSubclass:
    """``ProfileCallback`` is subclassable and overrides are dispatched.

    The base-class methods accept a ``Profile`` argument; constructing a
    ``Profile`` from pure Python is not supported (it wraps an SDK COM
    interface), so direct invocation of the base methods is exercised
    by the hardware test, not here.
    """

    def test_subclass_can_be_instantiated(self) -> None:
        class MyCb(pydecklink.ProfileCallback):
            pass

        # Instantiation alone exercises the trampoline machinery.
        MyCb()

    def test_override_dispatch_through_python(self) -> None:
        # Overrides defined in a subclass are reachable through a base
        # reference. Sentinel object stands in for the Profile so we
        # avoid touching the SDK.
        class Sentinel:
            pass

        seen: list[tuple[str, object]] = []

        class MyCb(pydecklink.ProfileCallback):
            def profile_changing(
                self,
                profile: object,
                streams_will_be_forced_to_stop: bool,
            ) -> None:
                seen.append(("changing", streams_will_be_forced_to_stop))

            def profile_activated(self, profile: object) -> None:
                seen.append(("activated", profile))

        cb: pydecklink.ProfileCallback = MyCb()
        sentinel = Sentinel()
        # Bypass the bound method's nanobind signature check by calling
        # the Python-side method directly.
        type(cb).profile_changing(cb, sentinel, True)  # type: ignore[arg-type]
        type(cb).profile_activated(cb, sentinel)  # type: ignore[arg-type]
        assert seen == [("changing", True), ("activated", sentinel)]


class TestDeviceProfileManager:
    """``Device.profile_manager`` returns a ``ProfileManager`` when hardware
    is present. Skipped otherwise — this is a shape probe, not a
    functional test."""

    def test_profile_manager_property_present(self) -> None:
        try:
            count = pydecklink.device_count()
        except RuntimeError:
            pytest.skip("DeckLink driver not installed")
        if count == 0:
            pytest.skip("No DeckLink hardware present")

        dev = pydecklink.Device(0)
        # Single-profile cards return None; multi-profile cards return
        # a ``ProfileManager``. Both are valid — we only check the type
        # contract.
        mgr = dev.profile_manager
        assert mgr is None or isinstance(mgr, pydecklink.ProfileManager)


# ---- hardware test ---------------------------------------------------------


@pytest.mark.hardware
def test_profile_callback_fires_on_real_switch() -> None:
    """End-to-end: register a callback, switch profile, assert both
    ``profile_changing`` and ``profile_activated`` fire on the target
    device within 10 seconds. Restores the original profile on exit.

    Requires a multi-profile DeckLink card (8K Pro). Skipped on hosts
    without one.
    """
    try:
        count = pydecklink.device_count()
    except RuntimeError:
        pytest.skip("DeckLink driver not installed")
    if count == 0:
        pytest.skip("No DeckLink hardware present")

    dev = pydecklink.Device(0)
    mgr = dev.profile_manager
    if mgr is None:
        pytest.skip("Device has no profile manager (single-profile card)")

    profiles = list(mgr.get_profiles())
    if len(profiles) < 2:
        pytest.skip("Device has fewer than two profiles")

    original_id = dev.active_profile()
    target = next((p for p in profiles if p.id != original_id), None)
    assert target is not None, "No alternate profile found despite len>=2"

    changing_evt = threading.Event()
    activated_evt = threading.Event()
    observed: dict[str, object] = {}

    class Capture(pydecklink.ProfileCallback):
        def profile_changing(
            self,
            profile: pydecklink.Profile,
            streams_will_be_forced_to_stop: bool,
        ) -> None:
            observed["changing_id"] = profile.id
            observed["forced"] = streams_will_be_forced_to_stop
            changing_evt.set()

        def profile_activated(self, profile: pydecklink.Profile) -> None:
            observed["activated_id"] = profile.id
            activated_evt.set()

    cb = Capture()
    mgr.set_callback(cb)
    try:
        target.set_active()
        assert changing_evt.wait(10.0), "profile_changing did not fire"
        assert activated_evt.wait(10.0), "profile_activated did not fire"
        assert observed["changing_id"] == target.id
        assert observed["activated_id"] == target.id
        assert isinstance(observed["forced"], bool)
    finally:
        # Restore. Wait for the restore activation before clearing the
        # callback so the SDK never invokes a freed adapter.
        restored = threading.Event()

        class Restore(pydecklink.ProfileCallback):
            def profile_activated(self, profile: pydecklink.Profile) -> None:
                if profile.id == original_id:
                    restored.set()

        mgr.set_callback(Restore())
        mgr.get_profile(original_id).set_active()
        restored.wait(10.0)
        mgr.set_callback(None)
