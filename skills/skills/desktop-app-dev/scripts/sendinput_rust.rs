//! Hardware-level keyboard input via Win32 SendInput.
//!
//! Add to Cargo.toml:
//!     [dependencies]
//!     windows = { version = "0.58", features = ["Win32_UI_Input_KeyboardAndMouse", "Win32_UI_WindowsAndMessaging", "Win32_Foundation"] }
//!
//! Drop-in usage:
//!     send_key(hwnd, "F5");
//!     press_combo(hwnd, "ctrl+shift+F1");
use std::collections::HashMap;
use std::sync::OnceLock;
use std::thread::sleep;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use windows::Win32::Foundation::HWND;
use windows::Win32::UI::Input::KeyboardAndMouse::{
    SendInput, INPUT, INPUT_KEYBOARD, KEYBDINPUT, KEYEVENTF_KEYUP, VIRTUAL_KEY,
};
use windows::Win32::UI::WindowsAndMessaging::{
    GetForegroundWindow, SetForegroundWindow, ShowWindow,
};

// Keep vk_map() in sync with scripts/vk_table.json (Python is checked automatically).
fn vk_map() -> &'static HashMap<String, u16> {
    static MAP: OnceLock<HashMap<String, u16>> = OnceLock::new();
    MAP.get_or_init(|| {
        let mut m: HashMap<String, u16> = HashMap::new();
        for (i, c) in "ABCDEFGHIJKLMNOPQRSTUVWXYZ".chars().enumerate() {
            m.insert(c.to_ascii_lowercase().to_string(), 0x41 + i as u16);
        }
        for (i, c) in "0123456789".chars().enumerate() {
            m.insert(c.to_string(), 0x30 + i as u16);
        }
        for i in 1..=24 {
            m.insert(format!("f{}", i), 0x70 + i - 1);
        }
        for i in 0..10 {
            m.insert(format!("num{}", i), 0x60 + i as u16);
        }
        m.extend([
            ("back".into(), 0x08), ("tab".into(), 0x09), ("enter".into(), 0x0D),
            ("escape".into(), 0x1B), ("esc".into(), 0x1B), ("space".into(), 0x20),
            ("pageup".into(), 0x21), ("pagedown".into(), 0x22), ("end".into(), 0x23), ("home".into(), 0x24),
            ("left".into(), 0x25), ("up".into(), 0x26), ("right".into(), 0x27), ("down".into(), 0x28),
            ("insert".into(), 0x2D), ("delete".into(), 0x2E),
            ("lshift".into(), 0xA0), ("rshift".into(), 0xA1),
            ("lctrl".into(), 0xA2), ("rctrl".into(), 0xA3),
            ("lalt".into(), 0xA4), ("ralt".into(), 0xA5),
            ("lwin".into(), 0x5B), ("rwin".into(), 0x5C),
            ("capslock".into(), 0x14), ("numlock".into(), 0x90), ("scrolllock".into(), 0x91),
            ("semicolon".into(), 0xBA), ("equals".into(), 0xBB), ("comma".into(), 0xBC),
            ("minus".into(), 0xBD), ("period".into(), 0xBE), ("slash".into(), 0xBF),
            ("backtick".into(), 0xC0), ("lbracket".into(), 0xDB), ("backslash".into(), 0xDC),
            ("rbracket".into(), 0xDD), ("apostrophe".into(), 0xDE),
            ("select".into(), 0x29), ("print".into(), 0x2A), ("execute".into(), 0x2B),
            ("snapshot".into(), 0x2C), ("help".into(), 0x2F),
            ("nummultiply".into(), 0x6A), ("numadd".into(), 0x6B), ("numseparator".into(), 0x6C),
            ("numsubtract".into(), 0x6D), ("numdecimal".into(), 0x6E), ("numdivide".into(), 0x6F),
        ].iter().cloned());
        m
    })
}

fn ensure_foreground(hwnd: HWND) -> bool {
    if hwnd.0.is_null() { return false; }
    unsafe {
        for _ in 0..5 {
            let _ = ShowWindow(hwnd, windows::Win32::UI::WindowsAndMessaging::SHOW_WINDOW_CMD(9));
            let _ = SetForegroundWindow(hwnd);
            if GetForegroundWindow() == hwnd { return true; }
            sleep(Duration::from_millis(50));
        }
        GetForegroundWindow() == hwnd
    }
}

fn jitter_ms(requested: u64) -> u64 {
    if requested > 0 { return requested; }
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .subsec_nanos() as u64;
    50 + (nanos % 101)
}

unsafe fn press_one(vk: u16, up: bool) -> INPUT {
    let mut input = INPUT::default();
    input.r#type = INPUT_KEYBOARD;
    input.Anonymous.ki = KEYBDINPUT {
        wVk: VIRTUAL_KEY(vk),
        wScan: 0,
        dwFlags: if up { KEYEVENTF_KEYUP } else { Default::default() },
        time: 0,
        dwExtraInfo: 0,
    };
    input
}

pub fn send_key(hwnd: HWND, key: &str, hold_ms: u64) {
    let vk = vk_map().get(&key.to_lowercase()).copied()
        .unwrap_or_else(|| panic!("Unknown key: {}", key));
    if !ensure_foreground(hwnd) { panic!("Failed to foreground window"); }
    unsafe {
        SendInput(&[press_one(vk, false)], std::mem::size_of::<INPUT>() as i32);
        sleep(Duration::from_millis(hold_ms));
        SendInput(&[press_one(vk, true)], std::mem::size_of::<INPUT>() as i32);
    }
}

pub fn press_combo(hwnd: HWND, combo: &str, jitter_ms: u64) {
    let tokens: Vec<&str> = combo.split('+').map(|s| s.trim()).filter(|s| !s.is_empty()).collect();
    if tokens.is_empty() { panic!("empty combo"); }
    let trigger = tokens[tokens.len() - 1].to_lowercase();
    let trigger_vk = vk_map().get(&trigger).copied()
        .unwrap_or_else(|| panic!("Unknown trigger key: {}", trigger));
    let mut mods: Vec<u16> = Vec::new();
    for tok in &tokens[..tokens.len() - 1] {
        match tok.to_lowercase().as_str() {
            "ctrl" | "control" => mods.push(0xA2u16),
            "shift" => mods.push(0xA0),
            "alt" => mods.push(0xA4),
            "win" | "meta" => mods.push(0x5B),
            _ => panic!("Unknown modifier: {}", tok),
        }
    }
    if !ensure_foreground(hwnd) { panic!("Failed to foreground window"); }
    unsafe {
        for &m in &mods {
            SendInput(&[press_one(m, false)], std::mem::size_of::<INPUT>() as i32);
        }
        sleep(Duration::from_millis(jitter_ms(jitter_ms)));
        SendInput(&[press_one(trigger_vk, false)], std::mem::size_of::<INPUT>() as i32);
        sleep(Duration::from_millis(jitter_ms(jitter_ms)));
        SendInput(&[press_one(trigger_vk, true)], std::mem::size_of::<INPUT>() as i32);
        sleep(Duration::from_millis(jitter_ms(jitter_ms)));
        for &m in mods.iter().rev() {
            SendInput(&[press_one(m, true)], std::mem::size_of::<INPUT>() as i32);
        }
    }
}
