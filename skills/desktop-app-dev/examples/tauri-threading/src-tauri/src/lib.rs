// Tauri (Rust) background work demo -- adapted from scripts/threading_tauri.rs.

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

#[tauri::command]
async fn run_long_job<R: Runtime>(
    app: AppHandle<R>,
    state: State<'_, AppState>,
    total: u32,
) -> Result<(), String> {
    let cancel = state.cancel_flag.clone();
    cancel.store(false, Ordering::SeqCst);
    let app2 = app.clone();
    let cancel2 = cancel.clone();
    let join = tauri::async_runtime::spawn_blocking(move || {
        for step in 1..=total {
            if cancel2.load(Ordering::SeqCst) {
                let _ = app2.emit("job://cancelled", ());
                return Err("cancelled".into());
            }
            std::thread::sleep(Duration::from_millis(30));
            let _ = app2.emit("job://progress", Progress { step, total });
        }
        Ok(())
    });
    match join.await {
        Ok(Ok(())) => { let _ = app.emit("job://done", total); Ok(()) }
        Ok(Err(e)) => Err(e),
        Err(join_err) => { let _ = app.emit("job://error", join_err.to_string()); Err(join_err.to_string()) }
    }
}

#[tauri::command]
fn cancel_job(state: State<'_, AppState>) {
    state.cancel_flag.store(true, Ordering::SeqCst);
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![run_long_job, cancel_job])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
