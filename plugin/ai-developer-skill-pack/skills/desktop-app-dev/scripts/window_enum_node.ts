// Top-level window enumeration via Win32, using koffi (modern Node FFI).
//
// Install: npm install koffi
//
// FindWindowW path is fully supported by koffi. For full EnumWindows in
// pure Node we delegate to the C++ helper `window_enum_node_shim.dll`.
// Build it once with the recipe at the top of window_enum_node_shim.cc.
//
// Drop the DLL next to your script (or in node_modules/koffi-helper/) and
// load it via koffi.load("win_enum_shim.dll").
import koffi from "koffi";
import path from "node:path";
import fs from "node:fs";
import { Worker } from "node:worker_threads";

const user32 = koffi.load("user32.dll");

const FindWindowW = user32.func("void* __stdcall FindWindowW(uint16_t* lpClassName, uint16_t* lpWindowName)");
const IsWindow = user32.func("bool __stdcall IsWindow(void* hWnd)");

// Load shim lazily so the script still runs (with reduced functionality)
// when the DLL is not present.
let shim: koffi.IKoffiLib | null = null;
let shimFuncs: { enum: any; cancel: any; fg: any } | null = null;
function tryLoadShim(): boolean {
    const candidates = [
        path.join(process.cwd(), "win_enum_shim.dll"),
        path.join(process.cwd(), "build", "win_enum_shim.dll"),
        path.join(__dirname, "win_enum_shim.dll"),
    ];
    for (const p of candidates) {
        if (fs.existsSync(p)) {
            shim = koffi.load(p);
            shimFuncs = {
                enum: shim.func(`
                    uint32_t __stdcall EnumWindowsToBuffer(
                        void* buffer, uint32_t maxRecords,
                        uint16_t* classFilter, uint16_t* titleFilter,
                        int matchAll, volatile uint32_t* cancelled)
                `),
                cancel: shim.func("void __stdcall CancelEnum(volatile uint32_t* cancelled)"),
                fg: shim.func("uint32_t __stdcall GetForegroundHwnd()"),
            };
            return true;
        }
    }
    return false;
}

export interface WindowInfo {
    hwnd: bigint;
    title: string;
    className: string;
}

const TIMEOUT_MS = 3000;

export class WindowFinder {
    private cache = new Map<string, bigint>();

    find(className: string | null, titleSubstring: string): bigint | null {
        const key = `${className ?? ""}|${titleSubstring}`;
        const cached = this.cache.get(key);
        if (cached !== undefined && IsWindow(cached)) return cached;

        if (className && !hasWildcards(titleSubstring)) {
            const clsBuf = Buffer.from((className + "\0"), "utf16le");
            const titleBuf = Buffer.from((titleSubstring + "\0"), "utf16le");
            const h = FindWindowW(
                koffi.as(clsBuf, "uint16_t*"),
                koffi.as(titleBuf, "uint16_t*"),
            ) as unknown as bigint;
            if (h && h !== 0n) { this.cache.set(key, h); return h; }
        }
        const all = this.listWindows(className);
        const match = all.find(w => !titleSubstring || w.title.includes(titleSubstring));
        if (match) { this.cache.set(key, match.hwnd); return match.hwnd; }
        return null;
    }

    listWindows(className: string | null = null): WindowInfo[] {
        if (!shimFuncs) {
            if (!tryLoadShim()) {
                throw new Error(
                    "win_enum_shim.dll not found. Build it from scripts/window_enum_node_shim.cc " +
                    "and place it next to your script.",
                );
            }
        }
        const MAX = 1024;
        const recordSize = 8 + 256 * 2 + 256 * 2;
        const buf = Buffer.alloc(recordSize * MAX);
        const cls = className ? Buffer.from((className + "\0"), "utf16le") : null;
        const title = Buffer.from(("\0"), "utf16le");
        const cancelBuf = Buffer.alloc(4); // volatile uint32_t

        // Run the synchronous DLL call in a worker so we can apply a timeout.
        const w = new Worker(__filename, { workerData: { buf, cls, title, cancelBuf, MAX, recordSize } });
        return new Promise<WindowInfo[]>((resolve, reject) => {
            let settled = false;
            const timer = setTimeout(() => {
                if (settled) return;
                settled = true;
                // Tell the DLL to bail on the next callback.
                cancelBuf.writeUInt32LE(1, 0);
                w.terminate();
                reject(new Error("EnumWindows timed out"));
            }, TIMEOUT_MS);
            w.once("message", msg => {
                if (settled) return;
                settled = true;
                clearTimeout(timer);
                if ((msg as any).error) reject(new Error((msg as any).error));
                else resolve((msg as any).windows as WindowInfo[]);
            });
            w.once("error", err => {
                if (settled) return;
                settled = true;
                clearTimeout(timer);
                reject(err);
            });
        }) as unknown as WindowInfo[];
    }

    invalidate(): void { this.cache.clear(); }
}

function hasWildcards(s: string): boolean { return s.includes("*") || s.includes("?"); }

// ---- Worker thread entry --------------------------------------------------
// Detects workerData and runs the actual EnumWindowsToBuffer call there so
// the main thread can enforce the timeout via worker.terminate().
if (!require.main || (require.main as any).filename !== __filename) {
    // nothing
}
declare const require: any;
declare const module: any;
if (typeof require !== "undefined" && typeof module !== "undefined") {
    // Worker branch executed when invoked as a worker via new Worker(__filename).
    const { parentPort, workerData } = require("node:worker_threads");
    if (parentPort && workerData) {
        // Load the shim inside the worker too -- shimFuncs is null here
        // because tryLoadShim() only ran on the main thread.
        let shimOk = false;
        const workerCandidates = [
            path.join(process.cwd(), "win_enum_shim.dll"),
            path.join(process.cwd(), "build", "win_enum_shim.dll"),
            path.join(__dirname, "win_enum_shim.dll"),
        ];
        for (const p of workerCandidates) {
            if (fs.existsSync(p)) {
                const wshim = koffi.load(p);
                shimFuncs = {
                    enum: wshim.func(`
                        uint32_t __stdcall EnumWindowsToBuffer(
                            void* buffer, uint32_t maxRecords,
                            uint16_t* classFilter, uint16_t* titleFilter,
                            int matchAll, volatile uint32_t* cancelled)
                    `),
                    cancel: wshim.func("void __stdcall CancelEnum(volatile uint32_t* cancelled)"),
                    fg: wshim.func("uint32_t __stdcall GetForegroundHwnd()"),
                };
                shimOk = true;
                break;
            }
        }
        if (!shimOk) {
            parentPort.postMessage({ error: "win_enum_shim.dll not found in worker context" });
        } else try {
            const count = shimFuncs!.enum(
                koffi.as(workerData.buf, "void*"),
                workerData.MAX,
                workerData.cls ? koffi.as(workerData.cls, "uint16_t*") : null,
                koffi.as(workerData.title, "uint16_t*"),
                1,
                koffi.as(workerData.cancelBuf, "volatile uint32_t*"),
            ) as number;
            const out: WindowInfo[] = [];
            for (let i = 0; i < count; i++) {
                const off = i * workerData.recordSize;
                const hwnd = workerData.buf.readBigUInt64LE(off);
                const titleU16 = new Uint16Array(workerData.buf.buffer, off + 8, 256);
                const clsU16 = new Uint16Array(workerData.buf.buffer, off + 8 + 512, 256);
                const title = Buffer.from(titleU16.buffer, titleU16.byteOffset, 512)
                    .toString("utf16le").replace(/\0+$/g, "");
                const cls = Buffer.from(clsU16.buffer, clsU16.byteOffset, 512)
                    .toString("utf16le").replace(/\0+$/g, "");
                out.push({ hwnd, title, className: cls });
            }
            parentPort.postMessage({ windows: out });
        } catch (e: any) {
            parentPort.postMessage({ error: e?.message ?? String(e) });
        }
    }
}

