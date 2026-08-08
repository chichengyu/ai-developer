#!/usr/bin/env bash
# smoke_macos.sh -- runnable smoke test for the macOS-side scripts in
# this skill. Designed for `macos-latest` GitHub Actions runners but
# runnable on any macOS host with bash + python3.
#
# Tests:
#   1. bash shell-script syntax (`bash -n`) for build_dmg.sh.
#   2. PowerShell script parse (`pwsh -NoProfile -Command`) for
#      build_macos.ps1 -- requires PowerShell on macOS, install via
#      `brew install --cask powershell` or skip if absent.
#   3. Python module import + const-table sanity for sendinput_macos.py
#      and window_enum_macos.py. They load their framework libraries
#      lazily, so this should NOT require a GUI session.
#   4. Swift syntax check (`swift -parse`) for threading_dispatch.swift
#      and auto_update_sparkle.swift. Skipped if no `swift` toolchain.
#   5. Python AST parse for any .py files in scripts/.
#
# Exits non-zero on any failure so CI fails the PR.

set -uo pipefail
SKILL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS="$SKILL_ROOT/scripts"
PASSES=0
FAILS=0
FAILED_TESTS=()

run() {
    local name="$1"; shift
    if "$@"; then
        echo "  [OK]   $name"
        PASSES=$((PASSES + 1))
    else
        echo "  [FAIL] $name"
        FAILS=$((FAILS + 1))
        FAILED_TESTS+=("$name")
    fi
}

echo "=== smoke_macos.sh ==="
echo "Skill root: $SKILL_ROOT"
echo ""

# 1. Bash syntax check
echo "--- bash syntax ---"
if [[ -f "$SCRIPTS/build_dmg.sh" ]]; then
    run "build_dmg.sh bash -n" bash -n "$SCRIPTS/build_dmg.sh"
else
    echo "  [SKIP] build_dmg.sh not found"
fi

# 2. PowerShell parse (optional)
echo ""
echo "--- powershell parse ---"
if command -v pwsh >/dev/null 2>&1; then
    run "all .ps1 parse" pwsh -NoProfile -Command "
        \$errors = @()
        Get-ChildItem -Path '$SKILL_ROOT' -Recurse -Filter '*.ps1' | ForEach-Object {
            \$e = \$null
            [System.Management.Automation.Language.Parser]::ParseFile(\$_.FullName, [ref]\$null, [ref]\$e) | Out-Null
            if (\$e) { \$errors += \$e }
        }
        if (\$errors.Count -gt 0) { \$errors | Out-String; exit 1 } else { exit 0 }
    "
else
    echo "  [SKIP] pwsh not installed (brew install --cask powershell)"
fi

# 3. Python import + const table
echo ""
echo "--- python imports ---"
if command -v python3 >/dev/null 2>&1; then
    run "sendinput_macos.py VK table" python3 -c "
import sys; sys.path.insert(0, '$SCRIPTS')
import importlib.util
spec = importlib.util.spec_from_file_location('si_macos', '$SCRIPTS/sendinput_macos.py')
m = importlib.util.module_from_spec(spec)
# We don't execute the ctypes LoadLibrary calls at import (they would
# fail on a non-macOS host); just parse and inspect VK table.
import ast
tree = ast.parse(open('$SCRIPTS/sendinput_macos.py', encoding='utf-8').read())
vk_names = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Assign) and any(
        (isinstance(t, ast.Name) and t.id == 'VK')
        for t in node.targets
    ):
        if isinstance(node.value, ast.Dict):
            vk_names = {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
assert 'f5' in vk_names, 'f5 missing'
assert 'left' in vk_names, 'left missing'
assert 'enter' in vk_names, 'enter missing'
assert 'lcmd' in vk_names, 'lcmd missing (macOS-specific)'
assert len(vk_names) >= 70, f'expected >= 70 VKs, got {len(vk_names)}'
print(f'  sendinput_macos.py: {len(vk_names)} VK entries')
"
    run "window_enum_macos.py parse" python3 -c "
import ast
ast.parse(open('$SCRIPTS/window_enum_macos.py', encoding='utf-8').read())
"
else
    echo "  [SKIP] python3 not installed"
fi

# 4. Swift syntax check (optional)
echo ""
echo "--- swift syntax ---"
if command -v swift >/dev/null 2>&1; then
    for f in threading_dispatch.swift auto_update_sparkle.swift; do
        if [[ -f "$SCRIPTS/$f" ]]; then
            run "$f swift -parse" swift -parse "$SCRIPTS/$f"
        fi
    done
else
    echo "  [SKIP] swift toolchain not installed (xcode-select --install)"
fi

# 5. Python AST parse all .py
echo ""
echo "--- python AST parse all .py in scripts/ ---"
if command -v python3 >/dev/null 2>&1; then
    for f in "$SCRIPTS"/*.py; do
        [[ -f "$f" ]] || continue
        bn="$(basename "$f")"
        run "$bn ast.parse" python3 -c "import ast; ast.parse(open(r'$f', encoding='utf-8').read())"
    done
    echo ""
    echo "--- python AST parse all .py in examples/ ---"
    while IFS= read -r f; do
        [[ -f "$f" ]] || continue
        bn="${f#"$SKILL_ROOT"/}"
        run "$bn ast.parse" python3 -c "import ast; ast.parse(open(r'$f', encoding='utf-8').read())"
    done < <(find "$SKILL_ROOT/examples" -type f -name '*.py' -not -path '*/__pycache__/*' | sort)
fi

# 6. Python structural + media tests
echo ""
echo "--- python structural + media tests ---"
if command -v python3 >/dev/null 2>&1; then
    run "test_docs.py" python3 "$SKILL_ROOT/tests/test_docs.py"
    run "test_media_pipeline.py" python3 "$SKILL_ROOT/tests/test_media_pipeline.py"
    run "test_no_bom.py" python3 "$SKILL_ROOT/tests/test_no_bom.py"
fi

# 7. Arch awareness (optional, requires PowerShell)
echo ""
echo "--- arch awareness ---"
if command -v pwsh >/dev/null 2>&1; then
    run "test_arch_awareness.ps1" pwsh -NoProfile -ExecutionPolicy Bypass -File "$SKILL_ROOT/tests/test_arch_awareness.ps1"
else
    echo "  [SKIP] pwsh not installed"
fi

# Summary
echo ""
echo "=== Summary ==="
echo "  Passed: $PASSES"
echo "  Failed: $FAILS"
if [[ $FAILS -gt 0 ]]; then
    echo "  Failed tests:"
    for t in "${FAILED_TESTS[@]}"; do echo "    - $t"; done
    exit 1
fi
exit 0
