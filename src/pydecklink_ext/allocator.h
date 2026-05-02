#pragma once

#include "DeckLinkAPI.h"
#include "comptr.h"
#include "platform.h"  // iid_matches, PYDECKLINK_IUNKNOWN_IID
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

class VideoBufferAllocator;

/// Pooled backing memory. Owned by the parent allocator's free-list
/// across all issuances. A `PooledBuffer` is created once (via the
/// allocator's `alloc_fn`) and returned to the free-list each time the
/// `BufferHandle` wrapping it is released. Its memory is freed via
/// `free_fn` only when the parent allocator is destroyed.
struct PooledBuffer {
    void* data;
    size_t size;
};

/// Per-issuance COM handle implementing IDeckLinkVideoBuffer.
///
/// Standard COM lifetime: `Release()` reaching zero destroys this
/// object (`delete this`). The destructor returns the underlying
/// `PooledBuffer*` to the parent allocator's free-list. The pooled
/// memory itself is not freed — it is amortized across many handle
/// issuances. This is the recycling mechanism that lets a Python-side
/// allocator (e.g. `cudaHostAlloc`) avoid running on the SDK input
/// thread at signal rate.
///
/// The handle holds a strong ref on the parent allocator via
/// `ComPtr<VideoBufferAllocator>`, so the parent stays alive across
/// the handle's lifetime and can service `return_to_free_list`.
class BufferHandle : public IDeckLinkVideoBuffer {
public:
    BufferHandle(ComPtr<VideoBufferAllocator> parent, PooledBuffer* pooled);

    // IUnknown
    HRESULT QueryInterface(REFIID iid, void** ppv) override {
        // Per SDK §2.5.55, the SDK wraps our buffer into its own video
        // frame and may call QueryInterface to obtain interface
        // pointers. Returning E_NOINTERFACE for IUnknown or our own
        // interface violates COM and stalls the input pipeline at the
        // no-signal → signal-locked transition. ``iid_matches`` and
        // the IUnknown IID name vary per platform — see platform.h.
        if (!ppv) return E_POINTER;
        if (iid_matches(iid, PYDECKLINK_IUNKNOWN_IID)) {
            *ppv = static_cast<IUnknown*>(this);
        } else if (iid_matches(iid, IID_IDeckLinkVideoBuffer)) {
            *ppv = static_cast<IDeckLinkVideoBuffer*>(this);
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

    // IDeckLinkVideoBuffer
    HRESULT GetBytes(void** buffer) override {
        if (!buffer) return E_INVALIDARG;
        *buffer = pooled_->data;
        return S_OK;
    }

    HRESULT StartAccess(BMDBufferAccessFlags) override { return S_OK; }
    HRESULT EndAccess(BMDBufferAccessFlags) override { return S_OK; }

    size_t size() const { return pooled_->size; }
    void* data() const { return pooled_->data; }

private:
    ~BufferHandle();  // Defined after VideoBufferAllocator.

    std::atomic<ULONG> ref_count_;
    PooledBuffer* pooled_;                   // Borrowed; returned to pool on dtor.
    ComPtr<VideoBufferAllocator> parent_;    // Strong ref keeps parent alive.
};

/// Implements IDeckLinkVideoBufferAllocator.
///
/// Backs `BufferHandle` instances with `PooledBuffer` memory from a
/// configurable allocation function (defaults to malloc/free). Suitable
/// for CUDA `cudaHostAlloc`, HIP `hipHostMalloc`, or any custom
/// allocator.
///
/// Maintains a free-list of `PooledBuffer*`. When a `BufferHandle` is
/// released (COM refcount → 0), the handle destructs and returns its
/// `PooledBuffer*` to the free-list instead of calling `free_fn`. The
/// next `AllocateVideoBuffer` pops a `PooledBuffer*` from the free-list
/// (when non-empty) and wraps it in a fresh `BufferHandle`. `free_fn`
/// runs only on allocator destruction, draining all pooled buffers.
/// This avoids the ~1ms-per-call cost of GPU page-locking syscalls at
/// frame rate (SPEC §4).
class VideoBufferAllocator : public IDeckLinkVideoBufferAllocator {
public:
    VideoBufferAllocator(size_t buffer_size,
                         AllocFn alloc_fn = nullptr,
                         FreeFn free_fn = nullptr)
        : ref_count_(1), buffer_size_(buffer_size),
          alloc_fn_(alloc_fn ? std::move(alloc_fn) : default_alloc),
          free_fn_(free_fn ? std::move(free_fn) : default_free) {}

    ~VideoBufferAllocator() {
        // Drain the free-list: free each pooled buffer's backing memory
        // and delete the PooledBuffer record. Live handles cannot
        // reach this destructor — each handle holds a strong ref on
        // us via its `parent_` ComPtr.
        std::lock_guard<std::mutex> lock(free_list_mutex_);
        for (PooledBuffer* p : free_list_) {
            if (p->data && free_fn_) {
                free_fn_(p->data, p->size);
            }
            delete p;
        }
        free_list_.clear();
    }

    // IUnknown
    HRESULT QueryInterface(REFIID iid, void** ppv) override {
        if (!ppv) return E_POINTER;
        if (iid_matches(iid, PYDECKLINK_IUNKNOWN_IID)) {
            *ppv = static_cast<IUnknown*>(this);
        } else if (iid_matches(iid, IID_IDeckLinkVideoBufferAllocator)) {
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

        PooledBuffer* pooled = take_or_alloc();
        if (!pooled) return E_OUTOFMEMORY;

        // AddRef paired with the ComPtr below adopting; the new
        // BufferHandle takes ownership of this ref.
        AddRef();
        *allocatedBuffer = new BufferHandle(
            ComPtr<VideoBufferAllocator>(this), pooled);
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

    /// Pre-allocate ``count`` pooled buffers and seat them on the
    /// free-list.
    ///
    /// The SDK input pipeline calls ``AllocateVideoBuffer`` on its own
    /// thread when it needs a buffer. With Python alloc callbacks,
    /// each SLOW-path call acquires the GIL, dispatches into Python,
    /// and returns — typically 1–10ms. The SDK pipeline cannot
    /// tolerate that latency at signal-rate, and stalls.
    ///
    /// ``prefill`` runs ``alloc_fn`` ``count`` times on the *calling*
    /// thread (typically Python's main thread, before
    /// ``start_streams``) and pushes each ``PooledBuffer*`` directly
    /// onto the free-list. At runtime the SDK's allocations take the
    /// FAST path: pop a pooled buffer, wrap it in a fresh handle, no
    /// Python involvement.
    void prefill(size_t count) {
        std::lock_guard<std::mutex> lock(free_list_mutex_);
        free_list_.reserve(free_list_.size() + count);
        for (size_t i = 0; i < count; ++i) {
            void* mem = alloc_fn_(buffer_size_);
            if (!mem)
                throw std::runtime_error(
                    "prefill: alloc_fn returned nullptr");
            free_list_.push_back(new PooledBuffer{mem, buffer_size_});
            ++allocated_count_;
            ++recycled_count_;
        }
    }

    /// Allocate a BufferHandle and return it (for Python use).
    /// BufferHandle : public IDeckLinkVideoBuffer (single inheritance),
    /// so the pointer layouts match and put() can receive the out-param.
    ComPtr<BufferHandle> allocate_managed() {
        ComPtr<BufferHandle> buf;
        HRESULT hr = AllocateVideoBuffer(
            reinterpret_cast<IDeckLinkVideoBuffer**>(buf.put()));
        if (hr != S_OK || !buf)
            throw std::runtime_error("AllocateVideoBuffer failed");
        return buf;
    }

private:
    friend class BufferHandle;

    /// Push a pooled buffer back onto the free-list. Called by
    /// `BufferHandle::~BufferHandle`.
    void return_to_free_list(PooledBuffer* p) {
        std::lock_guard<std::mutex> lock(free_list_mutex_);
        free_list_.push_back(p);
        ++recycled_count_;
    }

    /// Pop a pooled buffer from the free-list, or allocate a fresh
    /// one if the list is empty. Returns nullptr on alloc failure.
    PooledBuffer* take_or_alloc() {
        {
            std::lock_guard<std::mutex> lock(free_list_mutex_);
            if (!free_list_.empty()) {
                PooledBuffer* p = free_list_.back();
                free_list_.pop_back();
                return p;
            }
        }
        // Slow path: invoke alloc_fn. With Python alloc callbacks,
        // this acquires the GIL and calls into Python — taking
        // milliseconds, which the SDK input pipeline cannot tolerate
        // at signal-rate. Callers must pre-fill the free-list (see
        // ``prefill``) before streaming starts so this path never
        // runs on the SDK thread.
        void* mem = alloc_fn_(buffer_size_);
        if (!mem) return nullptr;
        ++allocated_count_;
        return new PooledBuffer{mem, buffer_size_};
    }

    std::atomic<ULONG> ref_count_;
    size_t buffer_size_;
    AllocFn alloc_fn_;
    FreeFn free_fn_;
    std::atomic<size_t> allocated_count_ = 0;
    std::atomic<size_t> recycled_count_ = 0;
    std::mutex free_list_mutex_;
    std::vector<PooledBuffer*> free_list_;  // Owned. Drained at allocator destruction.

    static void* default_alloc(size_t size) { return std::malloc(size); }
    static void default_free(void* ptr, size_t) { std::free(ptr); }
};

inline BufferHandle::BufferHandle(ComPtr<VideoBufferAllocator> parent,
                                  PooledBuffer* pooled)
    : ref_count_(1), pooled_(pooled), parent_(std::move(parent)) {}

inline BufferHandle::~BufferHandle() {
    // Return the pooled buffer to the parent's free-list before the
    // ComPtr drops the parent ref. The parent stays alive throughout
    // this call (parent_ is a member that destructs after the body).
    if (pooled_) {
        parent_->return_to_free_list(pooled_);
    }
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
        if (!ppv) return E_POINTER;
        if (iid_matches(iid, PYDECKLINK_IUNKNOWN_IID)) {
            *ppv = static_cast<IUnknown*>(this);
        } else if (iid_matches(iid, IID_IDeckLinkVideoBufferAllocatorProvider)) {
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
