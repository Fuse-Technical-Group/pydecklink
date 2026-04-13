#pragma once

#include <nanobind/nanobind.h>
#include "platform.h"
#include <string>

namespace nb = nanobind;

/// RAII wrapper for COM pointers.
template <typename T>
class ComPtr {
public:
    ComPtr() : ptr_(nullptr) {}
    explicit ComPtr(T* p) : ptr_(p) {}
    ~ComPtr() { if (ptr_) ptr_->Release(); }
    ComPtr(const ComPtr&) = delete;
    ComPtr& operator=(const ComPtr&) = delete;
    ComPtr(ComPtr&& other) noexcept : ptr_(other.ptr_) { other.ptr_ = nullptr; }
    ComPtr& operator=(ComPtr&& other) noexcept {
        if (this != &other) {
            if (ptr_) ptr_->Release();
            ptr_ = other.ptr_;
            other.ptr_ = nullptr;
        }
        return *this;
    }
    T* get() const { return ptr_; }
    T** put() { return &ptr_; }
    T* operator->() const { return ptr_; }
    explicit operator bool() const { return ptr_ != nullptr; }
    T* release() { T* p = ptr_; ptr_ = nullptr; return p; }
private:
    T* ptr_;
};

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
    OutputCallback* output_callback_ = nullptr;

    // Input state (managed by bind_input.cpp).
    ComPtr<IDeckLinkInput> input_;
    InputCallback* input_callback_ = nullptr;

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
