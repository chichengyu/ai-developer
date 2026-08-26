//! Top-level window enumeration with FindWindowW first and EnumWindows fallback.
//!
//! Always runs EnumWindows inside a thread guarded by a 3-second timeout,
//! and caches results by (class, title-substring) for the current session.
//!
//! Add to Cargo.toml:
//!     [dependencies]
//!     windows = { version = "0.58", features = ["Win32_UI_WindowsAndMessaging", "Win32_Foundation", "Win32_System_Threading"] }
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use windows::core::PCWSTR;
use windows::Win32::Foundation::{BOOL, HWND, LPARAM};
use windows::Win32::UI::WindowsAndMessaging::{
    EnumWindows, FindWindowW, GetClassNameW, GetWindowTextLengthW, GetWindowTextW, IsWindow,
};

#[derive(Debug, Clone)]
pub struct WindowInfo {
    pub hwnd: isize,
    pub title: String,
    pub class_name: String,
}

pub struct WindowFinder {
    timeout: Duration,
    cache: Arc<Mutex<HashMap<(Option<String>, String), isize>>>,
}

impl WindowFinder {
    pub fn new() -> Self {
        Self { timeout: Duration::from_secs(3), cache: Arc::new(Mutex::new(HashMap::new())) }
    }

    pub fn find(&self, class_name: Option<&str>, title_substring: &str) -> Option<isize> {
        let key = (class_name.map(String::from), title_substring.to_string());
        {
            let cache = self.cache.lock().unwrap();
            if let Some(&cached) = cache.get(&key) {
                if unsafe { IsWindow(HWND(cached as *mut _)).as_bool() } {
                    return Some(cached);
                }
            }
        }
        self.cache.lock().unwrap().remove(&key);

        if let Some(cls) = class_name {
            if !has_wildcards(title_substring) {
                let cls_w: Vec<u16> = cls.encode_utf16().chain(std::iter::once(0)).collect();
                let title_w: Vec<u16> = title_substring.encode_utf16().chain(std::iter::once(0)).collect();
                let h = unsafe {
                    FindWindowW(PCWSTR(cls_w.as_ptr()), PCWSTR(title_w.as_ptr()))
                };
                if !h.0.is_null() {
                    let val = h.0 as isize;
                    self.cache.lock().unwrap().insert(key, val);
                    return Some(val);
                }
            }
        }

        let matches = self.enum_with_timeout(class_name, title_substring, false);
        if let Some(m) = matches.first() {
            self.cache.lock().unwrap().insert(key, m.hwnd);
            return Some(m.hwnd);
        }
        None
    }

    pub fn list_windows(&self, class_name: Option<&str>) -> Vec<WindowInfo> {
        self.enum_with_timeout(class_name, "", true)
    }

    pub fn invalidate(&self) {
        self.cache.lock().unwrap().clear();
    }

    fn enum_with_timeout(&self, class_name: Option<&str>, title_substring: &str, match_all: bool) -> Vec<WindowInfo> {
        let (tx, rx) = std::sync::mpsc::channel();
        let class_owned = class_name.map(String::from);
        let title_owned = title_substring.to_string();
        let stop = Arc::new(std::sync::atomic::AtomicBool::new(false));
        let stop_clone = stop.clone();

        std::thread::spawn(move || {
            unsafe extern "system" fn cb(hwnd: HWND, lparam: LPARAM) -> BOOL {
                let state = &*(lparam.0 as *const EnumState);
                if state.stop.load(std::sync::atomic::Ordering::Relaxed) { return BOOL(0); }
                let len = GetWindowTextLengthW(hwnd);
                let mut title = String::new();
                if len > 0 {
                    let mut buf = vec![0u16; (len + 1) as usize];
                    GetWindowTextW(hwnd, &mut buf);
                    title = String::from_utf16_lossy(&buf[..len as usize]);
                }
                let mut cls_buf = vec![0u16; 256];
                let cls_len = GetClassNameW(hwnd, &mut cls_buf);
                let class_name = String::from_utf16_lossy(&cls_buf[..cls_len as usize]);
                if !state.match_all && title.is_empty() { return BOOL(1); }
                if let Some(ref want) = state.class_name {
                    if class_name != *want { return BOOL(1); }
                }
                if !state.match_all && !state.title_substring.is_empty() && !title.contains(&state.title_substring) {
                    return BOOL(1);
                }
                let _ = state.tx.send(WindowInfo { hwnd: hwnd.0 as isize, title, class_name });
                BOOL(1)
            }
            struct EnumState {
                class_name: Option<String>,
                title_substring: String,
                match_all: bool,
                tx: std::sync::mpsc::Sender<WindowInfo>,
                stop: Arc<std::sync::atomic::AtomicBool>,
            }
            let state = EnumState {
                class_name: class_owned,
                title_substring: title_owned,
                match_all,
                tx,
                stop: stop_clone,
            };
            let state_ptr = Box::into_raw(Box::new(state)) as *const EnumState as isize;
            unsafe { let _ = EnumWindows(cb, LPARAM(state_ptr)); }
        });

        let deadline = std::time::Instant::now() + self.timeout;
        let mut results = Vec::new();
        while let Ok(info) = rx.recv_timeout(Duration::from_millis(50)) {
            results.push(info);
            if std::time::Instant::now() >= deadline { break; }
        }
        stop.store(true, std::sync::atomic::Ordering::Relaxed);
        results
    }
}

fn has_wildcards(s: &str) -> bool { s.contains('*') || s.contains('?') }