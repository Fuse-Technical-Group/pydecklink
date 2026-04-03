#pragma once

#include <chrono>

// Platform compatibility layer for DeckLink SDK differences between
// Linux/Mac (dlopen dispatch, const char* strings) and
// Windows (COM CoCreateInstance, BSTR strings).

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

#else  // Linux / macOS

#include "DeckLinkAPI.h"
#include <cstdlib>
#include <string>

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

#endif

// Monotonic clock in microseconds (platform-independent).
inline int64_t steady_clock_us() {
    using namespace std::chrono;
    return duration_cast<microseconds>(
        steady_clock::now().time_since_epoch()).count();
}
