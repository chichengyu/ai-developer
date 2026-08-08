"""Built-in dependency manager for desktop apps.

Manages app-local runtimes (ffmpeg, tesseract, ImageMagick, etc.) with
one-click install semantics: check-only by default, and `install()` only
when the user clicks install. Downloads use the chunked concurrent
resumable downloader, verify SHA-256 when configured, extract safely,
and return app-local binary paths so the app never relies on the
recipient's system PATH.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from media_downloader import download_file

ProgressFn = Callable[[str, float | None, str], None]


class DependencyError(RuntimeError):
    """Raised when a built-in dependency cannot be installed."""


@dataclass(frozen=True)
class DependencySpec:
    name: str
    kind: str = "detect"
    url: str | None = None
    version: str = ""
    sha256: str | None = None
    bin_names: tuple[str, ...] = ()
    env_vars: tuple[str, ...] = ()
    extract_subdir: str | None = None
    download_name: str | None = None
    note: str = ""


def spec_from_dict(data: dict[str, Any]) -> DependencySpec:
    """Build a DependencySpec from a JSON manifest entry."""
    return DependencySpec(
        name=str(data.get("name", "")),
        kind=str(data.get("kind", "detect")),
        url=data.get("url"),
        version=str(data.get("version", "") or ""),
        sha256=data.get("sha256"),
        bin_names=tuple(str(item) for item in data.get("bin_names", [])),
        env_vars=tuple(str(item) for item in data.get("env_vars", [])),
        extract_subdir=data.get("extract_subdir"),
        download_name=data.get("download_name"),
        note=str(data.get("note", "") or ""),
    )


def default_runtime_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(local) / "BuiltinDependenciesRuntime"


def _noop_progress(stage: str, percent: float | None, message: str) -> None:
    print(f"[{stage}] {percent or 0:.0%} {message}")


def _zip_member_is_safe(member_name: str) -> bool:
    normalized = member_name.replace("\\", "/")
    if normalized.startswith("/") or (len(normalized) >= 2 and normalized[1] == ":"):
        return False
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    return bool(parts) and all(part != ".." for part in parts)


class BuiltinDependencyManager:
    """Check, download, install, and configure app-local dependencies."""

    def __init__(
        self,
        runtime_dir: str | Path,
        specs: list[DependencySpec | dict[str, Any]] | None = None,
        progress: ProgressFn | None = None,
    ) -> None:
        self.runtime_dir = Path(runtime_dir)
        self.specs = [
            spec_from_dict(item) if isinstance(item, dict) else item for item in (specs or [])
        ]
        self.progress = progress or _noop_progress
        self._cache_dir = self.runtime_dir / "downloads"
        self._manifest_path = self.runtime_dir / "dependencies.json"

    def check_status(self) -> dict[str, Any]:
        items = [self._status_for(spec) for spec in self.specs]
        return {
            "runtime_dir": str(self.runtime_dir),
            "ready": all(item["installed"] for item in items),
            "items": items,
        }

    def environment(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for spec in self.specs:
            status = self._status_for(spec)
            if not status["installed"]:
                continue
            env_vars: dict[str, str] = {}
            for var in spec.env_vars:
                if status["paths"]:
                    env_vars[var] = status["paths"][0]
            result[spec.name] = {
                "bin_dir": status["bin_dir"],
                "paths": status["paths"],
                "env_vars": env_vars,
            }
        return result

    def install(self, install: bool = True) -> dict[str, Any]:
        """Install all specs, or only report status when install=False."""
        if not install:
            return self.check_status()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        total = max(1, len(self.specs))
        for index, spec in enumerate(self.specs):
            self.progress(spec.name, index / total, f"installing {spec.name}")
            self._install_one(spec)
            self.progress(spec.name, (index + 1) / total, f"installed {spec.name}")
        self._write_manifest()
        return self.check_status()

    def _status_for(self, spec: DependencySpec) -> dict[str, Any]:
        install_dir = self.runtime_dir / spec.name
        found: list[str] = []
        for name in spec.bin_names:
            found_path = self._find_bin(install_dir, name)
            if found_path is None and spec.kind == "detect":
                which_path = shutil.which(name)
                if which_path is not None:
                    found_path = Path(which_path)
            if found_path is not None:
                found.append(str(found_path))
        installed = bool(found) and len(found) == len(spec.bin_names)
        version = self._read_version(install_dir) or spec.version
        return {
            "name": spec.name,
            "kind": spec.kind,
            "installed": installed,
            "version": version,
            "paths": found,
            "bin_dir": str(install_dir),
        }

    def _install_one(self, spec: DependencySpec) -> None:
        status = self._status_for(spec)
        if status["installed"] and spec.kind in ("detect", "archive", "portable"):
            self.progress(spec.name, 1.0, f"{spec.name} already installed")
            return
        if spec.kind == "pip":
            self._install_pip(spec)
            return
        if spec.kind == "detect" and spec.url is None:
            raise DependencyError(f"{spec.name} is not installed and has no built-in download URL")
        if spec.kind == "detect":
            spec = DependencySpec(
                name=spec.name,
                kind="portable" if self._looks_portable(spec.url or "") else "archive",
                url=spec.url,
                version=spec.version,
                sha256=spec.sha256,
                bin_names=spec.bin_names,
                env_vars=spec.env_vars,
                extract_subdir=spec.extract_subdir,
                download_name=spec.download_name,
                note=spec.note,
            )
        download_path = self._download(spec)
        install_dir = self.runtime_dir / spec.name
        self._reset_install_dir(install_dir)
        if spec.kind == "portable":
            target = install_dir / (spec.bin_names[0] if spec.bin_names else download_path.name)
            shutil.copy2(download_path, target)
            if os.name != "nt":
                target.chmod(target.stat().st_mode | 0o111)
        elif spec.kind == "archive":
            self._extract_archive(download_path, install_dir)
        else:
            raise DependencyError(f"unsupported dependency kind: {spec.kind}")
        self._write_version(install_dir, spec.version)

    def _download(self, spec: DependencySpec) -> Path:
        if spec.url is None:
            raise DependencyError(f"{spec.name} has no download URL")
        suffix = Path(spec.url).suffix.lower()
        name = spec.download_name or spec.name
        dest = self._cache_dir / (name + suffix if suffix else name)
        if dest.exists():
            if spec.sha256 and self._sha256(dest).lower() == spec.sha256.lower():
                self.progress(spec.name, 1.0, f"using cached {dest.name}")
                return dest
            if spec.sha256 is None:
                self.progress(spec.name, 1.0, f"using cached {dest.name}")
                return dest
            dest.unlink()
        self.progress(spec.name, 0.0, f"downloading {spec.url}")
        download_file(
            spec.url,
            dest,
            concurrency=4,
            chunk_size=8 * 1024 * 1024,
            progress=lambda event: self.progress(
                spec.name,
                event.percent,
                (
                    f"downloaded {event.downloaded:,}/{event.total or 0:,} bytes, "
                    f"{event.speed_avg:.0f} B/s, ETA {int(event.eta_s or 0)}s"
                ),
            ),
        )
        if spec.sha256:
            actual = self._sha256(dest)
            if actual.lower() != spec.sha256.lower():
                dest.unlink()
                raise DependencyError(
                    f"{spec.name} sha256 mismatch: expected {spec.sha256}, got {actual}"
                )
        return dest

    def _install_pip(self, spec: DependencySpec) -> None:
        if spec.url is None:
            raise DependencyError(f"{spec.name} has no pip package name")
        self.progress(spec.name, 0.2, f"installing pip package {spec.url}")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", spec.url],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise DependencyError(f"pip install {spec.url} failed: {result.stderr[-500:]}")
        self.progress(spec.name, 1.0, f"pip package {spec.url} installed")

    @staticmethod
    def _find_bin(install_dir: Path, name: str) -> Path | None:
        direct = install_dir / name
        if direct.is_file():
            return direct
        nested = install_dir / "bin" / name
        if nested.is_file():
            return nested
        for candidate in install_dir.rglob(name):
            if candidate.is_file():
                return candidate
        return None

    def _reset_install_dir(self, path: Path) -> None:
        if path.exists():
            if not path.is_relative_to(self.runtime_dir):
                raise DependencyError(f"refusing to reset outside runtime: {path}")
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _extract_archive(archive: Path, dest: Path) -> None:
        if archive.suffix.lower() == ".zip":
            with zipfile.ZipFile(archive) as zf:
                for zip_member in zf.infolist():
                    if not _zip_member_is_safe(zip_member.filename):
                        raise DependencyError(f"unsafe zip member: {zip_member.filename}")
                zf.extractall(dest)
            return
        with tarfile.open(archive) as tf:
            for tar_member in tf.getmembers():
                if tar_member.name.startswith("/") or ".." in Path(tar_member.name).parts:
                    raise DependencyError(f"unsafe tar member: {tar_member.name}")
            tf.extractall(dest)

    def _write_version(self, install_dir: Path, version: str) -> None:
        if version:
            (install_dir / ".version").write_text(version, encoding="utf-8")

    @staticmethod
    def _read_version(install_dir: Path) -> str:
        version_file = install_dir / ".version"
        if version_file.exists():
            return version_file.read_text(encoding="utf-8").strip()
        return ""

    def _write_manifest(self) -> None:
        self._manifest_path.write_text(
            json.dumps(self.check_status(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _looks_portable(url: str) -> bool:
        path = url.split("?", 1)[0].lower()
        return path.endswith((".exe", ".bin", ".appimage", ".dmg"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage app-local built-in dependencies")
    parser.add_argument("--check", action="store_true", help="default: no install")
    parser.add_argument("--install", action="store_true", help="install missing pieces")
    parser.add_argument("--runtime-dir", default=None)
    parser.add_argument("--manifest", default=None, help="JSON manifest of dependencies")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        with tempfile.TemporaryDirectory() as tmp:
            manager = BuiltinDependencyManager(tmp)
            assert manager.check_status()["ready"] is True
        print("builtin dependency manager self-test OK")
        return 0
    runtime = Path(args.runtime_dir) if args.runtime_dir else default_runtime_dir()
    specs: list[Any] = []
    if args.manifest:
        data = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        specs = data if isinstance(data, list) else data.get("dependencies", [])
    manager = BuiltinDependencyManager(runtime, specs)
    result = manager.install(install=args.install)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
