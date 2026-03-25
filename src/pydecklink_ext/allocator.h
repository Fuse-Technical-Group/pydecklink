#pragma once

#include "DeckLinkAPI.h"
#include "bind_device.h"
#include <atomic>
#include <cstdlib>
#include <functional>
#include <mutex>
#include <stdexcept>
#include <vector>

/// Custom allocation function signature.
/// Allocates `size` bytes and returns a pointer to the memory.
/// Must return nullptr on failure.
using AllocFn = std::function<void*(size_t)>;

/// Custom deallocation function signature.
using FreeFn = std::function<void(void*, size_t)>;

/// A managed video buffer backed by externally allocated memory.
/// Implements IDeckLinkVideoBuffer so the DeckLink SDK can use it
/// for both input (via allocator provider) and output (via
/// CreateVideoFrameWithBuffer).
class ManagedBuffer : public IDeckLinkVideoBuffer {
public:
    ManagedBuffer(size_t size, void* data, FreeFn free_fn)
        : ref_count_(1), size_(size), data_(data), free_fn_(std::move(free_fn)) {}

    ~ManagedBuffer() {
        if (data_ && free_fn_) {
            free_fn_(data_, size_);
        }
    }

    // IUnknown
    HRESULT QueryInterface(REFIID, void**) override { return E_NOINTERFACE; }
    ULONG AddRef() override { return ++ref_count_; }
    ULONG Release() override {
        ULONG c = --ref_count_;
        if (c == 0) delete this;
        return c;
    }

    // IDeckLinkVideoBuffer
    HRESULT GetBytes(void** buffer) override {
        if (!buffer) return E_INVALIDARG;
        *buffer = data_;
        return S_OK;
    }

    HRESULT StartAccess(BMDBufferAccessFlags) override { return S_OK; }
    HRESULT EndAccess(BMDBufferAccessFlags) override { return S_OK; }

    size_t size() const { return size_; }
    void* data() const { return data_; }

private:
    std::atomic<ULONG> ref_count_;
    size_t size_;
    void* data_;
    FreeFn free_fn_;
};

/// Implements IDeckLinkVideoBufferAllocator.
/// Allocates ManagedBuffer instances using a configurable allocation
/// function. Defaults to malloc/free. Can be configured to use
/// CUDA cudaHostAlloc or any other allocator.
class VideoBufferAllocator : public IDeckLinkVideoBufferAllocator {
public:
    VideoBufferAllocator(size_t buffer_size,
                         AllocFn alloc_fn = nullptr,
                         FreeFn free_fn = nullptr)
        : ref_count_(1), buffer_size_(buffer_size),
          alloc_fn_(alloc_fn ? std::move(alloc_fn) : default_alloc),
          free_fn_(free_fn ? std::move(free_fn) : default_free) {}

    // IUnknown
    HRESULT QueryInterface(REFIID, void**) override { return E_NOINTERFACE; }
    ULONG AddRef() override { return ++ref_count_; }
    ULONG Release() override {
        ULONG c = --ref_count_;
        if (c == 0) delete this;
        return c;
    }

    // IDeckLinkVideoBufferAllocator
    HRESULT AllocateVideoBuffer(IDeckLinkVideoBuffer** allocatedBuffer) override {
        if (!allocatedBuffer) return E_INVALIDARG;

        void* mem = alloc_fn_(buffer_size_);
        if (!mem) return E_OUTOFMEMORY;

        auto* buf = new ManagedBuffer(buffer_size_, mem, free_fn_);
        *allocatedBuffer = buf;

        {
            std::lock_guard<std::mutex> lock(mutex_);
            ++allocated_count_;
        }

        return S_OK;
    }

    size_t buffer_size() const { return buffer_size_; }

    size_t allocated_count() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return allocated_count_;
    }

    /// Allocate a ManagedBuffer and return it (for Python use).
    ManagedBuffer* allocate_managed() {
        IDeckLinkVideoBuffer* buf = nullptr;
        HRESULT hr = AllocateVideoBuffer(&buf);
        if (hr != S_OK || !buf)
            throw std::runtime_error("AllocateVideoBuffer failed");
        // buf is a ManagedBuffer*; safe to static_cast.
        return static_cast<ManagedBuffer*>(buf);
    }

private:
    std::atomic<ULONG> ref_count_;
    size_t buffer_size_;
    AllocFn alloc_fn_;
    FreeFn free_fn_;
    mutable std::mutex mutex_;
    size_t allocated_count_ = 0;

    static void* default_alloc(size_t size) { return std::malloc(size); }
    static void default_free(void* ptr, size_t) { std::free(ptr); }
};

/// Implements IDeckLinkVideoBufferAllocatorProvider.
/// Creates VideoBufferAllocator instances on demand, caching by buffer_size
/// so the SDK reuses allocators for the same format.
class VideoBufferAllocatorProvider : public IDeckLinkVideoBufferAllocatorProvider {
public:
    VideoBufferAllocatorProvider(AllocFn alloc_fn = nullptr, FreeFn free_fn = nullptr)
        : ref_count_(1),
          alloc_fn_(alloc_fn),
          free_fn_(free_fn) {}

    // IUnknown
    HRESULT QueryInterface(REFIID, void**) override { return E_NOINTERFACE; }
    ULONG AddRef() override { return ++ref_count_; }
    ULONG Release() override {
        ULONG c = --ref_count_;
        if (c == 0) delete this;
        return c;
    }

    // IDeckLinkVideoBufferAllocatorProvider
    HRESULT GetVideoBufferAllocator(
            uint32_t bufferSize, uint32_t /*width*/, uint32_t /*height*/,
            uint32_t /*rowBytes*/, BMDPixelFormat /*pixelFormat*/,
            IDeckLinkVideoBufferAllocator** allocator) override {
        if (!allocator) return E_INVALIDARG;

        std::lock_guard<std::mutex> lock(mutex_);

        // Check cache for existing allocator with this buffer size.
        for (auto& cached : allocators_) {
            if (cached->buffer_size() == bufferSize) {
                cached->AddRef();
                *allocator = cached;
                return S_OK;
            }
        }

        // Create new allocator.
        auto* alloc = new VideoBufferAllocator(bufferSize, alloc_fn_, free_fn_);
        allocators_.push_back(alloc);
        alloc->AddRef(); // One ref for the cache, one for the caller.
        *allocator = alloc;
        return S_OK;
    }

    /// Python-facing: get or create an allocator for the given parameters.
    VideoBufferAllocator* get_allocator_py(
            uint32_t bufferSize, uint32_t width, uint32_t height,
            uint32_t rowBytes, BMDPixelFormat pixelFormat) {
        IDeckLinkVideoBufferAllocator* alloc = nullptr;
        HRESULT hr = GetVideoBufferAllocator(
            bufferSize, width, height, rowBytes, pixelFormat, &alloc);
        if (hr != S_OK || !alloc)
            throw std::runtime_error("GetVideoBufferAllocator failed");
        return static_cast<VideoBufferAllocator*>(alloc);
    }

    ~VideoBufferAllocatorProvider() override {
        for (auto* a : allocators_)
            a->Release();
    }

private:
    std::atomic<ULONG> ref_count_;
    AllocFn alloc_fn_;
    FreeFn free_fn_;
    std::mutex mutex_;
    std::vector<VideoBufferAllocator*> allocators_;  // Cached allocators (owned via ref count).
};
