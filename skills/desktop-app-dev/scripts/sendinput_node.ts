// Hardware-level keyboard input via Win32 SendInput, using koffi (modern Node FFI).
//
// Install: npm install koffi
// Drop-in:
//     await sendKey(hwnd, "F5");
//     await pressCombo(hwnd, "ctrl+shift+F1");
import koffi from "koffi";

const user32 = koffi.load("user32.dll");

const ShowWindow = user32.func("bool __stdcall ShowWindow(void* hWnd, int nCmdShow)");
const SetForegroundWindow = user32.func("bool __stdcall SetForegroundWindow(void* hWnd)");
const GetForegroundWindow = user32.func("void* __stdcall GetForegroundWindow()");
const SendInput = user32.func("unsigned int __stdcall SendInput(unsigned int n, void* pInputs, int cbSize)");

const INPUT_KEYBOARD = 1;
const KEYEVENTF_KEYUP = 0x0002;
const SW_RESTORE = 9;

const KeybdInput = koffi.struct("KEYBDINPUT", {
    wVk: "uint16",
    wScan: "uint16",
    dwFlags: "uint32",
    time: "uint32",
    dwExtraInfo: "uintptr",
});
const Input = koffi.struct("INPUT", {
    type: "uint32",
    Anonymous: koffi.union({ ki: KeybdInput, padding: koffi.array("uint8", 8) }),
});

// Keep buildVkMap() in sync with scripts/vk_table.json (Python is checked automatically).
const VK: Record<string, number> = buildVkMap();

function buildVkMap(): Record<string, number> {
    const m: Record<string, number> = {};
    for (let i = 0; i < 26; i++) m[String.fromCharCode(0x61 + i)] = 0x41 + i;
    for (let i = 0; i < 10; i++) m[String(i)] = 0x30 + i;
    for (let i = 1; i <= 24; i++) m["f" + i] = 0x70 + i - 1;
    for (let i = 0; i < 10; i++) m["num" + i] = 0x60 + i;
    Object.assign(m, {
        back: 0x08, tab: 0x09, enter: 0x0D, escape: 0x1B, esc: 0x1B,
        space: 0x20, pageup: 0x21, pagedown: 0x22, end: 0x23, home: 0x24,
        left: 0x25, up: 0x26, right: 0x27, down: 0x28,
        insert: 0x2D, delete: 0x2E,
        select: 0x29, print: 0x2A, execute: 0x2B, snapshot: 0x2C, help: 0x2F,
        lshift: 0xA0, rshift: 0xA1, lctrl: 0xA2, rctrl: 0xA3,
        lalt: 0xA4, ralt: 0xA5, lwin: 0x5B, rwin: 0x5C,
        capslock: 0x14, numlock: 0x90, scrolllock: 0x91,
        semicolon: 0xBA, equals: 0xBB, comma: 0xBC, minus: 0xBD,
        period: 0xBE, slash: 0xBF, backtick: 0xC0,
        lbracket: 0xDB, backslash: 0xDC, rbracket: 0xDD, apostrophe: 0xDE,
        nummultiply: 0x6A, numadd: 0x6B, numseparator: 0x6C,
        numsubtract: 0x6D, numdecimal: 0x6E, numdivide: 0x6F,
    });
    return m;
}

function ensureForeground(hwnd: any): boolean {
    if (!hwnd) return false;
    ShowWindow(hwnd, SW_RESTORE);
    SetForegroundWindow(hwnd);
    return GetForegroundWindow() === hwnd;
}

function pressSingle(vkCode: number, up: boolean): void {
    const buf = Buffer.alloc(Input.size);
    const one = koffi.as(buf, Input, 1);
    one[0].type = INPUT_KEYBOARD;
    one[0].Anonymous.ki.wVk = vkCode;
    one[0].Anonymous.ki.wScan = 0;
    one[0].Anonymous.ki.dwFlags = up ? KEYEVENTF_KEYUP : 0;
    one[0].Anonymous.ki.time = 0;
    one[0].Anonymous.ki.dwExtraInfo = 0n;
    SendInput(1, one, Input.size);
}

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));
const jitterMs = (requested: number): number =>
    requested > 0 ? requested : 50 + Math.floor(Math.random() * 101);

export async function sendKey(hwnd: any, key: string, holdMs = 50): Promise<void> {
    const v = VK[key.toLowerCase()];
    if (v === undefined) throw new Error(`Unknown key: ${key}`);
    if (!ensureForeground(hwnd)) throw new Error("Failed to foreground window");
    pressSingle(v, false);
    await sleep(holdMs);
    pressSingle(v, true);
}

export async function pressCombo(hwnd: any, combo: string, jitterMs = 0): Promise<void> {
    const tokens = combo.toLowerCase().split("+").map(s => s.trim()).filter(Boolean);
    if (tokens.length === 0) throw new Error("empty combo");
    const trigger = tokens[tokens.length - 1];
    const triggerVk = VK[trigger];
    if (triggerVk === undefined) throw new Error(`Unknown trigger: ${trigger}`);
    const mods: number[] = [];
    for (const t of tokens.slice(0, -1)) {
        switch (t) {
            case "ctrl": case "control": mods.push(0xA2); break;
            case "shift": mods.push(0xA0); break;
            case "alt": mods.push(0xA4); break;
            case "win": case "meta": mods.push(0x5B); break;
            default: throw new Error(`Unknown modifier: ${t}`);
        }
    }
    if (!ensureForeground(hwnd)) throw new Error("Failed to foreground window");
    for (const m of mods) pressSingle(m, false);
    await sleep(jitterMs(jitterMs));
    pressSingle(triggerVk, false);
    await sleep(jitterMs(jitterMs));
    pressSingle(triggerVk, true);
    await sleep(jitterMs(jitterMs));
    for (const m of [...mods].reverse()) pressSingle(m, true);
}
