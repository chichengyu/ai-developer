"""Microsoft Active Accessibility (MSAA) -- legacy accessibility API.

MSAA is older than UIA but still works for many Windows apps that did
not adopt UIA. Prefer `accessibility_uia.py` for new code; reach for
MSAA only when the target app is genuinely UIA-incompatible.

Uses ctypes to load oleacc.dll directly (no pywin32 / comtypes needed
for the basic AccessibleObjectFromWindow / GetRoleText / GetStateText
path). Note: full IAccessible COM dispatch requires pywin32 or
comtypes -- this module focuses on the cheap, no-deps read path.
"""

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

oleacc = ctypes.windll.oleacc
user32 = ctypes.windll.user32

# ---- oleacc prototypes -----------------------------------------------------
_AccessibleObjectFromWindow = oleacc.AccessibleObjectFromWindow
_AccessibleObjectFromWindow.argtypes = [
    wintypes.HWND,
    wintypes.DWORD,
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.POINTER(ctypes.c_void_p),
]
_AccessibleObjectFromWindow.restype = ctypes.c_long

_GetRoleTextW = oleacc.GetRoleTextW
_GetRoleTextW.argtypes = [wintypes.DWORD, ctypes.c_wchar_p, wintypes.UINT]
_GetRoleTextW.restype = wintypes.UINT

_GetStateTextW = oleacc.GetStateTextW
_GetStateTextW.argtypes = [wintypes.DWORD, ctypes.c_wchar_p, wintypes.UINT]
_GetStateTextW.restype = wintypes.UINT


# ---- Constants -------------------------------------------------------------
OBJID_WINDOW = 0x00000000
OBJID_CLIENT = 0xFFFFFFFC

ROLE_SYSTEM_TITLEBAR = 0x00000001
ROLE_SYSTEM_MENU = 0x00000002
ROLE_SYSTEM_PUSHBUTTON = 0x0000002A
ROLE_SYSTEM_TEXT = 0x0000002C
ROLE_SYSTEM_CLIENT = 0x0000000A

STATE_SYSTEM_FOCUSED = 0x00000004
STATE_SYSTEM_INVISIBLE = 0x00008000


def role_text(role_id: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    n = _GetRoleTextW(role_id, buf, 256)
    return buf.value if n > 0 else f"role_{role_id}"


def state_text(state_bits: int) -> list[str]:
    out: list[str] = []
    bit = 1
    while bit <= 0x80000000 and bit <= state_bits:
        if state_bits & bit:
            buf = ctypes.create_unicode_buffer(64)
            if _GetStateTextW(bit, buf, 64):
                out.append(buf.value)
        bit <<= 1
    return out


@dataclass(frozen=True)
class MsaaObjectInfo:
    hwnd: int
    role_text: str
    name: str | None  # not implemented in pure-ctypes path


def object_from_window(hwnd: int, objid: int = OBJID_WINDOW):
    """Return an IDispatch pointer to the window's accessible object.

    Full IAccessible dispatch requires pywin32 / comtypes; this is a
    low-level handle only. Use it as a sanity check that MSAA exposes
    the window before reaching for a heavier client.
    """
    iid = ctypes.c_void_p()
    disp = ctypes.c_void_p()
    hr = _AccessibleObjectFromWindow(hwnd, objid, ctypes.byref(iid), ctypes.byref(disp))
    if hr != 0:  # S_OK == 0
        return None
    return disp.value


if __name__ == "__main__":
    # Enumerate top-level windows and report which ones are MSAA-visible.
    EnumWindows = user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    GetWindowTextW = user32.GetWindowTextW
    GetWindowTextLengthW = user32.GetWindowTextLengthW

    results = []

    def callback(hwnd, _lparam):
        length = GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        GetWindowTextW(hwnd, buf, length + 1)
        if not buf.value:
            return True
        if object_from_window(hwnd, OBJID_WINDOW):
            results.append(buf.value)
        return True

    EnumWindows(EnumWindowsProc(callback), 0)
    print(f"MSAA-visible windows: {len(results)}")
    for title in results[:5]:
        print(f"  {title!r}")
    print(f"\nrole_text({ROLE_SYSTEM_PUSHBUTTON}) = {role_text(ROLE_SYSTEM_PUSHBUTTON)!r}")
    print(f"role_text({ROLE_SYSTEM_TITLEBAR})  = {role_text(ROLE_SYSTEM_TITLEBAR)!r}")
