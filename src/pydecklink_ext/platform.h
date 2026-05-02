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
