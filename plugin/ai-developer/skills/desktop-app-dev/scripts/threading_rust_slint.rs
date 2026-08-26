// Slint background work with cancellation + progress + safe UI bridge.
//
// A worker thread sends events through `std::sync::mpsc` and updates the
// UI through `Weak::upgrade_in_event_loop`, which runs the callback on the
// Slint event loop. Replace `set_job_progress` / `set_job_done` with the
// properties generated from your .slint file.
//
// Usage:
//   let (cancel_tx, event_rx) = start_job(ui.as_weak(), 100);
//   // drain event_rx in the UI update callback:
//   while let Ok(event) = event_rx.try_recv() { ... }
//   // later: cancel_tx.send(()).ok();

use slint::{ComponentHandle, Weak};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{channel, Receiver, Sender};
use std::sync::Arc;
use std::thread;
use std::time::Duration;

pub enum JobEvent {
    Progress(f32),
    Done(u32),
    Error(String),
    Cancelled,
}

pub fn start_job(ui: Weak<AppWindow>, total: u32) -> (Sender<()>, Receiver<JobEvent>) {
    let (cancel_tx, cancel_rx) = channel::<()>();
    let (event_tx, event_rx) = channel();
    let cancel_flag = Arc::new(AtomicBool::new(false));
    let flag = Arc::clone(&cancel_flag);

    thread::spawn(move || {
        for step in 1..=total {
            if flag.load(Ordering::SeqCst) || cancel_rx.try_recv().is_ok() {
                let ui_for_cancel = ui.clone();
                let _ = ui_for_cancel.upgrade_in_event_loop(move |ui| ui.set_job_cancelled(true));
                let _ = event_tx.send(JobEvent::Cancelled);
                return;
            }
            let percent = step as f32 / total as f32;
            let ui_for_progress = ui.clone();
            let _ = ui_for_progress.upgrade_in_event_loop(move |ui| ui.set_job_progress(percent));
            let _ = event_tx.send(JobEvent::Progress(percent));
            thread::sleep(Duration::from_millis(50));
        }
        let ui_for_done = ui.clone();
        let _ = ui_for_done.upgrade_in_event_loop(move |ui| ui.set_job_done(total));
        let _ = event_tx.send(JobEvent::Done(total));
    });

    (cancel_tx, event_rx)
}
