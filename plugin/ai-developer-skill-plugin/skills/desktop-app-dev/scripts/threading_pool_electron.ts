// Electron main-process bounded worker pool.
//
// Runs independent tasks on a bounded set of Node worker_threads, forwards
// aggregate and per-item progress to the renderer, and supports cooperative
// cancellation. The worker side is threading_pool_electron_worker.ts.
//
// Usage (main process):
//   const job = startParallelJob(
//       mainWindow,
//       workerPath("threading_pool_electron_worker.js"),
//       [1, 2, 3, 4, 5],
//       4,
//       { onProgress: p => sendProgress(p), onDone: values => sendDone(values) });
//   // later: job.cancel();

import { join } from "node:path";
import { Worker } from "node:worker_threads";
import type { BrowserWindow } from "electron";

export interface PoolProgress {
  completed: number;
  total: number;
  percent: number;
}

export interface PoolResult {
  index: number;
  value: number;
  error?: string;
}

export type PoolWorkerMessage =
  | { type: "progress"; index: number; percent: number }
  | { type: "done"; index: number; value: number }
  | { type: "error"; index: number; error: string }
  | { type: "cancelled"; index: number };

export interface PoolCallbacks {
  onProgress?: (progress: PoolProgress) => void;
  onItemProgress?: (progress: { index: number; percent: number }) => void;
  onItemDone?: (result: PoolResult) => void;
  onError?: (result: PoolResult) => void;
  onDone?: (results: PoolResult[]) => void;
  onCancel?: () => void;
}

export interface RunningPool {
  cancel: () => void;
  isRunning: () => boolean;
}

export function startParallelJob(
  window: BrowserWindow,
  workerFile: string,
  inputs: number[],
  maxWorkers = 4,
  maxAttempts = 1,
  retryDelayMs = 100,
  callbacks: PoolCallbacks = {},
): RunningPool {
  const queue = inputs.map((value, index) => ({
    index,
    value,
    attempts: 0,
  }));
  const results: PoolResult[] = inputs.map((value, index) => ({
    index,
    value: 0,
    error: "pending",
  }));
  const settled = new Set<number>();
  const workers = new Map<number, Worker>();
  const total = inputs.length;
  let completed = 0;
  let active = 0;
  let cancelled = false;
  let finished = false;

  const send = (channel: string, payload?: unknown) => {
    if (!window.isDestroyed() && !window.webContents.isDestroyed()) {
      window.webContents.send(channel, payload);
    }
  };

  const finishTask = (index: number, result: PoolResult) => {
    if (settled.has(index)) return;
    settled.add(index);
    results[index] = result;
    completed += 1;
    if (result.error) {
      callbacks.onError?.(result);
      send("pool:item-error", result);
    } else {
      callbacks.onItemDone?.(result);
      send("pool:item-done", result);
    }
    const progress: PoolProgress = {
      completed,
      total,
      percent: total === 0 ? 1 : completed / total,
    };
    callbacks.onProgress?.(progress);
    send("pool:progress", progress);
  };

  const handleFailure = (task: { index: number; value: number; attempts: number }, error: string) => {
    if (cancelled) {
      finishTask(task.index, { index: task.index, value: 0, error: "cancelled" });
      return;
    }
    if (task.attempts + 1 < maxAttempts) {
      const retryTask = { index: task.index, value: task.value, attempts: task.attempts + 1 };
      setTimeout(() => {
        queue.push(retryTask);
        runNext();
      }, retryDelayMs);
      return;
    }
    finishTask(task.index, { index: task.index, value: 0, error });
  };

  const maybeFinish = () => {
    if (finished || completed < total) return;
    finished = true;
    if (cancelled) {
      callbacks.onCancel?.();
      send("pool:cancelled");
    } else {
      callbacks.onDone?.(results);
      send("pool:done", results);
    }
  };

  const runNext = () => {
    while (!cancelled && active < maxWorkers && queue.length > 0) {
      const task = queue.shift();
      if (!task) break;
      active += 1;
      const worker = new Worker(workerFile, {
        workerData: { index: task.index, value: task.value },
      });
      workers.set(task.index, worker);

      worker.on("message", (message: PoolWorkerMessage) => {
        switch (message.type) {
          case "progress":
            callbacks.onItemProgress?.({
              index: message.index,
              percent: message.percent,
            });
            send("pool:item-progress", {
              index: message.index,
              percent: message.percent,
            });
            break;
          case "done":
            finishTask(message.index, {
              index: message.index,
              value: message.value,
            });
            break;
          case "error":
            handleFailure(task, message.error);
            break;
          case "cancelled":
            finishTask(message.index, {
              index: message.index,
              value: 0,
              error: "cancelled",
            });
            break;
        }
      });

      worker.on("error", (error) => {
        handleFailure(task, error.message);
      });

      worker.on("exit", () => {
        active -= 1;
        workers.delete(task.index);
        maybeFinish();
        runNext();
      });
    }
  };

  runNext();

  return {
    cancel: () => {
      cancelled = true;
      for (const worker of workers.values()) {
        worker.postMessage({ type: "cancel" });
      }
    },
    isRunning: () => active > 0 || queue.length > 0,
  };
}

// Resolve a worker file next to the compiled main script.
export function workerPath(fileName: string): string {
  return join(__dirname, fileName);
}
