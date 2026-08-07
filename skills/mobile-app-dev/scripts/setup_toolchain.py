"""setup_toolchain.py -- check or install the toolchain for a framework.

Usage:
  python scripts/setup_toolchain.py --framework flutter
  python scripts/setup_toolchain.py --requirements requirements.json --check-only
  python scripts/setup_toolchain.py --framework tauri --install

The default mode only checks what is installed. Pass --install to run the
generated install commands, which may require administrator privileges.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from select_framework import select_framework


FRAMEWORK_KEYS = {
    "flutter": "flutter",
    "react native": "react-native",
    "kotlin + compose": "compose",
    "swift + swiftui": "swiftui",
    ".net maui": "maui",
    "kotlin multiplatform": "kmp",
    "capacitor": "capacitor",
    "tauri": "tauri",
}

TOOLCHAINS = {
    "flutter": {
        "name": "Flutter",
        "tools": ["git", "flutter", "java", "android sdk"],
        "notes": "Xcode is also required for iOS builds on macOS.",
    },
    "react-native": {
        "name": "React Native",
        "tools": ["node", "npm", "java", "android sdk"],
        "notes": "Xcode is also required for iOS builds on macOS.",
    },
    "compose": {
        "name": "Jetpack Compose",
        "tools": ["java", "android sdk"],
        "notes": "Android Studio is the recommended IDE.",
    },
    "swiftui": {
        "name": "Swift + SwiftUI",
        "tools": ["xcode"],
        "notes": "SwiftUI requires macOS and Xcode.",
    },
    "maui": {
        "name": ".NET MAUI",
        "tools": ["dotnet", "java", "android sdk"],
        "notes": "Run 'dotnet workload install maui' after installing the SDK.",
    },
    "kmp": {
        "name": "Kotlin Multiplatform",
        "tools": ["java", "android sdk"],
        "notes": "Xcode is also required for iOS targets on macOS.",
    },
    "capacitor": {
        "name": "Capacitor",
        "tools": ["node", "npm", "java", "android sdk"],
        "notes": "Xcode is also required for iOS builds on macOS.",
    },
    "tauri": {
        "name": "Tauri Mobile",
        "tools": ["node", "npm", "cargo", "java", "android sdk"],
        "notes": "Xcode is also required for iOS builds on macOS.",
    },
}


def framework_key(framework: str) -> str:
    normalized = framework.strip().lower()
    if normalized in FRAMEWORK_KEYS:
        return FRAMEWORK_KEYS[normalized]
    for alias, key in FRAMEWORK_KEYS.items():
        if alias in normalized:
            return key
    raise ValueError(f"Unsupported framework: {framework}")


def _which(name: str) -> str | None:
    return shutil.which(name)


def _android_sdk_path() -> Path | None:
    for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = os.environ.get(env)
        if value and Path(value).exists():
            return Path(value)
    system = platform.system()
    candidates = []
    if system == "Windows":
        candidates.append(Path.home() / "AppData" / "Local" / "Android" / "Sdk")
    elif system == "Darwin":
        candidates.append(Path.home() / "Library" / "Android" / "sdk")
    else:
        candidates.append(Path.home() / "Android" / "Sdk")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _tool_status(name: str) -> bool:
    if name == "android sdk":
        return _android_sdk_path() is not None
    if name == "xcode":
        if platform.system() != "Darwin":
            return False
        return _which("xcodebuild") is not None or Path("/Applications/Xcode.app").exists()
    return _which(name) is not None


def _windows_install_commands(key: str) -> list[str]:
    commands = []
    if key in {"flutter", "react-native", "compose", "kmp", "capacitor", "tauri", "maui"}:
        commands.append("winget install --id EclipseAdoptium.Temurin.17.JDK --accept-package-agreements --accept-source-agreements")
    if key in {"react-native", "capacitor", "tauri"}:
        commands.append("winget install --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements")
    if key in {"compose", "kmp", "react-native", "capacitor", "tauri"}:
        commands.append("winget install --id Google.AndroidStudio --accept-package-agreements --accept-source-agreements")
    if key == "flutter":
        commands.append("git clone -b stable https://github.com/flutter/flutter.git \"%USERPROFILE%\\flutter\"")
        commands.append("\"%USERPROFILE%\\flutter\\bin\\flutter\" doctor")
    if key == "maui":
        commands.append("winget install --id Microsoft.DotNet.SDK.8 --accept-package-agreements --accept-source-agreements")
        commands.append("dotnet workload install maui")
    if key == "tauri":
        commands.append("winget install --id Rustlang.Rustup --accept-package-agreements --accept-source-agreements")
    return commands


def _macos_install_commands(key: str) -> list[str]:
    commands = []
    if key in {"flutter", "react-native", "compose", "kmp", "capacitor", "tauri", "maui"}:
        commands.append("brew install --cask temurin@17")
    if key in {"react-native", "capacitor", "tauri"}:
        commands.append("brew install node")
    if key in {"compose", "kmp", "react-native", "capacitor", "tauri"}:
        commands.append("brew install --cask android-studio")
    if key in {"swiftui", "flutter", "react-native", "kmp", "capacitor", "tauri"}:
        commands.append("xcode-select --install")
    if key == "flutter":
        commands.append("git clone -b stable https://github.com/flutter/flutter.git \"$HOME/flutter\"")
        commands.append("\"$HOME/flutter/bin/flutter\" doctor")
    if key == "maui":
        commands.append("brew install --cask dotnet-sdk")
        commands.append("dotnet workload install maui")
    if key == "tauri":
        commands.append("brew install rustup-init")
        commands.append("rustup-init -y")
    return commands


def _linux_install_commands(key: str) -> list[str]:
    commands = []
    if key in {"flutter", "react-native", "compose", "kmp", "capacitor", "tauri", "maui"}:
        commands.append("sudo apt-get update && sudo apt-get install -y openjdk-17-jdk git unzip curl")
    if key in {"react-native", "capacitor", "tauri"}:
        commands.append("curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - && sudo apt-get install -y nodejs")
    if key in {"compose", "kmp", "react-native", "capacitor", "tauri"}:
        commands.append("mkdir -p \"$HOME/Android/cmdline-tools\" && curl -fsSL https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip -o /tmp/cmdline-tools.zip")
        commands.append("unzip -q /tmp/cmdline-tools.zip -d \"$HOME/Android/cmdline-tools\"")
        commands.append("\"$HOME/Android/cmdline-tools/cmdline-tools/bin/sdkmanager\" --install \"platform-tools\" \"platforms;android-34\"")
    if key == "flutter":
        commands.append("git clone -b stable https://github.com/flutter/flutter.git \"$HOME/flutter\"")
        commands.append("\"$HOME/flutter/bin/flutter\" doctor")
    if key == "maui":
        commands.append("curl -fsSL https://dot.net/v1/dotnet-install.sh | bash")
        commands.append("dotnet workload install maui")
    if key == "tauri":
        commands.append("curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y")
    return commands


def install_commands(key: str) -> list[str]:
    system = platform.system()
    if system == "Windows":
        return _windows_install_commands(key)
    if system == "Darwin":
        return _macos_install_commands(key)
    return _linux_install_commands(key)


def plan_toolchain(framework: str) -> dict:
    key = framework_key(framework)
    spec = TOOLCHAINS[key]
    tools = [
        {"name": name, "installed": _tool_status(name)}
        for name in spec["tools"]
    ]
    missing = [tool["name"] for tool in tools if not tool["installed"]]
    return {
        "framework": key,
        "framework_name": spec["name"],
        "platform": platform.system(),
        "tools": tools,
        "missing": missing,
        "notes": spec["notes"],
        "install_commands": install_commands(key),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check or install mobile toolchains.")
    parser.add_argument("--framework", help="framework key or Step 1.5 result")
    parser.add_argument("--requirements", help="requirements.json used for auto-selection")
    parser.add_argument("--check-only", action="store_true", help="only report status (default)")
    parser.add_argument("--install", action="store_true", help="run install commands")
    parser.add_argument("--dry-run", action="store_true", help="print commands without running")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)

    if args.framework:
        framework = args.framework
    elif args.requirements:
        req = json.loads(Path(args.requirements).read_text(encoding="utf-8"))
        framework = select_framework(req)["selected_framework"]
    else:
        parser.error("pass --framework or --requirements")

    plan = plan_toolchain(framework)
    if args.json:
        json.dump(plan, sys.stdout, indent=2)
        print()
        return 0

    print(f"Framework: {plan['framework_name']} ({plan['framework']})")
    print(f"Platform: {plan['platform']}")
    for tool in plan["tools"]:
        status = "OK" if tool["installed"] else "MISSING"
        print(f"  [{status}] {tool['name']}")
    if plan["notes"]:
        print(f"Note: {plan['notes']}")
    if plan["missing"]:
        print(f"Missing: {', '.join(plan['missing'])}")

    if args.install or args.dry_run:
        for command in plan["install_commands"]:
            if args.dry_run:
                print(f"  would run: {command}")
            else:
                print(f"  running: {command}")
                result = subprocess.run(command, shell=True)
                if result.returncode != 0:
                    print(f"  command failed: {command}")
                    return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
