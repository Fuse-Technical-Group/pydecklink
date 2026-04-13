#pragma once

#include <nanobind/nanobind.h>
#include "platform.h"
#include <atomic>
#include <string>

namespace nb = nanobind;

/// Live count of ComPtr instances holding a non-null COM pointer.
/// Incremented when a ComPtr acquires a pointer, decremented when it
/// releases one.  Exposed to Python as _comptr_live() for leak tests.
inline std::atomic<int64_t> g_comptr_live{0};

/// RAII wrapper for COM pointers.
///
/// Tracks all live instances via g_comptr_live.  Pointers acquired through
/// put() are tracked lazily: put() sets a pending flag and the next access
/// (get, operator->, operator bool, destructor) resolves it — incrementing
/// the counter if the pointer became non-null.
template <typename T>
class ComPtr {
public:
    ComPtr() : ptr_(nullptr) {}
    explicit ComPtr(T* p) : ptr_(p) { if (ptr_) g_comptr_live.fetch_add(1, std::memory_order_relaxed); }
    ~ComPtr() {
        resolve_put();
        if (ptr_) {
            g_comptr_live.fetch_sub(1, std::memory_order_relaxed);
            ptr_->Release();
        }
    }
    ComPtr(const ComPtr&) = delete;
    ComPtr& operator=(const ComPtr&) = delete;
    ComPtr(ComPtr&& other) noexcept
        : ptr_(other.ptr_), put_pending_(other.put_pending_) {
        other.ptr_ = nullptr;
        other.put_pending_ = false;
    }
    ComPtr& operator=(ComPtr&& other) noexcept {
        if (this != &other) {
            resolve_put();
            if (ptr_) {
                g_comptr_live.fetch_sub(1, std::memory_order_relaxed);
                ptr_->Release();
            }
            ptr_ = other.ptr_;
            put_pending_ = other.put_pending_;
            other.ptr_ = nullptr;
            other.put_pending_ = false;
        }
        return *this;
    }
    T* get() const { resolve_put(); return ptr_; }
    T** put() {
        resolve_put();
        if (ptr_) {
            g_comptr_live.fetch_sub(1, std::memory_order_relaxed);
            ptr_->Release();
        }
        ptr_ = nullptr;
        put_pending_ = true;
        return &ptr_;
    }
    T* operator->() const { resolve_put(); return ptr_; }
    explicit operator bool() const { resolve_put(); return ptr_ != nullptr; }
    T* detach() {
        resolve_put();
        T* p = ptr_;
        ptr_ = nullptr;
        // Caller takes ownership — counter stays elevated.
        // If they leak it, the counter shows it.
        return p;
    }
private:
    T* ptr_;
    mutable bool put_pending_ = false;
    /// If put() was called and the external writer filled in a non-null
    /// pointer, account for the acquisition now.
    void resolve_put() const {
        if (put_pending_) {
            if (ptr_) g_comptr_live.fetch_add(1, std::memory_order_relaxed);
            put_pending_ = false;
        }
    }
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
