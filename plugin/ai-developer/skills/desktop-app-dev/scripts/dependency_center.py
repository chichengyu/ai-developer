"""Manifest-driven in-app dependency center.

After development, every runtime dependency is recorded in a
`dependencies.json` manifest. The app lists one row per dependency in its
dependency center menu; the user clicks `install` and the center downloads,
verifies, extracts/configures, and refreshes status automatically.
The manifest also carries `help`, `description`, `homepage` (official
website), and `manual_install` text so the UI can explain each dependency,
open its official page, and tell users how to install it manually if they
prefer. Homepage URLs are read from the manifest only; never hard-code a
dependency's URL in application code because every project has different
dependencies.

Large or slow downloads use the chunked resumable downloader from
`scripts/media_downloader.py` through `BuiltinDependencyManager`.

Usage:
    python dependency_center.py --manifest dependencies.json --check
    python dependency_center.py --manifest dependencies.json --install
    python dependency_center.py --manifest dependencies.json --list
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from builtin_dependency_manager import (
    BuiltinDependencyManager,
    DependencySpec,
    spec_from_dict,
)

ProgressFn = Callable[[str, float | None, str], None]


class DependencyCenter:
    """Load a dependency manifest and expose menu rows plus one-click install."""

    def __init__(
        self,
        manifest_path: str | Path,
        runtime_dir: str | Path | None = None,
        progress: ProgressFn | None = None,
    ) -> None:
        self.manifest_path = Path(manifest_path)
        self.progress = progress or (lambda stage, percent, message: None)
        self._data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.app_name = str(self._data.get("app_name", "DesktopApp"))
        self.help = str(self._data.get("help", ""))
        self.runtime_dir = Path(runtime_dir) if runtime_dir else self._default_runtime_dir()
        raw_specs: list[Any] = self._data.get(
            "dependencies", self._data if isinstance(self._data, list) else []
        )
        self._info = {
            str(item.get("name", "")): item for item in raw_specs if isinstance(item, dict)
        }
        self.specs = [
            self._normalize(spec_from_dict(item)) for item in raw_specs if isinstance(item, dict)
        ]
        self._manager = BuiltinDependencyManager(
            self.runtime_dir,
            self.specs,
            progress=self.progress,
        )

    def _default_runtime_dir(self) -> Path:
        local = Path(os.environ.get("LOCALAPPDATA") or Path.home())
        return local / self.app_name / "runtime"

    def _normalize(self, spec: DependencySpec) -> DependencySpec:
        if spec.pip_target:
            target = Path(spec.pip_target)
            if not target.is_absolute():
                target = self.runtime_dir / target
            spec = DependencySpec(
                name=spec.name,
                kind=spec.kind,
                url=spec.url,
                version=spec.version,
                sha256=spec.sha256,
                bin_names=spec.bin_names,
                env_vars=spec.env_vars,
                extract_subdir=spec.extract_subdir,
                download_name=spec.download_name,
                note=spec.note,
                pip_target=str(target),
                module_name=spec.module_name,
            )
        return spec

    def check_status(self) -> dict[str, Any]:
        return self._enrich(self._manager.check_status())

    def _enrich(self, status: dict[str, Any]) -> dict[str, Any]:
        status["help"] = self.help
        for item in status["items"]:
            info = self._info.get(item["name"], {})
            item["description"] = str(info.get("description", ""))
            item["homepage"] = str(info.get("homepage", ""))
            item["manual_install"] = str(info.get("manual_install", ""))
        status["app_name"] = self.app_name
        return status

    def help_text(self) -> str:
        """Return overall help plus per-dependency manual install steps."""
        lines: list[str] = []
        if self.help:
            lines.append(self.help)
        for name, info in self._info.items():
            description = str(info.get("description", ""))
            manual = str(info.get("manual_install", ""))
            if description:
                lines.append(f"{name}：{description}")
            homepage = str(info.get("homepage", ""))
            if homepage:
                lines.append(f"官网：{homepage}")
            if manual:
                lines.append(f"手动安装：{manual}")
        return "\n\n".join(lines)

    def install_all(self) -> dict[str, Any]:
        return self._enrich(self._manager.install(install=True))

    def menu_rows(self) -> list[list[str]]:
        return [
            [
                item["name"],
                item.get("version") or "",
                "已安装" if item["installed"] else "未安装",
                "; ".join(item.get("paths") or []),
            ]
            for item in self.check_status()["items"]
        ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dependency center CLI")
    parser.add_argument("--manifest", required=True, help="dependencies.json path")
    parser.add_argument("--runtime-dir", default=None)
    parser.add_argument("--check", action="store_true", help="show status only")
    parser.add_argument("--install", action="store_true", help="install missing deps")
    parser.add_argument("--list", action="store_true", help="print dependency menu rows")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "dependencies.json"
            manifest.write_text(
                json.dumps({"app_name": "SelfTest", "dependencies": []}), encoding="utf-8"
            )
            center = DependencyCenter(manifest)
            status = center.check_status()
            assert status["ready"] is True
            assert center.menu_rows() == []
        print("dependency center self-test OK")
        return 0

    center = DependencyCenter(
        args.manifest,
        runtime_dir=args.runtime_dir,
        progress=lambda stage, percent, message: print(f"[{stage}] {percent or 0:.0%} {message}"),
    )
    if args.check or (not args.install and not args.list):
        print(json.dumps(center.check_status(), ensure_ascii=False, indent=2))
        return 0
    if args.list:
        print(json.dumps(center.menu_rows(), ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(center.install_all(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
