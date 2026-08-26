// window_enum_node_shim.cc -- C++ helper for koffi-based EnumWindows in Node.
//
// koffi cannot register raw stdcall callbacks across worker threads, so we
// expose a small DLL that walks windows synchronously and copies results
// into a caller-supplied buffer.
//
// Build (Visual Studio Developer Command Prompt):
//   cl /LD /EHsc /O2 window_enum_node_shim.cc /Fe:win_enum_shim.dll
//
// Or with CMake / Ninja:
//   cmake -B build -G Ninja . && cmake --build build --config Release
//
// From Node, load with koffi and call EnumWindowsToBuffer. The function
// walks windows, returns the count, and fills the caller's buffer with
// {hwnd, title, className} records up to maxRecords.
//
// Use together with scripts/window_enum_node.ts (which calls this shim).

#include <windows.h>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

#pragma pack(push, 1)
struct WindowRecord {
    uint64_t hwnd;
    uint16_t title[256];
    uint16_t className[256];
};
#pragma pack(pop)

struct EnumContext {
    std::vector<WindowRecord>* out;
    size_t max;
    const wchar_t* classFilter;   // may be null
    const wchar_t* titleFilter;   // may be null
    bool matchAll;                // when true, ignore titleFilter
    volatile bool* cancelled;
};

static BOOL CALLBACK Callback(HWND hwnd, LPARAM lParam) {
    auto* ctx = reinterpret_cast<EnumContext*>(lParam);
    if (*(ctx->cancelled)) return FALSE;

    // Skip invisible / owned windows unless matchAll
    if (!ctx->matchAll && !IsWindowVisible(hwnd)) return TRUE;

    wchar_t cls[256] = {0};
    GetClassNameW(hwnd, cls, 256);
    if (ctx->classFilter && std::wcscmp(cls, ctx->classFilter) != 0) return TRUE;

    int len = GetWindowTextLengthW(hwnd);
    if (len <= 0) {
        if (!ctx->matchAll) return TRUE;
        WindowRecord rec{};
        rec.hwnd = reinterpret_cast<uint64_t>(hwnd);
        std::wcsncpy(reinterpret_cast<wchar_t*>(rec.className), cls, 255);
        ctx->out->push_back(rec);
        return ctx->out->size() < ctx->max;
    }

    std::wstring title(len + 1, L'\0');
    GetWindowTextW(hwnd, &title[0], len + 1);
    if (!ctx->matchAll && ctx->titleFilter &&
        title.find(ctx->titleFilter) == std::wstring::npos) {
        return TRUE;
    }

    if (ctx->out->size() >= ctx->max) return FALSE;
    WindowRecord rec{};
    rec.hwnd = reinterpret_cast<uint64_t>(hwnd);
    std::wcsncpy(reinterpret_cast<wchar_t*>(rec.title), title.c_str(), 255);
    std::wcsncpy(reinterpret_cast<wchar_t*>(rec.className), cls, 255);
    ctx->out->push_back(rec);
    return TRUE;
}

extern "C" __declspec(dllexport)
uint32_t __stdcall EnumWindowsToBuffer(
    WindowRecord* buffer,
    uint32_t maxRecords,
    const wchar_t* classFilter,    // null = no filter
    const wchar_t* titleFilter,    // null = no filter
    int matchAll,
    volatile uint32_t* cancelled   // nonzero => abort
) {
    std::vector<WindowRecord> records;
    records.reserve(maxRecords);
    EnumContext ctx{&records, maxRecords, classFilter, titleFilter,
                    matchAll != 0, reinterpret_cast<volatile bool*>(cancelled)};
    EnumWindows(&Callback, reinterpret_cast<LPARAM>(&ctx));
    const size_t n = records.size();
    if (n > 0 && buffer) std::memcpy(buffer, records.data(), n * sizeof(WindowRecord));
    return static_cast<uint32_t>(n);
}

extern "C" __declspec(dllexport)
void __stdcall CancelEnum(volatile uint32_t* cancelled) {
    if (cancelled) *cancelled = 1;
}

extern "C" __declspec(dllexport)
uint32_t __stdcall GetForegroundHwnd() {
    return static_cast<uint32_t>(reinterpret_cast<uint64_t>(GetForegroundWindow()));
}
