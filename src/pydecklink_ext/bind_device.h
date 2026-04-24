#pragma once

#include <nanobind/nanobind.h>
#include "platform.h"
#include "comptr.h"
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

// Forward declarations for callback types (defined in bind_output.cpp / bind_input.cpp).
class OutputCallback;
class InputCallback;

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

    Device(int index);

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
