#!/usr/bin/env python3
"""select_framework.py -- deep-analysis framework auto-selector for desktop apps.

Input  : a JSON or YAML requirements brief (see templates/requirements_brief.md).
Output : the top 3 framework recommendations, each with a score, a one-line
         rationale, and the top reasons / blockers.

Usage  :
    python select_framework.py requirements.json
    python select_framework.py requirements.yaml
    python select_framework.py --self-test           # regression cases
    python select_framework.py --json brief.json     # machine-readable

Why this exists
    The Step 2 matrix in SKILL.md and the deeper notes in
    references/framework_matrix.md cover 24 frameworks. Humans routinely
    pick the wrong one because they read only the matrix row that matches
    their known language. This selector walks every framework, scores it on
    every relevant dimension, and returns an evidence-backed ranking.

Design contract
    * Pure Python 3.10+. No third-party deps.
    * All scoring tables live inside this file. If you add a new framework,
      add a new row to FRAMEWORKS and re-run --self-test.
    * Scoring is deterministic and reproducible (no LLM inside the loop).

See:
    * templates/requirements_brief.md             -- input schema
    * references/framework_selection_engine.md    -- scoring methodology
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Dimensions scored per framework. Scores are in [-1.0, +1.0].
# ---------------------------------------------------------------------------

# Framework -> team languages. Used by derive_weights() to boost frameworks that match known team skills.
FRAMEWORK_LANGUAGES: dict[str, tuple[str, ...]] = {
    "wpf": ("csharp",),
    "winforms": ("csharp",),
    "winui3": ("csharp",),
    "avalonia": ("csharp",),
    "maui": ("csharp",),
    "tkinter": ("python",),
    "pyside6": ("python",),
    "py_gtk": ("python",),
    "tauri": ("rust", "typescript", "javascript"),
    "electron": ("javascript", "typescript"),
    "neutralino": ("javascript", "typescript"),
    "qt6": ("cpp",),
    "win32_mfc": ("cpp",),
    "wails": ("go", "javascript", "typescript"),
    "fyne": ("go",),
    "gio": ("go",),
    "walk": ("go",),
    "compose_multiplatform": ("kotlin",),
    "javafx": ("java", "kotlin"),
    "tornadofx": ("kotlin",),
    "flutter": ("dart",),
    "slint": ("rust",),
    "egui": ("rust",),
    "swiftui": ("swift",),
}


DIMS = (
    "windows_support",
    "macos_support",
    "linux_support",
    "win_x64_arch",
    "win_arm64_arch",
    "win_x86_arch",
    "macos_x64_arch",
    "macos_arm64_arch",
    "linux_x64_arch",
    "linux_arm64_arch",
    "exe_size_small",
    "exe_size_tiny",
    "cold_start_fast",
    "native_look_win11",
    "native_look_macos",
    "native_look_linux",
    "sendinput_friendly",
    "win32_interop",
    "usb_serial_access",
    "web_ui_support",
    "single_file_output",
    "store_distribution",
    "auto_update",
    "ecosystem_maturity",
    "dev_speed",
    "long_term_maintenance",
    "oss_only",
    "binary_native_aot",
    "threading_quality",
)

FRAMEWORKS: dict[str, dict[str, float]] = {
    "wpf": {
        "windows_support": 1.0,
        "macos_support": -1.0,
        "linux_support": -1.0,
        "win_x64_arch": 1.0,
        "win_arm64_arch": 1.0,
        "win_x86_arch": 1.0,
        "macos_x64_arch": -1.0,
        "macos_arm64_arch": -1.0,
        "linux_x64_arch": -1.0,
        "linux_arm64_arch": -1.0,
        "exe_size_small": 0.0,
        "exe_size_tiny": -0.5,
        "cold_start_fast": 0.5,
        "native_look_win11": 0.5,
        "native_look_macos": -1.0,
        "native_look_linux": -1.0,
        "sendinput_friendly": 1.0,
        "win32_interop": 1.0,
        "usb_serial_access": 0.5,
        "web_ui_support": 0.5,
        "single_file_output": 0.5,
        "store_distribution": 0.0,
        "auto_update": 0.5,
        "ecosystem_maturity": 1.0,
        "dev_speed": 0.8,
        "long_term_maintenance": 0.8,
        "oss_only": 1.0,
        "binary_native_aot": -1.0,
        "threading_quality": 1.0,
    },
    "winforms": {
        "windows_support": 1.0,
        "macos_support": -1.0,
        "linux_support": -1.0,
        "win_x64_arch": 1.0,
        "win_arm64_arch": 1.0,
        "win_x86_arch": 1.0,
        "macos_x64_arch": -1.0,
        "macos_arm64_arch": -1.0,
        "linux_x64_arch": -1.0,
        "linux_arm64_arch": -1.0,
        "exe_size_small": 0.5,
        "exe_size_tiny": 1.0,
        "cold_start_fast": 0.8,
        "native_look_win11": 0.0,
        "native_look_macos": -1.0,
        "native_look_linux": -1.0,
        "sendinput_friendly": 1.0,
        "win32_interop": 1.0,
        "usb_serial_access": 0.8,
        "web_ui_support": 0.0,
        "single_file_output": 0.8,
        "store_distribution": 0.0,
        "auto_update": 0.5,
        "ecosystem_maturity": 0.8,
        "dev_speed": 0.9,
        "long_term_maintenance": 0.6,
        "oss_only": 1.0,
        "binary_native_aot": 1.0,
        "threading_quality": 0.5,
    },
    "winui3": {
        "windows_support": 1.0,
        "macos_support": -1.0,
        "linux_support": -1.0,
        "win_x64_arch": 1.0,
        "win_arm64_arch": 1.0,
        "win_x86_arch": 0.5,
        "macos_x64_arch": -1.0,
        "macos_arm64_arch": -1.0,
        "linux_x64_arch": -1.0,
        "linux_arm64_arch": -1.0,
        "exe_size_small": 0.0,
        "exe_size_tiny": -0.8,
        "cold_start_fast": 0.6,
        "native_look_win11": 1.0,
        "native_look_macos": -1.0,
        "native_look_linux": -1.0,
        "sendinput_friendly": 1.0,
        "win32_interop": 1.0,
        "usb_serial_access": 0.5,
        "web_ui_support": 0.5,
        "single_file_output": 0.0,
        "store_distribution": 1.0,
        "auto_update": 0.5,
        "ecosystem_maturity": 0.5,
        "dev_speed": 0.5,
        "long_term_maintenance": 0.7,
        "oss_only": 1.0,
        "binary_native_aot": -1.0,
        "threading_quality": 1.0,
    },
    "avalonia": {
        "windows_support": 1.0,
        "macos_support": 0.8,
        "linux_support": 0.8,
        "win_x64_arch": 1.0,
        "win_arm64_arch": 0.8,
        "win_x86_arch": 1.0,
        "macos_x64_arch": 1.0,
        "macos_arm64_arch": 1.0,
        "linux_x64_arch": 1.0,
        "linux_arm64_arch": 0.8,
        "exe_size_small": 0.0,
        "exe_size_tiny": -0.5,
        "cold_start_fast": 0.5,
        "native_look_win11": 0.5,
        "native_look_macos": 0.7,
        "native_look_linux": 0.7,
        "sendinput_friendly": 0.5,
        "win32_interop": 0.5,
        "usb_serial_access": 0.5,
        "web_ui_support": 0.7,
        "single_file_output": 0.5,
        "store_distribution": 0.5,
        "auto_update": 0.5,
        "ecosystem_maturity": 0.5,
        "dev_speed": 0.6,
        "long_term_maintenance": 0.7,
        "oss_only": 1.0,
        "binary_native_aot": 0.0,
        "threading_quality": 0.8,
    },
    "maui": {
        "windows_support": 0.8,
        "macos_support": 0.8,
        "linux_support": 0.0,
        "win_x64_arch": 1.0,
        "win_arm64_arch": 0.8,
        "win_x86_arch": 0.5,
        "macos_x64_arch": 1.0,
        "macos_arm64_arch": 1.0,
        "linux_x64_arch": 0.0,
        "linux_arm64_arch": 0.0,
        "exe_size_small": -0.5,
        "exe_size_tiny": -1.0,
        "cold_start_fast": 0.0,
        "native_look_win11": 0.7,
        "native_look_macos": 0.7,
        "native_look_linux": -0.5,
        "sendinput_friendly": 0.5,
        "win32_interop": 0.3,
        "usb_serial_access": 0.3,
        "web_ui_support": 0.7,
        "single_file_output": 0.0,
        "store_distribution": 1.0,
        "auto_update": 0.5,
        "ecosystem_maturity": 0.5,
        "dev_speed": 0.5,
        "long_term_maintenance": 0.6,
        "oss_only": 1.0,
        "binary_native_aot": -1.0,
        "threading_quality": 0.7,
    },
    "tkinter": {
        "windows_support": 1.0,
        "macos_support": 1.0,
        "linux_support": 1.0,
        "win_x64_arch": 1.0,
        "win_arm64_arch": 1.0,
        "win_x86_arch": 1.0,
        "macos_x64_arch": 1.0,
        "macos_arm64_arch": 1.0,
        "linux_x64_arch": 1.0,
        "linux_arm64_arch": 1.0,
        "exe_size_small": 0.0,
        "exe_size_tiny": -0.5,
        "cold_start_fast": 0.5,
        "native_look_win11": 0.0,
        "native_look_macos": 0.0,
        "native_look_linux": 0.0,
        "sendinput_friendly": 1.0,
        "win32_interop": 1.0,
        "usb_serial_access": 0.5,
        "web_ui_support": 0.0,
        "single_file_output": 0.5,
        "store_distribution": 0.0,
        "auto_update": 0.5,
        "ecosystem_maturity": 0.8,
        "dev_speed": 1.0,
        "long_term_maintenance": 1.0,
        "oss_only": 1.0,
        "binary_native_aot": -1.0,
        "threading_quality": 0.7,
    },
    "pyside6": {
        "windows_support": 1.0,
        "macos_support": 1.0,
        "linux_support": 1.0,
        "win_x64_arch": 1.0,
        "win_arm64_arch": 1.0,
        "win_x86_arch": 1.0,
        "macos_x64_arch": 1.0,
        "macos_arm64_arch": 1.0,
        "linux_x64_arch": 1.0,
        "linux_arm64_arch": 1.0,
        "exe_size_small": -0.5,
        "exe_size_tiny": -1.0,
        "cold_start_fast": 0.0,
        "native_look_win11": 0.3,
        "native_look_macos": 0.3,
        "native_look_linux": 0.3,
        "sendinput_friendly": 1.0,
        "win32_interop": 1.0,
        "usb_serial_access": 0.8,
        "web_ui_support": 0.0,
        "single_file_output": -0.5,
        "store_distribution": 0.0,
        "auto_update": 0.5,
        "ecosystem_maturity": 0.9,
        "dev_speed": 0.9,
        "long_term_maintenance": 0.9,
        "oss_only": 1.0,
        "binary_native_aot": -1.0,
        "threading_quality": 0.9,
    },
    "py_gtk": {
        "windows_support": 0.3,
        "macos_support": 0.5,
        "linux_support": 1.0,
        "win_x64_arch": 0.3,
        "win_arm64_arch": 0.0,
        "win_x86_arch": 0.3,
        "macos_x64_arch": 0.5,
        "macos_arm64_arch": 0.5,
        "linux_x64_arch": 1.0,
        "linux_arm64_arch": 1.0,
        "exe_size_small": -0.5,
        "exe_size_tiny": -1.0,
        "cold_start_fast": 0.0,
        "native_look_win11": -0.5,
        "native_look_macos": 0.0,
        "native_look_linux": 1.0,
        "sendinput_friendly": 0.7,
        "win32_interop": 0.5,
        "usb_serial_access": 0.5,
        "web_ui_support": 0.5,
        "single_file_output": -0.5,
        "store_distribution": 0.0,
        "auto_update": 0.5,
        "ecosystem_maturity": 0.5,
        "dev_speed": 0.6,
        "long_term_maintenance": 0.7,
        "oss_only": 1.0,
        "binary_native_aot": -1.0,
        "threading_quality": 0.6,
    },
    "tauri": {
        "windows_support": 1.0,
        "macos_support": 1.0,
        "linux_support": 1.0,
        "win_x64_arch": 1.0,
        "win_arm64_arch": 1.0,
        "win_x86_arch": 0.5,
        "macos_x64_arch": 1.0,
        "macos_arm64_arch": 1.0,
        "linux_x64_arch": 1.0,
        "linux_arm64_arch": 1.0,
        "exe_size_small": 0.9,
        "exe_size_tiny": 1.0,
        "cold_start_fast": 0.7,
        "native_look_win11": 0.3,
        "native_look_macos": 0.5,
        "native_look_linux": 0.3,
        "sendinput_friendly": 0.8,
        "win32_interop": 0.7,
        "usb_serial_access": 0.7,
        "web_ui_support": 1.0,
        "single_file_output": 1.0,
        "store_distribution": 0.8,
        "auto_update": 0.7,
        "ecosystem_maturity": 0.8,
        "dev_speed": 0.5,
        "long_term_maintenance": 0.9,
        "oss_only": 1.0,
        "binary_native_aot": 1.0,
        "threading_quality": 0.9,
    },
    "electron": {
        "windows_support": 1.0,
        "macos_support": 1.0,
        "linux_support": 1.0,
        "win_x64_arch": 1.0,
        "win_arm64_arch": 1.0,
        "win_x86_arch": 0.8,
        "macos_x64_arch": 1.0,
        "macos_arm64_arch": 1.0,
        "linux_x64_arch": 1.0,
        "linux_arm64_arch": 1.0,
        "exe_size_small": -1.0,
        "exe_size_tiny": -1.0,
        "cold_start_fast": -0.5,
        "native_look_win11": 0.0,
        "native_look_macos": 0.0,
        "native_look_linux": 0.0,
        "sendinput_friendly": 0.5,
        "win32_interop": 0.5,
        "usb_serial_access": 0.3,
        "web_ui_support": 1.0,
        "single_file_output": -0.5,
        "store_distribution": 0.8,
        "auto_update": 1.0,
        "ecosystem_maturity": 1.0,
        "dev_speed": 0.9,
        "long_term_maintenance": 0.9,
        "oss_only": 1.0,
        "binary_native_aot": -1.0,
        "threading_quality": 0.7,
    },
    "neutralino": {
        "windows_support": 1.0,
        "macos_support": 1.0,
        "linux_support": 1.0,
        "win_x64_arch": 1.0,
        "win_arm64_arch": 1.0,
        "win_x86_arch": 0.5,
        "macos_x64_arch": 1.0,
        "macos_arm64_arch": 1.0,
        "linux_x64_arch": 1.0,
        "linux_arm64_arch": 1.0,
        "exe_size_small": 1.0,
        "exe_size_tiny": 1.0,
        "cold_start_fast": 0.5,
        "native_look_win11": 0.0,
        "native_look_macos": 0.0,
        "native_look_linux": 0.0,
        "sendinput_friendly": 0.5,
        "win32_interop": 0.5,
        "usb_serial_access": 0.3,
        "web_ui_support": 1.0,
        "single_file_output": 1.0,
        "store_distribution": 0.0,
        "auto_update": 0.0,
        "ecosystem_maturity": 0.4,
        "dev_speed": 0.7,
        "long_term_maintenance": 0.6,
        "oss_only": 1.0,
        "binary_native_aot": -1.0,
        "threading_quality": 0.6,
    },
    "qt6": {
        "windows_support": 1.0,
        "macos_support": 1.0,
        "linux_support": 1.0,
        "win_x64_arch": 1.0,
        "win_arm64_arch": 1.0,
        "win_x86_arch": 1.0,
        "macos_x64_arch": 1.0,
        "macos_arm64_arch": 1.0,
        "linux_x64_arch": 1.0,
        "linux_arm64_arch": 1.0,
        "exe_size_small": 0.5,
        "exe_size_tiny": 0.0,
        "cold_start_fast": 0.7,
        "native_look_win11": 0.4,
        "native_look_macos": 0.5,
        "native_look_linux": 0.6,
        "sendinput_friendly": 1.0,
        "win32_interop": 1.0,
        "usb_serial_access": 1.0,
        "web_ui_support": 0.5,
        "single_file_output": 0.0,
        "store_distribution": 0.5,
        "auto_update": 0.5,
        "ecosystem_maturity": 1.0,
        "dev_speed": 0.4,
        "long_term_maintenance": 1.0,
        "oss_only": 0.0,
        "binary_native_aot": 0.0,
        "threading_quality": 1.0,
    },
    "win32_mfc": {
        "windows_support": 1.0,
        "macos_support": -1.0,
        "linux_support": -1.0,
        "win_x64_arch": 1.0,
        "win_arm64_arch": 1.0,
        "win_x86_arch": 1.0,
        "macos_x64_arch": -1.0,
        "macos_arm64_arch": -1.0,
        "linux_x64_arch": -1.0,
        "linux_arm64_arch": -1.0,
        "exe_size_small": 1.0,
        "exe_size_tiny": 1.0,
        "cold_start_fast": 1.0,
        "native_look_win11": 0.0,
        "native_look_macos": -1.0,
        "native_look_linux": -1.0,
        "sendinput_friendly": 1.0,
        "win32_interop": 1.0,
        "usb_serial_access": 1.0,
        "web_ui_support": 0.0,
        "single_file_output": 1.0,
        "store_distribution": 0.0,
        "auto_update": 0.0,
        "ecosystem_maturity": 0.5,
        "dev_speed": 0.1,
        "long_term_maintenance": 0.5,
        "oss_only": 1.0,
        "binary_native_aot": 1.0,
        "threading_quality": 0.3,
    },
    "wails": {
        "windows_support": 1.0,
        "macos_support": 1.0,
        "linux_support": 1.0,
        "win_x64_arch": 1.0,
        "win_arm64_arch": 0.8,
        "win_x86_arch": 0.5,
        "macos_x64_arch": 1.0,
        "macos_arm64_arch": 1.0,
        "linux_x64_arch": 1.0,
        "linux_arm64_arch": 0.8,
        "exe_size_small": 0.9,
        "exe_size_tiny": 0.9,
        "cold_start_fast": 0.7,
        "native_look_win11": 0.3,
        "native_look_macos": 0.5,
        "native_look_linux": 0.3,
        "sendinput_friendly": 0.7,
        "win32_interop": 0.7,
        "usb_serial_access": 0.5,
        "web_ui_support": 1.0,
        "single_file_output": 1.0,
        "store_distribution": 0.5,
        "auto_update": 0.5,
        "ecosystem_maturity": 0.6,
        "dev_speed": 0.6,
        "long_term_maintenance": 0.7,
        "oss_only": 1.0,
        "binary_native_aot": 1.0,
        "threading_quality": 0.7,
    },
    "fyne": {
        "windows_support": 1.0,
        "macos_support": 1.0,
        "linux_support": 1.0,
        "win_x64_arch": 1.0,
        "win_arm64_arch": 0.8,
        "win_x86_arch": 0.5,
        "macos_x64_arch": 1.0,
        "macos_arm64_arch": 1.0,
        "linux_x64_arch": 1.0,
        "linux_arm64_arch": 0.8,
        "exe_size_small": 0.8,
        "exe_size_tiny": 0.7,
        "cold_start_fast": 0.7,
        "native_look_win11": 0.0,
        "native_look_macos": 0.0,
        "native_look_linux": 0.0,
        "sendinput_friendly": 0.7,
        "win32_interop": 0.7,
        "usb_serial_access": 0.5,
        "web_ui_support": 0.0,
        "single_file_output": 1.0,
        "store_distribution": 0.3,
        "auto_update": 0.3,
        "ecosystem_maturity": 0.5,
        "dev_speed": 0.7,
        "long_term_maintenance": 0.7,
        "oss_only": 1.0,
        "binary_native_aot": 1.0,
        "threading_quality": 0.6,
    },
    "gio": {
        "windows_support": 0.5,
        "macos_support": 0.5,
        "linux_support": 0.7,
        "win_x64_arch": 0.5,
        "win_arm64_arch": 0.3,
        "win_x86_arch": 0.3,
        "macos_x64_arch": 0.5,
        "macos_arm64_arch": 0.5,
        "linux_x64_arch": 0.8,
        "linux_arm64_arch": 0.7,
        "exe_size_small": 1.0,
        "exe_size_tiny": 1.0,
        "cold_start_fast": 0.9,
        "native_look_win11": 0.0,
        "native_look_macos": 0.0,
        "native_look_linux": 0.0,
        "sendinput_friendly": 0.7,
        "win32_interop": 0.5,
        "usb_serial_access": 0.5,
        "web_ui_support": 0.0,
        "single_file_output": 1.0,
        "store_distribution": 0.0,
        "auto_update": 0.0,
        "ecosystem_maturity": 0.3,
        "dev_speed": 0.6,
        "long_term_maintenance": 0.6,
        "oss_only": 1.0,
        "binary_native_aot": 1.0,
        "threading_quality": 0.6,
    },
    "walk": {
        "windows_support": 1.0,
        "macos_support": -1.0,
        "linux_support": -1.0,
        "win_x64_arch": 1.0,
        "win_arm64_arch": 0.8,
        "win_x86_arch": 0.8,
        "macos_x64_arch": -1.0,
        "macos_arm64_arch": -1.0,
        "linux_x64_arch": -1.0,
        "linux_arm64_arch": -1.0,
        "exe_size_small": 1.0,
        "exe_size_tiny": 1.0,
        "cold_start_fast": 1.0,
        "native_look_win11": 0.3,
        "native_look_macos": -1.0,
        "native_look_linux": -1.0,
        "sendinput_friendly": 1.0,
        "win32_interop": 1.0,
        "usb_serial_access": 0.8,
        "web_ui_support": 0.0,
        "single_file_output": 1.0,
        "store_distribution": 0.0,
        "auto_update": 0.0,
        "ecosystem_maturity": 0.4,
        "dev_speed": 0.6,
        "long_term_maintenance": 0.5,
        "oss_only": 1.0,
        "binary_native_aot": 1.0,
        "threading_quality": 0.7,
    },
    "compose_multiplatform": {
        "windows_support": 0.7,
        "macos_support": 0.7,
        "linux_support": 0.7,
        "win_x64_arch": 1.0,
        "win_arm64_arch": 0.5,
        "win_x86_arch": 0.5,
        "macos_x64_arch": 0.8,
        "macos_arm64_arch": 0.7,
        "linux_x64_arch": 0.8,
        "linux_arm64_arch": 0.7,
        "exe_size_small": -0.7,
        "exe_size_tiny": -1.0,
        "cold_start_fast": -0.3,
        "native_look_win11": 0.5,
        "native_look_macos": 0.6,
        "native_look_linux": 0.5,
        "sendinput_friendly": 0.5,
        "win32_interop": 0.3,
        "usb_serial_access": 0.3,
        "web_ui_support": 0.5,
        "single_file_output": -0.5,
        "store_distribution": 0.7,
        "auto_update": 0.3,
        "ecosystem_maturity": 0.5,
        "dev_speed": 0.5,
        "long_term_maintenance": 0.6,
        "oss_only": 1.0,
        "binary_native_aot": -1.0,
        "threading_quality": 0.7,
    },
    "javafx": {
        "windows_support": 0.8,
        "macos_support": 0.7,
        "linux_support": 0.7,
        "win_x64_arch": 1.0,
        "win_arm64_arch": 0.3,
        "win_x86_arch": 0.8,
        "macos_x64_arch": 0.7,
        "macos_arm64_arch": 0.5,
        "linux_x64_arch": 0.7,
        "linux_arm64_arch": 0.5,
        "exe_size_small": -0.5,
        "exe_size_tiny": -1.0,
        "cold_start_fast": -0.3,
        "native_look_win11": 0.0,
        "native_look_macos": 0.0,
        "native_look_linux": 0.0,
        "sendinput_friendly": 0.5,
        "win32_interop": 0.5,
        "usb_serial_access": 0.3,
        "web_ui_support": 0.5,
        "single_file_output": -0.5,
        "store_distribution": 0.5,
        "auto_update": 0.3,
        "ecosystem_maturity": 0.5,
        "dev_speed": 0.5,
        "long_term_maintenance": 0.5,
        "oss_only": 1.0,
        "binary_native_aot": -1.0,
        "threading_quality": 0.5,
    },
    "swiftui": {
        "windows_support": 0.0,
        "macos_support": 1.0,
        "linux_support": 0.3,
        "win_x64_arch": 0.5,
        "win_arm64_arch": 0.0,
        "win_x86_arch": 0.3,
        "macos_x64_arch": 1.0,
        "macos_arm64_arch": 1.0,
        "linux_x64_arch": 0.3,
        "linux_arm64_arch": 0.0,
        "exe_size_small": 0.8,
        "exe_size_tiny": 0.8,
        "cold_start_fast": 0.8,
        "native_look_win11": -1.0,
        "native_look_macos": 1.0,
        "native_look_linux": -1.0,
        "sendinput_friendly": 0.7,
        "win32_interop": 0.5,
        "usb_serial_access": 0.5,
        "web_ui_support": 0.0,
        "single_file_output": 1.0,
        "store_distribution": 1.0,
        "auto_update": 0.5,
        "ecosystem_maturity": 0.8,
        "dev_speed": 0.7,
        "long_term_maintenance": 0.9,
        "oss_only": 1.0,
        "binary_native_aot": 0.0,
        "threading_quality": 0.9,
    },
    "flutter": {
        "windows_support": 0.8,
        "macos_support": 0.8,
        "linux_support": 0.8,
        "win_x64_arch": 1.0,
        "win_arm64_arch": 0.8,
        "win_x86_arch": 0.5,
        "macos_x64_arch": 1.0,
        "macos_arm64_arch": 1.0,
        "linux_x64_arch": 0.8,
        "linux_arm64_arch": 0.8,
        "exe_size_small": -0.3,
        "exe_size_tiny": -1.0,
        "cold_start_fast": 0.2,
        "native_look_win11": 0.3,
        "native_look_macos": 0.3,
        "native_look_linux": 0.3,
        "sendinput_friendly": 0.3,
        "win32_interop": 0.3,
        "usb_serial_access": 0.3,
        "web_ui_support": 0.0,
        "single_file_output": 0.0,
        "store_distribution": 0.7,
        "auto_update": 0.3,
        "ecosystem_maturity": 0.7,
        "dev_speed": 0.7,
        "long_term_maintenance": 0.6,
        "oss_only": 1.0,
        "binary_native_aot": -1.0,
        "threading_quality": 0.7,
    },
    "slint": {
        "windows_support": 0.9,
        "macos_support": 0.8,
        "linux_support": 0.9,
        "win_x64_arch": 1.0,
        "win_arm64_arch": 0.8,
        "win_x86_arch": 0.8,
        "macos_x64_arch": 1.0,
        "macos_arm64_arch": 1.0,
        "linux_x64_arch": 0.9,
        "linux_arm64_arch": 0.8,
        "exe_size_small": 1.0,
        "exe_size_tiny": 1.0,
        "cold_start_fast": 0.9,
        "native_look_win11": 0.4,
        "native_look_macos": 0.5,
        "native_look_linux": 0.5,
        "sendinput_friendly": 0.6,
        "win32_interop": 0.5,
        "usb_serial_access": 0.5,
        "web_ui_support": 0.5,
        "single_file_output": 1.0,
        "store_distribution": 0.3,
        "auto_update": 0.3,
        "ecosystem_maturity": 0.4,
        "dev_speed": 0.5,
        "long_term_maintenance": 0.6,
        "oss_only": 1.0,
        "binary_native_aot": 1.0,
        "threading_quality": 0.6,
    },
    "egui": {
        "windows_support": 0.9,
        "macos_support": 0.9,
        "linux_support": 0.9,
        "win_x64_arch": 1.0,
        "win_arm64_arch": 0.8,
        "win_x86_arch": 0.8,
        "macos_x64_arch": 1.0,
        "macos_arm64_arch": 1.0,
        "linux_x64_arch": 0.9,
        "linux_arm64_arch": 0.8,
        "exe_size_small": 1.0,
        "exe_size_tiny": 1.0,
        "cold_start_fast": 0.9,
        "native_look_win11": 0.3,
        "native_look_macos": 0.3,
        "native_look_linux": 0.3,
        "sendinput_friendly": 0.6,
        "win32_interop": 0.5,
        "usb_serial_access": 0.5,
        "web_ui_support": 0.5,
        "single_file_output": 1.0,
        "store_distribution": 0.0,
        "auto_update": 0.0,
        "ecosystem_maturity": 0.4,
        "dev_speed": 0.6,
        "long_term_maintenance": 0.5,
        "oss_only": 1.0,
        "binary_native_aot": 1.0,
        "threading_quality": 0.5,
    },
    "tornadofx": {
        "windows_support": 0.8,
        "macos_support": 0.7,
        "linux_support": 0.7,
        "win_x64_arch": 1.0,
        "win_arm64_arch": 0.3,
        "win_x86_arch": 0.8,
        "macos_x64_arch": 0.7,
        "macos_arm64_arch": 0.5,
        "linux_x64_arch": 0.7,
        "linux_arm64_arch": 0.5,
        "exe_size_small": -0.5,
        "exe_size_tiny": -1.0,
        "cold_start_fast": -0.3,
        "native_look_win11": 0.0,
        "native_look_macos": 0.0,
        "native_look_linux": 0.0,
        "sendinput_friendly": 0.5,
        "win32_interop": 0.5,
        "usb_serial_access": 0.3,
        "web_ui_support": 0.5,
        "single_file_output": -0.5,
        "store_distribution": 0.5,
        "auto_update": 0.3,
        "ecosystem_maturity": 0.4,
        "dev_speed": 0.5,
        "long_term_maintenance": 0.5,
        "oss_only": 1.0,
        "binary_native_aot": -1.0,
        "threading_quality": 0.5,
    },
}


DISPLAY_NAMES: dict[str, str] = {
    "wpf": "C# / WPF (.NET 8)",
    "winforms": "C# / WinForms (.NET 8)",
    "winui3": "C# / WinUI 3 (Windows App SDK)",
    "avalonia": "C# / Avalonia 11",
    "maui": ".NET MAUI",
    "tkinter": "Python tkinter (stdlib)",
    "pyside6": "Python PySide6 (Qt 6)",
    "py_gtk": "Python GTK (PyGObject)",
    "tauri": "Tauri (Rust + WebView)",
    "electron": "Electron (Chromium + Node)",
    "neutralino": "Neutralino.js (system WebView)",
    "qt6": "C++ / Qt 6",
    "win32_mfc": "C++ / Win32 + MFC",
    "wails": "Go Wails (web frontend)",
    "fyne": "Go Fyne (native widgets)",
    "gio": "Go Gio (immediate mode)",
    "walk": "Go walk (Win32 native)",
    "compose_multiplatform": "Kotlin Compose Multiplatform",
    "javafx": "JavaFX / TornadoFX",
    "tornadofx": "Kotlin TornadoFX (JavaFX DSL)",
    "flutter": "Flutter Desktop",
    "slint": "Rust + Slint",
    "egui": "Rust + egui",
    "swiftui": "Swift / SwiftUI",
}


HUMAN_DIM: dict[str, str] = {
    "windows_support": "Windows support",
    "macos_support": "macOS support",
    "linux_support": "Linux support",
    "win_x64_arch": "Windows x64 support",
    "win_arm64_arch": "Windows arm64 support",
    "win_x86_arch": "Windows x86 support",
    "macos_x64_arch": "macOS x64 support",
    "macos_arm64_arch": "macOS arm64 support",
    "linux_x64_arch": "Linux x64 support",
    "linux_arm64_arch": "Linux arm64 support",
    "exe_size_small": "small EXE (< 30 MB)",
    "exe_size_tiny": "tiny EXE (< 5 MB)",
    "cold_start_fast": "fast cold start",
    "native_look_win11": "native Windows 11 look",
    "native_look_macos": "native macOS look",
    "native_look_linux": "native Linux look",
    "sendinput_friendly": "hardware input (SendInput)",
    "web_ui_support": "web frontend",
    "single_file_output": "single-file output",
    "store_distribution": "Store distribution",
    "auto_update": "built-in auto-update",
    "ecosystem_maturity": "ecosystem maturity",
    "dev_speed": "dev speed",
    "long_term_maintenance": "long-term maintenance",
    "oss_only": "no paid license needed",
    "binary_native_aot": "NativeAOT support",
    "threading_quality": "first-class threading model",
}


# ---------------------------------------------------------------------------
# Requirements parsing
# ---------------------------------------------------------------------------


@dataclass
class Requirements:
    """Structured requirements used to score each framework."""

    target_os: list = field(default_factory=list)  # [(os, arch), ...]
    team_languages: list = field(default_factory=list)
    hardware_access: str = "none"  # none | sendinput | raw_input | usb_serial
    web_ui_required: bool = False
    exe_size_budget: str = "no_limit"  # tiny | small | no_limit
    cold_start_budget: str = "no_limit"  # fast | no_limit
    native_look_required: str = "none"  # win11 | macos | linux | any_native | none
    distribution: str = "any"  # any | portable_exe | installer | store | auto_update
    store_distribution: bool = False
    auto_update_required: bool = False
    oss_only: bool = True
    maintenance_horizon: str = "indefinite"  # one_shot | 6_months | 12_months | indefinite
    dev_speed_priority: str = "medium"  # low | medium | high

    @classmethod
    def from_dict(cls, d):
        tos = d.get("target_os", [])
        parsed_tos = []
        for entry in tos:
            if isinstance(entry, str):
                parsed_tos.append(("windows", entry))
            elif isinstance(entry, list | tuple) and len(entry) == 2:
                parsed_tos.append((entry[0], entry[1]))
            elif isinstance(entry, dict) and "os" in entry and "arch" in entry:
                parsed_tos.append((entry["os"], entry["arch"]))
        return cls(
            target_os=parsed_tos,
            team_languages=d.get("team_languages", []) or [],
            hardware_access=d.get("hardware_access", "none"),
            web_ui_required=bool(d.get("web_ui_required", False)),
            exe_size_budget=d.get("exe_size_budget", "no_limit"),
            cold_start_budget=d.get("cold_start_budget", "no_limit"),
            native_look_required=d.get("native_look_required", "none"),
            distribution=d.get("distribution", "any"),
            store_distribution=bool(d.get("store_distribution", False)),
            auto_update_required=bool(d.get("auto_update_required", False)),
            oss_only=bool(d.get("oss_only", True)),
            maintenance_horizon=d.get("maintenance_horizon", "indefinite"),
            dev_speed_priority=d.get("dev_speed_priority", "medium"),
        )


def derive_weights(req):
    """Convert a Requirements brief into a weight map (one weight per dimension)."""
    w = {d: 0.0 for d in DIMS}
    want_win = any(os == "windows" for os, _ in req.target_os)
    want_mac = any(os == "macos" for os, _ in req.target_os)
    want_lin = any(os == "linux" for os, _ in req.target_os)

    if want_win:
        w["windows_support"] = 1.0
    if want_mac:
        w["macos_support"] = 1.0
    if want_lin:
        w["linux_support"] = 1.0

    for _, arch in req.target_os:
        if arch == "x64":
            if want_win:
                w["win_x64_arch"] = 1.0
            if want_mac:
                w["macos_x64_arch"] = 1.0
            if want_lin:
                w["linux_x64_arch"] = 1.0
        elif arch == "arm64":
            if want_win:
                w["win_arm64_arch"] = 1.0
            if want_mac:
                w["macos_arm64_arch"] = 1.0
            if want_lin:
                w["linux_arm64_arch"] = 1.0
        elif arch == "x86":
            if want_win:
                w["win_x86_arch"] = 1.0

    n_os = sum([want_win, want_mac, want_lin])
    if n_os >= 2:
        for d in ("windows_support", "macos_support", "linux_support"):
            w[d] = max(w[d], 0.7)

    if req.hardware_access in ("sendinput", "raw_input"):
        w["sendinput_friendly"] = 1.0
        w["win32_interop"] = 0.7
    if req.hardware_access == "usb_serial":
        w["usb_serial_access"] = 1.0
        w["win32_interop"] = 0.7

    if req.web_ui_required:
        w["web_ui_support"] = 1.0

    if req.exe_size_budget == "tiny":
        w["exe_size_tiny"] = 1.0
        w["exe_size_small"] = 0.5
    elif req.exe_size_budget == "small":
        w["exe_size_small"] = 1.0

    if req.cold_start_budget == "fast":
        w["cold_start_fast"] = 1.0

    nl = req.native_look_required
    if nl == "win11":
        w["native_look_win11"] = 1.0
    elif nl == "macos":
        w["native_look_macos"] = 1.0
    elif nl == "linux":
        w["native_look_linux"] = 1.0
    elif nl == "any_native":
        w["native_look_win11"] = 0.7
        w["native_look_macos"] = 0.7
        w["native_look_linux"] = 0.7

    if req.distribution == "portable_exe" or req.exe_size_budget == "tiny":
        w["single_file_output"] = 1.0
    if req.distribution == "installer":
        w["auto_update"] = 0.5
    if req.store_distribution or req.distribution == "store":
        w["store_distribution"] = 1.0
    if req.auto_update_required:
        w["auto_update"] = 1.0

    if req.oss_only:
        w["oss_only"] = 0.7

    if req.maintenance_horizon in ("indefinite", "12_months"):
        w["long_term_maintenance"] = 1.0
    elif req.maintenance_horizon == "6_months":
        w["long_term_maintenance"] = 0.5

    if req.dev_speed_priority == "high":
        w["dev_speed"] = 1.0
    elif req.dev_speed_priority == "medium":
        w["dev_speed"] = 0.5

    w["ecosystem_maturity"] = max(w["ecosystem_maturity"], 0.4)
    w["threading_quality"] = max(w["threading_quality"], 0.3)

    # Team language match: applied at score_all() time, not as a single weight
    # (because each framework matches different languages). The score_all loop
    # reads this flag and applies a per-language boost.
    if req.team_languages:
        w["team_languages_present"] = 1.0
    return w


def team_match_boost(name: str, team_languages: list[str]) -> float:
    """Return a [0, 1] score for how well a framework matches known team languages.

    1.0 = primary language match, 0.5 = acceptable secondary match, 0.0 = no match.
    """
    if not team_languages:
        return 0.0
    langs = FRAMEWORK_LANGUAGES.get(name, ())
    # First language is the primary. Give it full credit.
    if team_languages[0] in langs:
        return 1.0
    # Other listed languages are acceptable but secondary.
    for lang in team_languages[1:]:
        if lang in langs:
            return 0.6
    return 0.0


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


@dataclass
class Score:
    name: str
    total: float
    weighted_dimensions: list

    def top_reasons(self, k: int = 3):
        positives = sorted(
            [(d, c) for d, _, c in self.weighted_dimensions if c > 0],
            key=lambda x: x[1],
            reverse=True,
        )
        return [d for d, _ in positives[:k]]

    def top_blockers(self, k: int = 3):
        negatives = sorted(
            [(d, c) for d, _, c in self.weighted_dimensions if c < 0],
            key=lambda x: x[1],
        )
        return [d for d, _ in negatives[:k]]


def score_all(req):
    """Return one Score per framework, sorted by total descending."""
    weights = derive_weights(req)
    has_team = bool(req.team_languages)
    team_weight = weights.get("team_languages_present", 0.0)
    scores = []
    for name, dims in FRAMEWORKS.items():
        contribs = []
        total = 0.0
        weight_sum = 0.0
        for d in DIMS:
            weight = weights.get(d, 0.0)
            dim_score = dims.get(d, 0.0)
            contrib = weight * dim_score
            contribs.append((d, weight, contrib))
            total += contrib
            weight_sum += weight
        # Apply team-language boost as a flat additive contribution.
        if has_team and team_weight > 0:
            boost = team_match_boost(name, req.team_languages)
            team_contrib = team_weight * boost
            contribs.append(("team_languages", team_weight, team_contrib))
            total += team_contrib
            weight_sum += team_weight
        norm = max(0.0, total / weight_sum) * 100.0 if weight_sum > 0 else 0.0
        scores.append(Score(name=name, total=norm, weighted_dimensions=contribs))
    scores.sort(key=lambda s: s.total, reverse=True)
    return scores


RATIONALES = {
    "wpf": "Best Windows-only choice for data-heavy MVVM apps with Win32 interop.",
    "winforms": "Smallest possible EXE in .NET (NativeAOT-compatible) for tool-style apps.",
    "winui3": "Modern Windows 11 Fluent look; required for Microsoft Store submission.",
    "avalonia": "Cross-platform .NET with XAML; closest to WPF if you need macOS/Linux too.",
    "maui": "Single .NET codebase across Windows + macOS + iOS + Android (mobile out of scope here).",
    "tkinter": "Zero-install Python, ships in the stdlib; ideal for solo indie tooling.",
    "pyside6": "Polished Qt 6 widgets for Python; charts, data grids, professional dashboards.",
    "py_gtk": "Native on Linux desktops; weaker on Windows/macOS.",
    "tauri": "Smallest cross-platform EXE; web frontend with Rust backend for performance.",
    "electron": "Mature cross-platform when bundle size and cold start don't matter.",
    "neutralino": "Tiny TS-based alternative to Electron; uses system WebView (no Chromium).",
    "qt6": "Mature cross-platform UI when you also need deep OS access (USB, hardware).",
    "win32_mfc": "Smallest possible Windows EXE; pick when ActiveX/OLE or minimum binary size is mandatory.",
    "wails": "Go backend with web frontend; lighter than Electron.",
    "fyne": "Pure-Go native widgets; best cross-platform Go choice for simple UIs.",
    "gio": "Immediate-mode GPU-driven UI; great for tools with heavy rendering.",
    "walk": "Windows-only native Go UI; smallest Go option for Win32 tools.",
    "compose_multiplatform": "Modern declarative UI shared across Windows / macOS / Linux; expect some rough edges.",
    "javafx": "Pick if the team is already a JVM shop and you want charts + 3D.",
    "tornadofx": "Kotlin DSL on JavaFX; good for JVM shops that prefer Kotlin syntax.",
    "flutter": "Single Dart codebase across Windows / macOS / Linux; weaker native input story.",
    "slint": "Small Rust UI with declarative markup; good balance of size and polish.",
    "egui": "Immediate-mode Rust UI; tiny binaries and fast iteration for tools.",
    "swiftui": "Apple-first; Windows is functional but second-class.",
}


def one_line_rationale(name, req):
    return RATIONALES.get(name, "")


def explain_top(scores, req):
    """Render the top-N with human-readable rationale."""
    top = scores[:3]
    lines = []
    lines.append("Framework auto-selection (deep analysis)")
    lines.append("=" * 60)
    tos_str = ", ".join(f"{os}-{arch}" for os, arch in req.target_os) or "(unspecified)"
    lines.append(f"Target OS / arch    : {tos_str}")
    lines.append(f"Team languages      : {', '.join(req.team_languages) or '(unspecified)'}")
    lines.append(f"Distribution shape  : {req.distribution}")
    lines.append(f"Hardware access     : {req.hardware_access}")
    lines.append(f"Web UI              : {'yes' if req.web_ui_required else 'no'}")
    lines.append(f"EXE size budget     : {req.exe_size_budget}")
    lines.append(f"Cold start budget   : {req.cold_start_budget}")
    lines.append(f"Native look needed  : {req.native_look_required}")
    lines.append(f"Store               : {'yes' if req.store_distribution else 'no'}")
    lines.append(f"Auto-update needed  : {'yes' if req.auto_update_required else 'no'}")
    lines.append(f"OSS only            : {'yes' if req.oss_only else 'no'}")
    lines.append(f"Maintenance horizon : {req.maintenance_horizon}")
    lines.append("")

    for i, sc in enumerate(top, 1):
        display = DISPLAY_NAMES.get(sc.name, sc.name)
        lines.append(f"#{i}  {display}    score = {sc.total:5.1f} / 100")
        reasons = sc.top_reasons(2)
        if reasons:
            lines.append("     + " + ", ".join(HUMAN_DIM.get(r, r) for r in reasons))
        blockers = sc.top_blockers(2)
        if blockers:
            lines.append("     - " + ", ".join(HUMAN_DIM.get(b, b) for b in blockers))
        line = one_line_rationale(sc.name, req)
        if line:
            lines.append("     > " + line)
        lines.append("")

    lines.append("(See references/framework_matrix.md for the full pros/cons of each pick.)")
    return "\n".join(lines)


def load_brief(path):
    """Load a JSON or simple YAML brief from path or stdin."""
    text = sys.stdin.read() if path is None else Path(path).read_text(encoding="utf-8-sig")
    if text.startswith("\ufeff"):
        text = text[1:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        out = {}
        for line in text.splitlines():
            line = line.split("#", 1)[0].rstrip()
            if not line or line.startswith(" ") or line.startswith("\t"):
                continue
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            value = value.strip()
            if not value:
                continue
            if value.startswith("[") and value.endswith("]"):
                try:
                    out[key.strip()] = json.loads(value)
                except json.JSONDecodeError:
                    inner = value[1:-1].strip()
                    out[key.strip()] = (
                        [v.strip().strip("\"'") for v in inner.split(",")] if inner else []
                    )
            elif value.lower() in ("true", "false"):
                out[key.strip()] = value.lower() == "true"
            elif value.lower() in ("null", "none", "~"):
                out[key.strip()] = None
            else:
                out[key.strip()] = value.strip().strip("\"'")
        return out


def validate_tables() -> list[str]:
    """Structural invariant checks for the scoring tables and toolchain map."""
    errors: list[str] = []
    dims = set(DIMS)
    for name, dims_map in FRAMEWORKS.items():
        if set(dims_map) != dims:
            missing = sorted(dims - set(dims_map))
            extra = sorted(set(dims_map) - dims)
            if missing:
                errors.append(f"{name}: missing dimensions {missing}")
            if extra:
                errors.append(f"{name}: extra dimensions {extra}")
        for dim, value in dims_map.items():
            if not isinstance(value, int | float) or not -1.0 <= value <= 1.0:
                errors.append(f"{name}.{dim}: score {value!r} outside [-1, 1]")

    for table_name, table in (
        ("FRAMEWORK_LANGUAGES", FRAMEWORK_LANGUAGES),
        ("DISPLAY_NAMES", DISPLAY_NAMES),
        ("RATIONALES", RATIONALES),
    ):
        missing = sorted(set(FRAMEWORKS) - set(table))
        extra = sorted(set(table) - set(FRAMEWORKS))
        if missing:
            errors.append(f"{table_name}: missing frameworks {missing}")
        if extra:
            errors.append(f"{table_name}: extra frameworks {extra}")

    try:
        toolchain_map = json.loads(
            (Path(__file__).resolve().parent / "toolchain_map.json").read_text(encoding="utf-8")
        )
        missing = sorted(set(FRAMEWORKS) - set(toolchain_map.get("framework_toolchains", {})))
        if missing:
            errors.append(f"toolchain_map.json: missing framework keys {missing}")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"toolchain_map.json unreadable: {exc}")
    return errors


def self_test():
    """Regression test: verify canonical requirements produce expected picks."""
    with tempfile.TemporaryDirectory() as tmp:
        brief_path = Path(tmp) / "brief.yaml"
        brief_path.write_text(
            'target_os: [["windows", "x64"], ["macos", "arm64"]]\n'
            "team_languages: [python, csharp]\n"
            "web_ui_required: false\n",
            encoding="utf-8",
        )
        loaded = load_brief(brief_path)
        if loaded.get("target_os") != [["windows", "x64"], ["macos", "arm64"]]:
            print("  [FAIL] yaml brief load: nested target_os")
            return 1
        if loaded.get("team_languages") != ["python", "csharp"]:
            print("  [FAIL] yaml brief load: team_languages")
            return 1
        if loaded.get("web_ui_required") is not False:
            print("  [FAIL] yaml brief load: bool")
            return 1
        print("  [OK]   yaml brief load")

        bom_path = Path(tmp) / "brief-bom.json"
        bom_path.write_text(
            "\ufeff" + json.dumps({"target_os": [["windows", "x64"]]}),
            encoding="utf-8",
        )
        bom_loaded = load_brief(bom_path)
        assert bom_loaded.get("target_os") == [["windows", "x64"]]
        print("  [OK]   bom json brief load")

        arch_req = Requirements.from_dict({"target_os": [["macos", "x64"], ["linux", "x64"]]})
        arch_weights = derive_weights(arch_req)
        assert arch_weights["macos_x64_arch"] == 1.0
        assert arch_weights["linux_x64_arch"] == 1.0
        assert arch_weights["macos_arm64_arch"] == 0.0
        assert arch_weights["linux_arm64_arch"] == 0.0
        print("  [OK]   macos/linux x64 arch weights")

    invariant_errors = validate_tables()
    for error in invariant_errors:
        print(f"  [FAIL] {error}")
    if invariant_errors:
        return 1
    print(f"  [OK]   framework tables: {len(FRAMEWORKS)} frameworks x {len(DIMS)} dimensions")

    cases = [
        # Windows-only, SendInput, C# team -> WPF (DataBinding + Win32 interop).
        (
            {
                "target_os": [["windows", "x64"]],
                "hardware_access": "sendinput",
                "team_languages": ["csharp"],
            },
            "wpf",
        ),
        # Windows-only, tiny EXE, C# team -> WinForms (NativeAOT).
        (
            {
                "target_os": [["windows", "x64"]],
                "exe_size_budget": "tiny",
                "team_languages": ["csharp"],
            },
            "winforms",
        ),
        # macOS-only, Swift team -> SwiftUI.
        (
            {"target_os": [["macos", "arm64"]], "team_languages": ["swift"]},
            "swiftui",
        ),
        # Cross-platform, web UI, small EXE, Rust team -> Tauri.
        (
            {
                "target_os": [["windows", "x64"], ["macos", "arm64"], ["linux", "x64"]],
                "web_ui_required": True,
                "exe_size_budget": "small",
                "team_languages": ["rust"],
            },
            "tauri",
        ),
        # Cross-platform, native look, C# team -> Avalonia (the cross-platform XAML).
        (
            {
                "target_os": [["windows", "x64"], ["macos", "arm64"], ["linux", "x64"]],
                "native_look_required": "any_native",
                "team_languages": ["csharp"],
            },
            "avalonia",
        ),
        # Windows-only, SendInput, Python-first team -> tkinter (PyInstaller + ctypes).
        (
            {
                "target_os": [["windows", "x64"]],
                "hardware_access": "sendinput",
                "team_languages": ["python"],
                "dev_speed_priority": "high",
            },
            "tkinter",
        ),
        # Cross-platform, web UI, JS team, no size constraint -> Electron.
        (
            {
                "target_os": [["windows", "x64"], ["macos", "arm64"], ["linux", "x64"]],
                "web_ui_required": True,
                "team_languages": ["typescript"],
            },
            "electron",
        ),
        # Windows-only, Microsoft Store -> WinUI 3.
        (
            {
                "target_os": [["windows", "x64"]],
                "store_distribution": True,
                "native_look_required": "win11",
                "team_languages": ["csharp"],
            },
            "winui3",
        ),
    ]

    failures = 0
    for i, (req_dict, expected) in enumerate(cases):
        req = Requirements.from_dict(req_dict)
        scores = score_all(req)
        winner = scores[0].name
        ok = winner == expected
        marker = "OK" if ok else "FAIL"
        print(f"  [{marker}] case {i + 1}: expected {expected!r:24} got {winner!r}")
        if not ok:
            failures += 1
    if failures:
        print(f"\n{failures} self-test case(s) failed.")
        return 1
    print("\nAll self-test cases passed.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Deep-analysis framework auto-selector.")
    parser.add_argument(
        "brief", nargs="?", help="Path to a JSON or YAML requirements brief. Use - for stdin."
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON instead of text."
    )
    parser.add_argument(
        "--self-test", action="store_true", help="Run built-in regression cases and exit."
    )
    parser.add_argument(
        "--top", type=int, default=3, help="How many frameworks to surface (default 3)."
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    brief_path = None if args.brief in (None, "-") else args.brief
    brief = load_brief(brief_path)
    req = Requirements.from_dict(brief)
    scores = score_all(req)
    scores = scores[: args.top]

    if args.json:
        out = {
            "requirements": brief,
            "ranked": [
                {
                    "framework": s.name,
                    "display_name": DISPLAY_NAMES.get(s.name, s.name),
                    "score": round(s.total, 2),
                    "rationale": one_line_rationale(s.name, req),
                    "top_reasons": [HUMAN_DIM.get(d, d) for d in s.top_reasons(5)],
                    "top_blockers": [HUMAN_DIM.get(d, d) for d in s.top_blockers(5)],
                }
                for s in scores
            ],
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(explain_top(scores, req))
    return 0


if __name__ == "__main__":
    sys.exit(main())
