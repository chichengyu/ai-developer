"""Windows UI Automation (UIA) client -- drive another app's UI legitimately.

UI Automation is the supported, accessibility-grade API for reading and
controlling another app's UI. It is what Narrator / NVDA use under the
hood. The target app can refuse to expose elements (rare), but for most
modern Windows apps UIA returns a tree of AutomationElements that you
can query by Name / AutomationId / ControlType.

Uses comtypes (preferred over pywin32 for UIA because the type library
is COM-heavy). Install:
    pip install comtypes

Anti-cheat note:
- UIA reads UI state. It can click via InvokePattern, but it does NOT
  generate hardware-level input. For games with anti-cheat, UIA is
  detectable and usually blocked. SendInput remains the only safe path
  for game automation. UIA is the right choice for:
    - productivity apps (Office, browsers, line-of-business tools)
    - accessibility (NVDA, Voice Access, UI testing)
    - legacy enterprise apps with no other automation hook
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from dataclasses import dataclass

try:
    import comtypes.client
except ImportError:
    comtypes = None


if comtypes is not None:
    # Load the UIA type library shipped with Windows.
    try:
        _UIA = comtypes.client.CreateObject(
            "{9442DE9E-CB52-49F4-AF65-EC1A4A9B7D27}",  # UIAutomationClient
            interface=None,
        )
        _IUIAutomation = comtypes.client.GetModule((r"UIAutomationCore.dll",))
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: UIA init failed: {exc}", file=sys.stderr)
        _IUIAutomation = None
else:
    _IUIAutomation = None


@dataclass(frozen=True)
class UIAElement:
    name: str
    automation_id: str
    control_type: str
    runtime_id: tuple


class UIAClient:
    """Thin wrapper around IUIAutomation for the common read paths."""

    def __init__(self) -> None:
        if _IUIAutomation is None:
            raise RuntimeError("comtypes is not installed; pip install comtypes")
        self._uia = comtypes.client.CreateObject("{9442DE9E-CB52-49F4-AF65-EC1A4A9B7D27}")

    def element_from_handle(self, hwnd: int):
        return self._uia.ElementFromHandle(hwnd)

    def element_from_point(self, x: int, y: int):
        pt = comtypes.client.CreateObject(
            "{00000000-0000-0000-0000-000000000000}",  # tagPOINT
        )
        pt.x = x
        pt.y = y
        return self._uia.ElementFromPoint(pt)

    def root_element(self):
        return self._uia.GetRootElement()

    def walk_tree(
        self,
        root,
        max_depth: int = 6,
        predicate=None,
    ) -> Iterator[UIAElement]:
        """Depth-first walk yielding elements that match `predicate`.

        `predicate(elem) -> bool` -- if None, yields all elements.
        """
        stack = [(root, 0)]
        while stack:
            elem, depth = stack.pop()
            if depth > max_depth:
                continue
            try:
                name = elem.CurrentName or ""
                aid = elem.CurrentAutomationId or ""
                ctype = str(elem.CurrentControlType) if elem.CurrentControlType else ""
                rid = tuple(elem.GetRuntimeId())
            except Exception:  # noqa: BLE001
                continue
            wrapped = UIAElement(name=name, automation_id=aid, control_type=ctype, runtime_id=rid)
            if predicate is None or predicate(wrapped):
                yield wrapped
            try:
                children = elem.FindAll(
                    0x00000004,  # TreeScope_Children
                    comtypes.client.CreateObject(
                        "{00000000-0000-0000-C000-000000000046}",  # IID_IUIAutomationCondition -- TrueCondition
                    )
                    if False
                    else _true_condition(),
                )
                for i in range(children.Length):
                    stack.append((children.GetElement(i), depth + 1))
            except Exception:  # noqa: BLE001
                continue


def _true_condition():
    """Get the UIA TrueCondition singleton (TreeScope walker needs it)."""
    import comtypes.gen.UIAutomationClient as UIA

    return comtypes.client.CreateObject(UIA.CLSID_CUIAutomation).CreatePropertyCondition(0, 0)


# ---- Common predicates ------------------------------------------------------
def by_name(name_substring: str):
    return lambda e: name_substring.lower() in e.name.lower()


def by_automation_id(aid: str):
    return lambda e: e.automation_id == aid


def by_control_type(*types: str):
    return lambda e: e.control_type in types


# ---- Example ---------------------------------------------------------------
if __name__ == "__main__":
    print("UIA accessibility template (no live HWND; supply one in your code).")
    print("Example:")
    print("    client = UIAClient()")
    print("    root = client.element_from_handle(hwnd)")
    print("    for elem in client.walk_tree(root, max_depth=4, predicate=by_name('OK')):")
    print("        print(elem)")
