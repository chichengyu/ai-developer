// Electron main-process background work with cancellation + progress.
//
// Heavy work runs in a Node `worker_threads` Worker so the Electron main
// process event loop stays responsive. Every event is forwarded to the
// renderer with `webContents.send`, and the renderer subscribes via
// `ipcRenderer.on("job:progress" | "job:done" | "job:error" | "job:cancelled")`.
//
// Usage (main process):
//   const worker = startBackgroundJob(
//       mainWindow,
//       path.join(__dirname, "threading_electron_worker.ts"),
//       { total: 100 },
//       {
//         onProgress: (p) => mainWindow.webContents.send("job:progress", p),
//         onDone: (value) => mainWindow.webContents.send("job:done", value),
//         onError: (message) => mainWindow.webContents.send("job:error", message),
//         onCancel: () => mainWindow.webContents.send("job:cancelled"),
//       },
//   );
//   // later: cancelBackgroundJob(worker);

import { join } from "node:path";
import { Worker } from "node:worker_threads";
import type { BrowserWindow } from "electron";

export interface JobProgress {
  percent: number;
  message?: string;
}

export type WorkerMessage =
  | { type: "progress"; percent: number }
  | { type: "done"; value: unknown }
  | { type: "error"; error: string }
  | { type: "cancelled" };

export interface JobCallbacks {
  onProgress?: (progress: number) => void;
  onDone?: (value: unknown) => void;
  onError?: (error: string) => void;
  onCancel?: () => void;
}

export function startBackgroundJob(
  window: BrowserWindow,
  workerFile: string,
  input: unknown,
  callbacks: JobCallbacks,
): Worker {
  const worker = new Worker(workerFile, { workerData: { input } });

  worker.on("message", (message: WorkerMessage) => {
    const send = (channel: string, payload?: unknown) => {
      if (!window.isDestroyed() && !window.webContents.isDestroyed()) {
        window.webContents.send(channel, payload);
      }
    };

    switch (message.type) {
      case "progress":
        callbacks.onProgress?.(message.percent);
        send("job:progress", { percent: message.percent });
        break;
      case "done":
        callbacks.onDone?.(message.value);
        send("job:done", message.value);
        break;
      case "error":
        callbacks.onError?.(message.error);
        send("job:error", message.error);
        break;
      case "cancelled":
        callbacks.onCancel?.();
        send("job:cancelled");
        break;
    }
  });

  worker.on("error", (error) => {
    callbacks.onError?.(error.message);
    if (!window.isDestroyed() && !window.webContents.isDestroyed()) {
      window.webContents.send("job:error", error.message);
    }
  });

  return worker;
}

export function cancelBackgroundJob(worker: Worker): void {
  worker.postMessage({ type: "cancel" });
}

// Resolve a worker file next to the compiled main script.
export function workerPath(fileName: string): string {
  return join(__dirname, fileName);
}
