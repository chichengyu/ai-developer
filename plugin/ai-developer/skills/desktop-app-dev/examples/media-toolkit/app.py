"""Tkinter media toolkit demo: fast downloads + all-format conversion.

Uses the canonical scripts from ../scripts so the UI shows live percent,
total file size, speed, ETA, and stage for both downloads and conversions.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from tkinter import StringVar, Tk, filedialog, ttk

SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from file_converter import convert_file  # noqa: E402
from media_downloader import CancelToken, download_file  # noqa: E402
from media_formats import FORMAT_CATALOG  # noqa: E402


def human_size(value: int | float | None) -> str:
    if value is None:
        return "-"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return "-"


class MediaToolkitApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.cancel_token: CancelToken | None = None
        root.title("Media Toolkit")
        root.geometry("760x420")
        root.minsize(680, 380)
        style = ttk.Style()
        style.theme_use("clam")
        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        self._build_download_tab(notebook)
        self._build_convert_tab(notebook)

    def _build_download_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=12)
        notebook.add(tab, text="Download")
        self.download_url = StringVar()
        self.download_dir = StringVar(value=str(Path.home() / "Downloads"))
        self.download_status = StringVar(value="Idle")
        self.download_detail = StringVar(value="Total: -")
        self.download_percent = StringVar(value="0%")
        self.download_progress = ttk.Progressbar(tab, maximum=1000, value=0)

        ttk.Label(tab, text="URL").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(tab, textvariable=self.download_url).grid(
            row=0, column=1, columnspan=4, sticky="ew", pady=4
        )
        ttk.Label(tab, text="Folder").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(tab, textvariable=self.download_dir).grid(
            row=1, column=1, columnspan=3, sticky="ew", pady=4
        )
        ttk.Button(tab, text="Browse", command=self._pick_download_dir).grid(
            row=1, column=4, padx=4
        )
        self.download_progress.grid(row=2, column=0, columnspan=5, sticky="ew", pady=8)
        ttk.Label(tab, textvariable=self.download_status).grid(
            row=3, column=0, columnspan=5, sticky="w"
        )
        ttk.Label(tab, textvariable=self.download_percent).grid(row=4, column=0, sticky="w")
        ttk.Label(tab, textvariable=self.download_detail).grid(
            row=4, column=1, columnspan=4, sticky="w"
        )
        actions = ttk.Frame(tab)
        actions.grid(row=5, column=0, columnspan=5, sticky="ew", pady=12)
        ttk.Button(actions, text="Start", command=self.start_download).pack(side="left")
        ttk.Button(actions, text="Cancel", command=self.cancel).pack(side="left", padx=8)
        tab.columnconfigure(1, weight=1)

    def _build_convert_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=12)
        notebook.add(tab, text="Convert")
        self.convert_source = StringVar()
        self.convert_target = StringVar()
        self.convert_output = StringVar()
        self.convert_status = StringVar(value="Idle")
        self.convert_detail = StringVar(value="Source: -")
        self.convert_progress = ttk.Progressbar(tab, maximum=1000, value=0)

        ttk.Label(tab, text="Source").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(tab, textvariable=self.convert_source).grid(
            row=0, column=1, columnspan=3, sticky="ew", pady=4
        )
        ttk.Button(tab, text="Browse", command=self._pick_source).grid(row=0, column=4, padx=4)
        ttk.Label(tab, text="Target").grid(row=1, column=0, sticky="w", pady=4)
        target_values = [
            f"{spec.extension} ({spec.category})"
            for spec in FORMAT_CATALOG
            if spec.engine in ("ffmpeg", "stdlib", "copy")
        ]
        target_box = ttk.Combobox(
            tab,
            textvariable=self.convert_target,
            values=target_values,
            state="readonly",
            width=32,
        )
        target_box.grid(row=1, column=1, columnspan=3, sticky="ew", pady=4)
        target_box.bind("<<ComboboxSelected>>", self._update_output)
        ttk.Label(tab, text="Output").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(tab, textvariable=self.convert_output).grid(
            row=2, column=1, columnspan=3, sticky="ew", pady=4
        )
        ttk.Button(tab, text="Browse", command=self._pick_output).grid(row=2, column=4, padx=4)
        self.convert_progress.grid(row=3, column=0, columnspan=5, sticky="ew", pady=8)
        ttk.Label(tab, textvariable=self.convert_status).grid(
            row=4, column=0, columnspan=5, sticky="w"
        )
        ttk.Label(tab, textvariable=self.convert_detail).grid(
            row=5, column=0, columnspan=5, sticky="w"
        )
        actions = ttk.Frame(tab)
        actions.grid(row=6, column=0, columnspan=5, sticky="ew", pady=12)
        ttk.Button(actions, text="Start", command=self.start_convert).pack(side="left")
        ttk.Button(actions, text="Cancel", command=self.cancel).pack(side="left", padx=8)
        tab.columnconfigure(1, weight=1)

    def _pick_download_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.download_dir.get())
        if selected:
            self.download_dir.set(selected)

    def _pick_source(self) -> None:
        selected = filedialog.askopenfilename()
        if selected:
            self.convert_source.set(selected)
            self._update_output()

    def _pick_output(self) -> None:
        selected = filedialog.asksaveasfilename(initialfile=self.convert_output.get())
        if selected:
            self.convert_output.set(selected)

    def _update_output(self, _event: object = None) -> None:
        source = Path(self.convert_source.get())
        target_text = self.convert_target.get()
        if source.is_file() and target_text:
            extension = target_text.split(" ", 1)[0]
            self.convert_output.set(str(source.with_suffix(f".{extension}")))

    def start_download(self) -> None:
        url = self.download_url.get().strip()
        if not url:
            return
        self.cancel_token = CancelToken()
        self.download_progress.configure(value=0)
        self.download_status.set("Probing...")
        thread = threading.Thread(
            target=self._download_worker,
            args=(url, Path(self.download_dir.get())),
            daemon=True,
        )
        thread.start()

    def _download_worker(self, url: str, dest_dir: Path) -> None:
        try:
            result = download_file(
                url,
                dest_dir / "download.bin",
                progress=self._download_progress_callback,
                cancel=self.cancel_token,
            )
            self.root.after(
                0,
                lambda: (
                    self.download_status.set(f"Done: {result.path.name}"),
                    self.download_percent.set("100%"),
                    self.download_detail.set(
                        f"Total: {human_size(result.total_size)} | " f"{result.elapsed_s:.1f}s"
                    ),
                ),
            )
        except Exception as exc:
            message = str(exc)
            self.root.after(
                0,
                lambda: (
                    self.download_status.set("Failed"),
                    self.download_detail.set(message),
                ),
            )

    def _download_progress_callback(self, progress: object) -> None:
        percent = getattr(progress, "percent", None)
        downloaded = getattr(progress, "downloaded", 0)
        total = getattr(progress, "total", None)
        speed = getattr(progress, "speed_avg", 0.0)
        eta = getattr(progress, "eta_s", None)
        self.root.after(
            0,
            lambda: (
                self.download_progress.configure(value=int((percent or 0) * 1000)),
                self.download_percent.set(f"{((percent or 0) * 100):.1f}%"),
                self.download_status.set(f"Stage: {getattr(progress, 'stage', '')}"),
                self.download_detail.set(
                    f"Downloaded: {human_size(downloaded)} / {human_size(total)} | "
                    f"Speed: {human_size(speed)}/s | ETA: {int(eta) if eta else '-'}s"
                ),
            ),
        )

    def start_convert(self) -> None:
        source = Path(self.convert_source.get())
        output = Path(self.convert_output.get())
        if not source.is_file() or not self.convert_target.get():
            return
        self.cancel_token = CancelToken()
        self.convert_progress.configure(value=0)
        self.convert_status.set("Converting...")
        thread = threading.Thread(
            target=self._convert_worker,
            args=(source, output),
            daemon=True,
        )
        thread.start()

    def _convert_worker(self, source: Path, output: Path) -> None:
        try:
            result = convert_file(
                source,
                output,
                progress=self._convert_progress_callback,
                cancel=self.cancel_token,
            )
            self.root.after(
                0,
                lambda: (
                    self.convert_status.set(f"Done: {result.path.name}"),
                    self.convert_detail.set(
                        f"Source: {human_size(result.input_size)} | "
                        f"Output: {human_size(result.output_size)} | "
                        f"{result.engine} | {result.elapsed_s:.1f}s"
                    ),
                ),
            )
        except Exception as exc:
            message = str(exc)
            self.root.after(
                0,
                lambda: (
                    self.convert_status.set("Failed"),
                    self.convert_detail.set(message),
                ),
            )

    def _convert_progress_callback(self, progress: object) -> None:
        percent = getattr(progress, "percent", None)
        input_size = getattr(progress, "input_size", 0)
        output_size = getattr(progress, "output_size", 0)
        self.root.after(
            0,
            lambda: (
                self.convert_progress.configure(value=int((percent or 0) * 1000)),
                self.convert_status.set(f"Stage: {getattr(progress, 'stage', '')}"),
                self.convert_detail.set(
                    f"Source: {human_size(input_size)} | " f"Output: {human_size(output_size)}"
                ),
            ),
        )

    def cancel(self) -> None:
        if self.cancel_token is not None:
            self.cancel_token.cancel()
            self.cancel_token = None


def main() -> None:
    root = Tk()
    MediaToolkitApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
