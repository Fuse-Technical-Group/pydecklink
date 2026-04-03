#pragma once

// Platform compatibility layer for DeckLink SDK differences between
// Linux/Mac (dlopen dispatch, const char* strings, POSIX clocks) and
// Windows (COM CoCreateInstance, BSTR strings, QPC).

#ifdef _WIN32

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <comdef.h>
#include "DeckLinkAPI.h"

#include <string>

// DeckLink type aliases differ per platform.
using dlstring_t = BSTR;
using dlbool_t = BOOL;

// On Windows, DeckLink uses COM.  The iterator is obtained via
// CoCreateInstance rather than the dlopen-based dispatch on Linux.
inline IDeckLinkIterator* CreateDeckLinkIteratorInstance() {
    IDeckLinkIterator* iter = nullptr;
    // CoInitializeEx is idempotent when called with the same flags.
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    HRESULT hr = CoCreateInstance(
        CLSID_CDeckLinkIterator, nullptr, CLSCTX_ALL,
        IID_IDeckLinkIterator, reinterpret_cast<void**>(&iter));
    if (FAILED(hr))
        return nullptr;
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

// Monotonic clock using QueryPerformanceCounter.
inline int64_t monotonic_raw_us() {
    static LARGE_INTEGER freq = []() {
        LARGE_INTEGER f;
        QueryPerformanceFrequency(&f);
        return f;
    }();
    LARGE_INTEGER now;
    QueryPerformanceCounter(&now);
    return now.QuadPart * 1000000 / freq.QuadPart;
}

#else  // Linux / macOS

#include "DeckLinkAPI.h"
#include <cstdlib>
#include <string>
#include <time.h>

// DeckLink type aliases on Linux/Mac.
using dlstring_t = const char*;
using dlbool_t = bool;

// On Linux/Mac, CreateDeckLinkIteratorInstance is provided by
// DeckLinkAPIDispatch.cpp — no wrapper needed.

// On Linux/Mac, DeckLink strings are const char* allocated with malloc.
inline std::string DeckLinkStringToStd(const char* str) {
    if (!str) return "";
    std::string result(str);
    free(const_cast<char*>(str));
    return result;
}

// Monotonic clock using CLOCK_MONOTONIC_RAW (Linux) or CLOCK_MONOTONIC (Mac).
inline int64_t monotonic_raw_us() {
#ifdef CLOCK_MONOTONIC_RAW
    clockid_t clk = CLOCK_MONOTONIC_RAW;
#else
    clockid_t clk = CLOCK_MONOTONIC;
#endif
    struct timespec ts;
    clock_gettime(clk, &ts);
    return static_cast<int64_t>(ts.tv_sec) * 1000000 + ts.tv_nsec / 1000;
}

#endif
