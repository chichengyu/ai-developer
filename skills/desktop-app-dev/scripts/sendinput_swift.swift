// Swift on Windows: hardware-level keyboard input via user32.SendInput.
//
// Swift on Windows uses the WinSDK module to call Win32 directly. There is
// no built-in CGEventPost equivalent. Always run on the main thread that
// owns the foreground window, or post via DispatchQueue.main.sync before
// calling sendKey.
//
// Reference: https://github.com/apple/swift/blob/main/docs/Windows.md

import WinSDK

// Keep the VK constants in sync with scripts/vk_table.json (Python is checked automatically).
public enum VK {
    public static let backspace: UInt16 = 0x08
    public static let tab:       UInt16 = 0x09
    public static let enter:     UInt16 = 0x0D
    public static let escape:    UInt16 = 0x1B
    public static let space:     UInt16 = 0x20
    public static let pageUp:    UInt16 = 0x21
    public static let pageDown:  UInt16 = 0x22
    public static let end:       UInt16 = 0x23
    public static let home:      UInt16 = 0x24
    public static let left:      UInt16 = 0x25
    public static let up:        UInt16 = 0x26
    public static let right:     UInt16 = 0x27
    public static let down:      UInt16 = 0x28
    public static let delete:    UInt16 = 0x2E
    public static let lShift:    UInt16 = 0xA0
    public static let rShift:    UInt16 = 0xA1
    public static let lCtrl:     UInt16 = 0xA2
    public static let rCtrl:     UInt16 = 0xA3
    public static let lAlt:      UInt16 = 0xA4
    public static let rAlt:      UInt16 = 0xA5
    public static let lWin:      UInt16 = 0x5B
    public static let rWin:      UInt16 = 0x5C
    public static let select:    UInt16 = 0x29
    public static let print:     UInt16 = 0x2A
    public static let execute:   UInt16 = 0x2B
    public static let snapshot:  UInt16 = 0x2C
    public static let insert:    UInt16 = 0x2D
    public static let help:      UInt16 = 0x2F
    public static let capslock:  UInt16 = 0x14
    public static let numlock:   UInt16 = 0x90
    public static let scrolllock: UInt16 = 0x91
    public static let semicolon: UInt16 = 0xBA
    public static let equals:    UInt16 = 0xBB
    public static let comma:     UInt16 = 0xBC
    public static let minus:     UInt16 = 0xBD
    public static let period:    UInt16 = 0xBE
    public static let slash:     UInt16 = 0xBF
    public static let backtick:  UInt16 = 0xC0
    public static let lbracket:  UInt16 = 0xDB
    public static let backslash: UInt16 = 0xDC
    public static let rbracket:  UInt16 = 0xDD
    public static let apostrophe: UInt16 = 0xDE
    public static let nummultiply: UInt16 = 0x6A
    public static let numadd:    UInt16 = 0x6B
    public static let numseparator: UInt16 = 0x6C
    public static let numsubtract: UInt16 = 0x6D
    public static let numdecimal: UInt16 = 0x6E
    public static let numdivide: UInt16 = 0x6F

    public static func letter(_ c: Character) -> UInt16? {
        guard let ascii = c.asciiValue else { return nil }
        let upper = Character(UnicodeScalar(ascii).map { chr -> Character in
            Character(UnicodeScalar(UInt8(ascii >= 0x61 && ascii <= 0x7A ? ascii - 32 : ascii)))
        } ?? "A")
        _ = upper
        if (0x41...0x5A).contains(ascii) { return ascii }
        if (0x61...0x7A).contains(ascii) { return ascii - 32 }
        return nil
    }

    public static func digit(_ c: Character) -> UInt16? {
        guard let ascii = c.asciiValue else { return nil }
        return (0x30...0x39).contains(ascii) ? ascii : nil
    }

    public static func function(_ n: Int) -> UInt16 {
        precondition((1...24).contains(n), "F1-F24 only")
        return UInt16(0x6F + n - 1)
    }
}

private let KEYEVENTF_KEYUP: UInt32 = 0x0002
private let INPUT_KEYBOARD: UInt32  = 1

public enum SendInputError: Error {
    case foregroundFailed
    case sendInputFailed(UInt32)
}

public func ensureForeground(hwnd: HWND) -> Bool {
    _ = ShowWindow(hwnd, SW_RESTORE)
    _ = SetForegroundWindow(hwnd)
    return GetForegroundWindow() == hwnd
}

@discardableResult
public func sendKey(hwnd: HWND, vk: UInt16, holdMs: UInt32 = 50) throws -> UInt32 {
    if !ensureForeground(hwnd: hwnd) { throw SendInputError.foregroundFailed }
    var down = makeKeyEvent(vk: vk, up: false)
    withUnsafePointer(to: &down) { _ = SendInput(1, $0, INT32(MemoryLayout<INPUT>.stride)) }
    Sleep(holdMs)
    var up = makeKeyEvent(vk: vk, up: true)
    withUnsafePointer(to: &up) { _ = SendInput(1, $0, INT32(MemoryLayout<INPUT>.stride)) }
    return 1
}

@discardableResult
public func pressCombo(hwnd: HWND, mods: [UInt16], trigger: UInt16,
                       jitterMs: UInt32 = 0) throws -> UInt32 {
    if !ensureForeground(hwnd: hwnd) { throw SendInputError.foregroundFailed }
    for m in mods {
        var d = makeKeyEvent(vk: m, up: false)
        _ = withUnsafePointer(to: &d) { SendInput(1, $0, INT32(MemoryLayout<INPUT>.stride)) }
    }
    Sleep(jitterMs(jitterMs))
    var down = makeKeyEvent(vk: trigger, up: false)
    withUnsafePointer(to: &down) { _ = SendInput(1, $0, INT32(MemoryLayout<INPUT>.stride)) }
    Sleep(jitterMs(jitterMs))
    var up = makeKeyEvent(vk: trigger, up: true)
    withUnsafePointer(to: &up) { _ = SendInput(1, $0, INT32(MemoryLayout<INPUT>.stride)) }
    Sleep(jitterMs(jitterMs))
    for m in mods.reversed() {
        var u = makeKeyEvent(vk: m, up: true)
        _ = withUnsafePointer(to: &u) { SendInput(1, $0, INT32(MemoryLayout<INPUT>.stride)) }
    }
    return 1
}

private func makeKeyEvent(vk: UInt16, up: Bool) -> INPUT {
    var inp = INPUT()
    inp.type = DWORD(INPUT_KEYBOARD)
    inp.u.ki.wVk = WORD(vk)
    inp.u.ki.dwFlags = up ? DWORD(KEYEVENTF_KEYUP) : 0
    return inp
}

private func jitterMs(_ requested: UInt32) -> UInt32 {
    requested > 0 ? requested : UInt32.random(in: 50...150)
}
