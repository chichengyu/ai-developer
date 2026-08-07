// Package sendinput provides hardware-level keyboard input via Win32 SendInput.
//
// Drop-in usage:
//     sendinput.SendKey(hwnd, "F5")
//     sendinput.PressCombo(hwnd, "ctrl+shift+F1")
//
// Requires: golang.org/x/sys/windows (go get golang.org/x/sys/windows)
package sendinput

import (
	"math/rand"
	"strings"
	"time"
	"unsafe"

	"golang.org/x/sys/windows"
)

var (
	user32                  = windows.NewLazySystemDLL("user32.dll")
	procShowWindow          = user32.NewProc("ShowWindow")
	procSetForegroundWindow = user32.NewProc("SetForegroundWindow")
	procGetForegroundWindow = user32.NewProc("GetForegroundWindow")
	procSendInput           = user32.NewProc("SendInput")
)

const (
	inputKeyboard  = 1
	keyeventfKeyup = 0x0002
	swRestore      = 9
)

type keybdInput struct {
	wVk         uint16
	wScan       uint16
	dwFlags     uint32
	time        uint32
	dwExtraInfo uintptr
}

type input struct {
	Type uint32
	Ki   keybdInput
	_    [8]byte
}

// Keep buildVkMap() in sync with scripts/vk_table.json (Python is checked automatically).
var vk = buildVkMap()

func buildVkMap() map[string]uint16 {
	m := make(map[string]uint16)
	for i, c := range "ABCDEFGHIJKLMNOPQRSTUVWXYZ" {
		m[strings.ToLower(string(c))] = uint16(0x41 + i)
	}
	for i, c := range "0123456789" {
		m[string(c)] = uint16(0x30 + i)
	}
	for i := 1; i <= 24; i++ {
		m["f"+itoa(i)] = uint16(0x6F + i - 1)
	}
	for i := 0; i < 10; i++ {
		m["num"+itoa(i)] = uint16(0x60 + i)
	}
	extras := map[string]uint16{
		"back": 0x08, "tab": 0x09, "enter": 0x0D, "escape": 0x1B, "esc": 0x1B,
		"space": 0x20, "pageup": 0x21, "pagedown": 0x22, "end": 0x23, "home": 0x24,
		"left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
		"insert": 0x2D, "delete": 0x2E,
		"lshift": 0xA0, "rshift": 0xA1, "lctrl": 0xA2, "rctrl": 0xA3,
		"lalt": 0xA4, "ralt": 0xA5, "lwin": 0x5B, "rwin": 0x5C,
		"capslock": 0x14, "numlock": 0x90, "scrolllock": 0x91,
		"semicolon": 0xBA, "equals": 0xBB, "comma": 0xBC, "minus": 0xBD,
		"period": 0xBE, "slash": 0xBF, "backtick": 0xC0,
		"lbracket": 0xDB, "backslash": 0xDC, "rbracket": 0xDD, "apostrophe": 0xDE,
		"select": 0x29, "print": 0x2A, "execute": 0x2B, "snapshot": 0x2C, "help": 0x2F,
		"nummultiply": 0x6A, "numadd": 0x6B, "numseparator": 0x6C,
		"numsubtract": 0x6D, "numdecimal": 0x6E, "numdivide": 0x6F,
	}
	for k, v := range extras {
		m[k] = v
	}
	return m
}

func EnsureForeground(hwnd uintptr) bool {
	if hwnd == 0 {
		return false
	}
	for i := 0; i < 5; i++ {
		procShowWindow.Call(hwnd, uintptr(swRestore))
		procSetForegroundWindow.Call(hwnd)
		fg, _, _ := procGetForegroundWindow.Call()
		if fg == hwnd {
			return true
		}
		time.Sleep(50 * time.Millisecond)
	}
	fg, _, _ := procGetForegroundWindow.Call()
	return fg == hwnd
}

func pressOne(vkCode uint16, up bool) {
	in := input{Type: inputKeyboard, Ki: keybdInput{wVk: vkCode, dwFlags: 0}}
	if up {
		in.Ki.dwFlags = keyeventfKeyup
	}
	procSendInput.Call(uintptr(1),
		uintptr(unsafe.Pointer(&in)),
		uintptr(unsafe.Sizeof(in)))
}

func jitterMs(requested int) int {
	if requested > 0 {
		return requested
	}
	return 50 + rand.Intn(101)
}

func SendKey(hwnd uintptr, key string, holdMs int) {
	v, ok := vk[strings.ToLower(key)]
	if !ok {
		panic("unknown key: " + key)
	}
	if !EnsureForeground(hwnd) {
		panic("failed to foreground window")
	}
	pressOne(v, false)
	time.Sleep(time.Duration(holdMs) * time.Millisecond)
	pressOne(v, true)
}

func PressCombo(hwnd uintptr, combo string, jitterMs int) {
	parts := strings.Split(combo, "+")
	trigger := strings.ToLower(strings.TrimSpace(parts[len(parts)-1]))
	triggerVk, ok := vk[trigger]
	if !ok {
		panic("unknown trigger key: " + trigger)
	}
	var modVks []uint16
	for _, t := range parts[:len(parts)-1] {
		switch strings.ToLower(strings.TrimSpace(t)) {
		case "ctrl", "control":
			modVks = append(modVks, 0xA2)
		case "shift":
			modVks = append(modVks, 0xA0)
		case "alt":
			modVks = append(modVks, 0xA4)
		case "win", "meta":
			modVks = append(modVks, 0x5B)
		default:
			panic("unknown modifier: " + t)
		}
	}
	if !EnsureForeground(hwnd) {
		panic("failed to foreground window")
	}
	for _, m := range modVks {
		pressOne(m, false)
	}
	time.Sleep(time.Duration(jitterMs(jitterMs)) * time.Millisecond)
	pressOne(triggerVk, false)
	time.Sleep(time.Duration(jitterMs(jitterMs)) * time.Millisecond)
	pressOne(triggerVk, true)
	time.Sleep(time.Duration(jitterMs(jitterMs)) * time.Millisecond)
	for i := len(modVks) - 1; i >= 0; i-- {
		pressOne(modVks[i], true)
	}
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	var buf [16]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	return string(buf[i:])
}
