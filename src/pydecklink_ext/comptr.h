#pragma once

/// RAII wrapper for COM pointers.
///
/// Ownership semantics:
///   - ComPtr(T*) adopts the pointer (no AddRef) — matches COM out-param
///     conventions where the callee has already AddRef'd.
///   - Copy constructor / copy assignment AddRef — standard COM shared
///     ownership. Prefer passing by `const ComPtr<T>&` to avoid churn.
///   - Move constructor / move assignment transfer ownership (no AddRef).
///   - Destructor calls Release.
template <typename T>
class ComPtr {
public:
    ComPtr() : ptr_(nullptr) {}
    explicit ComPtr(T* p) : ptr_(p) {}
    ~ComPtr() { if (ptr_) ptr_->Release(); }

    ComPtr(const ComPtr& other) : ptr_(other.ptr_) {
        if (ptr_) ptr_->AddRef();
    }
    ComPtr& operator=(const ComPtr& other) {
        if (this != &other) {
            if (other.ptr_) other.ptr_->AddRef();
            if (ptr_) ptr_->Release();
            ptr_ = other.ptr_;
        }
        return *this;
    }

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
private:
    T* ptr_;
};
