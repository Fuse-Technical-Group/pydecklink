#pragma once

#include <chrono>
#include <cstring>

// Platform compatibility layer for DeckLink SDK differences between
// Linux/Mac (dlopen dispatch, const char* strings) and
// Windows (COM CoCreateInstance, BSTR strings).

#ifdef _WIN32

#include <Python.h>  // PyErr_WarnEx for COM apartment check
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <comdef.h>
#include "DeckLinkAPI.h"
#include "comptr.h"

#include <string>

// DeckLink type aliases differ per platform.
using dlstring_t = BSTR;
using dlbool_t = BOOL;

// On Windows, DeckLink uses COM.  The iterator is obtained via
// CoCreateInstance rather than the dlopen-based dispatch on Linux.
// DeckLink SDK callbacks arrive on internal threads, so MTA
// (COINIT_MULTITHREADED) is required.  If the calling thread was
// already initialized as STA by a GUI framework, CoInitializeEx
// returns RPC_E_CHANGED_MODE — warn rather than silently proceed,
// because downstream SDK calls may fail in hard-to-diagnose ways.
inline ComPtr<IDeckLinkIterator> CreateDeckLinkIteratorInstance() {
    ComPtr<IDeckLinkIterator> iter;
    HRESULT co_hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (co_hr == RPC_E_CHANGED_MODE) {
        PyErr_WarnEx(PyExc_RuntimeWarning,
            "COM already initialized as STA on this thread. "
            "pydecklink requires MTA (COINIT_MULTITHREADED). "
            "DeckLink operations may fail.", 1);
    }
    HRESULT hr = CoCreateInstance(
        CLSID_CDeckLinkIterator, nullptr, CLSCTX_ALL,
        IID_IDeckLinkIterator, reinterpret_cast<void**>(iter.put()));
    if (FAILED(hr))
        return ComPtr<IDeckLinkIterator>();
    return iter;
}

// IDeckLinkAPIInformation is a process-global singleton.  Linux/macOS
// expose a free-function ``CreateDeckLinkAPIInformationInstance`` from
// DeckLinkAPIDispatch.cpp; Windows requires CoCreateInstance on
// CLSID_CDeckLinkAPIInformation.  The CO init mirrors the iterator
// path — same MTA requirement, same diagnostic if the thread is STA.
inline IDeckLinkAPIInformation* CreateDeckLinkAPIInformationInstance() {
    HRESULT co_hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (co_hr == RPC_E_CHANGED_MODE) {
        PyErr_WarnEx(PyExc_RuntimeWarning,
            "COM already initialized as STA on this thread. "
            "pydecklink requires MTA (COINIT_MULTITHREADED). "
            "DeckLink operations may fail.", 1);
    }
    IDeckLinkAPIInformation* info = nullptr;
    HRESULT hr = CoCreateInstance(
        CLSID_CDeckLinkAPIInformation, nullptr, CLSCTX_ALL,
        IID_IDeckLinkAPIInformation, reinterpret_cast<void**>(&info));
    if (FAILED(hr))
        return nullptr;
    return info;
}

// A DeckLink string the caller owns for the length of one call, freed on
// scope exit. `SetString` copies what it is handed, so the SDK never holds
// this pointer (§spec:ethernet).
class DeckLinkStringFromStd {
   public:
    explicit DeckLinkStringFromStd(const std::string& text) {
        int wlen = ::MultiByteToWideChar(CP_UTF8, 0, text.data(),
                                         static_cast<int>(text.size()), nullptr, 0);
        std::wstring wide(static_cast<size_t>(wlen), L'\0');
        ::MultiByteToWideChar(CP_UTF8, 0, text.data(), static_cast<int>(text.size()),
                              wide.data(), wlen);
        value_ = ::SysAllocStringLen(wide.data(), static_cast<UINT>(wlen));
    }
    ~DeckLinkStringFromStd() { if (value_) ::SysFreeString(value_); }
    DeckLinkStringFromStd(const DeckLinkStringFromStd&) = delete;
    DeckLinkStringFromStd& operator=(const DeckLinkStringFromStd&) = delete;
    dlstring_t get() const { return value_; }

   private:
    BSTR value_ = nullptr;
};

// DeckLink string type on Windows is BSTR (wide string).
// Helper to convert BSTR -> std::string and free it.
inline std::string DeckLinkStringToStd(BSTR bstr) {
    if (!bstr) return "";
    int wlen = ::SysStringLen(bstr);
    if (wlen == 0) {
        ::SysFreeString(bstr);
        return "";
    }
    int mblen = ::WideCharToMultiByte(CP_UTF8, 0, bstr, wlen, nullptr, 0, nullptr, nullptr);
    std::string result(mblen, '\0');
    ::WideCharToMultiByte(CP_UTF8, 0, bstr, wlen, &result[0], mblen, nullptr, nullptr);
    ::SysFreeString(bstr);
    return result;
}

#elif defined(__APPLE__)  // macOS

#include <CoreFoundation/CoreFoundation.h>
#include "DeckLinkAPI.h"
#include <string>

// DeckLink type aliases on macOS — the SDK uses CFStringRef.
using dlstring_t = CFStringRef;
using dlbool_t = bool;

// On macOS, CreateDeckLinkIteratorInstance is provided by
// DeckLinkAPIDispatch.cpp — no wrapper needed.

// See the Windows definition: one call's worth of DeckLink string,
// released on scope exit (§spec:ethernet).
class DeckLinkStringFromStd {
   public:
    explicit DeckLinkStringFromStd(const std::string& text)
        : value_(CFStringCreateWithBytes(kCFAllocatorDefault,
                                         reinterpret_cast<const UInt8*>(text.data()),
                                         static_cast<CFIndex>(text.size()),
                                         kCFStringEncodingUTF8, false)) {}
    ~DeckLinkStringFromStd() { if (value_) CFRelease(value_); }
    DeckLinkStringFromStd(const DeckLinkStringFromStd&) = delete;
    DeckLinkStringFromStd& operator=(const DeckLinkStringFromStd&) = delete;
    dlstring_t get() const { return value_; }

   private:
    CFStringRef value_ = nullptr;
};

// On macOS, DeckLink strings are CFStringRef.  Convert to std::string
// and release the CF object.
inline std::string DeckLinkStringToStd(CFStringRef cfstr) {
    if (!cfstr) return "";
    // Fast path: try direct pointer access (works for ASCII/UTF-8 backing).
    if (const char* cstr = CFStringGetCStringPtr(cfstr, kCFStringEncodingUTF8)) {
        std::string result(cstr);
        CFRelease(cfstr);
        return result;
    }
    // Slow path: copy into buffer.
    CFIndex len = CFStringGetLength(cfstr);
    CFIndex bufSize = 0;
    CFStringGetBytes(cfstr, CFRangeMake(0, len), kCFStringEncodingUTF8, '?', false, nullptr, 0, &bufSize);
    std::string result(static_cast<size_t>(bufSize), '\0');
    CFStringGetBytes(cfstr, CFRangeMake(0, len), kCFStringEncodingUTF8, '?', false,
                     reinterpret_cast<UInt8*>(&result[0]), bufSize, nullptr);
    CFRelease(cfstr);
    return result;
}

#else  // Linux

#include "DeckLinkAPI.h"
#include <cstdlib>
#include <string>

// DeckLink type aliases on Linux.
using dlstring_t = const char*;
using dlbool_t = bool;

// On Linux, CreateDeckLinkIteratorInstance is provided by
// DeckLinkAPIDispatch.cpp — no wrapper needed.

// See the Windows definition. On Linux a DeckLink string is a plain
// `const char*`, so this borrows the caller's buffer and allocates nothing
// (§spec:ethernet).
class DeckLinkStringFromStd {
   public:
    explicit DeckLinkStringFromStd(const std::string& text) : value_(text) {}
    DeckLinkStringFromStd(const DeckLinkStringFromStd&) = delete;
    DeckLinkStringFromStd& operator=(const DeckLinkStringFromStd&) = delete;
    dlstring_t get() const { return value_.c_str(); }

   private:
    std::string value_;
};

// On Linux, DeckLink strings are const char* allocated with malloc.
inline std::string DeckLinkStringToStd(const char* str) {
    if (!str) return "";
    std::string result(str);
    free(const_cast<char*>(str));
    return result;
}

#endif

// Monotonic clock in microseconds (platform-independent).
inline int64_t steady_clock_us() {
    using namespace std::chrono;
    return duration_cast<microseconds>(
        steady_clock::now().time_since_epoch()).count();
}

// Cross-platform IID comparison and IUnknown IID access.
//
// IIDs are 16-byte structs on every platform — Windows GUID, Linux
// REFIID (LinuxCOM.h), macOS CFUUIDBytes — so bytewise compare is
// equivalent to the platform-specific helper (``IsEqualIID`` on
// Windows is itself a memcmp).
//
// The IUnknown IID symbol differs:
//   - Windows: ``IID_IUnknown`` (from <unknwn.h>, included via <comdef.h>).
//   - Linux:   ``IUnknownUUID`` aliased to ``IID_IUnknown`` (REFIID).
//   - macOS:   ``IUnknownUUID`` is ``CFUUIDRef``; bytes via ``CFUUIDGetUUIDBytes``.
// On Linux, ``CFUUIDGetUUIDBytes(x)`` is ``#define``d to ``x`` — a no-op
// alias — so the same expression works on both POSIX platforms.
inline bool iid_matches(REFIID got, REFIID expected) {
    return std::memcmp(&got, &expected, sizeof(REFIID)) == 0;
}
#ifdef _WIN32
#define PYDECKLINK_IUNKNOWN_IID IID_IUnknown
#else
#define PYDECKLINK_IUNKNOWN_IID CFUUIDGetUUIDBytes(IUnknownUUID)
#endif
