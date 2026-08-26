import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

const statusEl = document.getElementById("status");
const barEl = document.getElementById("bar");
const startBtn = document.getElementById("start");
const cancelBtn = document.getElementById("cancel");

listen("job://progress", e => {
  const { step, total } = e.payload;
  const pct = Math.round((step / total) * 100);
  barEl.value = pct;
  statusEl.textContent = `progress ${pct}%`;
});
listen("job://done", () => { statusEl.textContent = "done"; startBtn.disabled = false; cancelBtn.disabled = true; });
listen("job://cancelled", () => { statusEl.textContent = "cancelled"; startBtn.disabled = false; cancelBtn.disabled = true; });
listen("job://error", e => { statusEl.textContent = `error: ${e.payload}`; startBtn.disabled = false; cancelBtn.disabled = true; });

startBtn.addEventListener("click", async () => {
  startBtn.disabled = true; cancelBtn.disabled = false;
  statusEl.textContent = "started";
  barEl.value = 0;
  try { await invoke("run_long_job", { total: 100 }); }
  catch (e) { statusEl.textContent = `error: ${e}`; startBtn.disabled = false; cancelBtn.disabled = true; }
});
cancelBtn.addEventListener("click", () => invoke("cancel_job"));
cancelBtn.disabled = true;
