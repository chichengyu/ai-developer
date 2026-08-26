"""Hardware-level keyboard input via ctypes user32.SendInput.

Drop-in usage:
    from sendinput_python import send_key, press_combo, VK
    send_key(hwnd, "F5")
    press_combo(hwnd, "ctrl+shift+F1")
"""

import ctypes
import random
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

# Virtual-key codes: canonical source is scripts/vk_table.json (checked by check_vk_tables.py).
VK = {}
for letter, code in zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", range(0x41, 0x5B), strict=False):
    VK[letter.lower()] = code
for digit, code in zip("0123456789", range(0x30, 0x3A), strict=False):
    VK[digit] = code
for i in range(1, 25):
    VK[f"f{i}"] = 0x70 + i - 1
for i in range(0, 10):
    VK[f"num{i}"] = 0x60 + i
VK.update(
    {
        "back": 0x08,
        "tab": 0x09,
        "enter": 0x0D,
        "escape": 0x1B,
        "esc": 0x1B,
        "space": 0x20,
        "pageup": 0x21,
        "pagedown": 0x22,
        "end": 0x23,
        "home": 0x24,
        "left": 0x25,
        "up": 0x26,
        "right": 0x27,
        "down": 0x28,
        "select": 0x29,
        "print": 0x2A,
        "execute": 0x2B,
        "snapshot": 0x2C,
        "insert": 0x2D,
        "delete": 0x2E,
        "help": 0x2F,
        "lshift": 0xA0,
        "rshift": 0xA1,
        "lctrl": 0xA2,
        "rctrl": 0xA3,
        "lalt": 0xA4,
        "ralt": 0xA5,
        "lwin": 0x5B,
        "rwin": 0x5C,
        "semicolon": 0xBA,
        "equals": 0xBB,
        "comma": 0xBC,
        "minus": 0xBD,
        "period": 0xBE,
        "slash": 0xBF,
        "backtick": 0xC0,
        "lbracket": 0xDB,
        "backslash": 0xDC,
        "rbracket": 0xDD,
        "apostrophe": 0xDE,
        "capslock": 0x14,
        "numlock": 0x90,
        "scrolllock": 0x91,
        "nummultiply": 0x6A,
        "numadd": 0x6B,
        "numseparator": 0x6C,
        "numsubtract": 0x6D,
        "numdecimal": 0x6E,
        "numdivide": 0x6F,
    }
)
_MOD_ALIAS = {
    "ctrl": ("lctrl",),
    "control": ("lctrl",),
    "shift": ("lshift",),
    "alt": ("lalt",),
    "win": ("lwin",),
    "meta": ("lwin",),
}

KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _UNION)]


SW_RESTORE = 9

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000
WHEEL_DELTA = 120


def _ensure_foreground(hwnd: int) -> bool:
    if not hwnd:
        return False
    for _ in range(5):
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        if user32.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.05)
    return user32.GetForegroundWindow() == hwnd


def _jitter_seconds(jitter_range_ms: tuple[int, int]) -> float:
    return random.uniform(jitter_range_ms[0], jitter_range_ms[1]) / 1000


def _press(vk: int, up: bool) -> INPUT:
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.u.ki.wVk = vk
    inp.u.ki.wScan = 0
    inp.u.ki.dwFlags = KEYEVENTF_KEYUP if up else 0
    inp.u.ki.time = 0
    inp.u.ki.dwExtraInfo = None
    return inp


def send_key(hwnd: int, key: str, hold_ms: int = 50) -> None:
    vk = VK.get(key.lower())
    if vk is None:
        raise ValueError(f"Unknown key: {key!r}")
    if not _ensure_foreground(hwnd):
        raise RuntimeError("Could not bring target window to foreground")
    user32.SendInput(1, (INPUT * 1)(_press(vk, False)), ctypes.sizeof(INPUT))
    if hold_ms > 0:
        time.sleep(hold_ms / 1000)
    user32.SendInput(1, (INPUT * 1)(_press(vk, True)), ctypes.sizeof(INPUT))


def press_combo(
    hwnd: int,
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

    if not _ensure_foreground(hwnd):
        raise RuntimeError("Could not bring target window to foreground")
    for m in mods:
        user32.SendInput(1, (INPUT * 1)(_press(VK[m], False)), ctypes.sizeof(INPUT))
    time.sleep(_jitter_seconds(jitter_range_ms))
    user32.SendInput(1, (INPUT * 1)(_press(VK[trigger], False)), ctypes.sizeof(INPUT))
    time.sleep(_jitter_seconds(jitter_range_ms))
    user32.SendInput(1, (INPUT * 1)(_press(VK[trigger], True)), ctypes.sizeof(INPUT))
    time.sleep(_jitter_seconds(jitter_range_ms))
    for m in reversed(mods):
        user32.SendInput(1, (INPUT * 1)(_press(VK[m], True)), ctypes.sizeof(INPUT))


def _mouse(flags: int, data: int = 0, dx: int = 0, dy: int = 0) -> INPUT:
    inp = INPUT()
    inp.type = 0  # INPUT_MOUSE
    inp.u.mi.dx = dx
    inp.u.mi.dy = dy
    inp.u.mi.mouseData = data
    inp.u.mi.dwFlags = flags
    inp.u.mi.time = 0
    inp.u.mi.dwExtraInfo = None
    return inp


def _screen_size() -> tuple[int, int]:
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def move_mouse(x: int, y: int) -> None:
    """Move the cursor to absolute screen coordinates (0,0 = top-left)."""
    width, height = _screen_size()
    dx = int(x * 65535 / max(1, width - 1))
    dy = int(y * 65535 / max(1, height - 1))
    user32.SendInput(
        1,
        (INPUT * 1)(_mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, dx=dx, dy=dy)),
        ctypes.sizeof(INPUT),
    )


def click(
    x: int | None = None,
    y: int | None = None,
    button: str = "left",
    hold_ms: int = 50,
) -> None:
    """Click at absolute screen coordinates (or the current cursor position)."""
    if x is not None and y is not None:
        move_mouse(x, y)
    down, up = {
        "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
        "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
        "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
    }[button.lower()]
    user32.SendInput(1, (INPUT * 1)(_mouse(down)), ctypes.sizeof(INPUT))
    if hold_ms > 0:
        time.sleep(hold_ms / 1000)
    user32.SendInput(1, (INPUT * 1)(_mouse(up)), ctypes.sizeof(INPUT))


def scroll(delta: int, x: int | None = None, y: int | None = None) -> None:
    """Scroll the wheel by a multiple of WHEEL_DELTA at the given position."""
    if x is not None and y is not None:
        move_mouse(x, y)
    data = delta * WHEEL_DELTA
    user32.SendInput(1, (INPUT * 1)(_mouse(MOUSEEVENTF_WHEEL, data=data)), ctypes.sizeof(INPUT))


if __name__ == "__main__":
    print("VK entries:", len(VK))
