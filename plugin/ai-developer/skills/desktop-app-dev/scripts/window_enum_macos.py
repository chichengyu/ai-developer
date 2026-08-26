"""Top-level window enumeration on macOS via Quartz CGWindowListCopyWindowInfo.

Quartz is part of CoreGraphics, which is part of ApplicationServices. We
load the framework directly via ctypes -- no PyObjC needed.

CGWindowListCopyWindowInfo returns CFArrayRef of CFDictionaryRef; we walk
it and extract kCGWindowNumber / kCGWindowOwnerName / kCGWindowName.
Run inside a thread guarded by a 3-second timeout; cache results for
the session.

Note: On macOS Sonoma+ the OS restricts what windows are visible to a
non-foreground app. If you need to enumerate ALL windows regardless of
foreground state, your binary needs Screen Recording entitlement in
System Settings -> Privacy & Security. Many apps ship without this and
see only their own windows.

Timeout caveat:
- `threading.Thread.join(timeout=3)` does NOT interrupt a running
  CGWindowListCopyWindowInfo call -- Quartz is synchronous C and the
  Python interpreter cannot preempt it mid-walk. The 3-second value is
  a **soft** timeout: if the underlying Quartz call is still running,
  we detach and return whatever the callback accumulated so far.
- For a true hard timeout you would need to spawn a subprocess
  (multiprocessing) or use Quartz under a Swift async bridge.
"""

import ctypes
import ctypes.util
import threading
from ctypes import c_uint32, c_void_p
from dataclasses import dataclass

app_services = ctypes.cdll.LoadLibrary(
    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
)
foundation = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Foundation.framework/Foundation")
core_foundation = ctypes.cdll.LoadLibrary(
    "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
)


@dataclass(frozen=True)
class WindowInfo:
    wid: int
    owner_name: str
    window_name: str


# Quartz / CoreFoundation prototypes
_cg_window_list_copy = app_services.CGWindowListCopyWindowInfo
_cg_window_list_copy.restype = c_void_p
_cg_window_list_copy.argtypes = [c_uint32, c_uint32]

_cf_array_get_count = core_foundation.CFArrayGetCount
_cf_array_get_count.restype = ctypes.c_long
_cf_array_get_count.argtypes = [c_void_p]

_cf_array_get_value_at_index = core_foundation.CFArrayGetValueAtIndex
_cf_array_get_value_at_index.restype = c_void_p
_cf_array_get_value_at_index.argtypes = [c_void_p, ctypes.c_long]

_cf_dict_get_value = core_foundation.CFDictionaryGetValue
_cf_dict_get_value.restype = c_void_p
_cf_dict_get_value.argtypes = [c_void_p, c_void_p]

_cf_string_get_c_string = core_foundation.CFStringGetCString
_cf_string_get_c_string.restype = ctypes.c_bool
_cf_string_get_c_string.argtypes = [c_void_p, ctypes.c_char_p, ctypes.c_long, c_uint32]

_cf_number_get_value = core_foundation.CFNumberGetValue
_cf_number_get_value.restype = ctypes.c_bool
_cf_number_get_value.argtypes = [c_void_p, c_uint32, ctypes.c_void_p]

_cf_release = foundation.CFRelease
_cf_release.restype = None
_cf_release.argtypes = [c_void_p]


# CGWindowListOption constants
kCGWindowListOptionOnScreenOnly = 0x0001
kCGWindowListExcludeDesktopElements = 0x0004
kCGWindowListOptionAll = 0x0007

# CFNumber type
kCFNumberSInt32Type = 3
kCFNumberSInt64Type = 4
kCFNumberIntType = 9

# CFString encoding
kCFStringEncodingUTF8 = 0x08000100


def _cfstr_to_python(s: c_void_p) -> str:
    if not s:
        return ""
    buf = ctypes.create_string_buffer(4096)
    if _cf_string_get_c_string(s, buf, 4096, kCFStringEncodingUTF8):
        return buf.value.decode("utf-8", errors="replace")
    return ""


def _cfnum_to_int(n: c_void_p) -> int:
    if not n:
        return -1
    out = ctypes.c_int64(0)
    if _cf_number_get_value(n, kCFNumberSInt64Type, ctypes.byref(out)):
        return out.value
    return -1


def _extract_window(dict_ref: c_void_p) -> WindowInfo | None:
    """Pull (kCGWindowNumber, kCGWindowOwnerName, kCGWindowName) from a dict."""
    # Keys are CFString constants exported by the framework.
    kCGWindowNumber = ctypes.c_void_p.in_dll(app_services, "kCGWindowNumber").value
    kCGWindowOwnerName = ctypes.c_void_p.in_dll(app_services, "kCGWindowOwnerName").value
    kCGWindowName = ctypes.c_void_p.in_dll(app_services, "kCGWindowName").value

    wid_ref = _cf_dict_get_value(dict_ref, kCGWindowNumber)
    owner_ref = _cf_dict_get_value(dict_ref, kCGWindowOwnerName)
    name_ref = _cf_dict_get_value(dict_ref, kCGWindowName)
    wid = _cfnum_to_int(wid_ref)
    owner = _cfstr_to_python(owner_ref)
    name = _cfstr_to_python(name_ref)
    if wid <= 0:
        return None
    return WindowInfo(wid=wid, owner_name=owner, window_name=name)


class WindowFinder:
    DEFAULT_TIMEOUT_S = 3.0

    def __init__(self, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        self._timeout_s = timeout_s
        self._cache: dict[tuple[str | None, str], int] = {}
        self._lock = threading.Lock()

    def find(self, owner_name: str | None, title_substring: str) -> int | None:
        key = (owner_name, title_substring)
        with self._lock:
            cached = self._cache.get(key)
            if cached:
                return cached
            self._cache.pop(key, None)

        wins = self.list_windows(owner_name=owner_name)
        match = next(
            (w for w in wins if not title_substring or title_substring in w.window_name),
            None,
        )
        if match:
            with self._lock:
                self._cache[key] = match.wid
            return match.wid
        return None

    def list_windows(self, owner_name: str | None = None) -> list[WindowInfo]:
        windows: list[WindowInfo] = []
        done_holder = {"done": False}
        lock = threading.Lock()

        def worker():
            try:
                arr = _cg_window_list_copy(
                    kCGWindowListOptionAll,
                    0,  # kCGNullWindowID
                )
                if not arr:
                    return
                try:
                    count = _cf_array_get_count(arr)
                    for i in range(count):
                        dict_ref = _cf_array_get_value_at_index(arr, i)
                        win = _extract_window(dict_ref)
                        if win is None:
                            continue
                        if owner_name and win.owner_name != owner_name:
                            continue
                        with lock:
                            windows.append(win)
                finally:
                    _cf_release(arr)
            finally:
                done_holder["done"] = True

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        t.join(timeout=self._timeout_s)
        if t.is_alive():
            # Quartz can't be cancelled mid-walk; let it finish, but
            # return whatever we have so the UI thread is responsive.
            t.join(timeout=0.5)
        return windows

    def invalidate(self) -> None:
        with self._lock:
            self._cache.clear()


if __name__ == "__main__":
    f = WindowFinder()
    wins = f.list_windows()
    print(f"Visible windows: {len(wins)}")
    for w in wins[:5]:
        print(f"  wid={w.wid:>6}  owner={w.owner_name!r}  name={w.window_name!r}")
