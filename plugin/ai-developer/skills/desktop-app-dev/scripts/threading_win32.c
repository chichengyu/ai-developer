// Raw Win32 background work with cancellation + progress + safe UI bridge.
//
// The worker thread posts WM_APP messages to the owning HWND. Only the UI
// thread handles those messages and touches controls. Do NOT use this
// PostMessage bridge to synthesize keyboard/mouse input -- hardware input
// must go through SendInput (see scripts/sendinput_win32.c).
//
// WndProc sketch:
//   case WM_JOB_PROGRESS:
//       SetProgressBarPos(hwnd, (int)wParam);
//       return 0;
//   case WM_JOB_DONE:
//       SetWindowTextW(hwnd, L"done");
//       return 0;
//   case WM_JOB_ERROR:
//       SetWindowTextW(hwnd, L"error");
//       return 0;
//   case WM_JOB_CANCELLED:
//       SetWindowTextW(hwnd, L"cancelled");
//       return 0;

#include <windows.h>

#define WM_JOB_PROGRESS (WM_APP + 1)
#define WM_JOB_DONE     (WM_APP + 2)
#define WM_JOB_ERROR    (WM_APP + 3)
#define WM_JOB_CANCELLED (WM_APP + 4)

typedef struct JobContext {
    HWND hwnd;
    int total;
    volatile LONG cancelled;
} JobContext;

static DWORD WINAPI JobThreadProc(LPVOID param) {
    JobContext* ctx = (JobContext*)param;
    for (int step = 1; step <= ctx->total; step++) {
        if (InterlockedCompareExchange(&ctx->cancelled, 0, 0) != 0) {
            PostMessageW(ctx->hwnd, WM_JOB_CANCELLED, 0, 0);
            return 0;
        }
        PostMessageW(
            ctx->hwnd,
            WM_JOB_PROGRESS,
            (WPARAM)((step * 100) / ctx->total),
            0);
        Sleep(50);
    }
    PostMessageW(ctx->hwnd, WM_JOB_DONE, (WPARAM)ctx->total, 0);
    return 0;
}

void JobStart(HWND hwnd, int total, HANDLE* thread, JobContext* ctx) {
    ctx->hwnd = hwnd;
    ctx->total = total;
    InterlockedExchange(&ctx->cancelled, 0);
    *thread = CreateThread(NULL, 0, JobThreadProc, ctx, 0, NULL);
}

void JobCancel(JobContext* ctx) {
    InterlockedExchange(&ctx->cancelled, 1);
}
