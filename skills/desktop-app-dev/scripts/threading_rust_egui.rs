// egui background work with cancellation + progress + safe UI bridge.
//
// A worker thread sends events through `std::sync::mpsc` and calls
// `egui::Context::request_repaint()` so the UI thread wakes up and drains
// the channel. The worker never touches egui widgets.
//
// Usage:
//   let (cancel_tx, event_rx) = start_job(ctx.clone(), 100);
//   // in the UI update closure:
//   while let Ok(event) = event_rx.try_recv() {
//       match event {
//           JobEvent::Progress(p) => *progress = p,
//           JobEvent::Done(total) => *status = format!("done: {total}"),
//           JobEvent::Error(message) => *status = format!("error: {message}"),
//           JobEvent::Cancelled => *status = "cancelled".to_string(),
//       }
//   }
//   // later: cancel_tx.send(()).ok();

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

pub fn start_job(ctx: egui::Context, total: u32) -> (Sender<()>, Receiver<JobEvent>) {
    let (cancel_tx, cancel_rx) = channel::<()>();
    let (event_tx, event_rx) = channel();
    let cancel_flag = Arc::new(AtomicBool::new(false));
    let flag = Arc::clone(&cancel_flag);

    thread::spawn(move || {
        for step in 1..=total {
            if flag.load(Ordering::SeqCst) || cancel_rx.try_recv().is_ok() {
                let _ = event_tx.send(JobEvent::Cancelled);
                ctx.request_repaint();
                return;
            }
            thread::sleep(Duration::from_millis(50));
            let percent = step as f32 / total as f32;
            let _ = event_tx.send(JobEvent::Progress(percent));
            ctx.request_repaint();
        }
        let _ = event_tx.send(JobEvent::Done(total));
        ctx.request_repaint();
    });

    (cancel_tx, event_rx)
}
