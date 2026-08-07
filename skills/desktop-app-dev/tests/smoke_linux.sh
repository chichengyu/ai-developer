#!/usr/bin/env bash
# smoke_linux.sh -- runnable smoke test for the Linux-side scripts in
# this skill. Designed for `ubuntu-latest` GitHub Actions runners but
# runnable on any Linux host with bash + python3.
#
# Tests:
#   1. bash shell-script syntax (`bash -n`) for build_appimage.sh and
#      build_deb.sh.
#   2. PowerShell script parse (if pwsh is installed; skipped otherwise).
#   3. Python module + const-table sanity for sendinput_linux.py and
#      window_enum_linux.py. They call `ctypes.cdll.LoadLibrary("libX11...")`
#      lazily; on a headless Linux runner the lib may be absent, so we
#      inspect the AST rather than executing the file.
#   4. Python AST parse for all .py in scripts/.
#
# Exits non-zero on any failure.

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

echo "=== smoke_linux.sh ==="
echo "Skill root: $SKILL_ROOT"
echo ""

# 1. Bash syntax
echo "--- bash syntax ---"
for f in build_appimage.sh build_deb.sh; do
    if [[ -f "$SCRIPTS/$f" ]]; then
        run "$f bash -n" bash -n "$SCRIPTS/$f"
    fi
done

# 2. PowerShell parse (optional, skipped on minimal images)
echo ""
echo "--- powershell parse ---"
if command -v pwsh >/dev/null 2>&1; then
    for f in build_linux.ps1 build_dotnet.ps1 build_electron.ps1; do
        if [[ -f "$SCRIPTS/$f" ]]; then
            run "$f pwsh parse" pwsh -NoProfile -Command "
                \$errors = \$null; \$null = [System.Management.Automation.Language.Parser]::ParseFile(
                    '$SCRIPTS/$f', [ref]\$null, [ref]\$errors);
                if (\$errors) { \$errors | Out-String; exit 1 } else { exit 0 }
            "
        fi
    done
else
    echo "  [SKIP] pwsh not installed (sudo apt install powershell)"
fi

# 3. Python import + const table
echo ""
echo "--- python AST checks ---"
if command -v python3 >/dev/null 2>&1; then
    run "sendinput_linux.py XK table" python3 -c "
import ast
tree = ast.parse(open('$SCRIPTS/sendinput_linux.py', encoding='utf-8').read())
xk_names = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Assign) and any(
        (isinstance(t, ast.Name) and t.id == 'XK')
        for t in node.targets
    ):
        if isinstance(node.value, ast.Dict):
            xk_names = {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
assert 'f5' in xk_names, 'f5 missing'
assert 'left' in xk_names, 'left missing'
assert 'enter' in xk_names, 'enter missing'
assert 'control_l' in xk_names, 'control_l missing (X11-specific)'
assert 'super_l' in xk_names, 'super_l missing (X11-specific)'
assert len(xk_names) >= 70, f'expected >= 70 XKs, got {len(xk_names)}'
print(f'  sendinput_linux.py: {len(xk_names)} XK entries')
"
    run "window_enum_linux.py parse" python3 -c "
import ast
ast.parse(open('$SCRIPTS/window_enum_linux.py', encoding='utf-8').read())
"
    run "threading_glib.py parse" python3 -c "
import ast
ast.parse(open('$SCRIPTS/threading_glib.py', encoding='utf-8').read())
"
else
    echo "  [SKIP] python3 not installed"
fi

# 4. Python AST parse all .py
echo ""
echo "--- python AST parse all .py in scripts/ ---"
if command -v python3 >/dev/null 2>&1; then
    for f in "$SCRIPTS"/*.py; do
        [[ -f "$f" ]] || continue
        bn="$(basename "$f")"
        run "$bn ast.parse" python3 -c "import ast; ast.parse(open(r'$f', encoding='utf-8').read())"
    done
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