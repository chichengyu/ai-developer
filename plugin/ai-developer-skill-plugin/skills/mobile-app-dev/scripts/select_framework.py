"""select_framework.py -- Step 1.5 framework auto-selection.

Reads a requirements JSON document and applies the deterministic decision
tree described in references/auto_selection.md. Prints a JSON result with
the selected framework, rationale, alternatives, and confidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HARD_NATIVE = {
    "widget",
    "widgetkit",
    "live activity",
    "liveactivity",
    "app intent",
    "appintent",
    "carplay",
    "healthkit",
    "arkit",
    "realitykit",
    "callkit",
    "watch face",
    "watchface",
    "visionos spatial ui",
    "visionos-spatialui",
    "metal",
    "wear os tile",
    "wearos-tile",
    "android auto",
    "androidauto",
    "secure enclave",
    "strongbox",
    "hardware-backed keystore",
    "hardware backed keychain",
}

APPLE_PLATFORMS = {"ios", "ipados", "watchos", "visionos", "tvos"}
ANDROID_PLATFORMS = {"android", "wearos", "android tv", "androidtv", "tv"}

CROSS_PLATFORM_DEFAULT_CATEGORIES = {"B", "C"}
NATIVE_DEFAULT_CATEGORIES = {"A", "E", "F", "G", "H"}


def _norm(value: object) -> str:
    return str(value).strip().lower()


def load_requirements(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def infer_platforms(req: dict) -> list[str]:
    distribution = req.get("distribution", {}) or {}
    app_store = bool(distribution.get("appStore") or distribution.get("app_store"))
    play_store = bool(distribution.get("playStore") or distribution.get("play_store"))
    if app_store and not play_store:
        return ["ios"]
    if play_store and not app_store:
        return ["android"]
    if app_store and play_store:
        return ["ios", "android"]
    return ["ios", "android"]


def _has_any(values: list[str], candidates: set[str]) -> bool:
    return any(value in candidates for value in values)


def _pick_cross_platform(req: dict, criteria: dict) -> str | None:
    if criteria.get("nativeUiMandated"):
        return "Kotlin Multiplatform (native UI)"
    if criteria.get("customUi") or criteria.get("heavyAnimation"):
        return "Flutter"

    team = req.get("teamProfile", {}) or {}
    languages = [_norm(x) for x in team.get("languages", [])]
    codebases = [_norm(x) for x in team.get("existingCodebases", [])]
    web_first = criteria.get("webFirst")
    if web_first is None:
        web_first = (
            _has_any(languages, {"typescript", "javascript", "js"})
            and not _has_any(languages, {"swift", "kotlin"})
        ) or _has_any(codebases, {"react", "web", "typescript"})
    if web_first or criteria.get("hugeJsLibrarySurface"):
        return "React Native"

    dotnet_first = criteria.get("dotnetFirst")
    if dotnet_first is None:
        dotnet_first = _has_any(languages, {"c#", "csharp", ".net"}) or _has_any(
            codebases, {"c#", ".net", "xaml"}
        )
    if dotnet_first:
        return ".NET MAUI"

    if criteria.get("wrapExistingWebApp"):
        return "Capacitor"
    return None


def _existing_preference(codebases: list[str]) -> str | None:
    if _has_any(codebases, {"react", "typescript", "web"}):
        return "React Native"
    if _has_any(codebases, {"c#", ".net", "xaml"}):
        return ".NET MAUI"
    if _has_any(codebases, {"dart", "flutter"}):
        return "Flutter"
    return None


def select_framework(req: dict) -> dict:
    category = _norm(req.get("category", "B")).upper()
    platforms = [_norm(x) for x in req.get("platforms") or infer_platforms(req)]
    integration = req.get("integration", {}) or {}
    features = [_norm(x) for x in integration.get("frameworks", [])]
    team = req.get("teamProfile", {}) or {}
    languages = [_norm(x) for x in team.get("languages", [])]
    codebases = [_norm(x) for x in team.get("existingCodebases", [])]
    criteria = req.get("selectionCriteria", {}) or {}
    rationale: list[str] = []
    alternatives: list[str] = []
    confidence = "HIGH"
    override_applied = False
    hard_constraint = False

    if category == "D":
        return {
            "selected_framework": "Game engine (out of scope)",
            "platforms": platforms,
            "rationale": ["Category D routes to a game-engine skill, not mobile-app-dev."],
            "alternatives": [],
            "confidence": "HIGH",
            "override_applied": False,
            "out_of_scope": True,
        }

    apple_only = bool(platforms) and all(p in APPLE_PLATFORMS for p in platforms)
    android_only = bool(platforms) and all(p in ANDROID_PLATFORMS for p in platforms)
    hard_features = [
        feature
        for feature in features
        if feature in HARD_NATIVE or "foregroundservicetype" in feature
    ]

    if hard_features:
        hard_constraint = True
        if apple_only:
            selected = "Swift + SwiftUI"
        elif android_only:
            selected = "Kotlin + Compose"
        else:
            selected = "Swift + SwiftUI (iOS) + Kotlin + Compose (Android)"
        rationale.append(
            f"Hard native constraint matched: {', '.join(sorted(hard_features))}."
        )
        rationale.append("Cross-platform options are not viable for these features.")
        return {
            "selected_framework": selected,
            "platforms": platforms,
            "rationale": rationale,
            "alternatives": ["Flutter", "React Native"],
            "confidence": "HIGH",
            "override_applied": False,
            "out_of_scope": False,
        }

    if apple_only:
        selected = "Swift + SwiftUI"
        rationale.append("Single-platform Apple delivery defaults to Swift + SwiftUI.")
        if not _has_any(languages, {"swift", "objective-c", "objc"}):
            preferred = _existing_preference(codebases) or "Flutter"
            alternatives.append(selected)
            selected = preferred
            confidence = "LOW"
            override_applied = True
            rationale.append(
                f"No Swift team; swapped to {preferred} per team override."
            )
        return {
            "selected_framework": selected,
            "platforms": platforms,
            "rationale": rationale,
            "alternatives": alternatives,
            "confidence": confidence,
            "override_applied": override_applied,
            "out_of_scope": False,
        }

    if android_only:
        selected = "Kotlin + Compose"
        rationale.append("Single-platform Android delivery defaults to Kotlin + Compose.")
        if not _has_any(languages, {"kotlin"}):
            preferred = _existing_preference(codebases) or "Flutter"
            alternatives.append(selected)
            selected = preferred
            confidence = "LOW"
            override_applied = True
            rationale.append(
                f"No Kotlin team; swapped to {preferred} per team override."
            )
        return {
            "selected_framework": selected,
            "platforms": platforms,
            "rationale": rationale,
            "alternatives": alternatives,
            "confidence": confidence,
            "override_applied": override_applied,
            "out_of_scope": False,
        }

    selected = _pick_cross_platform(req, criteria)
    if selected is None:
        if category in CROSS_PLATFORM_DEFAULT_CATEGORIES:
            selected = "Flutter"
        elif category in NATIVE_DEFAULT_CATEGORIES:
            selected = "Swift + SwiftUI (iOS) + Kotlin + Compose (Android)"
        else:
            selected = "Flutter"
        confidence = "LOW"
        rationale.append("No decisive criterion; used the category default.")
    else:
        confidence = "MEDIUM"
        rationale.append(f"Cross-platform criterion matched: {selected}.")

    preference = _existing_preference(codebases)
    if preference and preference != selected:
        alternatives.append(selected)
        selected = preference
        confidence = "LOW"
        override_applied = True
        rationale.append(
            f"Existing codebase preference overrides selection to {preference}."
        )

    if not hard_constraint and selected in {"Swift + SwiftUI", "Kotlin + Compose"}:
        if selected == "Swift + SwiftUI" and not _has_any(languages, {"swift"}):
            preferred = _existing_preference(codebases) or "Flutter"
            alternatives.append(selected)
            selected = preferred
            confidence = "LOW"
            override_applied = True
            rationale.append(f"No Swift team; swapped to {preferred}.")
        elif selected == "Kotlin + Compose" and not _has_any(languages, {"kotlin"}):
            preferred = _existing_preference(codebases) or "Flutter"
            alternatives.append(selected)
            selected = preferred
            confidence = "LOW"
            override_applied = True
            rationale.append(f"No Kotlin team; swapped to {preferred}.")

    return {
        "selected_framework": selected,
        "platforms": platforms,
        "rationale": rationale,
        "alternatives": alternatives,
        "confidence": confidence,
        "override_applied": override_applied,
        "out_of_scope": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Step 1.5 framework selection.")
    parser.add_argument("requirements", nargs="?", default="-", help="requirements.json path, or - for stdin")
    parser.add_argument("--pretty", action="store_true", help="pretty-print the JSON result")
    args = parser.parse_args(argv)

    if args.requirements == "-":
        req = json.load(sys.stdin)
    else:
        req = load_requirements(args.requirements)

    result = select_framework(req)
    json.dump(result, sys.stdout, indent=2 if args.pretty else None, ensure_ascii=True)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
