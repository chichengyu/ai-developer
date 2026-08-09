"""Runtime tests for the manifest-driven dependency center."""

from __future__ import annotations

import hashlib
import http.server
import io
import json
import sys
import tempfile
import threading
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from builtin_dependency_manager import (  # noqa: E402
    BuiltinDependencyManager,
    DependencyError,
    spec_from_dict,
)
from dependency_center import DependencyCenter  # noqa: E402


def test_homepage_urls_are_manifest_driven() -> None:
    code = (ROOT / "scripts" / "dependency_center.py").read_text(encoding="utf-8")
    assert "https://" not in code, "dependency_center.py must not hard-code URLs"


class _Handler(http.server.BaseHTTPRequestHandler):
    payload = b""

    def do_HEAD(self) -> None:
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.payload)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.payload)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, *args: object) -> None:
        return


def test_dependency_center_lists_and_installs() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bin/tool.bin", b"tool")
    payload = buffer.getvalue()
    digest = hashlib.sha256(payload).hexdigest()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    _Handler.payload = payload
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            base = f"http://127.0.0.1:{server.server_port}"
            manifest = Path(tmp) / "dependencies.json"
            manifest.write_text(
                json.dumps(
                    {
                        "app_name": "DependencyCenterTest",
                        "help": "依赖中心会自动下载安装；也可手动下载后安装。",
                        "dependencies": [
                            {
                                "name": "tool",
                                "kind": "archive",
                                "url": f"{base}/tool.zip",
                                "sha256": digest,
                                "bin_names": ["tool.bin"],
                                "description": "测试用工具。",
                                "homepage": "https://example.invalid/tool",
                                "manual_install": "自动安装或手动解压到 runtime。",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            center = DependencyCenter(manifest, runtime_dir=Path(tmp) / "runtime")
            before = center.check_status()
            assert before["items"][0]["installed"] is False
            assert before["help"] == "依赖中心会自动下载安装；也可手动下载后安装。"
            assert before["items"][0]["homepage"] == "https://example.invalid/tool"
            assert before["items"][0]["manual_install"] == "自动安装或手动解压到 runtime。"
            assert "官网：https://example.invalid/tool" in center.help_text()
            assert "手动安装：自动安装或手动解压到 runtime。" in center.help_text()

            result = center.install_all()
            assert result["ready"] is True
            assert result["items"][0]["homepage"] == "https://example.invalid/tool"
            assert result["items"][0]["manual_install"] == "自动安装或手动解压到 runtime。"
            rows = center.menu_rows()
            assert rows[0][0] == "tool"
            assert rows[0][2] == "已安装"
            assert Path(rows[0][3]).is_file()
    finally:
        server.shutdown()


def test_frozen_pip_install_is_blocked() -> None:
    original = getattr(sys, "frozen", None)
    try:
        sys.frozen = True
        with tempfile.TemporaryDirectory() as tmp:
            manager = BuiltinDependencyManager(Path(tmp) / "runtime")
            spec = spec_from_dict({"name": "missing", "kind": "pip", "url": "missing"})
            try:
                manager._install_pip(spec)
            except DependencyError as exc:
                assert "not bundled in this EXE" in str(exc)
            else:
                raise AssertionError("frozen pip install should be blocked")
    finally:
        if original is None:
            del sys.frozen
        else:
            sys.frozen = original


def main() -> int:
    tests = [
        test_homepage_urls_are_manifest_driven,
        test_dependency_center_lists_and_installs,
        test_frozen_pip_install_is_blocked,
    ]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"  [OK] {test.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  [FAIL] {test.__name__}: {exc}")
    print(f"Dependency center: {len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
