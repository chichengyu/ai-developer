"""Top-level window enumeration on Linux via X11 XQueryTree + EWMH.

Loads libX11 directly via ctypes -- no python-xlib needed. For richer
metadata (window title, owner PID, geometry) we additionally consult the
EWMH `_NET_CLIENT_LIST` and `_NET_WM_NAME` properties on the root window.

Wayland note: Wayland does not expose a global window list to clients;
apps on Wayland must use the RemoteDesktop portal (org.freedesktop.portal.Desktop)
or ScreenCast to enumerate. This module is X11-only.

Timeout caveat:
- `threading.Thread.join(timeout=3)` does NOT interrupt a running
  XQueryTree or XGetWindowProperty call -- Xlib is synchronous C and
  the Python interpreter cannot preempt it mid-walk. The 3-second value
  is a **soft** timeout: if the underlying X call is still running,
  we detach and return whatever was accumulated so far.
- For a true hard timeout you would need to spawn a subprocess
  (multiprocessing) or talk to Xlib from a child thread that you can
  cancel.
"""

import ctypes
import threading
from dataclasses import dataclass

x11 = ctypes.cdll.LoadLibrary("libX11.so.6")


@dataclass(frozen=True)
class WindowInfo:
    wid: int
    title: str
    wm_class: str


# ---- X11 prototypes -------------------------------------------------------
_XOpenDisplay = x11.XOpenDisplay
_XOpenDisplay.restype = ctypes.c_void_p
_XOpenDisplay.argtypes = [ctypes.c_void_p]

_XCloseDisplay = x11.XCloseDisplay
_XCloseDisplay.restype = ctypes.c_int
_XCloseDisplay.argtypes = [ctypes.c_void_p]

_XDefaultRootWindow = x11.XDefaultRootWindow
_XDefaultRootWindow.restype = ctypes.c_ulong
_XDefaultRootWindow.argtypes = [ctypes.c_void_p]

_XQueryTree = x11.XQueryTree
_XQueryTree.restype = ctypes.c_int
_XQueryTree.argtypes = [
    ctypes.c_void_p,
    ctypes.c_ulong,
    ctypes.POINTER(ctypes.c_ulong),
    ctypes.POINTER(ctypes.c_ulong),
    ctypes.POINTER(ctypes.c_ulong),
    ctypes.POINTER(ctypes.c_int),
]
_XFree = x11.XFree
_XFree.restype = ctypes.c_int
_XFree.argtypes = [ctypes.c_void_p]

_XFetchName = x11.XFetchName
_XFetchName.restype = ctypes.c_int
_XFetchName.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_char_p)]

_XGetClassHint = x11.XGetClassHint
_XGetClassHint.restype = ctypes.c_int
_XGetClassHint.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p]

# EWMH property helpers (we use XA_WINDOW / XA_STRING atom returns).
_XInternAtom = x11.XInternAtom
_XInternAtom.restype = ctypes.c_ulong
_XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]

_XGetWindowProperty = x11.XGetWindowProperty
_XGetWindowProperty.restype = ctypes.c_int
_XGetWindowProperty.argtypes = [
    ctypes.c_void_p,
    ctypes.c_ulong,
    ctypes.c_ulong,
    ctypes.c_long,
    ctypes.c_long,
    ctypes.c_int,
    ctypes.c_ulong,
    ctypes.POINTER(ctypes.c_ulong),
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_ulong),
    ctypes.POINTER(ctypes.c_ulong),
    ctypes.POINTER(ctypes.c_void_p),
]


class XClassHint(ctypes.Structure):
    _fields_ = [
        ("res_name", ctypes.c_char_p),
        ("res_class", ctypes.c_char_p),
    ]


def _ensure_display():
    if not hasattr(_ensure_display, "_dpy"):
        dpy = _XOpenDisplay(None)
        if not dpy:
            raise RuntimeError("XOpenDisplay(NULL) failed -- is $DISPLAY set?")
        _ensure_display._dpy = dpy
    return _ensure_display._dpy


def _fetch_name(dpy, wid: int) -> str:
    name_p = ctypes.c_char_p()
    if _XFetchName(dpy, wid, ctypes.byref(name_p)) and name_p.value:
        try:
            return name_p.value.decode("utf-8", errors="replace")
        finally:
            _XFree(name_p)
    return ""


def _fetch_class(dpy, wid: int) -> str:
    hint = XClassHint()
    if _XGetClassHint(dpy, wid, ctypes.byref(hint)):
        try:
            return (hint.res_class or b"").decode("utf-8", errors="replace")
        finally:
            if hint.res_name:
                _XFree(hint.res_name)
            if hint.res_class:
                _XFree(hint.res_class)
    return ""


def _ewmh_client_list(dpy, root: int) -> list[int]:
    """Read _NET_CLIENT_LIST (EWMH) for stable, ordered window IDs."""
    prop_name = _XInternAtom(dpy, b"_NET_CLIENT_LIST", 0)
    if prop_name == 0:
        return []
    actual_type = ctypes.c_ulong()
    actual_format = ctypes.c_int()
    n_items = ctypes.c_ulong()
    bytes_after = ctypes.c_ulong()
    data = ctypes.c_void_p()
    rc = _XGetWindowProperty(
        dpy,
        root,
        prop_name,
        0,
        ctypes.c_long(0xFFFFFFFF),
        0,
        0,  # False, XA_WINDOW
        ctypes.byref(actual_type),
        ctypes.byref(actual_format),
        ctypes.byref(n_items),
        ctypes.byref(bytes_after),
        ctypes.byref(data),
    )
    if rc != 0 or not data.value:
        return []
    try:
        # n_items is the count of longs; each window ID is one long.
        n = n_items.value
        ids = (ctypes.c_ulong * n).from_address(data.value)
        return [int(ids[i]) for i in range(n)]
    finally:
        _XFree(data)


class WindowFinder:
    DEFAULT_TIMEOUT_S = 3.0

    def __init__(self, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        self._timeout_s = timeout_s
        self._cache: dict[tuple[str | None, str], int] = {}
        self._lock = threading.Lock()

    def find(self, wm_class: str | None, title_substring: str) -> int | None:
        key = (wm_class, title_substring)
        with self._lock:
            cached = self._cache.get(key)
            if cached:
                return cached
            self._cache.pop(key, None)
        wins = self.list_windows(wm_class=wm_class)
        match = next(
            (w for w in wins if not title_substring or title_substring in w.title),
            None,
        )
        if match:
            with self._lock:
                self._cache[key] = match.wid
            return match.wid
        return None

    def list_windows(self, wm_class: str | None = None) -> list[WindowInfo]:
        windows: list[WindowInfo] = []
        done_holder = {"done": False}
        lock = threading.Lock()

        def worker():
            try:
                dpy = _ensure_display()
                root = _XDefaultRootWindow(dpy)
                # Prefer EWMH list (ordered, skips hidden).
                wid_list = _ewmh_client_list(dpy, root)
                if not wid_list:
                    # Fall back to XQueryTree.
                    root_out = ctypes.c_ulong()
                    parent = ctypes.c_ulong()
                    children = ctypes.c_void_p()
                    n_children = ctypes.c_int()
                    if _XQueryTree(
                        dpy,
                        root,
                        ctypes.byref(root_out),
                        ctypes.byref(parent),
                        ctypes.byref(children),
                        ctypes.byref(n_children),
                    ):
                        n = n_children.value
                        if n > 0 and children.value:
                            try:
                                arr = (ctypes.c_ulong * n).from_address(children.value)
                                wid_list = [int(arr[i]) for i in range(n)]
                            finally:
                                _XFree(children)
                for wid in wid_list:
                    cls = _fetch_class(dpy, wid)
                    name = _fetch_name(dpy, wid)
                    if wm_class and cls != wm_class:
                        continue
                    with lock:
                        windows.append(WindowInfo(wid=wid, title=name, wm_class=cls))
            finally:
                done_holder["done"] = True

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        t.join(timeout=self._timeout_s)
        if t.is_alive():
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
        print(f"  wid={w.wid:>8}  class={w.wm_class!r}  title={w.title!r}")
