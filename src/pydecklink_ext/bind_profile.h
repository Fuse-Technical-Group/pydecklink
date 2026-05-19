#pragma once

#include <nanobind/nanobind.h>
#include <nanobind/trampoline.h>
#include "bind_device.h"
#include <atomic>

namespace nb = nanobind;

/// Python-subclassable trampoline for ``IDeckLinkProfileCallback``.
///
/// Split from the COM-side ``ProfileCallbackAdapter`` deliberately:
/// nanobind's trampoline vtable cannot coexist with the SDK's
/// ``IUnknown`` vtable on a single class. The Python class is the
/// public face; the adapter is an internal forwarder.
struct ProfileCallback {
    virtual ~ProfileCallback() = default;
    virtual void profile_changing(nb::object profile,
                                  bool streams_will_be_forced_to_stop) {
        (void)profile;
        (void)streams_will_be_forced_to_stop;
    }
    virtual void profile_activated(nb::object profile) {
        (void)profile;
    }
};

struct PyProfileCallback : ProfileCallback {
    NB_TRAMPOLINE(ProfileCallback, 2);
    void profile_changing(nb::object profile,
                          bool streams_will_be_forced_to_stop) override {
        NB_OVERRIDE(profile_changing, profile, streams_will_be_forced_to_stop);
    }
    void profile_activated(nb::object profile) override {
        NB_OVERRIDE(profile_activated, profile);
    }
};

/// Internal ``IDeckLinkProfileCallback`` COM implementation. Holds a
/// Python reference to the user's ``ProfileCallback``; forwards SDK
/// callbacks into Python after acquiring the GIL.
///
/// SDK threads have undefined GIL state — the forwarder must take
/// the GIL itself before touching ``user_``.
class ProfileCallbackAdapter : public IDeckLinkProfileCallback {
public:
    explicit ProfileCallbackAdapter(nb::object user)
        : ref_count_(1), user_(std::move(user)) {}

    // IUnknown
    HRESULT QueryInterface(REFIID, void**) override { return E_NOINTERFACE; }
    ULONG AddRef() override { return ++ref_count_; }
    ULONG Release() override {
        ULONG c = --ref_count_;
        if (c == 0) {
            // ``user_`` is an nb::object — dropping it requires the
            // GIL. The adapter may be Released from an SDK thread.
            nb::gil_scoped_acquire gil;
            delete this;
        }
        return c;
    }

    HRESULT ProfileChanging(IDeckLinkProfile* profileToBeActivated,
                            dlbool_t streamsWillBeForcedToStop) override;
    HRESULT ProfileActivated(IDeckLinkProfile* activatedProfile) override;

private:
    std::atomic<ULONG> ref_count_;
    nb::object user_;  // GIL required to touch / destroy.
};

/// Lightweight ``IDeckLinkProfile`` wrapper.
struct Profile {
    ComPtr<IDeckLinkProfile> profile;

    Profile() = default;
    explicit Profile(ComPtr<IDeckLinkProfile> p) : profile(std::move(p)) {}
};

/// Lightweight ``IDeckLinkProfileManager`` wrapper. Holds a strong ref
/// to the live adapter (if any) so ``Device::~Device`` can break the
/// SDK->adapter->Python ref chain.
struct ProfileManager {
    ComPtr<IDeckLinkProfileManager> mgr;
    // The SDK retains its own ref via ``SetCallback``; this ComPtr
    // exists so ``Device`` can call ``mgr->SetCallback(nullptr)`` and
    // drop the adapter cleanly when the device is torn down.
    ComPtr<ProfileCallbackAdapter> adapter;

    ProfileManager() = default;
    explicit ProfileManager(ComPtr<IDeckLinkProfileManager> m)
        : mgr(std::move(m)) {}
};

void init_decklink_profile(nb::module_& m, nb::class_<Device>& device);
