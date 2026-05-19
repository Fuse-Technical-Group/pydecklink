"""Tests for profile-change-notification bindings.

Two layers:

* Shape tests (no hardware): class existence, subclassability, base-method
  no-op behaviour, ``Device.profile_manager`` reachable on a constructed
  ``Device`` (skipped if no device present).
* Hardware test (``@pytest.mark.hardware``): cycles through every
  profile on a multi-profile DeckLink card (8K Pro is canonical) and
  asserts ``profile_changing`` and ``profile_activated`` fire on each
  transition with the correct ``Profile``.
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


class _CaptureCallback(pydecklink.ProfileCallback):
    """Records the most recent ``profile_changing`` / ``profile_activated``
    invocations and exposes events so the test can wait for each phase."""

    def __init__(self) -> None:
        super().__init__()
        self.changing_evt = threading.Event()
        self.activated_evt = threading.Event()
        self.changing_id: object = None
        self.forced: object = None
        self.activated_id: object = None

    def profile_changing(
        self,
        profile: pydecklink.Profile,
        streams_will_be_forced_to_stop: bool,
    ) -> None:
        self.changing_id = profile.id
        self.forced = streams_will_be_forced_to_stop
        self.changing_evt.set()

    def profile_activated(self, profile: pydecklink.Profile) -> None:
        self.activated_id = profile.id
        self.activated_evt.set()


def _switch_and_verify(
    mgr: pydecklink.ProfileManager,
    target: pydecklink.Profile,
) -> None:
    """Register a fresh capture callback, drive ``target.set_active()``,
    assert both callbacks fire with ``profile.id == target.id`` within
    10 seconds. Re-registers a fresh callback each call so the test
    exercises ``set_callback`` replacement on every transition."""
    cb = _CaptureCallback()
    mgr.set_callback(cb)
    target.set_active()
    assert cb.changing_evt.wait(10.0), f"profile_changing did not fire for {target.id}"
    assert cb.activated_evt.wait(10.0), (
        f"profile_activated did not fire for {target.id}"
    )
    assert cb.changing_id == target.id, (
        f"profile_changing fired with {cb.changing_id}, expected {target.id}"
    )
    assert cb.activated_id == target.id, (
        f"profile_activated fired with {cb.activated_id}, expected {target.id}"
    )
    assert isinstance(cb.forced, bool)


@pytest.mark.hardware
def test_profile_callback_cycles_through_profiles() -> None:
    """End-to-end: cycle through every profile on a multi-profile card,
    asserting ``profile_changing`` and ``profile_activated`` fire with
    the correct target ``Profile`` on each transition. Restores the
    original profile on exit.

    Cycling (rather than a single switch + restore) exercises
    ``set_callback`` replacement, guards against silent no-ops if the
    card is left on the previously-targeted profile by an earlier run,
    and walks the full profile state space the card supports.

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

    # Visit every non-current profile, then end on the original. The
    # ``get_profile`` lookup re-resolves the COM pointer fresh each
    # iteration so we don't rely on iterator-bound ``Profile`` lifetimes.
    targets = [p.id for p in profiles if p.id != original_id] + [original_id]
    try:
        for target_id in targets:
            _switch_and_verify(mgr, mgr.get_profile(target_id))
            assert dev.active_profile() == target_id, (
                f"active_profile() reports {dev.active_profile()} after "
                f"activating {target_id}"
            )
    finally:
        # Defensive restore: if a mid-cycle assertion fired, ensure the
        # card ends on the profile it started on. Wait for activation
        # before clearing the callback so the SDK never invokes a freed
        # adapter.
        if dev.active_profile() != original_id:
            restore_cb = _CaptureCallback()
            mgr.set_callback(restore_cb)
            mgr.get_profile(original_id).set_active()
            restore_cb.activated_evt.wait(10.0)
        mgr.set_callback(None)
