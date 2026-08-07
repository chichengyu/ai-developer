"""Top-level window enumeration with FindWindowW first and EnumWindows fallback.

Always runs EnumWindows inside a thread guarded by a 3-second timeout, and
caches results by (class, title-substring) for the current session. Owner-drawn
windows can otherwise hang EnumWindows indefinitely and freeze the UI.
"""

import ctypes
import threading
from ctypes import wintypes
from dataclasses import dataclass

user32 = ctypes.WinDLL("user32", use_last_error=True)
EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    class_name: str


class WindowFinder:
    DEFAULT_TIMEOUT_S = 3.0

    def __init__(self, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        self._timeout_s = timeout_s
        self._cache: dict[tuple[str | None, str], int] = {}
        self._lock = threading.Lock()

    def find(self, class_name: str | None, title_substring: str) -> int | None:
        key = (class_name, title_substring)
        with self._lock:
            cached = self._cache.get(key)
            if cached and user32.IsWindow(cached):
                return cached
            self._cache.pop(key, None)

        if class_name and not _has_wildcards(title_substring):
            hwnd = user32.FindWindowW(class_name, title_substring)
            if hwnd:
                with self._lock:
                    self._cache[key] = hwnd
                return hwnd

        matches = self._enum_with_timeout(class_name, title_substring)
        if matches:
            with self._lock:
                self._cache[key] = matches[0].hwnd
            return matches[0].hwnd
        return None

    def list_windows(self, class_name: str | None = None) -> list[WindowInfo]:
        return self._enum_with_timeout(class_name, title_substring="", match_all=True)

    def invalidate(self) -> None:
        with self._lock:
            self._cache.clear()

    def _enum_with_timeout(self, class_name, title_substring, match_all=False):
        results = []
        holder = {"done": False}

        def callback(hwnd, _lparam):
            if holder["done"]:
                return False
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0 and not match_all:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            cls = cls_buf.value
            if class_name and cls != class_name:
                return True
            if not match_all and title_substring and title_substring not in title:
                return True
            results.append(WindowInfo(hwnd=hwnd, title=title, class_name=cls))
            return True

        def worker():
            try:
                user32.EnumWindows(EnumWindowsProc(callback), 0)
            finally:
                holder["done"] = True

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        t.join(timeout=self._timeout_s)
        if t.is_alive():
            holder["done"] = True
            t.join(timeout=0.1)
        return results


def _has_wildcards(s: str) -> bool:
    return any(ch in s for ch in "*?")


if __name__ == "__main__":
    f = WindowFinder()
    print("Top-level windows:")
    for w in f.list_windows()[:5]:
        print(f"  {w.hwnd:>8}  [{w.class_name}]  {w.title!r}")
