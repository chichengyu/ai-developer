// Electron worker_threads worker used by threading_pool_electron.ts.
//
// Receives `{ index, value }` through workerData, answers cancel requests
// from the main process, and reports progress/done/error messages back.
// It never touches Electron, DOM, or renderer APIs.

import { parentPort, workerData } from "node:worker_threads";

const port = parentPort;
if (!port) throw new Error("this file must run inside worker_threads");

const { index, value } = workerData as { index: number; value: number };
let cancelled = false;

port.on("message", (message: { type: "cancel" }) => {
  if (message.type === "cancel") cancelled = true;
});

for (let step = 1; step <= 10; step++) {
  if (cancelled) {
    port.postMessage({ type: "cancelled", index });
    return;
  }
  port.postMessage({ type: "progress", index, percent: step / 10 });
  // Replace with real work; keep CPU work out of the Electron main process.
  const finish = Date.now() + 30;
  while (Date.now() < finish) {
    /* busy work for demo only */
  }
}

port.postMessage({ type: "done", index, value: value * 2 });
