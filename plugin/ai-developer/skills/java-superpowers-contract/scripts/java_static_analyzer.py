#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Java Static Analyzer - Run Checkstyle/PMD/SpotBugs and report issues.
Usage:
  python java_static_analyzer.py --path /path/to/project --tool checkstyle
  python java_static_analyzer.py --path /path/to/project --tool pmd --output report.json
  python java_static_analyzer.py --path /path/to/project --auto-detect
"""
import os, json, subprocess, sys, argparse, xml.etree.ElementTree as ET
from pathlib import Path

TOOLS = {
    "checkstyle": {"jar": "checkstyle.jar", "url": "https://github.com/checkstyle/checkstyle/releases"},
    "pmd": {"jar": "pmd-bin", "url": "https://pmd.github.io/"},
    "spotbugs": {"jar": "spotbugs.jar", "url": "https://spotbugs.github.io/"},
}

def find_maven_home():
    mvn = os.environ.get("M2_HOME", "") or os.environ.get("MAVEN_HOME", "")
    if mvn: return mvn
    for p in os.environ.get("PATH", "").split(os.pathsep):
        mvn_cmd = Path(p) / "mvn.cmd" if os.name == "nt" else Path(p) / "mvn"
        if mvn_cmd.exists():
            return str(mvn_cmd.parent.parent)
    return None

def run_checkstyle(project_path, config=None):
    """Run Checkstyle check. Uses project's checkstyle.xml or sun_checks.xml."""
    pp = Path(project_path).resolve()
    config_file = config
    if not config_file:
        for candidate in ["checkstyle.xml", "config/checkstyle/checkstyle.xml", ".checkstyle"]:
            cf = pp / candidate
            if cf.exists(): config_file = str(cf); break
    if not config_file:
        config_file = str(pp / "checkstyle.xml")  # will fail if not exists, that's OK
    java_files = list(pp.rglob("*.java"))
    if not java_files:
        return {"status": "skipped", "message": "No Java files found", "errors": []}
    src_dirs = sorted(set(str(f.parent) for f in java_files))
    result = {"status": "unknown", "tool": "checkstyle", "total_issues": 0, "issues": []}
    cmd = ["java", "-cp", "", "com.puppycrawl.tools.checkstyle.Main",
           "-c", config_file, "-f", "xml"]
    for src in src_dirs[:20]:  # limit to 20 source dirs
        try:
            proc = subprocess.run(
                ["java", "-jar", "checkstyle.jar", "-c", config_file, "-f", "xml", src],
                capture_output=True, text=True, timeout=60
            )
            if proc.returncode == 0 or proc.returncode == 1:
                root = ET.fromstring(proc.stdout)
                for file_elem in root.findall(".//file"):
                    file_name = file_elem.get("name", "")
                    for err in file_elem.findall("error"):
                        result["issues"].append({
                            "file": file_name,
                            "line": int(err.get("line", 0)),
                            "severity": err.get("severity", "error"),
                            "message": err.get("message", ""),
                            "source": err.get("source", ""),
                        })
        except (subprocess.TimeoutExpired, FileNotFoundError, ET.ParseError):
            pass
    result["total_issues"] = len(result["issues"])
    result["status"] = "success"
    return result

def run_pmd(project_path):
    """Run PMD static analysis."""
    pp = Path(project_path).resolve()
    java_files = list(pp.rglob("*.java"))
    if not java_files:
        return {"status": "skipped", "message": "No Java files found", "issues": []}
    file_list = "\n".join(str(f) for f in java_files[:200])
    result = {"status": "unknown", "tool": "pmd", "total_issues": 0, "issues": []}
    try:
        proc = subprocess.run(
            ["pmd", "check", "-f", "xml", "-R", "category/java/bestpractices.xml",
             "-d", str(pp)],
            capture_output=True, text=True, timeout=120
        )
        try:
            root = ET.fromstring(proc.stdout)
            for file_elem in root.findall(".//file"):
                fn = file_elem.get("name", "")
                for viol in file_elem.findall("violation"):
                    result["issues"].append({
                        "file": fn, "line": int(viol.get("beginline", 0)),
                        "rule": viol.get("rule", ""), "ruleset": viol.get("ruleset", ""),
                        "priority": viol.get("priority", ""),
                        "message": (viol.text or "").strip(),
                    })
        except ET.ParseError:
            pass
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # PMD CLI not available - skip
        return {"status": "skipped", "message": "PMD not installed. Install: https://pmd.github.io/", "issues": []}
    result["total_issues"] = len(result["issues"])
    result["status"] = "success"
    return result

def run_spotbugs(project_path):
    """Run SpotBugs on compiled classes."""
    pp = Path(project_path).resolve()
    class_files = list(pp.rglob("*.class"))
    if not class_files:
        return {"status": "skipped", "message": "No .class files found. Run compile first.", "issues": []}
    result = {"status": "unknown", "tool": "spotbugs", "total_issues": 0, "issues": []}
    classes_dir = pp / "target" / "classes"
    if not classes_dir.exists():
        classes_dir = pp / "build" / "classes" / "java" / "main"
    if not classes_dir.exists():
        return {"status": "skipped", "message": "No compiled classes directory found. Run compile first.", "issues": []}
    try:
        proc = subprocess.run(
            ["java", "-jar", "spotbugs.jar", "-textui", "-xml:withMessages",
             "-output", "spotbugs_report.xml", str(classes_dir)],
            capture_output=True, text=True, timeout=120
        )
        report_path = pp / "spotbugs_report.xml"
        if report_path.exists():
            try:
                root = ET.parse(str(report_path)).getroot()
                for bug in root.findall(".//BugInstance"):
                    result["issues"].append({
                        "type": bug.get("type", ""),
                        "priority": bug.get("priority", ""),
                        "category": bug.get("category", ""),
                        "message": (bug.findtext("LongMessage", "") or "").strip(),
                    })
                report_path.unlink()
            except ET.ParseError: pass
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"status": "skipped", "message": "SpotBugs not installed. Install: https://spotbugs.github.io/", "issues": []}
    result["total_issues"] = len(result["issues"])
    result["status"] = "success"
    return result

def summarize_issues(issues, max_show=30):
    if not issues:
        return "No issues found."
    lines = [f"Found {len(issues)} issue(s):", ""]
    for i, iss in enumerate(issues[:max_show]):
        fp = iss.get("file", "")
        ln = iss.get("line", "")
        msg = iss.get("message", iss.get("rule", ""))
        sev = iss.get("severity", iss.get("priority", ""))
        lines.append(f"  [{sev}] {Path(fp).name}:{ln}  {msg[:120]}")
    if len(issues) > max_show:
        lines.append(f"  ... and {len(issues) - max_show} more issue(s)")
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="Java Static Analyzer")
    parser.add_argument("--path", required=True, help="Java project root path")
    parser.add_argument("--tool", choices=["checkstyle", "pmd", "spotbugs", "all"], default="all")
    parser.add_argument("--output", "-o", help="Save result to JSON file")
    parser.add_argument("--summary", action="store_true", help="Print human-readable summary instead of JSON")
    parser.add_argument("--ruleset", choices=["strict", "moderate", "lenient"], default="moderate",
                        help="Rule strictness preset (default: moderate)")
    parser.add_argument("--severity", choices=["error", "warning", "info", "all"], default="all",
                        help="Minimum severity to report (default: all)")
    parser.add_argument("--config", help="Custom Checkstyle/PMD config file path")
    args = parser.parse_args()

    results = {"project": str(Path(args.path).resolve())}
    tools = ["checkstyle", "pmd", "spotbugs"] if args.tool == "all" else [args.tool]

    for tool in tools:
        if tool == "checkstyle":
            results["checkstyle"] = run_checkstyle(args.path, args.config)
            results["checkstyle"]["ruleset"] = RULESETS[args.ruleset]["checkstyle"]
        elif tool == "pmd":
            results["pmd"] = run_pmd(args.path)
            results["pmd"]["ruleset"] = RULESETS[args.ruleset]["pmd"]
        elif tool == "spotbugs":
            results["spotbugs"] = run_spotbugs(args.path)

    # Filter by severity
    for tool in ["checkstyle", "pmd", "spotbugs"]:
        r = results.get(tool, {})
        if r.get("issues") and args.severity != "all":
            r["issues"] = filter_by_severity(r["issues"], args.severity)
            r["total_issues"] = len(r["issues"])

    total_issues = sum(r.get("total_issues", 0) for r in results.values() if isinstance(r, dict))
    results["total_issues"] = total_issues

    if args.summary:
        print(f"# Java Static Analysis - {results['project']}")
        print(f"Total issues: {total_issues}")
        print()
        for tool in tools:
            r = results.get(tool, {})
            print(f"## {tool.title()} ({r.get('status', 'unknown')})")
            print(summarize_issues(r.get("issues", [])))
            print()
    else:
        print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    if args.output:
        Path(args.output).write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    sys.exit(0 if total_issues == 0 else 1)

if __name__ == "__main__":
    main()
*** End of File
RULESETS = {
    "strict": {
        "checkstyle": "category/java/design.xml,category/java/naming.xml,category/java/javadoc.xml",
        "pmd": "category/java/bestpractices.xml,category/java/design.xml,category/java/errorprone.xml,category/java/performance.xml",
    },
    "moderate": {
        "checkstyle": "category/java/design.xml,category/java/naming.xml",
        "pmd": "category/java/bestpractices.xml,category/java/design.xml",
    },
    "lenient": {
        "checkstyle": "category/java/naming.xml",
        "pmd": "category/java/bestpractices.xml",
    },
}

def filter_by_severity(issues, min_severity):
    severity_order = {"error": 0, "warning": 1, "info": 2}
    min_lvl = severity_order.get(min_severity, -1)
    if min_lvl < 0:
        return issues
    return [i for i in issues if severity_order.get(i.get("severity", "info"), 2) >= min_lvl]
