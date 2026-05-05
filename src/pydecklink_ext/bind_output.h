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
    void add_pinned_frame(ComPtr<IDeckLinkMutableVideoFrame>&& frame) {
        std::lock_guard<std::mutex> lock(pool_mutex_);
        available_.push(frame.get());
        all_frames_.push_back(std::move(frame));
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
    // all_frames_ owns every pooled frame; available_ holds non-owning
    // pointers into that set for O(1) acquire.
    std::vector<ComPtr<IDeckLinkMutableVideoFrame>> all_frames_;
    std::queue<IDeckLinkMutableVideoFrame*> available_;
};

/// Python-visible wrapper around IDeckLinkMutableVideoFrame.
///
/// Per SDK §2.5.53.2, ``StartAccess(ReadAndWrite)`` /
/// ``EndAccess(ReadAndWrite)`` is the access-synchronization
/// primitive — it bounds the interval the producer is reading and
/// writing the buffer's contents, independent of the COM refcount.
///
/// Mirrors the input-side ``CaptureFrameRef`` lifetime model: the
/// access window opens when the frame is handed to Python (acquired
/// from the pool, or freshly created), and closes either when the
/// frame is scheduled (ownership transfers to the SDK) or when the
/// wrapper is dropped. Allocators with non-trivial access semantics
/// (mapped GPU memory, macOS XPC-marshaled, dmabuf) depend on the
/// pairing — ``BufferHandle`` makes both calls no-ops, but we honour
/// the contract regardless.
///
/// Move-only: the access window is a non-copyable resource. After a
/// move, the source no longer owns the window.
struct MutableFrame {
    ComPtr<IDeckLinkMutableVideoFrame> frame;
    ComPtr<IDeckLinkVideoBuffer> buffer;
    bool access_open = false;  // True if we owe an EndAccess(ReadAndWrite).

    MutableFrame() = default;
    MutableFrame(const MutableFrame&) = delete;
    MutableFrame& operator=(const MutableFrame&) = delete;

    MutableFrame(MutableFrame&& o) noexcept
        : frame(std::move(o.frame)),
          buffer(std::move(o.buffer)),
          access_open(o.access_open) {
        o.access_open = false;
    }

    MutableFrame& operator=(MutableFrame&& o) noexcept {
        if (this != &o) {
            close_access();
            frame = std::move(o.frame);
            buffer = std::move(o.buffer);
            access_open = o.access_open;
            o.access_open = false;
        }
        return *this;
    }

    ~MutableFrame() { close_access(); }

    long width() const { return frame->GetWidth(); }
    long height() const { return frame->GetHeight(); }
    long row_bytes() const { return frame->GetRowBytes(); }

    /// Open the read/write access window. Call once after the wrapper
    /// adopts a frame; idempotent if already open.
    void open_access() {
        if (access_open || !buffer) return;
        if (buffer->StartAccess(bmdBufferAccessReadAndWrite) == S_OK) {
            access_open = true;
        }
    }

    /// Close the access window. Called by ``schedule_output_frame``
    /// before handing the frame to the SDK, and by the destructor for
    /// frames the user drops without scheduling.
    void close_access() {
        if (access_open && buffer) {
            buffer->EndAccess(bmdBufferAccessReadAndWrite);
        }
        access_open = false;
    }

    void* get_data_ptr() {
        if (!buffer)
            throw std::runtime_error("Frame has no video buffer");
        void* bytes = nullptr;
        buffer->GetBytes(&bytes);
        if (!bytes)
            throw std::runtime_error("Failed to get frame buffer bytes");
        return bytes;
    }
};

void init_decklink_output(nb::module_& m, nb::class_<Device>& device);
