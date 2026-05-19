#pragma once

#include <nanobind/nanobind.h>
#include "platform.h"
#include "comptr.h"
#include <memory>
#include <stdexcept>
#include <string>

namespace nb = nanobind;

/// Get an IDeckLinkIterator, throwing if the driver is not installed.
/// Uniform across platforms: on Windows CreateDeckLinkIteratorInstance
/// returns ComPtr and the move ctor is selected; on Linux/Mac the SDK
/// returns raw IDeckLinkIterator* and the explicit T* ctor is selected.
inline ComPtr<IDeckLinkIterator> require_iterator() {
    ComPtr<IDeckLinkIterator> iter(CreateDeckLinkIteratorInstance());
    if (!iter)
        throw std::runtime_error(
            "DeckLink driver not installed (CreateDeckLinkIteratorInstance returned NULL). "
            "Install Desktop Video from blackmagicdesign.com.");
    return iter;
}

// Forward declarations for callback types (defined in bind_output.cpp / bind_input.cpp / bind_profile.cpp).
class OutputCallback;
class InputCallback;
struct ProfileManager;

/// Lightweight device info returned by list_devices().
struct DeviceInfo {
    std::string model_name;
    std::string display_name;
    int index;
};

/// Python-visible Device class wrapping IDeckLink.
/// Sub-interfaces (output, input) are acquired lazily and stored here
/// so that multiple binding files can access them.
struct Device {
    ComPtr<IDeckLink> dl;

    // Output state (managed by bind_output.cpp).
    ComPtr<IDeckLinkOutput> output_;
    ComPtr<OutputCallback> output_callback_;

    // Input state (managed by bind_input.cpp).
    ComPtr<IDeckLinkInput> input_;
    ComPtr<InputCallback> input_callback_;

    // Profile state (managed by bind_profile.cpp). Cached on first
    // access to ``profile_manager`` so a single ``ProfileManager``
    // owns the live ``ProfileCallbackAdapter`` for this device's
    // lifetime; ``~Device`` clears the SDK registration and drops the
    // adapter before the wrapper falls out of scope. ``unique_ptr`` so
    // the forward declaration above is sufficient.
    std::unique_ptr<ProfileManager> profile_manager_;

    Device(int index);
    ~Device();  // Explicit teardown drops SDK callback refs to avoid cycles.

    std::string model_name() const;
    std::string display_name() const;
    bool supports_capture() const;
    bool supports_playback() const;
    bool supports_input_format_detection() const;
    bool supports_hdr() const;
};

/// Initialize device bindings and return the Device class handle
/// so that other init functions can add methods to it.
nb::class_<Device> init_decklink_device(nb::module_& m);
