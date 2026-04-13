#pragma once

#include <nanobind/nanobind.h>
#include "bind_device.h"
#include <atomic>
#include <condition_variable>
#include <mutex>
#include <queue>
#include <stdexcept>
#include <string>
#include <vector>

namespace nb = nanobind;

/// Global counter: host-side refs to IDeckLinkMutableVideoFrame objects
/// created by schedule_frame.  Incremented after CreateVideoFrame;
/// decremented in the destructor only when Release() will fire (ptr
/// still non-null).  A non-zero value after playback stops means a ref
/// was leaked.
inline std::atomic<int64_t> g_host_frame_refs{0};

/// RAII wrapper around ComPtr<IDeckLinkMutableVideoFrame> that maintains
/// g_host_frame_refs.  Call mark_created() once after CreateVideoFrame
/// succeeds.  The destructor decrements only if the inner pointer is
/// still live (i.e. Release() will actually fire).
class TrackedFramePtr {
public:
    TrackedFramePtr() = default;
    ~TrackedFramePtr() {
        if (inner_) g_host_frame_refs.fetch_sub(1, std::memory_order_relaxed);
    }
    TrackedFramePtr(const TrackedFramePtr&) = delete;
    TrackedFramePtr& operator=(const TrackedFramePtr&) = delete;
    TrackedFramePtr(TrackedFramePtr&& o) noexcept : inner_(std::move(o.inner_)) {}
    TrackedFramePtr& operator=(TrackedFramePtr&& o) noexcept {
        if (this != &o) {
            if (inner_) g_host_frame_refs.fetch_sub(1, std::memory_order_relaxed);
            inner_ = std::move(o.inner_);
        }
        return *this;
    }

    IDeckLinkMutableVideoFrame* get() const { return inner_.get(); }
    IDeckLinkMutableVideoFrame** put() { return inner_.put(); }
    IDeckLinkMutableVideoFrame* operator->() const { return inner_.get(); }
    explicit operator bool() const { return bool(inner_); }

    void mark_created() {
        if (inner_) g_host_frame_refs.fetch_add(1, std::memory_order_relaxed);
    }

private:
    ComPtr<IDeckLinkMutableVideoFrame> inner_;
};

/// Tracks scheduled frame completion statistics.
struct OutputStatus {
    uint32_t completed = 0;
    uint32_t late = 0;
    uint32_t dropped = 0;
    uint32_t flushed = 0;
    bool underrun = false;
};

/// C++ implementation of IDeckLinkVideoOutputCallback.
/// Tracks frame completion results and manages a frame pool.
class OutputCallback : public IDeckLinkVideoOutputCallback {
public:
    OutputCallback() : ref_count_(1) {}

    // IUnknown
    HRESULT QueryInterface(REFIID, void**) override { return E_NOINTERFACE; }
    ULONG AddRef() override { return ++ref_count_; }
    ULONG Release() override {
        ULONG c = --ref_count_;
        if (c == 0) delete this;
        return c;
    }

    HRESULT ScheduledFrameCompleted(IDeckLinkVideoFrame* completedFrame, BMDOutputFrameCompletionResult result) override {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            switch (result) {
                case bmdOutputFrameCompleted:    ++status_.completed; break;
                case bmdOutputFrameDisplayedLate: ++status_.late; break;
                case bmdOutputFrameDropped:      ++status_.dropped; break;
                case bmdOutputFrameFlushed:      ++status_.flushed; break;
            }
        }

        // Return completed frame to pool if it belongs to one.
        if (completedFrame && pool_enabled_) {
            std::lock_guard<std::mutex> lock(pool_mutex_);
            // Check if this frame is one of ours.
            for (auto& pf : all_frames_) {
                if (static_cast<IDeckLinkVideoFrame*>(pf.get()) == completedFrame) {
                    available_.push(pf.get());
                    pool_cv_.notify_one();
                    break;
                }
            }
        }

        return S_OK;
    }

    HRESULT ScheduledPlaybackHasStopped() override {
        std::lock_guard<std::mutex> lock(mutex_);
        status_.underrun = true;
        return S_OK;
    }

    OutputStatus get_status() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return status_;
    }

    void reset() {
        std::lock_guard<std::mutex> lock(mutex_);
        status_ = OutputStatus{};
    }

    // -- Frame pool --

    void create_pool(IDeckLinkOutput* output, int count,
                     int32_t width, int32_t height, int32_t row_bytes,
                     _BMDPixelFormat pixel_format) {
        std::lock_guard<std::mutex> lock(pool_mutex_);
        all_frames_.clear();
        // Drain any leftover available frames.
        while (!available_.empty()) available_.pop();

        for (int i = 0; i < count; ++i) {
            ComPtr<IDeckLinkMutableVideoFrame> frame;
            HRESULT hr = output->CreateVideoFrame(
                width, height, row_bytes, pixel_format,
                bmdFrameFlagDefault, frame.put());
            if (hr != S_OK || !frame)
                throw std::runtime_error(
                    "CreateVideoFrame failed for pool frame " + std::to_string(i));
            available_.push(frame.get());
            all_frames_.push_back(std::move(frame));
        }
        pool_enabled_ = true;
    }

    /// Acquire a frame from the pool.  Blocks until one is available.
    IDeckLinkMutableVideoFrame* acquire(int timeout_ms) {
        std::unique_lock<std::mutex> lock(pool_mutex_);
        if (!pool_cv_.wait_for(lock, std::chrono::milliseconds(timeout_ms),
                               [this] { return !available_.empty(); })) {
            return nullptr;  // timeout
        }
        auto* f = available_.front();
        available_.pop();
        return f;
    }

    size_t pool_size() const {
        std::lock_guard<std::mutex> lock(pool_mutex_);
        return all_frames_.size();
    }

    size_t pool_available() const {
        std::lock_guard<std::mutex> lock(pool_mutex_);
        return available_.size();
    }

    /// Add a pre-created frame (e.g. from CreateVideoFrameWithBuffer) to the pool.
    void add_pinned_frame(IDeckLinkMutableVideoFrame* frame) {
        std::lock_guard<std::mutex> lock(pool_mutex_);
        all_frames_.emplace_back(frame);
        available_.push(frame);
        pool_enabled_ = true;
    }

private:
    std::atomic<ULONG> ref_count_;
    mutable std::mutex mutex_;
    OutputStatus status_;

    // Frame pool
    bool pool_enabled_ = false;
    mutable std::mutex pool_mutex_;
    std::condition_variable pool_cv_;
    std::vector<ComPtr<IDeckLinkMutableVideoFrame>> all_frames_;
    std::queue<IDeckLinkMutableVideoFrame*> available_;
};

/// Python-visible wrapper around IDeckLinkMutableVideoFrame.
struct MutableFrame {
    ComPtr<IDeckLinkMutableVideoFrame> frame;
    ComPtr<IDeckLinkVideoBuffer> buffer;

    long width() const { return frame->GetWidth(); }
    long height() const { return frame->GetHeight(); }
    long row_bytes() const { return frame->GetRowBytes(); }

    void* get_data_ptr() {
        if (!buffer)
            throw std::runtime_error("Frame has no video buffer");
        void* bytes = nullptr;
        buffer->StartAccess(bmdBufferAccessReadAndWrite);
        buffer->GetBytes(&bytes);
        if (!bytes) {
            buffer->EndAccess(bmdBufferAccessReadAndWrite);
            throw std::runtime_error("Failed to get frame buffer bytes");
        }
        return bytes;
    }

    void end_access() {
        if (buffer)
            buffer->EndAccess(bmdBufferAccessReadAndWrite);
    }
};

void init_decklink_output(nb::module_& m, nb::class_<Device>& device);
