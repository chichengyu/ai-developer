// Package winenum provides top-level window enumeration with FindWindowW
// first and EnumWindows fallback. Always runs EnumWindows with a 3-second
// timeout, and caches results by (class, title-substring) per session.
//
// Requires: golang.org/x/sys/windows
package winenum

import (
	"strings"
	"sync"
	"syscall"
	"time"
	"unsafe"

	"golang.org/x/sys/windows"
)

var (
	user32                  = windows.NewLazySystemDLL("user32.dll")
	procFindWindowW         = user32.NewProc("FindWindowW")
	procIsWindow            = user32.NewProc("IsWindow")
	procGetWindowTextLength = user32.NewProc("GetWindowTextLengthW")
	procGetWindowText       = user32.NewProc("GetWindowTextW")
	procGetClassName        = user32.NewProc("GetClassNameW")
	procEnumWindows         = user32.NewProc("EnumWindows")
)

type WindowInfo struct {
	Hwnd      uintptr
	Title     string
	ClassName string
}

type Finder struct {
	mu    sync.Mutex
	cache map[string]uintptr
}

func NewFinder() *Finder {
	return &Finder{cache: make(map[string]uintptr)}
}

func (f *Finder) Find(className, titleSubstring string) uintptr {
	key := className + "\x00" + titleSubstring
	f.mu.Lock()
	if cached, ok := f.cache[key]; ok {
		if r, _, _ := procIsWindow.Call(cached); r != 0 {
			f.mu.Unlock()
			return cached
		}
		delete(f.cache, key)
	}
	f.mu.Unlock()

	if className != "" && !hasWildcards(titleSubstring) {
		clsPtr, _ := syscall.UTF16PtrFromString(className)
		titlePtr, _ := syscall.UTF16PtrFromString(titleSubstring)
		if h, _, _ := procFindWindowW.Call(uintptr(unsafePtr(clsPtr)), uintptr(unsafePtr(titlePtr))); h != 0 {
			f.mu.Lock()
			f.cache[key] = h
			f.mu.Unlock()
			return h
		}
	}

	matches := f.enumWithTimeout(className, titleSubstring, false)
	if len(matches) > 0 {
		f.mu.Lock()
		f.cache[key] = matches[0].Hwnd
		f.mu.Unlock()
		return matches[0].Hwnd
	}
	return 0
}

func (f *Finder) ListWindows(className string) []WindowInfo {
	return f.enumWithTimeout(className, "", true)
}

func (f *Finder) Invalidate() {
	f.mu.Lock()
	f.cache = make(map[string]uintptr)
	f.mu.Unlock()
}

func (f *Finder) enumWithTimeout(className, titleSubstring string, matchAll bool) []WindowInfo {
	var mu sync.Mutex
	var results []WindowInfo
	done := make(chan struct{})

	cb := syscall.NewCallback(func(hwnd uintptr, _ uintptr) uintptr {
		mu.Lock()
		defer mu.Unlock()
		r, _, _ := procGetWindowTextLength.Call(hwnd)
		length := int32(r)
		if length == 0 && !matchAll {
			return 1
		}
		buf := make([]uint16, length+1)
		procGetWindowText.Call(hwnd, uintptr(unsafePtr(&buf[0])), uintptr(length+1))
		title := windows.UTF16ToString(buf)
		clsBuf := make([]uint16, 256)
		n, _, _ := procGetClassName.Call(hwnd, uintptr(unsafePtr(&clsBuf[0])), 256)
		class := windows.UTF16ToString(clsBuf[:n])
		if className != "" && class != className {
			return 1
		}
		if !matchAll && titleSubstring != "" && !strings.Contains(title, titleSubstring) {
			return 1
		}
		results = append(results, WindowInfo{Hwnd: hwnd, Title: title, ClassName: class})
		return 1
	})

	go func() {
		defer close(done)
		procEnumWindows.Call(cb, 0)
	}()

	select {
	case <-done:
	case <-time.After(3 * time.Second):
	}

	return results
}

func hasWildcards(s string) bool {
	return strings.ContainsAny(s, "*?")
}

// unsafePtr converts a pointer to uintptr without import cycle; mirrors unsafe.Pointer cast
func unsafePtr(p unsafe.Pointer) uintptr { return uintptr(p) }