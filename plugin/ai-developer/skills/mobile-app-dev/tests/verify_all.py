"""verify_all.py -- run all smoke tests in this skill and report."""
import subprocess, sys
from pathlib import Path

tests_dir = Path(__file__).parent
tests = sorted(tests_dir.glob("test_*.py"))

failures = []
for t in tests:
    r = subprocess.run(
        [sys.executable, str(t)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    ok = r.returncode == 0
    status = "OK" if ok else "FAIL"
    stdout_lines = (r.stdout or "").strip().splitlines()
    stderr_lines = (r.stderr or "").strip().splitlines()
    msg = stdout_lines[-1] if stdout_lines else (stderr_lines[-1] if stderr_lines else "(no output)")
    print(f"  [{status}] {t.name}: {msg}")
    if not ok:
        failures.append(t.name)

print(f"\n{len(tests) - len(failures)}/{len(tests)} tests passed")
sys.exit(1 if failures else 0)
