"""Hardware-level keyboard input on macOS via Quartz CGEventPost.

Uses ctypes to load the ApplicationServices framework directly -- no PyObjC
dependency required. CGEventPost injects events into the system-wide event
stream at the kernel HID layer, similar in spirit to user32.SendInput.

Anti-cheat / safety:
- Do NOT use AppleScript or `osascript` (detectable, slow, and many apps
  ignore them).
- CGEventPost requires the process to be a foreground app OR to be running
  with accessibility privileges (TCC `Accessibility` permission in
  System Settings -> Privacy & Security). On macOS Sonoma+, the OS may
  still throttle synthetic events from unsigned binaries.

Foreground requirement:
- CGEventPost only delivers to the foreground app on macOS (the Input
  Monitoring restriction in System Settings). Use:
    NSRunningApplication.activateWithOptions_(NSApplicationActivateAllWindows)
  before each call, or call into PyObjC if installed.

Timing:
- 30-80 ms hold for a single key.
- 50-150 ms jitter between events when targeting a game.
"""

import ctypes
import random
import time
from ctypes import c_bool, c_uint16, c_uint32, c_void_p

# ApplicationServices framework -- shipped with macOS.
app_services = ctypes.cdll.LoadLibrary(
    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
)

# CoreGraphics -- also inside ApplicationServices.
cg = app_services
foundation = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Foundation.framework/Foundation")


# ---- Virtual-key codes (Carbon CGEvent virtual keycodes) --------------------
VK = {
    # Letters (Carbon kVK_ANSI_*)
    "a": 0x00,
    "s": 0x01,
    "d": 0x02,
    "f": 0x03,
    "h": 0x04,
    "g": 0x05,
    "z": 0x06,
    "x": 0x07,
    "c": 0x08,
    "v": 0x09,
    "b": 0x0B,
    "q": 0x0C,
    "w": 0x0D,
    "e": 0x0E,
    "r": 0x0F,
    "y": 0x10,
    "t": 0x11,
    "o": 0x1F,
    "u": 0x20,
    "i": 0x22,
    "p": 0x23,
    "l": 0x25,
    "j": 0x26,
    "k": 0x28,
    "n": 0x2D,
    "m": 0x2E,
    # Digits (kVK_ANSI_1..0)
    "1": 0x12,
    "2": 0x13,
    "3": 0x14,
    "4": 0x15,
    "5": 0x17,
    "6": 0x16,
    "7": 0x1A,
    "8": 0x1C,
    "9": 0x19,
    "0": 0x1D,
    # Function keys F1-F12 (kVK_F1..kVK_F12)
    "f1": 0x7A,
    "f2": 0x78,
    "f3": 0x63,
    "f4": 0x76,
    "f5": 0x60,
    "f6": 0x61,
    "f7": 0x62,
    "f8": 0x64,
    "f9": 0x65,
    "f10": 0x6D,
    "f11": 0x67,
    "f12": 0x6F,
    # Common control / nav keys
    "enter": 0x24,
    "return": 0x24,
    "esc": 0x35,
    "escape": 0x35,
    "backspace": 0x33,
    "delete": 0x75,  # forward delete; backspace is 0x33
    "tab": 0x30,
    "space": 0x31,
    "left": 0x7B,
    "right": 0x7C,
    "up": 0x7E,
    "down": 0x7D,
    "pageup": 0x74,
    "pagedown": 0x79,
    "home": 0x73,
    "end": 0x77,
    # Modifiers
    "lshift": 0x38,
    "rshift": 0x3C,
    "lctrl": 0x3B,
    "rctrl": 0x3E,
    "lalt": 0x3A,
    "ralt": 0x3D,
    "lcmd": 0x37,
    "rcmd": 0x36,
    "capslock": 0x39,
}

_MOD_ALIAS = {
    "ctrl": ("lctrl",),
    "control": ("lctrl",),
    "shift": ("lshift",),
    "alt": ("lalt",),
    "option": ("lalt",),
    "cmd": ("lcmd",),
    "command": ("lcmd",),
    "meta": ("lcmd",),
}


# ---- Quartz prototypes ------------------------------------------------------
# CGEventCreateKeyboardEvent returns a CGEventRef (opaque).
_cg_event_create_keyboard = cg.CGEventCreateKeyboardEvent
_cg_event_create_keyboard.restype = c_void_p
_cg_event_create_keyboard.argtypes = [c_void_p, c_uint16, c_bool]

# CGEventPost(location, eventRef) -> void.
_cg_event_post = cg.CGEventPost
_cg_event_post.restype = None
_cg_event_post.argtypes = [c_uint32, c_void_p]

# CGEventCreate(NULL) returns a source event.
_cg_event_source_create = cg.CGEventCreate
_cg_event_source_create.restype = c_void_p
_cg_event_source_create.argtypes = [c_void_p]

# CFRelease -- many CG types are CFTypeRef (toll-free bridged).
_cf_release = foundation.CFRelease
_cf_release.restype = None
_cf_release.argtypes = [c_void_p]

# Locations
kCGHIDEventTap = 0  # kernel-level HID event tap (foreground app only)
kCGSessionEventTap = 1

# Key down / up flag for CGEventCreateKeyboardEvent (True = down).
DOWN = True
UP = False


def _post_key(vk: int, down: bool) -> None:
    src = _cg_event_source_create(None)
    if not src:
        raise RuntimeError("CGEventCreate returned NULL")
    try:
        ev = _cg_event_create_keyboard(src, vk, down)
        if not ev:
            raise RuntimeError(f"CGEventCreateKeyboardEvent(vk={vk:#x}, down={down}) returned NULL")
        try:
            _cg_event_post(kCGHIDEventTap, ev)
        finally:
            _cf_release(ev)
    finally:
        _cf_release(src)


def _jitter_seconds(jitter_range_ms: tuple[int, int]) -> float:
    return random.uniform(jitter_range_ms[0], jitter_range_ms[1]) / 1000


def send_key(bundle_id_or_none, key: str, hold_ms: int = 50) -> None:
    """Press + release one key.

    `bundle_id_or_none` is accepted for API symmetry with the Windows version.
    Pass None unless you have PyObjC installed and want to force-foreground
    the target app via NSWorkspace.
    """
    vk = VK.get(key.lower())
    if vk is None:
        raise ValueError(f"Unknown key: {key!r}")
    _post_key(vk, DOWN)
    time.sleep(hold_ms / 1000)
    _post_key(vk, UP)


def press_combo(
    bundle_id_or_none,
    combo: str,
    jitter_range_ms: tuple[int, int] = (50, 150),
) -> None:
    tokens = [t.strip().lower() for t in combo.split("+") if t.strip()]
    if not tokens:
        raise ValueError("empty combo")
    trigger = tokens[-1]
    if trigger not in VK:
        raise ValueError(f"Unknown trigger key: {trigger!r}")
    mods: list[str] = []
    for tok in tokens[:-1]:
        if tok not in _MOD_ALIAS:
            raise ValueError(f"Unknown modifier: {tok!r}")
        mods.extend(_MOD_ALIAS[tok])

    for m in mods:
        _post_key(VK[m], DOWN)
    time.sleep(_jitter_seconds(jitter_range_ms))
    _post_key(VK[trigger], DOWN)
    time.sleep(_jitter_seconds(jitter_range_ms))
    _post_key(VK[trigger], UP)
    time.sleep(_jitter_seconds(jitter_range_ms))
    for m in reversed(mods):
        _post_key(VK[m], UP)


if __name__ == "__main__":
    print(f"VK entries: {len(VK)}")
    print(f"sample VKs: f5={VK['f5']:#x}, left={VK['left']:#x}, enter={VK['enter']:#x}")
