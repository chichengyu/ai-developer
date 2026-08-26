// Electron worker_threads worker used by threading_electron.ts.
//
// The worker receives `{ input }` via `workerData` and answers cancel
// requests posted from the main process. It never touches Electron or DOM
// APIs; it only sends structured messages back to the main thread.

import { parentPort, workerData } from "node:worker_threads";

const port = parentPort;
if (!port) throw new Error("this file must run inside worker_threads");

const { input } = workerData as { input: { total: number } };
const total = input.total;

function run(): void {
  let cancelled = false;

  port.on("message", (message: { type: "cancel" }) => {
    if (message.type === "cancel") cancelled = true;
  });

  for (let step = 1; step <= total; step++) {
    if (cancelled) {
      port.postMessage({ type: "cancelled" });
      return;
    }
    // Replace with real work; keep the worker CPU-bound and the main process free.
    const finish = Date.now() + 50;
    while (Date.now() < finish) {
      /* busy work for demo only */
    }
    port.postMessage({ type: "progress", percent: step / total });
  }

  port.postMessage({ type: "done", value: total });
}

run();
