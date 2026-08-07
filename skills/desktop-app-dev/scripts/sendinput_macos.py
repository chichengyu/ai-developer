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


# ---- Virtual-key codes (USB HID usage page 0x07) -----------------------------
VK = {
    # Letters (USB HID: a=0x04 .. z=0x1d)
    **{chr(c): 0x04 + i for i, c in enumerate(range(ord("a"), ord("z") + 1))},
    # Digits (USB HID: 1=0x1e .. 9=0x26, 0=0x27)
    **{str(d): (0x1E + d - 1) if d >= 1 else 0x27 for d in range(0, 10)},
    # Function keys
    **{f"f{i}": (0x3A + i - 1) for i in range(1, 13)},
    # Common control / nav keys
    "enter": 0x28,
    "return": 0x28,
    "esc": 0x29,
    "escape": 0x29,
    "backspace": 0x2A,
    "delete": 0x2A,  # macOS: backspace = delete
    "tab": 0x2B,
    "space": 0x2C,
    "left": 0x50,
    "right": 0x4F,
    "up": 0x52,
    "down": 0x51,
    "pageup": 0x4B,
    "pagedown": 0x4E,
    "home": 0x4A,
    "end": 0x4D,
    # Modifiers
    "lshift": 0xE1,
    "rshift": 0xE5,
    "lctrl": 0xE0,
    "rctrl": 0xE4,
    "lalt": 0xE2,
    "ralt": 0xE6,
    "lcmd": 0xE3,
    "rcmd": 0xE7,
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
