// Tauri (Rust) background work with cancellation + progress + safe UI bridge.
//
// The Tauri runtime is single-threaded for UI; long work runs on tokio's
// thread pool and reports results back via window.emit (which marshals the
// payload to the webview). Do NOT touch State / window directly from the
// spawned future -- hold an AppHandle clone and use it.
//
// Cargo.toml:
//   tauri = { version = "2", features = [] }
//   tokio = { version = "1", features = ["rt-multi-thread", "sync", "macros", "time"] }
//
// frontend/src/lib/bridge.ts (sketch):
//   import { listen } from "@tauri-apps/api/event";
//   listen("job://progress", e => updateProgress(e.payload));
//   listen("job://done",    e => onDone(e.payload));
//   listen("job://error",   e => onError(e.payload));
//   invoke("run_long_job", { input: 42 });

use serde::Serialize;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager, Runtime, State};

#[derive(Default)]
pub struct AppState {
    pub cancel_flag: Arc<AtomicBool>,
}

#[derive(Clone, Serialize)]
pub struct Progress {
    pub step: u32,
    pub total: u32,
}

pub async fn run_long_job<R: Runtime>(
    app: AppHandle<R>,
    state: State<'_, AppState>,
    total: u32,
) -> Result<(), String> {
    let cancel = state.cancel_flag.clone();
    cancel.store(false, Ordering::SeqCst);

    // Spawn on tokio's blocking pool so we can do CPU-ish work safely.
    let app2 = app.clone();
    let cancel2 = cancel.clone();
    let join = tauri::async_runtime::spawn_blocking(move || {
        for step in 1..=total {
            if cancel2.load(Ordering::SeqCst) {
                let _ = app2.emit("job://cancelled", ());
                return Err("cancelled".into());
            }
            std::thread::sleep(Duration::from_millis(50));
            let _ = app2.emit("job://progress", Progress { step, total });
        }
        Ok(())
    });

    match join.await {
        Ok(Ok(())) => {
            let _ = app.emit("job://done", total);
            Ok(())
        }
        Ok(Err(e)) => Err(e),
        Err(join_err) => {
            let _ = app.emit("job://error", join_err.to_string());
            Err(join_err.to_string())
        }
    }
}

#[tauri::command]
pub fn cancel_job(state: State<'_, AppState>) {
    state.cancel_flag.store(true, Ordering::SeqCst);
}

// ---- main.rs wiring --------------------------------------------------------
pub fn register<R: Runtime>(builder: tauri::Builder<R>) -> tauri::Builder<R> {
    builder
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![run_long_job, cancel_job])
}
