#!/usr/bin/env python3
"""Structural doc audit for the skill.

Checks the SKILL.md frontmatter, duplicate-section regression, relative
Markdown references, and the canonical file counts advertised in docs.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAILURES: list[str] = []
CHECKS = 0


def check(condition: bool, message: str) -> None:
    global CHECKS
    CHECKS += 1
    if not condition:
        FAILURES.append(message)


def main() -> int:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8").splitlines()
    check(skill[0] == "---", "SKILL.md must start with YAML frontmatter")
    check(
        skill[2].startswith('description: "') and skill[2].endswith('"'),
        "SKILL.md description must be a quoted single-line YAML scalar",
    )
    check(
        sum(1 for line in skill if line.startswith("## Tests (fixtures + smoke tests + CI)")) == 1,
        "SKILL.md must contain exactly one Tests heading",
    )
    check(
        sum(1 for line in skill if line == "## 界面硬性要求（UI hard requirements）") == 1,
        "SKILL.md must contain exactly one 界面硬性要求 heading",
    )
    ui_ids = [f"UI-{i:02d}" for i in range(1, 19)]
    skill_text = "\n".join(skill)
    for uid in ui_ids:
        check(f"| {uid} |" in skill_text, f"SKILL.md missing {uid} table row")
    code_ids = [f"CODE-{i:02d}" for i in range(1, 6)]
    check(
        sum(
            1 for line in skill if line == "## 代码开发硬性要求（minimal-change hard requirements）"
        )
        == 1,
        "SKILL.md must contain exactly one 代码开发硬性要求 heading",
    )
    check(
        "CODE-01..CODE-05" in skill_text
        and "references/minimal_change_requirements.md" in skill_text,
        "SKILL.md missing CODE-01..CODE-05 minimal-change rules",
    )
    check(
        "MUST open `references/ui_hard_requirements.md`" in skill_text,
        "SKILL.md missing mandatory open for ui_hard_requirements.md",
    )
    check(
        "MUST open `references/minimal_change_requirements.md`" in skill_text,
        "SKILL.md missing mandatory open for minimal_change_requirements.md",
    )
    check(
        "CODE-01..CODE-05 item or waiver" in skill_text,
        "SKILL.md Step 0 must record CODE-01..CODE-05 item or waiver",
    )

    for md in ROOT.rglob("*.md"):
        text = md.read_text(encoding="utf-8")
        for match in re.finditer(r"`([^`]+)`", text):
            ref = match.group(1).strip()
            if not ref.startswith(
                ("scripts/", "templates/", "examples/", "references/", "tests/", ".github/")
            ):
                continue
            if any(ch in ref for ch in "*<>[]{}|...") or "<lang>" in ref:
                continue
            if not (ROOT / ref).exists():
                check(False, f"missing relative reference: {ref} in {md.relative_to(ROOT)}")

    for md in ROOT.rglob("*.md"):
        headings = [
            line.strip()
            for line in md.read_text(encoding="utf-8").splitlines()
            if line.startswith("## ")
        ]
        duplicates = sorted({h for h in headings if headings.count(h) > 1})
        check(not duplicates, f"{md.relative_to(ROOT)} has duplicate ## headings: {duplicates}")

    ui_ref = ROOT / "references" / "ui_hard_requirements.md"
    check(ui_ref.exists(), "missing references/ui_hard_requirements.md")
    if ui_ref.exists():
        ui_text = ui_ref.read_text(encoding="utf-8")
        required_ui_terms = [
            "UI-01",
            "UI-17",
            "UI-18",
            "Codex",
            "主题库",
            "自动刷新",
            "分页",
            "持久化",
            "日志",
            "滚动条",
            "对比",
            "语义",
            "桌面端",
            "Web 化",
        ]
        for term in required_ui_terms:
            check(term in ui_text, f"ui_hard_requirements.md missing required term: {term}")
        for uid in ui_ids:
            check(f"## {uid} " in ui_text, f"ui_hard_requirements.md missing {uid} heading")
        for url in [
            "https://fluent2.microsoft.design/",
            "https://github.com/dracula/dracula-theme",
            "https://m3.material.io/theme-builder",
        ]:
            check(url in ui_text, f"ui_hard_requirements.md missing theme URL: {url}")
    code_ref = ROOT / "references" / "minimal_change_requirements.md"
    check(code_ref.exists(), "missing references/minimal_change_requirements.md")
    if code_ref.exists():
        code_text = code_ref.read_text(encoding="utf-8")
        for cid in code_ids:
            check(
                f"## {cid} " in code_text,
                f"minimal_change_requirements.md missing {cid} heading",
            )
        for term in ["SKILL.md", "requirements.md", "回归验证", "diff 保持最小"]:
            check(
                term in code_text,
                f"minimal_change_requirements.md missing required term: {term}",
            )

    req_template = (ROOT / "templates" / "requirements_checklist.md").read_text(encoding="utf-8")
    for uid in ui_ids:
        check(f"| {uid} |" in req_template, f"requirements_checklist.md missing {uid} row")
    release_text = (ROOT / "templates" / "release_checklist.md").read_text(encoding="utf-8")
    check("UI-01..UI-18" in release_text, "release_checklist.md missing UI-01..UI-18 release gate")
    check(
        "single distributable artifact" in release_text and "Idle memory" in release_text,
        "release_checklist.md missing single-file / idle-memory release gates",
    )
    readme_text = (ROOT / "README.md").read_text(encoding="utf-8")
    index_text = (ROOT / "INDEX.md").read_text(encoding="utf-8")
    check(
        "references/ui_hard_requirements.md" in readme_text,
        "README.md missing ui_hard_requirements.md link",
    )
    check(
        "references/ui_hard_requirements.md" in index_text,
        "INDEX.md missing ui_hard_requirements.md link",
    )
    check(
        "CODE-01..CODE-05" in req_template
        and all(f"| {cid} |" in req_template for cid in code_ids),
        "requirements_checklist.md missing CODE-01..CODE-05 rows",
    )
    check(
        "CODE-01..CODE-05" in release_text,
        "release_checklist.md missing CODE-01..CODE-05 release gate",
    )
    check(
        "CODE-01..CODE-05" in readme_text,
        "README.md missing CODE-01..CODE-05 minimal-change rules",
    )
    check(
        "CODE-01..CODE-05" in index_text,
        "INDEX.md missing CODE-01..CODE-05 minimal-change rules",
    )
    check("SendInput(2" not in skill_text, "SKILL.md still documents batched SendInput(2)")
    check("mobile-app-dev-ios" not in skill_text, "SKILL.md references removed mobile skill name")
    check(
        "backup_source.ps1" in skill_text and "-BackupSource" in skill_text,
        "SKILL.md missing source preservation docs",
    )
    check(
        "backup_source.ps1" in readme_text and "-BackupSource" in readme_text,
        "README.md missing source preservation docs",
    )
    check(
        "clients/bootstrap_environment.ps1" not in readme_text,
        "README.md misplaces bootstrap_environment.ps1 under clients/",
    )
    check(
        "bootstrap_environment.ps1" in readme_text and "toolchain_map.json" in readme_text,
        "README.md layout missing scripts/toolchain files",
    )
    check(
        "backup_source.ps1" in index_text and "-BackupSource" in index_text,
        "INDEX.md missing source preservation docs",
    )
    check("find_python.ps1" in readme_text, "README.md layout missing find_python.ps1")
    check(
        re.search(r"\(\d+\s*/\s*\d+ currently pass", skill_text) is not None,
        "SKILL.md missing Windows smoke count",
    )
    skill_size = (ROOT / "SKILL.md").stat().st_size
    check(
        skill_size <= 25 * 1024,
        f"SKILL.md grew to {skill_size} bytes; keep it context-light",
    )
    check("usesystem CMake" not in index_text, "INDEX.md has usesystem CMake typo")

    reference_files = sorted(p.name for p in (ROOT / "references").glob("*.md"))
    check(len(reference_files) == 14, f"references count = {len(reference_files)}, expected 14")
    for ref_name in reference_files:
        check(
            f"references/{ref_name}" in skill_text,
            f"SKILL.md missing reference link {ref_name}",
        )
        check(ref_name in readme_text, f"README.md missing reference {ref_name}")
    for framework_row in (
        "Rust + Slint",
        "Rust + egui",
        "Flutter Desktop",
        "JavaFX",
        "TornadoFX",
        "walk (Go, Win32)",
    ):
        check(framework_row in index_text, f"INDEX.md missing {framework_row} row")

    for text_file in ROOT.rglob("*"):
        if not text_file.is_file():
            continue
        rel = text_file.relative_to(ROOT)
        if any(
            part
            in {
                ".git",
                ".mypy_cache",
                ".pytest_cache",
                ".ruff_cache",
                ".venv",
                "build",
                "dist",
                "node_modules",
                "target",
                "__pycache__",
            }
            for part in rel.parts
        ):
            continue
        raw = text_file.read_bytes()
        if b"\x00" in raw:
            continue
        if text_file.suffix.lower() in (".ps1", ".bat", ".cmd"):
            stripped = raw.replace(b"\r\n", b"")
            check(
                b"\n" not in stripped,
                f"{rel} uses LF/mixed endings (PowerShell files should be CRLF)",
            )
        else:
            check(b"\r\n" not in raw, f"{rel} uses CRLF (text files should be LF)")

    win32_text = (ROOT / "references" / "win32_recipes.md").read_text(encoding="utf-8")
    for recipe_id in range(1, 14):
        check(
            win32_text.count(f"## R{recipe_id}:") == 1,
            f"win32_recipes.md R{recipe_id} heading count != 1",
        )
    matrix_text = (ROOT / "references" / "framework_matrix.md").read_text(encoding="utf-8")
    check(
        "## Python / GTK (PyGObject)" in matrix_text,
        "framework_matrix.md missing Python GTK section",
    )
    dist_text = (ROOT / "references" / "distribution_playbook.md").read_text(encoding="utf-8")
    for term in [
        "Single-file, zero-runtime, small footprint",
        "NativeAOT",
        "PyInstaller",
        "CARGO_PROFILE_RELEASE_OPT_LEVEL",
        "compression",
        "Idle memory",
        "no runtime",
        "-c.compression=maximum",
        "--no-translations",
    ]:
        check(
            term in dist_text,
            f"distribution_playbook.md missing required term: {term}",
        )
    check(
        "tiny single-file portable EXE" in readme_text,
        "README.md missing tiny single-file packaging recipe",
    )
    check(
        "tiny single-file EXE" in index_text,
        "INDEX.md missing tiny single-file packaging section",
    )

    media_ref = ROOT / "references" / "media_acquisition_playbook.md"
    check(media_ref.exists(), "missing references/media_acquisition_playbook.md")
    if media_ref.exists():
        media_text = media_ref.read_text(encoding="utf-8")
        for term in [
            "SQLite",
            "HLS",
            "分片",
            "断点续传",
            "持久化",
            "CAPTCHA",
            "ffmpeg",
            "publish",
        ]:
            check(
                term in media_text,
                f"media_acquisition_playbook.md missing required term: {term}",
            )
    for script_name in [
        "media_session.py",
        "media_parser.py",
        "page_data_parser.py",
        "scrape_guard.py",
        "media_downloader.py",
        "hls_downloader.py",
        "captcha_solver.py",
        "browser_session.py",
        "task_queue.py",
        "ffmpeg_transcoder.py",
        "platform_publisher.py",
        "media_dependencies.py",
        "media_pipeline_service.py",
        "setup_media_dependencies.ps1",
        "api_client.py",
        "data_processor.py",
        "web_data_pipeline.py",
        "api_analyzer.py",
        "proxy_pool.py",
        "account_manager.py",
        "task_scheduler.py",
        "notifier.py",
        "security_detector.py",
        "cloudflare_challenge.py",
        "deep_crawler.py",
    ]:
        check(
            (ROOT / "scripts" / script_name).exists(),
            f"missing scripts/{script_name}",
        )
    web_data_ref = ROOT / "references" / "web_data_pipeline_playbook.md"
    check(web_data_ref.exists(), "missing references/web_data_pipeline_playbook.md")
    if web_data_ref.exists():
        web_data_text = web_data_ref.read_text(encoding="utf-8")
        for term in [
            "CAPTCHA",
            "fingerprint",
            "api_client.py",
            "data_processor.py",
            "web_data_pipeline.py",
            "aggregate",
            "Compliance",
            "manifest",
            "join",
            "progress",
            "proxy_pool.py",
            "account_manager.py",
            "task_scheduler.py",
            "notifier.py",
            "security_detector.py",
            "cloudflare_challenge.py",
            "deep_crawler.py",
            "Cloudflare",
            "cf_clearance",
            "turnstile",
            "sitemap",
            "auto_handle",
            "skip_blocked",
        ]:
            check(
                term in web_data_text,
                f"web_data_pipeline_playbook.md missing required term: {term}",
            )
    for doc_name, doc_text in (
        ("SKILL.md", skill_text),
        ("README.md", readme_text),
        ("INDEX.md", index_text),
    ):
        for script_name in (
            "api_client.py",
            "data_processor.py",
            "web_data_pipeline.py",
            "proxy_pool.py",
            "account_manager.py",
            "task_scheduler.py",
            "notifier.py",
            "security_detector.py",
            "cloudflare_challenge.py",
            "deep_crawler.py",
        ):
            check(
                script_name in doc_text,
                f"{doc_name} missing {script_name} reference",
            )
        check(
            "threading_playbook.md" in doc_text,
            f"{doc_name} missing threading_playbook.md reference",
        )
    threading_ref = ROOT / "references" / "threading_playbook.md"
    check(threading_ref.exists(), "missing references/threading_playbook.md")
    if threading_ref.exists():
        threading_text = threading_ref.read_text(encoding="utf-8")
        for term in [
            "UI thread affinity",
            "cooperative cancellation",
            "worker pool",
            "Graceful shutdown",
            "Anti-patterns",
            "threading_",
            "Dispatcher",
            "idle_add",
            "RunSafe",
            "ReceivePort",
        ]:
            check(
                term in threading_text,
                f"threading_playbook.md missing required term: {term}",
            )
    clients_ref = ROOT / "references" / "media_pipeline_clients.md"
    check(clients_ref.exists(), "missing references/media_pipeline_clients.md")
    if clients_ref.exists():
        clients_text = clients_ref.read_text(encoding="utf-8")
        for language in [
            "C#",
            "TypeScript",
            "Go",
            "Rust",
            "Kotlin",
            "Swift",
            "Java",
            "C++",
            "127.0.0.1",
        ]:
            check(
                language in clients_text,
                f"media_pipeline_clients.md missing {language} section",
            )
    for client_name in [
        "media_client.ts",
        "MediaClient.cs",
        "media_client.go",
        "media_client.rs",
        "MediaClient.kt",
        "MediaClient.swift",
        "MediaClient.java",
        "media_client.cpp",
        "README.md",
    ]:
        check(
            (ROOT / "clients" / client_name).exists(),
            f"missing clients/{client_name}",
        )
    for client_name in [
        "media_client.ts",
        "MediaClient.cs",
        "media_client.go",
        "media_client.rs",
        "MediaClient.kt",
        "MediaClient.swift",
        "MediaClient.java",
        "media_client.cpp",
    ]:
        client_text = (ROOT / "clients" / client_name).read_text(encoding="utf-8")
        for endpoint in ("tasks", "deps/status", "deps/progress", "deps/install"):
            check(
                endpoint in client_text,
                f"clients/{client_name} missing {endpoint}",
            )

    examples = [p for p in (ROOT / "examples").iterdir() if p.is_dir()]
    build_ps1 = list((ROOT / "scripts").glob("build_*.ps1"))
    threading = list((ROOT / "scripts").glob("threading_*"))
    sendinput = list((ROOT / "scripts").glob("sendinput_*"))
    window_enum = list((ROOT / "scripts").glob("window_enum*"))
    check(len(examples) == 8, f"examples count = {len(examples)}, expected 8")
    check(len(build_ps1) == 14, f"build_*.ps1 count = {len(build_ps1)}, expected 14")
    check(len(threading) == 30, f"threading_* count = {len(threading)}, expected 30")
    check(len(sendinput) == 11, f"sendinput_* count = {len(sendinput)}, expected 11")
    check(len(window_enum) == 11, f"window_enum* count = {len(window_enum)}, expected 11")
    for py_script in sorted((ROOT / "scripts").glob("*.py")):
        check(
            "__main__" in py_script.read_text(encoding="utf-8"),
            f"{py_script.name} missing __main__ block",
        )
    find_python_text = (ROOT / "scripts" / "find_python.ps1").read_text(encoding="utf-8")
    check("$env:PYTHON" in find_python_text, "find_python.ps1 missing PYTHON env support")
    check(
        "Join-Path $HOME" in find_python_text,
        "find_python.ps1 still hardcodes a user-specific Codex path",
    )
    shared_python_scripts = {
        "build_python.ps1": ROOT / "scripts" / "build_python.ps1",
        "bootstrap_environment.ps1": ROOT / "scripts" / "bootstrap_environment.ps1",
        "setup_media_dependencies.ps1": ROOT / "scripts" / "setup_media_dependencies.ps1",
        "run_lint.ps1": ROOT / "tests" / "run_lint.ps1",
        "smoke_windows.ps1": ROOT / "tests" / "smoke_windows.ps1",
    }
    for script_name, script_path in shared_python_scripts.items():
        check(
            "find_python.ps1" in script_path.read_text(encoding="utf-8"),
            f"{script_name} missing shared find_python.ps1 resolver",
        )
    check("24 canonical" in skill_text, "SKILL.md does not advertise 24 canonical frameworks")
    check(
        "C# / WinForms (.NET 8+)" in skill_text and "Python / GTK (PyGObject)" in skill_text,
        "SKILL.md canonical framework list missing WinForms or GTK",
    )

    selector_text = (ROOT / "scripts" / "select_framework.py").read_text(encoding="utf-8")
    selector_tree = ast.parse(selector_text)
    framework_keys: list[str] = []
    framework_dict_node = None
    for node in ast.walk(selector_tree):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "FRAMEWORKS"
            and isinstance(node.value, ast.Dict)
        ):
            framework_keys = [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
            framework_dict_node = node.value
    check(
        len(framework_keys) == 24, f"selector FRAMEWORKS count = {len(framework_keys)}, expected 24"
    )
    check("walk" in framework_keys, "selector missing walk framework")
    check(
        'w["macos_x64_arch"]' in selector_text and 'w["linux_x64_arch"]' in selector_text,
        "selector derive_weights must map macOS/Linux x64 architecture weights",
    )

    dim_nodes = [
        node.value.elts
        for node in ast.walk(selector_tree)
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "DIMS"
        and isinstance(node.value, ast.Tuple)
    ]
    dims = [elt.value for elt in dim_nodes[0] if isinstance(elt, ast.Constant)] if dim_nodes else []
    check(len(dims) == 29, f"selector DIMS count = {len(dims)}, expected 29")
    check(
        "macos_x64_arch" in dims and "linux_x64_arch" in dims,
        "selector DIMS missing macOS/Linux x64 architecture dimensions",
    )
    if framework_dict_node is not None and dims:
        dim_set = set(dims)

        def scalar(node: ast.expr) -> object:
            if isinstance(node, ast.Constant):
                return node.value
            if (
                isinstance(node, ast.UnaryOp)
                and isinstance(node.op, ast.USub)
                and isinstance(node.operand, ast.Constant)
            ):
                return -node.operand.value
            return None

        for key_node, value_node in zip(
            framework_dict_node.keys, framework_dict_node.values, strict=False
        ):
            if not isinstance(key_node, ast.Constant) or not isinstance(value_node, ast.Dict):
                continue
            value_keys = {k.value for k in value_node.keys if isinstance(k, ast.Constant)}
            check(
                value_keys == dim_set,
                f"selector {key_node.value} dimension set mismatch",
            )
            scores = [
                s for s in (scalar(v) for v in value_node.values) if isinstance(s, int | float)
            ]
            check(
                len(scores) == len(dims),
                f"selector {key_node.value} has {len(scores)} scores, expected {len(dims)}",
            )
            check(
                all(isinstance(s, int | float) and -1.0 <= s <= 1.0 for s in scores),
                f"selector {key_node.value} has out-of-range score",
            )
    for table_name in ("FRAMEWORK_LANGUAGES", "DISPLAY_NAMES", "RATIONALES"):
        table_keys: list[str] = []
        for node in ast.walk(selector_tree):
            if isinstance(node, ast.Assign | ast.AnnAssign):
                target = node.targets[0] if isinstance(node, ast.Assign) else node.target
                if (
                    isinstance(target, ast.Name)
                    and target.id == table_name
                    and isinstance(node.value, ast.Dict)
                ):
                    table_keys = [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
        check(
            set(table_keys) == set(framework_keys),
            f"selector {table_name} keys mismatch",
        )
    toolchain_map = json.loads(
        (ROOT / "scripts" / "toolchain_map.json").read_text(encoding="utf-8")
    )
    missing_toolchain = sorted(set(framework_keys) - set(toolchain_map["framework_toolchains"]))
    check(
        not missing_toolchain,
        f"toolchain_map.json missing frameworks: {missing_toolchain}",
    )

    matrix_text = (ROOT / "references" / "framework_matrix.md").read_text(encoding="utf-8")
    matrix_headings = [
        line[3:].strip()
        for line in matrix_text.splitlines()
        if line.startswith("## ")
        and "Quick verdict" not in line
        and "Quick decision tree" not in line
        and "Threading bridge quick reference" not in line
        and "Resource embedding quick reference" not in line
    ]
    check(
        len(matrix_headings) == 24,
        f"framework_matrix headings = {len(matrix_headings)}, expected 24",
    )
    check(
        any("WinForms" in heading for heading in matrix_headings),
        "framework_matrix.md missing WinForms section",
    )
    quick_section = matrix_text.split("## Quick verdict", 1)[1]
    quick_bullets = [line.strip() for line in quick_section.splitlines() if line.startswith("- **")]
    check(
        len(quick_bullets) == len(set(quick_bullets)),
        "framework_matrix.md quick verdict has duplicate bullets",
    )

    gui_tree_text = (ROOT / "templates" / "gui_framework_decision_tree.md").read_text(
        encoding="utf-8"
    )
    check(
        "CommunityToolkit.Mvvm" in gui_tree_text and "Wpfdataload" not in gui_tree_text,
        "gui_framework_decision_tree.md has stale CommunityToolkit typo",
    )
    check(
        "Avalonia for a Windows-only app" in gui_tree_text,
        "gui_framework_decision_tree.md Avalonia anti-pattern text is stale",
    )

    build_dotnet_text = (ROOT / "scripts" / "build_dotnet.ps1").read_text(encoding="utf-8")
    build_linux_text = (ROOT / "scripts" / "build_linux.ps1").read_text(encoding="utf-8")
    build_electron_text = (ROOT / "scripts" / "build_electron.ps1").read_text(encoding="utf-8")
    build_fyne_text = (ROOT / "scripts" / "build_go_fyne.ps1").read_text(encoding="utf-8")
    for build_script in build_ps1:
        build_text = build_script.read_text(encoding="utf-8")
        check(
            "[switch] $BackupSource" in build_text and "backup_source.ps1" in build_text,
            f"{build_script.name} missing -BackupSource wiring",
        )
    check("OutputDir" in build_dotnet_text, "build_dotnet.ps1 missing -OutputDir")
    qt_build_text = (ROOT / "scripts" / "build_qt.ps1").read_text(encoding="utf-8")
    check(
        "Refusing to remove" in qt_build_text,
        "build_qt.ps1 must refuse staging removal that overlaps project source",
    )
    check("-H windowsgui" not in build_linux_text, "build_linux.ps1 still uses -H windowsgui")
    check(
        "$py3.Source -m PyInstaller" in build_linux_text,
        "build_linux.ps1 must invoke PyInstaller via resolved python3 module",
    )
    check(
        '[ValidateSet("win", "nsis", "msi", "portable", "all")]' in build_electron_text,
        "build_electron.ps1 missing -Target ValidateSet",
    )
    check("env:AppId" not in build_fyne_text, "build_go_fyne.ps1 EXE-name derivation is broken")
    check(
        "$tfm/$Rid/publish" in build_dotnet_text,
        "build_dotnet.ps1 still hardcodes net8.0 publish fallback",
    )
    check(
        "TargetFrameworks" in build_dotnet_text and "TargetFramework" in build_dotnet_text,
        "build_dotnet.ps1 missing TFM extraction",
    )

    install_guards = {
        "build_python.ps1": ["pip install pyinstaller"],
        "build_tauri.ps1": ["cargo install tauri-cli", "rustup target add"],
        "build_electron.ps1": ["npm ci", "npm install --save-dev electron-builder"],
        "build_linux.ps1": [
            "cargo install tauri-cli",
            "rustup target add",
            "pip install pyinstaller",
        ],
        "build_macos.ps1": ["cargo install tauri-cli", "rustup target add"],
        "build_go_fyne.ps1": ["go install fyne.io"],
        "build_go_wails.ps1": ["go install github.com/wailsapp"],
    }
    for script_name, commands in install_guards.items():
        script_text = (ROOT / "scripts" / script_name).read_text(encoding="utf-8")
        check(
            "$Install" in script_text and "-not $Install" in script_text,
            f"{script_name} missing -Install guard",
        )
        for command in commands:
            check(command in script_text, f"{script_name} missing {command}")

    wails_text = (ROOT / "scripts" / "build_go_wails.ps1").read_text(encoding="utf-8")
    check(
        "build/bin/myapp.exe" not in wails_text,
        "build_go_wails.ps1 still hardcodes myapp EXE path",
    )
    check(
        "Where-Object { $_.Name -notmatch 'installer' }" in wails_text,
        "build_go_wails.ps1 missing dynamic EXE discovery",
    )
    squirrel_text = (ROOT / "scripts" / "auto_update_squirrel.ps1").read_text(encoding="utf-8")
    check(
        "Copy-Item -LiteralPath $MainExe" in squirrel_text,
        "auto_update_squirrel.ps1 must copy, not move, the main EXE",
    )
    check(
        "Move-Item -Path $MainExe" not in squirrel_text,
        "auto_update_squirrel.ps1 still moves the main EXE",
    )
    sparkle_text = (ROOT / "scripts" / "auto_update_winsparkle.cpp").read_text(encoding="utf-8")
    check(
        "to_narrow(appName).c_str()" in sparkle_text
        and "to_narrow(appVersion).c_str()" in sparkle_text,
        "auto_update_winsparkle.cpp must pass narrow UTF-8 strings to WinSparkle",
    )
    check(
        "set_app_name(appName.c_str())" not in sparkle_text,
        "auto_update_winsparkle.cpp passes wide strings to narrow API",
    )
    appimage_text = (ROOT / "scripts" / "build_appimage.sh").read_text(encoding="utf-8")
    deb_text = (ROOT / "scripts" / "build_deb.sh").read_text(encoding="utf-8")
    check(
        "--download" in appimage_text and '[[ "$DOWNLOAD_LINUXDEPLOY" -ne 1 ]]' in appimage_text,
        "build_appimage.sh must make linuxdeploy download opt-in",
    )
    check(
        "LINUXDEPLOY_ARCH" in appimage_text and "APPIMAGE_ARCH" in appimage_text,
        "build_appimage.sh missing per-arch linuxdeploy/AppImage support",
    )
    check(
        "mv -f *.AppImage" not in appimage_text,
        "build_appimage.sh fallback may move the linuxdeploy helper",
    )
    check(
        "DEB_ARCH" in deb_text and "Architecture: ${DEB_ARCH}" in deb_text,
        "build_deb.sh missing arch parameter",
    )

    smoke_linux_text = (ROOT / "tests" / "smoke_linux.sh").read_text(encoding="utf-8")
    smoke_macos_text = (ROOT / "tests" / "smoke_macos.sh").read_text(encoding="utf-8")
    smoke_windows_text = (ROOT / "tests" / "smoke_windows.ps1").read_text(encoding="utf-8")
    ci_text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    check(
        "test_docs.py" in smoke_linux_text and "test_media_pipeline.py" in smoke_linux_text,
        "smoke_linux.sh missing Python structural/media tests",
    )
    check(
        "test_docs.py" in smoke_macos_text and "test_media_pipeline.py" in smoke_macos_text,
        "smoke_macos.sh missing Python structural/media tests",
    )
    check(
        'Get-ChildItem $root -Recurse -Filter "*.ps1"' in smoke_windows_text,
        "smoke_windows.ps1 missing all-.ps1 parse coverage",
    )
    check(
        "all .ps1 parse" in smoke_linux_text and "all .ps1 parse" in smoke_macos_text,
        "Linux/macOS smoke tests missing all-.ps1 parse coverage",
    )
    check(
        "ruff format --check scripts/ tests/ examples/" in ci_text,
        "ci.yml missing expanded ruff format check",
    )
    check(
        "test_no_bom.py" in smoke_windows_text
        and "test_no_bom.py" in smoke_linux_text
        and "test_no_bom.py" in smoke_macos_text,
        "smoke tests missing test_no_bom.py invocation",
    )
    check(
        'Get-ChildItem "$root\\examples" -Recurse -Filter "*.py"' in smoke_windows_text,
        "smoke_windows.ps1 missing examples Python AST coverage",
    )
    check(
        '"$SKILL_ROOT/examples"' in smoke_linux_text
        and '"$SKILL_ROOT/examples"' in smoke_macos_text,
        "Linux/macOS smoke tests missing examples Python AST coverage",
    )
    tests_readme_text = (ROOT / "tests" / "README.md").read_text(encoding="utf-8")
    check(
        "ubuntu-22.04" in readme_text
        and "ubuntu-22.04" in tests_readme_text
        and "ubuntu-22.04" in skill_text
        and "ubuntu-22.04" in ci_text,
        "CI docs/workflow must agree on ubuntu-22.04",
    )
    check("ubuntu-22.04" in index_text, "INDEX.md stale CI runner")
    check("ruff format --check" in readme_text, "README.md CI table must show format check")
    readme_count = re.search(r"Passed:\s*(\d+)", tests_readme_text)
    skill_count = re.search(r"\((\d+)\s*/\s*\d+ currently pass", skill_text)
    check(
        readme_count is not None
        and skill_count is not None
        and int(readme_count.group(1)) == int(skill_count.group(1)),
        "SKILL.md Windows smoke count must match tests/README.md",
    )
    run_lint_text = (ROOT / "tests" / "run_lint.ps1").read_text(encoding="utf-8")
    check(
        "-InstallDeps" in run_lint_text,
        "run_lint.ps1 missing check-only -InstallDeps switch",
    )
    dev_reqs_text = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    check(
        "requirements-dev.txt" in ci_text
        and "requirements-dev.txt" in run_lint_text
        and "requirements-dev.txt" in readme_text,
        "requirements-dev.txt must be referenced by CI, run_lint.ps1, and README.md",
    )
    for dev_pin in ("ruff==", "mypy==", "types-requests"):
        check(dev_pin in dev_reqs_text, f"requirements-dev.txt missing {dev_pin}")
    precommit_text = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    ruff_req = re.search(r"ruff==([\d.]+)", dev_reqs_text)
    mypy_req = re.search(r"mypy==([\d.]+)", dev_reqs_text)
    check(
        ruff_req is not None
        and mypy_req is not None
        and f"v{ruff_req.group(1)}" in precommit_text
        and f"v{mypy_req.group(1)}" in precommit_text,
        "pre-commit ruff/mypy revs must match requirements-dev.txt",
    )
    contributing_text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    check(
        "14 `build_*.ps1`" in contributing_text
        and "auto_update_velopack.ps1" in contributing_text
        and "veloappck" not in contributing_text,
        "CONTRIBUTING.md stale build count or auto-update typo",
    )
    bootstrap_text = (ROOT / "scripts" / "bootstrap_environment.ps1").read_text(encoding="utf-8")
    check(
        "Where-Object { $_ -ne $name }" in bootstrap_text,
        "bootstrap_environment.ps1 must clear successfully installed toolchains",
    )
    check(
        bootstrap_text.count("Test-Toolchain $map.toolchains.python") >= 2,
        "bootstrap_environment.ps1 dry-run must not print a pip plan when Python is missing",
    )
    backup_text = (ROOT / "scripts" / "backup_source.ps1").read_text(encoding="utf-8")
    check(
        "-split '[\\\\/]'" in backup_text,
        "backup_source.ps1 must match exclude segments exactly",
    )

    if FAILURES:
        print(f"Doc audit failed ({CHECKS} checks):")
        for item in FAILURES:
            print(f"  - {item}")
        return 1
    print(f"Doc audit OK ({CHECKS} checks).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
