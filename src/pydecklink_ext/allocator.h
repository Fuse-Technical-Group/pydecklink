#pragma once

#include "DeckLinkAPI.h"
#include "comptr.h"
#include <atomic>
#include <cstdlib>
#include <cstring>
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

class VideoBufferAllocator;

/// A managed video buffer backed by externally allocated memory.
/// Implements IDeckLinkVideoBuffer so the DeckLink SDK can use it
/// for both input (via allocator provider) and output (via
/// CreateVideoFrameWithBuffer).
///
/// On COM `Release()` reaching zero, the buffer returns to its parent
/// allocator's free-list rather than freeing its memory. The buffer's
/// memory is freed only when the parent allocator is destroyed. See
/// SPEC §4 — buffer recycling.
class ManagedBuffer : public IDeckLinkVideoBuffer {
public:
    ManagedBuffer(VideoBufferAllocator* parent, size_t size, void* data);

    // IUnknown
    HRESULT QueryInterface(REFIID iid, void** ppv) override {
        // Per SPEC §2.5.55, the SDK wraps our buffer into its own video
        // frame and may call QueryInterface to obtain interface
        // pointers. Returning E_NOINTERFACE for IUnknown / our own
        // interface violates COM and triggers SDK-internal stalls
        // when the input pipeline transitions out of no-signal state.
        // Copy IID macros to locals: on Linux they expand to compound
        // literals (rvalues), so &IID_IUnknown is invalid.
        REFIID iunknown = IID_IUnknown;
        REFIID ividbuf = IID_IDeckLinkVideoBuffer;
        if (!ppv) return E_POINTER;
        if (memcmp(&iid, &iunknown, sizeof(REFIID)) == 0) {
            *ppv = static_cast<IUnknown*>(this);
        } else if (memcmp(&iid, &ividbuf, sizeof(REFIID)) == 0) {
            *ppv = static_cast<IDeckLinkVideoBuffer*>(this);
        } else {
            *ppv = nullptr;
            return E_NOINTERFACE;
        }
        AddRef();
        return S_OK;
    }
    ULONG AddRef() override { return ++ref_count_; }
    ULONG Release() override;  // Defined after VideoBufferAllocator.

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
    friend class VideoBufferAllocator;

    /// Reset to live state when popped from the parent's free-list.
    /// The parent already holds a strong ref on behalf of the new
    /// owner of this buffer (Python or SDK), so do not AddRef again.
    void revive() { ref_count_.store(1); }

    std::atomic<ULONG> ref_count_;
    size_t size_;
    void* data_;
    /// Borrowed pointer. The buffer keeps the parent alive via an
    /// AddRef'd ref while the buffer's refcount is non-zero. While
    /// the buffer sits on the parent's free-list (refcount == 0),
    /// the parent owns the buffer instead — see `return_to_free_list`.
    VideoBufferAllocator* parent_;
};

/// Implements IDeckLinkVideoBufferAllocator.
///
/// Backs `ManagedBuffer` instances with memory from a configurable
/// allocation function (defaults to malloc/free). Suitable for
/// CUDA `cudaHostAlloc`, HIP `hipHostMalloc`, or any custom allocator.
///
/// Maintains a free-list of recycled buffers. When the SDK releases
/// a `ManagedBuffer` (COM refcount → 0), the buffer returns to the
/// free-list instead of calling `free_fn`. The next
/// `AllocateVideoBuffer` pops from the free-list when non-empty.
/// `free_fn` runs only on allocator destruction, draining all
/// recycled buffers. This avoids the ~1ms-per-call cost of GPU
/// page-locking syscalls at frame rate (SPEC §4).
class VideoBufferAllocator : public IDeckLinkVideoBufferAllocator {
public:
    VideoBufferAllocator(size_t buffer_size,
                         AllocFn alloc_fn = nullptr,
                         FreeFn free_fn = nullptr)
        : ref_count_(1), buffer_size_(buffer_size),
          alloc_fn_(alloc_fn ? std::move(alloc_fn) : default_alloc),
          free_fn_(free_fn ? std::move(free_fn) : default_free) {}

    ~VideoBufferAllocator() {
        // Drain the free-list: free each recycled buffer's backing
        // memory and delete the ManagedBuffer object. Live buffers
        // (refcount > 0) cannot reach this destructor — they hold
        // the parent's free-list slot indirectly via the SDK or
        // Python wrapper.
        std::lock_guard<std::mutex> lock(free_list_mutex_);
        for (ManagedBuffer* buf : free_list_) {
            if (buf->data_ && free_fn_) {
                free_fn_(buf->data_, buf->size_);
            }
            delete buf;
        }
        free_list_.clear();
    }

    // IUnknown
    HRESULT QueryInterface(REFIID iid, void** ppv) override {
        REFIID iunknown = IID_IUnknown;
        REFIID ialloc = IID_IDeckLinkVideoBufferAllocator;
        if (!ppv) return E_POINTER;
        if (memcmp(&iid, &iunknown, sizeof(REFIID)) == 0) {
            *ppv = static_cast<IUnknown*>(this);
        } else if (memcmp(&iid, &ialloc, sizeof(REFIID)) == 0) {
            *ppv = static_cast<IDeckLinkVideoBufferAllocator*>(this);
        } else {
            *ppv = nullptr;
            return E_NOINTERFACE;
        }
        AddRef();
        return S_OK;
    }
    ULONG AddRef() override { return ++ref_count_; }
    ULONG Release() override {
        ULONG c = --ref_count_;
        if (c == 0) delete this;
        return c;
    }

    // IDeckLinkVideoBufferAllocator
    HRESULT AllocateVideoBuffer(IDeckLinkVideoBuffer** allocatedBuffer) override {
        if (!allocatedBuffer) return E_INVALIDARG;

        // Fast path: pop from free-list. The free-list owns recycled
        // buffers (no parent ref); reviving transfers ownership back
        // to the new caller, who needs a parent ref to keep us alive.
        {
            std::lock_guard<std::mutex> lock(free_list_mutex_);
            if (!free_list_.empty()) {
                ManagedBuffer* recycled = free_list_.back();
                free_list_.pop_back();
                recycled->revive();
                AddRef();  // The buffer holds a ref on us again.
                *allocatedBuffer = recycled;
                return S_OK;
            }
        }

        // Slow path: invoke alloc_fn. ManagedBuffer constructor AddRefs us.
        // With Python alloc callbacks, this path acquires the GIL and
        // calls into Python — taking milliseconds, which the SDK input
        // pipeline cannot tolerate at signal-rate. Callers must
        // pre-fill the free-list (see ``prefill``) before streaming
        // starts so that this path never runs on the SDK thread.
        void* mem = alloc_fn_(buffer_size_);
        if (!mem) return E_OUTOFMEMORY;

        auto* buf = new ManagedBuffer(this, buffer_size_, mem);
        *allocatedBuffer = buf;

        ++allocated_count_;
        return S_OK;
    }

    size_t buffer_size() const { return buffer_size_; }

    size_t allocated_count() const {
        return allocated_count_;
    }

    size_t recycled_count() const {
        return recycled_count_;
    }

    ULONG refcount() const { return ref_count_.load(); }

    /// Pre-allocate ``count`` buffers and seat them on the free-list.
    ///
    /// The SDK input pipeline calls ``AllocateVideoBuffer`` on its own
    /// thread when it needs a buffer. With Python alloc callbacks,
    /// each SLOW-path call acquires the GIL, dispatches into Python,
    /// and returns — typically 1–10ms. The SDK pipeline cannot
    /// tolerate that latency at signal-rate, and stalls.
    ///
    /// ``prefill`` runs the SLOW path ``count`` times on the *calling*
    /// thread (typically Python's main thread, before
    /// ``start_streams``) and pushes each buffer onto the free-list.
    /// At runtime the SDK's allocations take the FAST path with no
    /// Python involvement. The buffers stay on the free-list until
    /// the SDK requests one, at which point they are revived.
    void prefill(size_t count) {
        std::vector<ManagedBuffer*> staged;
        staged.reserve(count);
        for (size_t i = 0; i < count; ++i) {
            void* mem = alloc_fn_(buffer_size_);
            if (!mem)
                throw std::runtime_error(
                    "prefill: alloc_fn returned nullptr");
            auto* buf = new ManagedBuffer(this, buffer_size_, mem);
            ++allocated_count_;
            staged.push_back(buf);
        }
        // Drop each buffer's ref to send it to the free-list. Each
        // ManagedBuffer ctor AddRef'd the parent (us); Release brings
        // the buffer's refcount to 0 and the parent ref drops with it.
        for (ManagedBuffer* buf : staged) {
            buf->Release();
        }
    }

    /// Allocate a ManagedBuffer and return it (for Python use).
    /// ManagedBuffer : public IDeckLinkVideoBuffer (single inheritance),
    /// so the pointer layouts match and put() can receive the out-param.
    ComPtr<ManagedBuffer> allocate_managed() {
        ComPtr<ManagedBuffer> buf;
        HRESULT hr = AllocateVideoBuffer(
            reinterpret_cast<IDeckLinkVideoBuffer**>(buf.put()));
        if (hr != S_OK || !buf)
            throw std::runtime_error("AllocateVideoBuffer failed");
        return buf;
    }

private:
    friend class ManagedBuffer;

    /// Push a buffer back onto the free-list. Called by
    /// `ManagedBuffer::Release` when refcount reaches zero.
    void return_to_free_list(ManagedBuffer* buf) {
        std::lock_guard<std::mutex> lock(free_list_mutex_);
        free_list_.push_back(buf);
        ++recycled_count_;
    }

    std::atomic<ULONG> ref_count_;
    size_t buffer_size_;
    AllocFn alloc_fn_;
    FreeFn free_fn_;
    std::atomic<size_t> allocated_count_ = 0;
    std::atomic<size_t> recycled_count_ = 0;
    std::mutex free_list_mutex_;
    std::vector<ManagedBuffer*> free_list_;  // Owned. Drained at allocator destruction.

    static void* default_alloc(size_t size) { return std::malloc(size); }
    static void default_free(void* ptr, size_t) { std::free(ptr); }
};

inline ManagedBuffer::ManagedBuffer(VideoBufferAllocator* parent,
                                    size_t size, void* data)
    : ref_count_(1), size_(size), data_(data), parent_(parent) {
    if (parent_) parent_->AddRef();  // Keep parent alive while buffer is live.
}

inline ULONG ManagedBuffer::Release() {
    ULONG c = --ref_count_;
    if (c == 0 && parent_) {
        // Hand ownership of `this` to the parent's free-list. The
        // parent's destructor drains the free-list and frees memory
        // via free_fn. The buffer's parent ref is released LAST so
        // the parent stays alive across return_to_free_list.
        VideoBufferAllocator* parent = parent_;
        parent->return_to_free_list(this);
        parent->Release();  // Drop the buffer's ref on parent.
    }
    return c;
}

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
    HRESULT QueryInterface(REFIID iid, void** ppv) override {
        REFIID iunknown = IID_IUnknown;
        REFIID iprov = IID_IDeckLinkVideoBufferAllocatorProvider;
        if (!ppv) return E_POINTER;
        if (memcmp(&iid, &iunknown, sizeof(REFIID)) == 0) {
            *ppv = static_cast<IUnknown*>(this);
        } else if (memcmp(&iid, &iprov, sizeof(REFIID)) == 0) {
            *ppv = static_cast<IDeckLinkVideoBufferAllocatorProvider*>(this);
        } else {
            *ppv = nullptr;
            return E_NOINTERFACE;
        }
        AddRef();
        return S_OK;
    }
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
        for (ComPtr<VideoBufferAllocator>& cached : allocators_) {
            if (cached->buffer_size() == bufferSize) {
                cached->AddRef();
                *allocator = cached.get();
                return S_OK;
            }
        }

        // Create new allocator.
        auto& alloc = allocators_.emplace_back(new VideoBufferAllocator(bufferSize, alloc_fn_, free_fn_));

        alloc->AddRef(); // One ref for the cache, one for the caller.
        *allocator = alloc.get();
        return S_OK;
    }

private:
    std::atomic<ULONG> ref_count_;
    AllocFn alloc_fn_;
    FreeFn free_fn_;
    std::mutex mutex_;
    std::vector<ComPtr<VideoBufferAllocator>> allocators_;  // Cached allocators (owned via ref count).
};
