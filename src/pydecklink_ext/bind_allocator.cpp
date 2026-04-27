#include "bind_allocator.h"
#include "allocator.h"
#include "bind_device.h"
#include "bind_input.h"
#include "bind_output.h"
#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/string.h>
#include <optional>
#include <stdexcept>
#include <string>

namespace nb = nanobind;

namespace {

// Wrap an optional Python callable as an AllocFn / FreeFn. The std::function
// owns the nb::object; when the std::function is destroyed the captured
// nb::object's destructor drops the Python ref.
AllocFn make_alloc_fn(std::optional<nb::callable>& alloc_fn) {
    if (!alloc_fn) return nullptr;
    nb::object alloc_ref = nb::borrow(*alloc_fn);
    return [alloc_ref](size_t sz) -> void* {
        nb::gil_scoped_acquire gil;
        nb::object result = alloc_ref(sz);
        return reinterpret_cast<void*>(nb::cast<uintptr_t>(result));
    };
}

FreeFn make_free_fn(std::optional<nb::callable>& free_fn) {
    if (!free_fn) return nullptr;
    nb::object free_ref = nb::borrow(*free_fn);
    return [free_ref](void* ptr, size_t sz) {
        nb::gil_scoped_acquire gil;
        free_ref(reinterpret_cast<uintptr_t>(ptr), sz);
    };
}

}  // namespace

void init_decklink_allocator(nb::module_& m, nb::class_<Device>& device) {

    // -- ManagedBuffer --
    nb::class_<ComPtr<ManagedBuffer>>(m, "ManagedBuffer")
        .def_prop_ro("size",
                     [](ComPtr<ManagedBuffer>& self) { return self->size(); },
                     "Buffer size in bytes.")
        .def_prop_ro("data", [](nb::handle self) {
            auto& h = nb::cast<ComPtr<ManagedBuffer>&>(self);
            void* ptr = h->data();
            if (!ptr)
                throw std::runtime_error("Buffer has no data");
            size_t n = h->size();
            return nb::ndarray<nb::numpy, uint8_t, nb::ndim<1>>(
                ptr, {n}, self);
        }, "Writeable numpy uint8 view of the buffer.")
        .def("__repr__", [](const ComPtr<ManagedBuffer>& self) {
            return "ManagedBuffer(size=" + std::to_string(self->size()) + ")";
        }, nb::sig("def __repr__(self) -> str")); // avoid platform-specific C++ type in stub

    // -- VideoBufferAllocator --
    nb::class_<ComPtr<VideoBufferAllocator>>(m, "VideoBufferAllocator")
        .def("__init__",
             [](ComPtr<VideoBufferAllocator>* self, size_t size,
                std::optional<nb::callable> alloc_fn,
                std::optional<nb::callable> free_fn) {
                 AllocFn a = make_alloc_fn(alloc_fn);
                 FreeFn  f = make_free_fn(free_fn);
                 // VideoBufferAllocator ctor starts refcount at 1; ComPtr takes it.
                 auto* raw = new VideoBufferAllocator(size, std::move(a), std::move(f));
                 new (self) ComPtr<VideoBufferAllocator>(raw);
             },
             nb::arg("size"),
             nb::arg("alloc") = nb::none(),
             nb::arg("free") = nb::none(),
             "Create a buffer allocator for the given buffer size.\n\n"
             "Args:\n"
             "  size: Buffer size in bytes.\n"
             "  alloc: Optional callable(size: int) -> int returning a pointer.\n"
             "         Defaults to malloc.\n"
             "  free: Optional callable(ptr: int, size: int) -> None.\n"
             "        Defaults to free.\n\n"
             "For CUDA pinned memory, pass cudaHostAlloc/cudaFreeHost wrappers.")
        .def_prop_ro("size",
                     [](ComPtr<VideoBufferAllocator>& self) { return self->buffer_size(); },
                     "Buffer size that this allocator produces.")
        .def_prop_ro("allocated_count",
                     [](ComPtr<VideoBufferAllocator>& self) { return self->allocated_count(); },
                     "Number of buffers allocated so far.")
        .def_prop_ro("recycled_count",
                     [](ComPtr<VideoBufferAllocator>& self) { return self->recycled_count(); },
                     "Number of times a buffer has been returned to the free-list. "
                     "Each release of a ManagedBuffer increments this counter; the "
                     "next AllocateVideoBuffer reuses the recycled memory.")
        .def_prop_ro("_refcount",
                     [](ComPtr<VideoBufferAllocator>& self) { return self->refcount(); },
                     "Internal COM refcount. Test/debug hook; not a public API.")
        .def("allocate",
             [](ComPtr<VideoBufferAllocator>& self) -> ComPtr<ManagedBuffer> {
                 return self->allocate_managed();
             },
             "Allocate a new ManagedBuffer.")
        .def("__repr__", [](const ComPtr<VideoBufferAllocator>& self) {
            return "VideoBufferAllocator(size=" +
                   std::to_string(self->buffer_size()) + ", allocated=" +
                   std::to_string(self->allocated_count()) + ")";
        }, nb::sig("def __repr__(self) -> str")); // avoid platform-specific C++ type in stub

    // -- VideoBufferAllocatorProvider --
    nb::class_<ComPtr<VideoBufferAllocatorProvider>>(m, "VideoBufferAllocatorProvider")
        .def("__init__",
             [](ComPtr<VideoBufferAllocatorProvider>* self,
                std::optional<nb::callable> alloc_fn,
                std::optional<nb::callable> free_fn) {
                 AllocFn a = make_alloc_fn(alloc_fn);
                 FreeFn  f = make_free_fn(free_fn);
                 auto* raw = new VideoBufferAllocatorProvider(std::move(a), std::move(f));
                 new (self) ComPtr<VideoBufferAllocatorProvider>(raw);
             },
             nb::arg("alloc") = nb::none(),
             nb::arg("free") = nb::none(),
             "Create a buffer allocator provider.\n\n"
             "Args:\n"
             "  alloc: Optional callable(size: int) -> int returning a pointer.\n"
             "  free: Optional callable(ptr: int, size: int) -> None.\n\n"
             "Allocators are cached by buffer size. Custom alloc/free are\n"
             "propagated to each VideoBufferAllocator created by the provider.")
        .def("get_allocator",
             [](ComPtr<VideoBufferAllocatorProvider>& self,
                uint32_t buffer_size, uint32_t width, uint32_t height,
                uint32_t row_bytes, _BMDPixelFormat pixel_format)
                     -> ComPtr<VideoBufferAllocator> {

                 ComPtr<VideoBufferAllocator> alloc;
                 HRESULT hr = self->GetVideoBufferAllocator(
                     buffer_size, width, height, row_bytes,
                     static_cast<BMDPixelFormat>(pixel_format),
                     reinterpret_cast<IDeckLinkVideoBufferAllocator**>(alloc.put()));
                 if (hr != S_OK || !alloc)
                     throw std::runtime_error("GetVideoBufferAllocator failed");
                 return alloc;
             },
             nb::arg("buffer_size"), nb::arg("width"), nb::arg("height"),
             nb::arg("row_bytes"), nb::arg("pixel_format"),
             "Get or create a VideoBufferAllocator for the given parameters.")
        .def("__repr__", [](const ComPtr<VideoBufferAllocatorProvider>&) {
            return "VideoBufferAllocatorProvider()";
        });

    // -- Device: enable_video_input_with_allocator --
    device.def("enable_video_input_with_allocator",
        [](Device& self, _BMDDisplayMode mode, _BMDPixelFormat pixel_format,
           _BMDVideoInputFlags flags,
           ComPtr<VideoBufferAllocatorProvider>& provider,
           bool zero_copy) {
            ComPtr<IDeckLinkInput> input;
            if (self.dl->QueryInterface(IID_IDeckLinkInput, (void**)input.put()) != S_OK)
                throw std::runtime_error("Device does not support input");
            HRESULT hr = input->EnableVideoInputWithAllocatorProvider(
                mode, pixel_format, flags, provider.get());
            if (hr != S_OK)
                throw std::runtime_error(
                    "EnableVideoInputWithAllocatorProvider failed (HRESULT " +
                    std::to_string(hr) + ")");
            self.input_ = std::move(input);
            self.input_callback_ = ComPtr<InputCallback>(
                new InputCallback(self.input_, 8, zero_copy));
            self.input_callback_->set_current_format(mode, pixel_format, flags);
            bool format_detection = (flags & bmdVideoInputEnableFormatDetection) != 0;
            self.input_callback_->set_format_detection(format_detection);
            self.input_->SetCallback(self.input_callback_.get());
        },
        nb::arg("mode"), nb::arg("pixel_format"),
        nb::arg("flags"), nb::arg("allocator_provider"),
        nb::arg("zero_copy") = true,
        "Enable video input using a custom buffer allocator provider. "
        "The SDK will call the provider to obtain allocators for DMA buffers, "
        "enabling GPU-pinned memory for zero-copy capture.");

    // -- Device: create_frame_pool_pinned --
    device.def("create_frame_pool_pinned",
        [](Device& self, int count, int32_t width, int32_t height,
           int32_t row_bytes, _BMDPixelFormat pixel_format,
           ComPtr<VideoBufferAllocator>& allocator) {
            if (!self.output_)
                throw std::runtime_error("Video output not enabled");
            if (!self.output_callback_)
                throw std::runtime_error("No output callback");

            for (int i = 0; i < count; ++i) {
                ComPtr<ManagedBuffer> buf = allocator->allocate_managed();
                ComPtr<IDeckLinkMutableVideoFrame> frame;
                HRESULT hr = self.output_->CreateVideoFrameWithBuffer(
                    width, height, row_bytes, pixel_format,
                    bmdFrameFlagDefault,
                    static_cast<IDeckLinkVideoBuffer*>(buf.get()),
                    frame.put());
                if (hr != S_OK || !frame)
                    throw std::runtime_error(
                        "CreateVideoFrameWithBuffer failed for pool frame " +
                        std::to_string(i) + " (HRESULT " + std::to_string(hr) + ")");

                self.output_callback_->add_pinned_frame(std::move(frame));
            }
        },
        nb::arg("count"), nb::arg("width"), nb::arg("height"),
        nb::arg("row_bytes"), nb::arg("pixel_format"),
        nb::arg("allocator"),
        "Create a frame pool backed by pinned (allocator-managed) buffers. "
        "Each frame uses CreateVideoFrameWithBuffer. "
        "For GPU DMA, pass an allocator using CUDA pinned memory.");
}
