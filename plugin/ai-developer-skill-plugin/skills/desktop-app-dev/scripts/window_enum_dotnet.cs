// Top-level window enumeration for .NET.
// Always runs EnumWindows inside a thread with a 3-second timeout, and caches
// results per (class, title-substring) for the current session.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

public sealed class WindowInfo
{
    public IntPtr Hwnd { get; init; }
    public string Title { get; init; } = "";
    public string ClassName { get; init; } = "";
    public override string ToString() => $"{Hwnd,8}  [{ClassName}]  {Title}";
}

public sealed class WindowFinder
{
    public TimeSpan Timeout { get; set; } = TimeSpan.FromSeconds(3);
    private readonly Dictionary<(string, string), IntPtr> _cache = new();
    private readonly object _lock = new();

    private delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern IntPtr FindWindowW(string? cls, string? title);
    [DllImport("user32.dll")] private static extern bool IsWindow(IntPtr hWnd);
    [DllImport("user32.dll")] private static extern int GetWindowTextLengthW(IntPtr hWnd);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetWindowTextW(IntPtr hWnd, System.Text.StringBuilder text, int count);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetClassNameW(IntPtr hWnd, System.Text.StringBuilder cls, int count);
    [DllImport("user32.dll")] private static extern bool EnumWindows(EnumProc lpEnumFunc, IntPtr lParam);

    public IntPtr? Find(string? className, string titleSubstring)
    {
        var key = (className ?? "", titleSubstring);
        lock (_lock)
        {
            if (_cache.TryGetValue(key, out var cached) && IsWindow(cached)) return cached;
            _cache.Remove(key);
        }
        if (className != null && !HasWildcards(titleSubstring))
        {
            var h = FindWindowW(className, titleSubstring);
            if (h != IntPtr.Zero) { lock (_lock) _cache[key] = h; return h; }
        }
        var matches = EnumWithTimeout(className, titleSubstring).Result;
        if (matches.Count > 0) { lock (_lock) _cache[key] = matches[0].Hwnd; return matches[0].Hwnd; }
        return null;
    }

    public List<WindowInfo> ListWindows(string? className = null) =>
        EnumWithTimeout(className, "", matchAll: true).Result;

    public void Invalidate() { lock (_lock) _cache.Clear(); }

    private async Task<List<WindowInfo>> EnumWithTimeout(string? className, string titleSubstring, bool matchAll = false)
    {
        var results = new List<WindowInfo>();
        var done = false;
        bool Callback(IntPtr hWnd, IntPtr _)
        {
            if (done) return false;
            var len = GetWindowTextLengthW(hWnd);
            if (len <= 0 && !matchAll) return true;
            var title = new System.Text.StringBuilder(len + 1);
            GetWindowTextW(hWnd, title, title.Capacity);
            var cls = new System.Text.StringBuilder(256);
            GetClassNameW(hWnd, cls, cls.Capacity);
            if (className != null && cls.ToString() != className) return true;
            if (!matchAll && titleSubstring.Length > 0 && !title.ToString().Contains(titleSubstring)) return true;
            results.Add(new WindowInfo { Hwnd = hWnd, Title = title.ToString(), ClassName = cls.ToString() });
            return true;
        }
        var t = new Thread(() => { try { EnumWindows(Callback, IntPtr.Zero); } finally { done = true; } }) { IsBackground = true };
        t.Start();
        var sw = System.Diagnostics.Stopwatch.StartNew();
        while (t.IsAlive && sw.Elapsed < Timeout) await Task.Delay(50);
        if (t.IsAlive) { done = true; t.Join(100); }
        return results;
    }

    private static bool HasWildcards(string s) => s.IndexOfAny(new[] { '*', '?' }) >= 0;
}
