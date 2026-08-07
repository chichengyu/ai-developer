"""plan_project.py -- generate requirements.md and tasks.md.

Reads a requirements JSON document, runs Step 1.5 selection, and writes a
markdown requirements summary plus a DAG-shaped task card backlog.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from select_framework import select_framework


def _bullet(value: object) -> str:
    text = str(value).replace("\n", " ")
    return f"- {text}"


def _list_items(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None or value == "":
        return []
    return [str(value)]


def render_requirements(req: dict, selection: dict) -> str:
    meta = req.get("meta", {}) or {}
    functional = req.get("functional", {}) or {}
    non_functional = req.get("nonFunctional", {}) or {}
    distribution = req.get("distribution", {}) or {}
    integration = req.get("integration", {}) or {}
    failure_modes = req.get("failureModes", {}) or {}
    compliance = req.get("compliance", {}) or {}
    ops = req.get("ops", {}) or {}
    team = req.get("teamProfile", {}) or {}
    showstoppers = req.get("showstoppers", []) or []
    out_of_scope = req.get("outOfScope", []) or []

    lines = [
        f"# {meta.get('appName', 'Mobile App')} - Requirements",
        "",
        f"- Owner: {meta.get('owner', 'TBD')}",
        f"- Target ship: {meta.get('targetShip', 'TBD')}",
        f"- Category: {req.get('category', 'B')}",
        "",
        "## Functional",
        _bullet(functional.get("description", "TBD")),
        _bullet(f"Screens: {', '.join(_list_items(functional.get('screens'))) or 'TBD'}"),
        _bullet(f"Offline-first: {functional.get('offlineFirst', 'TBD')}"),
        "",
        "## Non-functional",
        _bullet(f"Cold start: {non_functional.get('coldStartMs', 'TBD')} ms"),
        _bullet(f"Memory: {non_functional.get('memoryMb', 'TBD')} MB"),
        _bullet(f"Locales: {', '.join(_list_items(non_functional.get('locales'))) or 'TBD'}"),
        "",
        "## Distribution",
        _bullet(f"App Store: {distribution.get('appStore', 'TBD')}"),
        _bullet(f"Play Store: {distribution.get('playStore', 'TBD')}"),
        _bullet(f"TestFlight / internal: {distribution.get('testflight', 'TBD')}"),
        "",
        "## Integration",
        _bullet(f"API: {integration.get('apiSurface', 'TBD')}"),
        _bullet(f"Auth: {integration.get('auth', 'TBD')}"),
        _bullet(f"Frameworks: {', '.join(_list_items(integration.get('frameworks'))) or 'none'}"),
        "",
        "## Failure modes",
        _bullet(f"Offline: {failure_modes.get('offlineBehavior', 'TBD')}"),
        _bullet(f"Permission denied: {failure_modes.get('permissionDenied', 'TBD')}"),
        "",
        "## Compliance",
        _bullet(f"Privacy labels: {compliance.get('privacyLabels', 'TBD')}"),
        _bullet(f"Data safety form: {compliance.get('dataSafetyForm', 'TBD')}"),
        _bullet(f"Kids: {compliance.get('kids', 'TBD')}"),
        "",
        "## Ops",
        _bullet(f"Crash reporting: {ops.get('crashReporting', 'TBD')}"),
        _bullet(f"Analytics: {ops.get('analytics', 'TBD')}"),
        _bullet(f"Feature flags: {ops.get('featureFlags', 'TBD')}"),
        _bullet(f"CI: {ops.get('ci', 'TBD')}"),
        "",
        "## Team profile",
        _bullet(f"Languages: {', '.join(_list_items(team.get('languages'))) or 'TBD'}"),
        _bullet(f"Existing codebases: {', '.join(_list_items(team.get('existingCodebases'))) or 'TBD'}"),
        "",
        "## Step 1.5 result",
        f"- Selected framework: **{selection['selected_framework']}**",
        f"- Confidence: **{selection['confidence']}**",
        f"- Override applied: {selection['override_applied']}",
    ]
    for reason in selection.get("rationale", []):
        lines.append(f"- Rationale: {reason}")
    if selection.get("alternatives"):
        lines.append(f"- Alternatives: {', '.join(selection['alternatives'])}")

    lines.extend(["", "## Showstopper assumptions"])
    lines.extend(_bullet(item) if item else _bullet("TBD") for item in showstoppers)
    lines.extend(["", "## Out of scope for v1"])
    lines.extend(_bullet(item) if item else _bullet("TBD") for item in out_of_scope)
    return "\n".join(lines) + "\n"


TASKS = [
    {
        "id": "T-001",
        "title": "Project scaffold",
        "depends": [],
        "estimate": "1d",
        "category": "build",
        "verification": "CI",
        "acceptance": "Fresh clone builds the selected framework with the documented commands.",
    },
    {
        "id": "T-002",
        "title": "Navigation shell",
        "depends": ["T-001"],
        "estimate": "1d",
        "category": "ui",
        "verification": "simulator",
        "acceptance": "Root tabs/routes load and deep links resolve on cold start.",
    },
    {
        "id": "T-003",
        "title": "Data and repository layer",
        "depends": ["T-001"],
        "estimate": "1d",
        "category": "data",
        "verification": "unit test",
        "acceptance": "Offline and online paths emit the same state contract.",
    },
    {
        "id": "T-004",
        "title": "Primary list screen",
        "depends": ["T-002", "T-003"],
        "estimate": "1d",
        "category": "ui",
        "verification": "device",
        "acceptance": "1000 rows scroll at the project frame budget on a mid-tier device.",
    },
    {
        "id": "T-005",
        "title": "Detail and form screens",
        "depends": ["T-004"],
        "estimate": "1d",
        "category": "ui",
        "verification": "device",
        "acceptance": "Mutation succeeds, rolls back on error, and restores state after process death.",
    },
    {
        "id": "T-006",
        "title": "Permissions and privacy strings",
        "depends": ["T-001"],
        "estimate": "0.5d",
        "category": "ops",
        "verification": "device",
        "acceptance": "Every permission shows a rationale, and denial degrades gracefully.",
    },
    {
        "id": "T-007",
        "title": "Unit and UI test suite",
        "depends": ["T-004"],
        "estimate": "1d",
        "category": "ops",
        "verification": "CI",
        "acceptance": "Unit, widget/Compose/UI tests pass in CI with no flaky retries.",
    },
    {
        "id": "T-008",
        "title": "Signing and store config",
        "depends": ["T-001"],
        "estimate": "1d",
        "category": "build",
        "verification": "CI",
        "acceptance": "Release archive/AAB is signed and uploads to the internal track.",
    },
    {
        "id": "T-009",
        "title": "CI pipeline",
        "depends": ["T-008"],
        "estimate": "1d",
        "category": "ops",
        "verification": "CI",
        "acceptance": "One command runs lint, tests, build, and upload.",
    },
    {
        "id": "T-010",
        "title": "Store metadata and compliance",
        "depends": ["T-009"],
        "estimate": "0.5d",
        "category": "ops",
        "verification": "store console",
        "acceptance": "Privacy labels, data safety, screenshots, and metadata match the app.",
    },
    {
        "id": "T-011",
        "title": "Device verification and handoff",
        "depends": ["T-004", "T-005", "T-006", "T-009", "T-010"],
        "estimate": "1d",
        "category": "ops",
        "verification": "device",
        "acceptance": "Verification report is complete and user-facing README is published.",
    },
]


def render_tasks(req: dict, selection: dict) -> str:
    framework = selection["selected_framework"]
    lines = [
        f"# {req.get('meta', {}).get('appName', 'Mobile App')} - Tasks",
        "",
        f"Framework: **{framework}**",
        "",
    ]
    for task in TASKS:
        lines.extend(
            [
                f"## {task['id']} - {task['title']}",
                "",
                f"- Estimate: {task['estimate']}",
                f"- Depends on: {', '.join(task['depends']) or 'none'}",
                f"- Category: {task['category']}",
                f"- Verification: {task['verification']}",
                f"- Acceptance: {task['acceptance']}",
                "",
            ]
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate requirements.md and tasks.md.")
    parser.add_argument("--requirements", required=True, help="requirements.json path")
    parser.add_argument("--output-dir", default="plan", help="output directory")
    args = parser.parse_args(argv)

    req = json.loads(Path(args.requirements).read_text(encoding="utf-8"))
    selection = select_framework(req)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "requirements.md").write_text(
        render_requirements(req, selection), encoding="utf-8"
    )
    (output_dir / "tasks.md").write_text(render_tasks(req, selection), encoding="utf-8")
    print(f"Wrote {output_dir / 'requirements.md'} and {output_dir / 'tasks.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
