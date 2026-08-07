// SendInput for C/C++ (Win32, Qt, MFC, any C++ UI).
// Compile: cl /EHsc sendinput_win32.c user32.lib
// Drop-in usage:
//   ensureForeground(hwnd);
//   sendKey(hwnd, "F5", 50);
//   pressCombo(hwnd, "ctrl+shift+F1", 0);   // 0 = random 50-150 ms jitter
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

// Keep VK_MAP in sync with scripts/vk_table.json (Python is checked automatically).
#define INPUT_KEYBOARD 1
#define KEYEVENTF_KEYUP 0x0002
#define SW_RESTORE 9

static const struct { const char *name; WORD vk; } VK_MAP[] = {
    {"back", VK_BACK}, {"tab", VK_TAB}, {"enter", VK_RETURN}, {"escape", VK_ESCAPE}, {"esc", VK_ESCAPE},
    {"space", VK_SPACE}, {"pageup", VK_PRIOR}, {"pagedown", VK_NEXT}, {"end", VK_END}, {"home", VK_HOME},
    {"left", VK_LEFT}, {"up", VK_UP}, {"right", VK_RIGHT}, {"down", VK_DOWN},
    {"insert", VK_INSERT}, {"delete", VK_DELETE},
    {"select", 0x29}, {"print", 0x2A}, {"execute", 0x2B}, {"snapshot", 0x2C}, {"help", 0x2F},
    {"lshift", VK_LSHIFT}, {"rshift", VK_RSHIFT}, {"lctrl", VK_LCONTROL}, {"rctrl", VK_RCONTROL},
    {"lalt", VK_LMENU}, {"ralt", VK_RMENU}, {"lwin", VK_LWIN}, {"rwin", VK_RWIN},
    {"capslock", VK_CAPITAL}, {"numlock", VK_NUMLOCK}, {"scrolllock", VK_SCROLL},
    {"semicolon", VK_OEM_1}, {"equals", VK_OEM_PLUS}, {"comma", VK_OEM_COMMA},
    {"minus", VK_OEM_MINUS}, {"period", VK_OEM_PERIOD}, {"slash", VK_OEM_2},
    {"backtick", VK_OEM_3}, {"lbracket", VK_OEM_4}, {"backslash", VK_OEM_5},
    {"rbracket", VK_OEM_6}, {"apostrophe", VK_OEM_7},
    {"num0", VK_NUMPAD0}, {"num1", VK_NUMPAD1}, {"num2", VK_NUMPAD2}, {"num3", VK_NUMPAD3},
    {"num4", VK_NUMPAD4}, {"num5", VK_NUMPAD5}, {"num6", VK_NUMPAD6}, {"num7", VK_NUMPAD7},
    {"num8", VK_NUMPAD8}, {"num9", VK_NUMPAD9},
    {"nummultiply", VK_MULTIPLY}, {"numadd", VK_ADD}, {"numsubtract", VK_SUBTRACT},
    {"numdecimal", VK_DECIMAL}, {"numdivide", VK_DIVIDE}, {"numseparator", 0x6C},
    {NULL, 0}
};

static WORD lookup_vk(const char *key) {
    if (strlen(key) == 1) {
        char c = (char)tolower((unsigned char)key[0]);
        if (c >= 'a' && c <= 'z') return (WORD)(0x41 + (c - 'a'));
        if (c >= '0' && c <= '9') return (WORD)(0x30 + (c - '0'));
    }
    if (key[0] == 'f' || key[0] == 'F') {
        int n = atoi(key + 1);
        if (n >= 1 && n <= 24) return (WORD)(VK_F1 + n - 1);
    }
    for (int i = 0; VK_MAP[i].name; ++i)
        if (_stricmp(key, VK_MAP[i].name) == 0) return VK_MAP[i].vk;
    return 0;
}

static int jitter_ms(int requested) {
    if (requested > 0) return requested;
    static int seeded = 0;
    if (!seeded) {
        srand((unsigned)GetTickCount());
        seeded = 1;
    }
    return 50 + (rand() % 101);
}

BOOL ensureForeground(HWND hwnd) {
    if (!hwnd) return FALSE;
    for (int i = 0; i < 5; ++i) {
        ShowWindow(hwnd, SW_RESTORE);
        SetForegroundWindow(hwnd);
        if (GetForegroundWindow() == hwnd) return TRUE;
        Sleep(50);
    }
    return GetForegroundWindow() == hwnd;
}

void pressOne(WORD vk, BOOL up) {
    INPUT inp = {0};
    inp.type = INPUT_KEYBOARD;
    inp.ki.wVk = vk;
    inp.ki.wScan = 0;
    inp.ki.dwFlags = up ? KEYEVENTF_KEYUP : 0;
    inp.ki.time = 0;
    inp.ki.dwExtraInfo = 0;
    SendInput(1, &inp, sizeof(INPUT));
}

void sendKey(HWND hwnd, const char *key, int holdMs) {
    WORD vk = lookup_vk(key);
    if (!vk) { fprintf(stderr, "Unknown key: %s\n", key); return; }
    if (!ensureForeground(hwnd)) { fprintf(stderr, "Foreground failed\n"); return; }
    pressOne(vk, FALSE);
    Sleep(holdMs);
    pressOne(vk, TRUE);
}

void pressCombo(HWND hwnd, const char *combo, int jitterMs) {
    char buf[256]; strncpy(buf, combo, sizeof(buf) - 1); buf[sizeof(buf) - 1] = 0;
    char *tokens[16]; int n = 0;
    char *save; char *tok = strtok_r(buf, "+", &save);
    while (tok && n < 16) { tokens[n++] = tok; tok = strtok_r(NULL, "+", &save); }
    if (!n) return;
    char *trigger = tokens[n - 1];
    WORD triggerVk = lookup_vk(trigger);
    if (!triggerVk) { fprintf(stderr, "Unknown trigger: %s\n", trigger); return; }
    WORD modVks[8]; int m = 0;
    for (int i = 0; i < n - 1 && m < 8; ++i) {
        char *t = tokens[i];
        if      (_stricmp(t, "ctrl")  == 0 || _stricmp(t, "control") == 0) { modVks[m++] = VK_LCONTROL; }
        else if (_stricmp(t, "shift") == 0) { modVks[m++] = VK_LSHIFT; }
        else if (_stricmp(t, "alt")   == 0) { modVks[m++] = VK_LMENU; }
        else if (_stricmp(t, "win")   == 0 || _stricmp(t, "meta") == 0) { modVks[m++] = VK_LWIN; }
        else fprintf(stderr, "Unknown modifier: %s\n", t);
    }
    if (!ensureForeground(hwnd)) { fprintf(stderr, "Foreground failed\n"); return; }
    for (int i = 0; i < m; ++i) pressOne(modVks[i], FALSE);
    Sleep(jitter_ms(jitterMs));
    pressOne(triggerVk, FALSE);
    Sleep(jitter_ms(jitterMs));
    pressOne(triggerVk, TRUE);
    Sleep(jitter_ms(jitterMs));
    for (int i = m - 1; i >= 0; --i) pressOne(modVks[i], TRUE);
}
