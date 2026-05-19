#include "bind_profile.h"
#include <nanobind/stl/optional.h>
#include <nanobind/stl/vector.h>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

// --- ProfileCallbackAdapter ---

namespace {

// AddRef the raw ``IDeckLinkProfile*`` from an SDK callback parameter
// (the SDK does NOT pre-AddRef in/out params) and wrap it in a
// ``Profile`` ready to hand to Python.
Profile wrap_profile_from_callback(IDeckLinkProfile* raw) {
    if (raw) raw->AddRef();
    return Profile(ComPtr<IDeckLinkProfile>(raw));
}

}  // namespace

HRESULT ProfileCallbackAdapter::ProfileChanging(
        IDeckLinkProfile* profileToBeActivated,
        dlbool_t streamsWillBeForcedToStop) {
    nb::gil_scoped_acquire gil;
    try {
        Profile p = wrap_profile_from_callback(profileToBeActivated);
        ProfileCallback* cb = nb::cast<ProfileCallback*>(user_);
        cb->profile_changing(nb::cast(std::move(p)),
                             static_cast<bool>(streamsWillBeForcedToStop));
    } catch (const std::exception& e) {
        // SDK callbacks must not let exceptions escape — they cross
        // the FFI back into C. Log via Python's stderr and swallow.
        PyErr_WriteUnraisable(user_.ptr());
        (void)e;
    } catch (...) {
        PyErr_WriteUnraisable(user_.ptr());
    }
    return S_OK;
}

HRESULT ProfileCallbackAdapter::ProfileActivated(
        IDeckLinkProfile* activatedProfile) {
    nb::gil_scoped_acquire gil;
    try {
        Profile p = wrap_profile_from_callback(activatedProfile);
        ProfileCallback* cb = nb::cast<ProfileCallback*>(user_);
        cb->profile_activated(nb::cast(std::move(p)));
    } catch (...) {
        PyErr_WriteUnraisable(user_.ptr());
    }
    return S_OK;
}

// --- Module bindings ---

void init_decklink_profile(nb::module_& m, nb::class_<Device>& device) {

    // -- ProfileCallback (Python-subclassable) --
    nb::class_<ProfileCallback, PyProfileCallback>(m, "ProfileCallback",
        "Base class for profile-change callbacks. Subclass and override "
        "``profile_changing`` and/or ``profile_activated``. The SDK invokes "
        "both synchronously on an internal thread; the binding acquires the "
        "GIL before dispatching into Python.")
        .def(nb::init<>())
        .def("profile_changing",
             &ProfileCallback::profile_changing,
             nb::arg("profile"),
             nb::arg("streams_will_be_forced_to_stop"),
             "Called before firmware reconfiguration. The SDK waits for "
             "this method to return before proceeding. Release I/O "
             "interfaces here when ``streams_will_be_forced_to_stop`` is "
             "True.")
        .def("profile_activated",
             &ProfileCallback::profile_activated,
             nb::arg("profile"),
             "Called after firmware reconfiguration completes.");

    // -- Profile --
    nb::class_<Profile>(m, "Profile",
        "Wraps ``IDeckLinkProfile``. A handle to one of a card's "
        "connector profiles.")
        .def_prop_ro("id",
            [](Profile& self) -> _BMDProfileID {
                if (!self.profile)
                    throw std::runtime_error("Profile is null");
                ComPtr<IDeckLinkProfileAttributes> attrs;
                if (self.profile->QueryInterface(IID_IDeckLinkProfileAttributes,
                                                 (void**)attrs.put()) != S_OK)
                    throw std::runtime_error(
                        "Profile does not expose IDeckLinkProfileAttributes");
                int64_t value = 0;
                HRESULT hr = attrs->GetInt(BMDDeckLinkProfileID, &value);
                if (hr != S_OK)
                    throw std::runtime_error(
                        "Failed to read ProfileID (HRESULT " +
                        std::to_string(hr) + ")");
                return static_cast<_BMDProfileID>(value);
            },
            "The profile's identifier.")
        .def_prop_ro("is_active",
            [](Profile& self) -> bool {
                if (!self.profile)
                    throw std::runtime_error("Profile is null");
                dlbool_t active = false;
                HRESULT hr = self.profile->IsActive(&active);
                if (hr != S_OK)
                    throw std::runtime_error(
                        "IsActive failed (HRESULT " + std::to_string(hr) + ")");
                return static_cast<bool>(active);
            },
            "True if this profile is currently active on the card.")
        .def("set_active",
            [](Profile& self) {
                if (!self.profile)
                    throw std::runtime_error("Profile is null");
                HRESULT hr = self.profile->SetActive();
                if (hr != S_OK)
                    throw std::runtime_error(
                        "SetActive failed (HRESULT " + std::to_string(hr) + ")");
            },
            "Request activation of this profile. Returns immediately; "
            "activation completes asynchronously and is signalled via "
            "the registered ``ProfileCallback``.")
        .def("get_peers",
            [](Profile& self) -> std::vector<Profile> {
                if (!self.profile)
                    throw std::runtime_error("Profile is null");
                ComPtr<IDeckLinkProfileIterator> iter;
                HRESULT hr = self.profile->GetPeers(iter.put());
                if (hr != S_OK || !iter)
                    throw std::runtime_error(
                        "GetPeers failed (HRESULT " + std::to_string(hr) + ")");
                std::vector<Profile> peers;
                for (;;) {
                    ComPtr<IDeckLinkProfile> p;
                    if (iter->Next(p.put()) != S_OK || !p) break;
                    peers.emplace_back(std::move(p));
                }
                return peers;
            },
            "Return profiles of peer sub-devices that activate together "
            "when this profile becomes active.")
        .def("__repr__",
            [](Profile& self) {
                return std::string("Profile(") +
                       (self.profile ? "active" : "null") + ")";
            }, nb::sig("def __repr__(self) -> str"));

    // -- ProfileManager --
    nb::class_<ProfileManager>(m, "ProfileManager",
        "Wraps ``IDeckLinkProfileManager``. Created on demand via "
        "``Device.profile_manager``; one per ``IDeckLink``.")
        .def("get_profiles",
            [](ProfileManager& self) -> std::vector<Profile> {
                if (!self.mgr)
                    throw std::runtime_error("ProfileManager is null");
                ComPtr<IDeckLinkProfileIterator> iter;
                HRESULT hr = self.mgr->GetProfiles(iter.put());
                if (hr != S_OK || !iter)
                    throw std::runtime_error(
                        "GetProfiles failed (HRESULT " +
                        std::to_string(hr) + ")");
                std::vector<Profile> out;
                for (;;) {
                    ComPtr<IDeckLinkProfile> p;
                    if (iter->Next(p.put()) != S_OK || !p) break;
                    out.emplace_back(std::move(p));
                }
                return out;
            },
            "Return all profiles available on this device.")
        .def("get_profile",
            [](ProfileManager& self, _BMDProfileID profileID) -> Profile {
                if (!self.mgr)
                    throw std::runtime_error("ProfileManager is null");
                ComPtr<IDeckLinkProfile> profile;
                HRESULT hr = self.mgr->GetProfile(profileID, profile.put());
                if (hr != S_OK || !profile)
                    throw std::runtime_error(
                        "Profile not available (HRESULT " +
                        std::to_string(hr) + ")");
                return Profile(std::move(profile));
            },
            nb::arg("profile_id"),
            "Look up a specific profile by its identifier.")
        .def("set_callback",
            [](ProfileManager& self, std::optional<nb::object> callback) {
                if (!self.mgr)
                    throw std::runtime_error("ProfileManager is null");
                // Clear path: drop the SDK registration, drop our ref.
                if (!callback || callback->is_none()) {
                    self.mgr->SetCallback(nullptr);
                    self.adapter = ComPtr<ProfileCallbackAdapter>();
                    return;
                }
                // Verify the object is a ProfileCallback so the adapter's
                // nb::cast<ProfileCallback*> on the SDK thread can't fail.
                try {
                    (void)nb::cast<ProfileCallback*>(*callback);
                } catch (const nb::cast_error&) {
                    throw std::runtime_error(
                        "callback must be a ProfileCallback (or subclass)");
                }
                // Build the adapter. ctor seats refcount at 1 — adopt
                // into ComPtr without an extra AddRef.
                auto* raw = new ProfileCallbackAdapter(*callback);
                ComPtr<ProfileCallbackAdapter> new_adapter(raw);
                HRESULT hr = self.mgr->SetCallback(new_adapter.get());
                if (hr != S_OK) {
                    throw std::runtime_error(
                        "SetCallback failed (HRESULT " +
                        std::to_string(hr) + ")");
                }
                // Replace any prior adapter only after the SDK accepted
                // the new one; the SDK now holds its own ref.
                self.adapter = std::move(new_adapter);
            },
            nb::arg("callback"),
            "Register a ``ProfileCallback``. Pass ``None`` to clear. "
            "The SDK accepts one callback per manager; subsequent calls "
            "replace prior registrations.")
        .def("__repr__",
            [](ProfileManager& self) {
                return std::string("ProfileManager(") +
                       (self.mgr ? "valid" : "null") + ")";
            }, nb::sig("def __repr__(self) -> str"));

    // -- Device.profile_manager --
    //
    // Cached on first access. The ``ProfileManager`` owns the live
    // ``ProfileCallbackAdapter`` (if any); caching guarantees one
    // wrapper per ``Device``, so a callback registered through any
    // call site survives subsequent ``.profile_manager`` reads.
    //
    // ``reference_internal`` ties the Python wrapper's lifetime to the
    // owning ``Device``, mirroring the cached-once-on-the-C++-side
    // semantics.
    device.def_prop_ro("profile_manager",
        [](Device& self) -> ProfileManager* {
            if (!self.profile_manager_) {
                ComPtr<IDeckLinkProfileManager> mgr;
                if (self.dl->QueryInterface(IID_IDeckLinkProfileManager,
                                             (void**)mgr.put()) != S_OK || !mgr)
                    return nullptr;
                self.profile_manager_ =
                    std::make_unique<ProfileManager>(std::move(mgr));
            }
            return self.profile_manager_.get();
        },
        nb::rv_policy::reference_internal,
        // Override the auto-generated stub: nanobind translates a null
        // raw-pointer return to ``None`` at runtime, but the default
        // stub elides the ``| None``. Spell it out so mypy agrees.
        nb::sig("def profile_manager(self) -> ProfileManager | None"),
        "Return the device's ``ProfileManager``, or ``None`` if the "
        "device is single-profile.");
}
