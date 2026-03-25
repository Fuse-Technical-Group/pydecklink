#pragma once

#include <nanobind/nanobind.h>
#include "bind_device.h"
#include "DeckLinkAPI.h"
#include <atomic>
#include <condition_variable>
#include <cstring>
#include <mutex>
#include <optional>
#include <queue>
#include <time.h>
#include <vector>

namespace nb = nanobind;

/// Return CLOCK_MONOTONIC_RAW time in microseconds.
inline int64_t monotonic_raw_us() {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return static_cast<int64_t>(ts.tv_sec) * 1000000 + ts.tv_nsec / 1000;
}

/// Captured frame data, copied from the SDK's callback thread.
struct CaptureFrame {
    std::vector<uint8_t> pixels;
    long width = 0;
    long height = 0;
    long row_bytes = 0;
    _BMDPixelFormat pixel_format = bmdFormatUnspecified;
    int64_t stream_time = 0;
    int64_t stream_duration = 0;
    int64_t hw_ref_timestamp = 0;
    bool has_signal = true;
};

/// Zero-copy captured frame holding a ref to the SDK's IDeckLinkVideoInputFrame.
struct CaptureFrameRef {
    ComPtr<IDeckLinkVideoInputFrame> frame;
    bool has_signal = true;
    int64_t stream_time = 0;
    int64_t stream_duration = 0;
    int64_t hw_ref_timestamp = 0;
    int64_t callback_arrived_us = 0;  // CLOCK_MONOTONIC_RAW, microseconds

    long width() const { return frame ? frame->GetWidth() : 0; }
    long height() const { return frame ? frame->GetHeight() : 0; }
    long row_bytes() const { return frame ? frame->GetRowBytes() : 0; }
    _BMDPixelFormat pixel_format() const {
        return frame ? static_cast<_BMDPixelFormat>(frame->GetPixelFormat())
                     : bmdFormatUnspecified;
    }
};

/// Information about the currently detected input format.
struct InputFormatInfo {
    _BMDDisplayMode mode = bmdModeUnknown;
    _BMDPixelFormat pixel_format = bmdFormatUnspecified;
    _BMDVideoInputFlags flags = bmdVideoInputFlagDefault;
};

/// C++ implementation of IDeckLinkInputCallback.
/// Copies frame data into a bounded thread-safe queue.
class InputCallback : public IDeckLinkInputCallback {
public:
    InputCallback(IDeckLinkInput* input, size_t max_queue = 8, bool zero_copy = false)
        : ref_count_(1), input_(input), max_queue_(max_queue),
          format_detection_enabled_(false), zero_copy_(zero_copy) {}

    void set_format_detection(bool enabled) {
        format_detection_enabled_ = enabled;
    }

    void set_timescale(int64_t ts) { timescale_ = ts; }

    // IUnknown
    HRESULT QueryInterface(REFIID, void**) override { return E_NOINTERFACE; }
    ULONG AddRef() override { return ++ref_count_; }
    ULONG Release() override {
        ULONG c = --ref_count_;
        if (c == 0) delete this;
        return c;
    }

    HRESULT VideoInputFormatChanged(
            BMDVideoInputFormatChangedEvents events,
            IDeckLinkDisplayMode* newMode,
            BMDDetectedVideoInputFormatFlags flags) override {
        if (!format_detection_enabled_) return S_OK;

        // Determine new pixel format from detected flags.
        _BMDPixelFormat new_pf = bmdFormat8BitYUV;
        if (flags & bmdDetectedVideoInputRGB444) {
            if (flags & bmdDetectedVideoInput12BitDepth)
                new_pf = bmdFormat12BitRGB;
            else if (flags & bmdDetectedVideoInput10BitDepth)
                new_pf = bmdFormat10BitRGB;
            else
                new_pf = bmdFormat8BitARGB;
        } else {
            // YCbCr
            if (flags & bmdDetectedVideoInput10BitDepth)
                new_pf = bmdFormat10BitYUV;
            else
                new_pf = bmdFormat8BitYUV;
        }

        BMDDisplayMode new_mode = newMode->GetDisplayMode();

        // Update current format info.
        {
            std::lock_guard<std::mutex> lock(format_mutex_);
            current_format_.mode = static_cast<_BMDDisplayMode>(new_mode);
            current_format_.pixel_format = new_pf;
        }

        // Reconfigure: stop, disable, re-enable, restart.
        input_->StopStreams();
        input_->DisableVideoInput();
        input_->EnableVideoInput(new_mode, new_pf,
                                 bmdVideoInputEnableFormatDetection);
        input_->StartStreams();

        return S_OK;
    }

    HRESULT VideoInputFrameArrived(
            IDeckLinkVideoInputFrame* videoFrame,
            IDeckLinkAudioInputPacket*) override {
        if (!videoFrame) return S_OK;

        int64_t arrived_us = monotonic_raw_us();
        bool has_signal = !(videoFrame->GetFlags() & bmdFrameHasNoInputSource);
        int64_t st = 0, sd = 0, hw_time = 0, hw_dur = 0;
        videoFrame->GetStreamTime(&st, &sd, timescale_);
        videoFrame->GetHardwareReferenceTimestamp(timescale_, &hw_time, &hw_dur);

        if (zero_copy_) {
            // Zero-copy path: AddRef the SDK frame and enqueue.
            CaptureFrameRef cfr;
            videoFrame->AddRef();
            cfr.frame = ComPtr<IDeckLinkVideoInputFrame>(videoFrame);
            cfr.has_signal = has_signal;
            cfr.stream_time = st;
            cfr.stream_duration = sd;
            cfr.hw_ref_timestamp = hw_time;
            cfr.callback_arrived_us = arrived_us;

            {
                std::lock_guard<std::mutex> lock(ref_queue_mutex_);
                if (ref_queue_.size() >= max_queue_)
                    ref_queue_.pop();
                ref_queue_.push(std::move(cfr));
            }
            ref_queue_cv_.notify_one();
        } else {
            // Copy path: memcpy pixel data into CaptureFrame.
            CaptureFrame cf;
            cf.width = videoFrame->GetWidth();
            cf.height = videoFrame->GetHeight();
            cf.row_bytes = videoFrame->GetRowBytes();
            cf.pixel_format = static_cast<_BMDPixelFormat>(videoFrame->GetPixelFormat());
            cf.has_signal = has_signal;
            cf.stream_time = st;
            cf.stream_duration = sd;
            cf.hw_ref_timestamp = hw_time;

            IDeckLinkVideoBuffer* buf = nullptr;
            videoFrame->QueryInterface(IID_IDeckLinkVideoBuffer, (void**)&buf);
            if (buf) {
                buf->StartAccess(bmdBufferAccessRead);
                void* bytes = nullptr;
                buf->GetBytes(&bytes);
                if (bytes) {
                    size_t total = static_cast<size_t>(cf.row_bytes) * cf.height;
                    cf.pixels.resize(total);
                    std::memcpy(cf.pixels.data(), bytes, total);
                }
                buf->EndAccess(bmdBufferAccessRead);
                buf->Release();
            }

            {
                std::lock_guard<std::mutex> lock(queue_mutex_);
                if (queue_.size() >= max_queue_)
                    queue_.pop();
                queue_.push(std::move(cf));
            }
            queue_cv_.notify_one();
        }

        return S_OK;
    }

    std::optional<CaptureFrame> pop(int timeout_ms) {
        std::unique_lock<std::mutex> lock(queue_mutex_);
        if (!queue_cv_.wait_for(lock, std::chrono::milliseconds(timeout_ms),
                                [this] { return !queue_.empty(); })) {
            return std::nullopt;
        }
        CaptureFrame f = std::move(queue_.front());
        queue_.pop();
        return f;
    }

    std::optional<CaptureFrameRef> pop_ref(int timeout_ms) {
        std::unique_lock<std::mutex> lock(ref_queue_mutex_);
        if (!ref_queue_cv_.wait_for(lock, std::chrono::milliseconds(timeout_ms),
                                    [this] { return !ref_queue_.empty(); })) {
            return std::nullopt;
        }
        CaptureFrameRef f = std::move(ref_queue_.front());
        ref_queue_.pop();
        return f;
    }

    InputFormatInfo current_format() const {
        std::lock_guard<std::mutex> lock(format_mutex_);
        return current_format_;
    }

    void set_current_format(_BMDDisplayMode mode, _BMDPixelFormat pf, _BMDVideoInputFlags flags) {
        std::lock_guard<std::mutex> lock(format_mutex_);
        current_format_.mode = mode;
        current_format_.pixel_format = pf;
        current_format_.flags = flags;
    }

private:
    std::atomic<ULONG> ref_count_;
    IDeckLinkInput* input_;  // Non-owning; Device owns this.
    size_t max_queue_;
    bool format_detection_enabled_;
    bool zero_copy_;
    int64_t timescale_ = 10000000;  // Default 10MHz.

    std::mutex queue_mutex_;
    std::condition_variable queue_cv_;
    std::queue<CaptureFrame> queue_;

    std::mutex ref_queue_mutex_;
    std::condition_variable ref_queue_cv_;
    std::queue<CaptureFrameRef> ref_queue_;

    mutable std::mutex format_mutex_;
    InputFormatInfo current_format_;
};

void init_decklink_input(nb::module_& m, nb::class_<Device>& device);
