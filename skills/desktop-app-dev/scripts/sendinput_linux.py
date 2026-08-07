"""Hardware-level keyboard input on Linux via X11 XTestFakeInputEvent.

Loads libXtst (X11 testing extension) directly via ctypes. Works on X11
sessions only. Wayland requires either uinput (kernel-level) or the
RemoteDesktop portal -- not covered here.

Anti-cheat / safety:
- XTestFakeInputEvent injects events at the X server level; most apps and
  games accept it (same channel as a real keyboard).
- Wayland compositors (GNOME, KDE) intentionally block XTest from remote
  sources. You must either run on X11 or use uinput (which requires
  /dev/uinput access and is much more invasive).
- Do NOT use xdotool's CLI (`xdotool key F5`) -- it shells out, blocks,
  and is detectable.

Foreground requirement:
- XTestFakeInputEvent delivers to whichever window the X server thinks
  has focus. To force a window to the foreground, use XSetInputFocus or
  _NET_ACTIVE_WINDOW (EWMH) -- both covered in window_enum_linux.

Timing:
- 30-80 ms hold for a single key.
- 50-150 ms jitter between events when targeting a game.
"""

import ctypes
import random
import time
from ctypes import c_int, c_uint, c_ulong, c_void_p

# Load X11 + XTest
x11 = ctypes.cdll.LoadLibrary("libX11.so.6")
xtst = ctypes.cdll.LoadLibrary("libXtst.so.6")

# ---- X11 prototypes -------------------------------------------------------
_XOpenDisplay = x11.XOpenDisplay
_XOpenDisplay.restype = c_void_p
_XOpenDisplay.argtypes = [c_void_p]

_XCloseDisplay = x11.XCloseDisplay
_XCloseDisplay.restype = c_int
_XCloseDisplay.argtypes = [c_void_p]

_XDefaultRootWindow = x11.XDefaultRootWindow
_XDefaultRootWindow.restype = c_ulong
_XDefaultRootWindow.argtypes = [c_void_p]

# ---- XTest prototypes ------------------------------------------------------
_XTestFakeKeyEvent = xtst.XTestFakeKeyEvent
_XTestFakeKeyEvent.restype = c_int
_XTestFakeKeyEvent.argtypes = [
    c_void_p,
    c_uint,
    c_int,
    c_ulong,
]  # display, keycode, is_press, delay

_XKeysymToKeycode = x11.XKeysymToKeycode
_XKeysymToKeycode.restype = c_uint
_XKeysymToKeycode.argtypes = [c_void_p, c_ulong]


# ---- Keysym table (X11 keysyms) --------------------------------------------
# Use the XK_ keysyms from X11/keysymdef.h. Only a useful subset here.
XK = {
    # Letters (lowercase keysyms)
    **{chr(c): 0x0061 + i for i, c in enumerate(range(ord("a"), ord("z") + 1))},
    # Digits
    **{str(d): 0x0030 + d for d in range(0, 10)},
    # Function keys
    **{f"f{i}": (0xFFBE + i - 1) for i in range(1, 13)},
    # Common nav / control
    "backspace": 0xFF08,
    "tab": 0xFF09,
    "linefeed": 0xFF0A,
    "clear": 0xFF0B,
    "enter": 0xFF0D,
    "return": 0xFF0D,
    "shift_l": 0xFFE1,
    "shift_r": 0xFFE2,
    "control_l": 0xFFE3,
    "control_r": 0xFFE4,
    "caps_lock": 0xFFE5,
    "shift_lock": 0xFFE6,
    "meta_l": 0xFFE7,
    "meta_r": 0xFFE8,
    "alt_l": 0xFFE9,
    "alt_r": 0xFFEA,
    "super_l": 0xFFEB,
    "super_r": 0xFFEC,
    "escape": 0xFF1B,
    "space": 0x0020,
    "left": 0xFF51,
    "up": 0xFF52,
    "right": 0xFF53,
    "down": 0xFF54,
    "pageup": 0xFF55,
    "pagedown": 0xFF56,
    "home": 0xFF50,
    "end": 0xFF57,
    "insert": 0xFF63,
    "delete": 0xFFFF,
    "kp_0": 0xFFB0,
    "kp_1": 0xFFB1,
    "kp_2": 0xFFB2,
    "kp_3": 0xFFB3,
    "kp_4": 0xFFB4,
    "kp_5": 0xFFB5,
    "kp_6": 0xFFB6,
    "kp_7": 0xFFB7,
    "kp_8": 0xFFB8,
    "kp_9": 0xFFB9,
}

_MOD_ALIAS = {
    "ctrl": ("control_l",),
    "control": ("control_l",),
    "shift": ("shift_l",),
    "alt": ("alt_l",),
    "super": ("super_l",),
    "meta": ("super_l",),
    "cmd": ("super_l",),
    "command": ("super_l",),
}


def _ensure_display():
    """Open the default display, cached on the module."""
    if not hasattr(_ensure_display, "_dpy"):
        dpy = _XOpenDisplay(None)
        if not dpy:
            raise RuntimeError("XOpenDisplay(NULL) failed -- is $DISPLAY set?")
        _ensure_display._dpy = dpy
    return _ensure_display._dpy


def _keysym_to_keycode(dpy, keysym: int) -> int:
    return _XKeysymToKeycode(dpy, keysym)


def _post_key(keysym_name: str, is_press: bool) -> None:
    dpy = _ensure_display()
    keysym = XK.get(keysym_name.lower())
    if keysym is None:
        raise ValueError(f"Unknown keysym: {keysym_name!r}")
    keycode = _keysym_to_keycode(dpy, keysym)
    if keycode == 0:
        raise RuntimeError(f"XKeysymToKeycode({keysym_name}) returned 0")
    rc = _XTestFakeKeyEvent(dpy, keycode, 1 if is_press else 0, 0)
    if rc == 0:
        raise RuntimeError("XTestFakeKeyEvent returned 0")


def _jitter_seconds(jitter_range_ms: tuple[int, int]) -> float:
    return random.uniform(jitter_range_ms[0], jitter_range_ms[1]) / 1000


def send_key(display_or_none, key: str, hold_ms: int = 50) -> None:
    """Press + release one key. `display_or_none` is for API symmetry."""
    _post_key(key, is_press=True)
    time.sleep(hold_ms / 1000)
    _post_key(key, is_press=False)


def press_combo(
    display_or_none,
    combo: str,
    jitter_range_ms: tuple[int, int] = (50, 150),
) -> None:
    tokens = [t.strip().lower() for t in combo.split("+") if t.strip()]
    if not tokens:
        raise ValueError("empty combo")
    trigger = tokens[-1]
    if trigger not in XK:
        raise ValueError(f"Unknown trigger key: {trigger!r}")
    mods: list[str] = []
    for tok in tokens[:-1]:
        if tok not in _MOD_ALIAS:
            raise ValueError(f"Unknown modifier: {tok!r}")
        mods.extend(_MOD_ALIAS[tok])

    for m in mods:
        _post_key(m, is_press=True)
    time.sleep(_jitter_seconds(jitter_range_ms))
    _post_key(trigger, is_press=True)
    time.sleep(_jitter_seconds(jitter_range_ms))
    _post_key(trigger, is_press=False)
    time.sleep(_jitter_seconds(jitter_range_ms))
    for m in reversed(mods):
        _post_key(m, is_press=False)


if __name__ == "__main__":
    print(f"XK entries: {len(XK)}")
    print(f"sample XKs: f5={XK['f5']:#x}, left={XK['left']:#x}, enter={XK['enter']:#x}")
