// SendInput via P/Invoke for .NET (WPF, WinUI 3, WinForms, Avalonia).
// Drop-in usage:
//   SendInput.SendKey(hwnd, "F5");
//   SendInput.PressCombo(hwnd, "ctrl+shift+F1");
using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;

// Keep BuildVkMap() in sync with scripts/vk_table.json (Python is checked automatically).
public static class SendInput
{
    private const int INPUT_KEYBOARD = 1;
    private const int KEYEVENTF_KEYUP = 0x0002;
    private const int SW_RESTORE = 9;

    [DllImport("user32.dll")] private static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] private static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] private static extern uint SendInput(uint n, INPUT[] pInputs, int cbSize);

    [StructLayout(LayoutKind.Sequential)]
    private struct KEYBDINPUT { public ushort wVk; public ushort wScan; public uint dwFlags; public uint time; public IntPtr dwExtraInfo; }

    [StructLayout(LayoutKind.Explicit)]
    private struct INPUT_UNION { [FieldOffset(0)] public KEYBDINPUT ki; }

    [StructLayout(LayoutKind.Sequential)]
    private struct INPUT { public uint type; public INPUT_UNION u; }

    private static readonly Dictionary<string, ushort> Vk = BuildVkMap();

    private static Dictionary<string, ushort> BuildVkMap()
    {
        var map = new Dictionary<string, ushort>(StringComparer.OrdinalIgnoreCase);
        for (char c = 'A'; c <= 'Z'; c++) map[c.ToString()] = (ushort)(0x41 + (c - 'A'));
        for (char c = '0'; c <= '9'; c++) map[c.ToString()] = (ushort)(0x30 + (c - '0'));
        for (int i = 1; i <= 24; i++) map["F" + i] = (ushort)(0x6F + i - 1);
        for (int i = 0; i < 10; i++) map["NUM" + i] = (ushort)(0x60 + i);
        map["BACK"] = 0x08; map["TAB"] = 0x09; map["ENTER"] = 0x0D;
        map["ESCAPE"] = 0x1B; map["ESC"] = 0x1B; map["SPACE"] = 0x20;
        map["PAGEUP"] = 0x21; map["PAGEDOWN"] = 0x22; map["END"] = 0x23; map["HOME"] = 0x24;
        map["LEFT"] = 0x25; map["UP"] = 0x26; map["RIGHT"] = 0x27; map["DOWN"] = 0x28;
        map["INSERT"] = 0x2D; map["DELETE"] = 0x2E;
        map["LSHIFT"] = 0xA0; map["RSHIFT"] = 0xA1;
        map["LCTRL"] = 0xA2; map["RCTRL"] = 0xA3;
        map["LALT"] = 0xA4; map["RALT"] = 0xA5;
        map["LWIN"] = 0x5B; map["RWIN"] = 0x5C;
        map["CAPSLOCK"] = 0x14; map["NUMLOCK"] = 0x90; map["SCROLLLOCK"] = 0x91;
        map["SEMICOLON"] = 0xBA; map["EQUALS"] = 0xBB; map["COMMA"] = 0xBC;
        map["MINUS"] = 0xBD; map["PERIOD"] = 0xBE; map["SLASH"] = 0xBF;
        map["BACKTICK"] = 0xC0; map["LBRACKET"] = 0xDB; map["BACKSLASH"] = 0xDC;
        map["RBRACKET"] = 0xDD; map["APOSTROPHE"] = 0xDE;
        map["SELECT"] = 0x29; map["PRINT"] = 0x2A; map["EXECUTE"] = 0x2B;
        map["SNAPSHOT"] = 0x2C; map["HELP"] = 0x2F;
        map["NUMMULTIPLY"] = 0x6A; map["NUMADD"] = 0x6B; map["NUMSEPARATOR"] = 0x6C;
        map["NUMSUBTRACT"] = 0x6D; map["NUMDECIMAL"] = 0x6E; map["NUMDIVIDE"] = 0x6F;
        return map;
    }

    private static readonly Dictionary<string, string[]> ModAliases = new(StringComparer.OrdinalIgnoreCase)
    {
        ["CTRL"]   = new[] { "LCTRL" },
        ["SHIFT"]  = new[] { "LSHIFT" },
        ["ALT"]    = new[] { "LALT" },
        ["WIN"]    = new[] { "LWIN" },
        ["META"]   = new[] { "LWIN" },
    };

    public static bool EnsureForeground(IntPtr hWnd)
    {
        if (hWnd == IntPtr.Zero) return false;
        for (int i = 0; i < 5; i++)
        {
            ShowWindow(hWnd, SW_RESTORE);
            SetForegroundWindow(hWnd);
            if (GetForegroundWindow() == hWnd) return true;
            Thread.Sleep(50);
        }
        return GetForegroundWindow() == hWnd;
    }

    private static INPUT BuildInput(ushort vk, bool up)
    {
        return new INPUT
        {
            type = INPUT_KEYBOARD,
            u = new INPUT_UNION
            {
                ki = new KEYBDINPUT
                {
                    wVk = vk, wScan = 0,
                    dwFlags = up ? KEYEVENTF_KEYUP : 0u,
                    time = 0, dwExtraInfo = IntPtr.Zero
                }
            }
        };
    }

    public static void SendKey(IntPtr hWnd, string key, int holdMs = 50)
    {
        if (!Vk.TryGetValue(key, out var vk))
            throw new ArgumentException($"Unknown key: {key}");
        if (!EnsureForeground(hWnd))
            throw new InvalidOperationException("Failed to foreground window");
        SendInput(1, new[] { BuildInput(vk, false) }, Marshal.SizeOf<INPUT>());
        Thread.Sleep(holdMs);
        SendInput(1, new[] { BuildInput(vk, true) }, Marshal.SizeOf<INPUT>());
    }

    public static void PressCombo(IntPtr hWnd, string combo, int jitterMs = 0)
    {
        var tokens = combo.Split('+', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (tokens.Length == 0) throw new ArgumentException("empty combo");
        var trigger = tokens[^1];
        if (!Vk.TryGetValue(trigger, out var triggerVk))
            throw new ArgumentException($"Unknown trigger key: {trigger}");
        var mods = new List<string>();
        foreach (var tok in tokens.Take(tokens.Length - 1))
        {
            if (!ModAliases.TryGetValue(tok, out var pair))
                throw new ArgumentException($"Unknown modifier: {tok}");
            mods.AddRange(pair);
        }
        if (!EnsureForeground(hWnd))
            throw new InvalidOperationException("Failed to foreground window");
        foreach (var m in mods) SendInput(1, new[] { BuildInput(Vk[m], false) }, Marshal.SizeOf<INPUT>());
        Thread.Sleep(JitterMs(jitterMs));
        SendInput(1, new[] { BuildInput(triggerVk, false) }, Marshal.SizeOf<INPUT>());
        Thread.Sleep(JitterMs(jitterMs));
        SendInput(1, new[] { BuildInput(triggerVk, true) }, Marshal.SizeOf<INPUT>());
        Thread.Sleep(JitterMs(jitterMs));
        foreach (var m in mods.AsEnumerable().Reverse()) SendInput(1, new[] { BuildInput(Vk[m], true) }, Marshal.SizeOf<INPUT>());
    }

    private static int JitterMs(int requested)
    {
        return requested > 0 ? requested : Random.Shared.Next(50, 151);
    }
}
