#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Java Compiler - Auto compile verification for Maven/Gradle projects.
Auto-detects build tool, runs compilation, parses errors with file:line info.
Usage:
  python java_compiler.py --path /path/to/project
  python java_compiler.py --path /path/to/project --build-tool maven --verbose
"""
import os, json, subprocess, sys, argparse
from pathlib import Path

def detect_build_tool(project_path):
    pp = Path(project_path)
    if (pp / "pom.xml").exists(): return "maven", str(pp / "pom.xml")
    if (pp / "build.gradle").exists() or (pp / "build.gradle.kts").exists():
        bg = "build.gradle" if (pp / "build.gradle").exists() else "build.gradle.kts"
        return "gradle", str(pp / bg)
    return None, None

def find_jdk():  # windows or linux
    java_home = os.environ.get("JAVA_HOME", "")
    if java_home:
        javac = Path(java_home) / "bin" / "javac.exe" if os.name == "nt" else Path(java_home) / "bin" / "javac"
        if javac.exists(): return str(javac)
    for p in os.environ.get("PATH", "").split(os.pathsep):
        for name in ["javac.exe", "javac"]:
            javac = Path(p) / name
            if javac.exists(): return str(javac)
    return None

def parse_maven_errors(output):
    errors = []
    for line in output.split("\n"):
        if "[ERROR]" in line:
            parts = line.split("[ERROR]", 1)[1].strip()
            fp, rest = None, parts
            if ":" in parts and parts[0].isascii() and "\\" in parts[0] or "/" in parts[0][0:2]:
                seg = parts.split(" ", 1)
                if len(seg) >= 1 and ":" in seg[0]:
                    seg2 = seg[0].rsplit(":", 2)
                    if len(seg2) == 3:
                        try:
                            fp = {"file": seg2[0], "line": int(seg2[1]), "column": int(seg2[2])}
                            rest = seg[1] if len(seg) > 1 else ""
                        except ValueError: pass
            errors.append({
                "file": fp["file"] if fp else None,
                "line": fp["line"] if fp else None,
                "message": rest.strip()
            })
    return errors

def parse_gradle_errors(output):
    errors = []
    for line in output.split("\n"):
        if ".java:" in line and "error:" in line.lower():
            parts = line.split(":")
            if len(parts) >= 3:
                try:
                    errors.append({
                        "file": parts[0].strip(),
                        "line": int(parts[1]),
                        "message": ":".join(parts[2:]).strip()
                    })
                except ValueError: pass
    return errors

def run_compile(project_path, build_tool=None, verbose=False, extra_args=""):
    pp = Path(project_path).resolve()
    if not pp.exists():
        return {"status": "error", "message": f"Path not found: {project_path}"}
    tool, tool_file = detect_build_tool(project_path)
    if build_tool: tool = build_tool
    if not tool:
        return {"status": "error", "message": "No Maven/Gradle project (need pom.xml or build.gradle)"}
    javac = find_jdk()
    if not javac:
        return {"status": "error", "message": "JDK not found. Set JAVA_HOME or add javac to PATH."}
    result = {"status": "unknown", "project": str(pp), "build_tool": tool}
    try:
        if tool == "maven":
            cmd = f"mvn compile {'-q' if not verbose else ''} {extra_args}"
        else:
            cmd = f"gradle compileJava {'-q' if not verbose else ''} {extra_args}"
        proc = subprocess.run(cmd, shell=True, cwd=pp, capture_output=True, text=True, timeout=300)
        result["return_code"] = proc.returncode
        if proc.returncode == 0:
            result["status"] = "success"
            result["message"] = f"{tool.title()} compilation successful"
            if verbose: result["output"] = proc.stdout
        else:
            errors = parse_maven_errors(proc.stderr + proc.stdout) if tool == "maven" else parse_gradle_errors(proc.stderr + proc.stdout)
            result["status"] = "failure"
            result["errors"] = errors
            result["error_count"] = len(errors)
            result["message"] = f"Compilation failed with {len(errors)} error(s)"
    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["message"] = "Compilation timed out (300s)"
    except FileNotFoundError as e:
        result["status"] = "error"
        result["message"] = f"{tool.title()} not found. Install {tool.title()} or check PATH."
    except Exception as e:
        result["status"] = "error"
        result["message"] = str(e)
    return result

def main():
    parser = argparse.ArgumentParser(description="Java Compiler - Auto compile verification")
    parser.add_argument("--path", required=True, help="Java project root path")
    parser.add_argument("--build-tool", choices=["maven", "gradle"], help="Force build tool (auto-detect)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show full compilation output")
    parser.add_argument("--extra-args", default="", help="Extra args for build tool")
    parser.add_argument("--output", "-o", help="Save result to JSON file")
    parser.add_argument("--timing", action="store_true", help="Show compilation duration")
    parser.add_argument("--incremental", action="store_true", help="Only compile changed files")
    parser.add_argument("--git-ref", default="HEAD", help="Git ref for incremental diff (default: HEAD)")
    args = parser.parse_args()
    import time as _time
    _start = _time.time()

    # Incremental check
    if args.incremental:
        changed, has_changes = check_source_changes(args.path, args.git_ref)
        if not has_changes:
            print(json.dumps({"status":"skipped","message":"No Java source changes detected","changed_files":[]}))
            return
        if args.verbose:
            print(json.dumps({"status":"info","message":"Incremental build","changed_files":changed}, indent=2))

    result = run_compile(args.path, args.build_tool, args.verbose, args.extra_args)

    if args.timing:
        _elapsed = _time.time() - _start
        result["timing_seconds"] = round(_elapsed, 2)
        result["timing_human"] = measure_timing(_start, _time.time())

    output = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(json.dumps({"status": "saved", "file": args.output, "compile_status": result["status"]}))
    else:
        print(output)
    sys.exit(0 if result["status"] == "success" else 1)

if __name__ == "__main__":
    main()
*** End of File
def check_source_changes(project_path, since_ref="HEAD"):
    """Check which Java source files changed since a git ref.
    Returns (changed_files, is_incremental) tuple.
    """
    pp = Path(project_path).resolve()
    git_dir = pp / ".git"
    if not git_dir.exists():
        return [], False
    import subprocess
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", since_ref, "--", "*.java"],
            cwd=pp, capture_output=True, text=True, timeout=30
        )
        if proc.returncode == 0:
            files = [f for f in proc.stdout.strip().split("\n") if f.strip()]
            return files, len(files) > 0
    except Exception:
        pass
    return [], False

def measure_timing(start_time, end_time):
    """Format timing duration."""
    duration = end_time - start_time
    if duration < 60:
        return f"{duration:.1f}s"
    return f"{int(duration//60)}m {int(duration%60)}s"
