// auto_update_winsparkle.cpp -- WinSparkle drop-in for C++ / Qt / wxWidgets / MFC.
//
// WinSparkle is a tiny DLL (winsparkle.dll + winsparkle.lib) that handles
// the entire update flow over HTTPS. Call once at startup, then poll
// (or trigger manually). https://winsparkle.com/
//
// Link: winsparkle.lib
// Ship: winsparkle.dll alongside your EXE
//
// Build (MSVC):
//   cl /EHsc /O2 auto_update_winsparkle.cpp winsparkle.lib /Fe:myapp.exe

#include <winsparkle.h>
#include <windows.h>
#include <string>
#include <atomic>

namespace upd {
namespace {
    // Convert wide string to UTF-8 narrow string for Win32 char APIs.
    // Returns empty string on conversion failure.
    std::string to_narrow(const std::wstring& w) {
        if (w.empty()) return {};
        int needed = WideCharToMultiByte(CP_UTF8, 0, w.c_str(),
                                         static_cast<int>(w.size()),
                                         nullptr, 0, nullptr, nullptr);
        if (needed <= 0) return {};
        std::string out(static_cast<size_t>(needed), '\0');
        int written = WideCharToMultiByte(CP_UTF8, 0, w.c_str(),
                                          static_cast<int>(w.size()),
                                          &out[0], needed, nullptr, nullptr);
        if (written != needed) return {};
        return out;
    }
}


namespace detail {
    std::atomic<bool> g_initialized{false};
    std::wstring g_feedUrl;
    std::wstring g_appName;
    std::wstring g_appVersion;
}

void init(const std::wstring& feedUrl,
          const std::wstring& appName,
          const std::wstring& appVersion,
          const std::wstring& signature = L"") {
    if (detail::g_initialized.exchange(true)) return;
    detail::g_feedUrl  = feedUrl;
    detail::g_appName  = appName;
    detail::g_appVersion = appVersion;

    // WinSparkle takes narrow (UTF-8) strings; we hold wide in the API.
    // wcstombs via std::wstring_convert, or just hard-code narrow when known.
    win_sparkle_set_appcast_url(to_narrow(feedUrl).c_str());
    win_sparkle_set_app_name(to_narrow(appName).c_str());
    win_sparkle_set_app_version(to_narrow(appVersion).c_str());

    // Optional: code-sign public key (Ed25519). Empty for unsigned dev builds.
    if (!signature.empty()) {
        win_sparkle_set_ed25519_signature(signature.c_str());
    }

    // Check every 6 hours; skip silently on first launch.
    win_sparkle_set_update_check_interval(6 * 3600);

    // Polish: notify only when an update is available (default).
    win_sparkle_init();

    // Run a check immediately so the user sees the dialog at startup if needed.
    win_sparkle_check_update_without_ui();
}

void checkNow() {
    if (!detail::g_initialized) return;
    win_sparkle_check_update_with_ui();
}

void shutdown() {
    if (!detail::g_initialized.exchange(false)) return;
    win_sparkle_cleanup();
}

}  // namespace upd

// ---- Example: integrate into a Qt main() -------------------------------
#if 0
#include <QApplication>
#include "mainwindow.h"

int main(int argc, char** argv) {
    QApplication app(argc, argv);
    upd::init(L"https://updates.example.com/myapp/appcast.xml",
              L"MyApp",
              L"1.4.2",
              L"");  // Ed25519 pubkey in hex
    QObject::connect(&app, &QCoreApplication::aboutToQuit, &upd::shutdown);
    MainWindow w; w.show();
    return app.exec();
}
#endif
