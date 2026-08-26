// Tauri (Rust) bounded parallel pool with aggregate progress + cancellation.
//
// Cargo.toml:
//   tauri = { version = "2", features = [] }
//   tokio = { version = "1", features = ["rt-multi-thread", "sync", "macros", "time"] }
//   serde = { version = "1", features = ["derive"] }
//
// The frontend subscribes to:
//   pool://progress, pool://done, pool://error, pool://cancelled
// and calls `cancel_pool` from the UI when the user hits Cancel.

use serde::Serialize;
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::Arc;
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager, Runtime, State};
use tokio::sync::Semaphore;
use tokio::task::JoinSet;

#[derive(Default)]
pub struct PoolState {
    pub cancel_flag: Arc<AtomicBool>,
}

#[derive(Clone, Serialize)]
pub struct PoolProgress {
    pub completed: u32,
    pub total: u32,
    pub percent: f32,
}

#[derive(Clone, Serialize)]
pub struct PoolItemResult {
    pub index: usize,
    pub value: u32,
    pub error: Option<String>,
}

pub async fn run_parallel_job<R: Runtime>(
    app: AppHandle<R>,
    state: State<'_, PoolState>,
    inputs: Vec<u32>,
    concurrency: usize,
) -> Result<Vec<PoolItemResult>, String> {
    let total = inputs.len() as u32;
    let cancel = state.cancel_flag.clone();
    cancel.store(false, Ordering::SeqCst);

    let semaphore = Arc::new(Semaphore::new(concurrency.max(1)));
    let completed = Arc::new(AtomicU32::new(0));
    let mut set = JoinSet::new();

    for (index, input) in inputs.into_iter().enumerate() {
        let permit = semaphore
            .clone()
            .acquire_owned()
            .await
            .map_err(|_| "parallel pool closed".to_string())?;
        let app2 = app.clone();
        let cancel2 = cancel.clone();
        let completed2 = completed.clone();

        set.spawn(async move {
            let _permit = permit;
            tauri::async_runtime::spawn_blocking(move || {
                let mut error = None;
                for _step in 1..=10 {
                    if cancel2.load(Ordering::SeqCst) {
                        error = Some("cancelled".to_string());
                        break;
                    }
                    std::thread::sleep(Duration::from_millis(30));
                }

                let value = if error.is_none() { input * 2 } else { 0 };
                let done = completed2.fetch_add(1, Ordering::SeqCst) + 1;
                let _ = app2.emit(
                    "pool://progress",
                    PoolProgress {
                        completed: done,
                        total,
                        percent: done as f32 / total as f32,
                    },
                );

                PoolItemResult {
                    index,
                    value,
                    error,
                }
            })
            .await
            .unwrap_or_else(|join_err| PoolItemResult {
                index,
                value: 0,
                error: Some(join_err.to_string()),
            })
        });
    }

    let mut results = Vec::with_capacity(total as usize);
    while let Some(joined) = set.join_next().await {
        match joined {
            Ok(item) => results.push(item),
            Err(join_err) => {
                let _ = app.emit("pool://error", join_err.to_string());
                return Err(join_err.to_string());
            }
        }
    }
    results.sort_by_key(|item| item.index);

    if cancel.load(Ordering::SeqCst) {
        let _ = app.emit("pool://cancelled", ());
    } else {
        let _ = app.emit("pool://done", &results);
    }
    Ok(results)
}

#[tauri::command]
pub fn cancel_pool(state: State<'_, PoolState>) {
    state.cancel_flag.store(true, Ordering::SeqCst);
}

// ---- main.rs wiring --------------------------------------------------------
pub fn register<R: Runtime>(builder: tauri::Builder<R>) -> tauri::Builder<R> {
    builder
        .manage(PoolState::default())
        .invoke_handler(tauri::generate_handler![run_parallel_job, cancel_pool])
}
