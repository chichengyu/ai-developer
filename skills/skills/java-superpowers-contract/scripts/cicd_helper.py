#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CI/CD 集成助手 (Python 版)
自动化审计流程：运行数据质量检查 → 生成审计报告 → Git提交规范校验。
用法：
  python cicd_helper.py --audit audit_data.json --output-dir ./reports
  python cicd_helper.py --check-commit-msg "feat(user): 新增用户注册接口"
  python cicd_helper.py --pre-commit-install
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
_SCRIPT_DIR = Path(__file__).resolve().parent

import json, sys, os, subprocess, argparse, datetime
from pathlib import Path
try:
    from database_query import MySQLQuery
except ImportError:
    print("错误：缺少 pymysql 依赖。请执行: pip install -r requirements.txt")
    sys.exit(1)

AUDIT_DIR = Path.home() / ".java-superpowers-audit"

def check_commit_message(msg):
    errors = []
    pattern = r"^(feat|fix|refactor|test|docs|chore|perf|style|ci)(\([\w-]+\))?:\s.+"
    if not msg: errors.append("提交信息为空")
    elif not re.match(pattern, msg): errors.append("格式不符: <类型>(<范围>): <描述>")
    if len(msg) > 100: errors.append("提交信息超过100字符")
    return errors or ["提交信息格式正确"]

def run_quality_check(db_host, db_port, db_name, db_user, db_password, tables):
    results = {}
    q = MySQLQuery(db_host, db_port, db_name, db_user, db_password)
    q.connect()
    for table in tables:
        try:
            data = q.analyze_table(table)
            analysis = data.get("analysis", {})
            columns = analysis.get("columns", [])
            issues = []
            for col in columns:
                wrn = col.get("warning")
                if wrn and wrn != "正常": issues.append({"column":col["name"],"warning":wrn})
            results[table] = {"columns": len(columns), "issues": issues, "issueCount": len(issues)}
        except Exception as e:
            results[table] = {"error": str(e)}
    q.close()
    return results

def main():
    parser = argparse.ArgumentParser(description="CI/CD 集成助手")
    parser.add_argument("--audit", help="审计JSON数据文件")
    parser.add_argument("--output-dir", default="./reports", help="报告输出目录")
    parser.add_argument("--check-commit-msg", help="校验Git提交信息")
    parser.add_argument("--pre-commit-install", action="store_true", help="安装Git pre-commit钩子")
    parser.add_argument("--quality-check", nargs="+", help="运行数据质量检查（指定表名列表）")
    parser.add_argument("--db-host", default="localhost"); parser.add_argument("--db-port", type=int, default=3306)
    parser.add_argument("--db-name", required=True); parser.add_argument("--db-user", default="root")
    parser.add_argument("--db-password", default=os.environ.get("DB_PASSWORD", ""))
    args = parser.parse_args()
    if args.check_commit_msg:
        results = check_commit_message(args.check_commit_msg)
        print(json.dumps({"status":"ok" if "正确" in results[0] else "error","messages":results}))
    elif args.pre_commit_install:
        hook_dir = Path(".git/hooks")
        hook_dir.mkdir(parents=True, exist_ok=True)
        hook = hook_dir / "pre-commit"
        hook.write_text('#!/bin/sh\npython scripts/cicd_helper.py --check-commit-msg "$(git log -1 --pretty=%B)"\n')
        hook.chmod(0o755)
        print(json.dumps({"status":"installed","hook":str(hook)}))
    elif args.quality_check:
        results = run_quality_check(args.db_host, args.db_port, args.db_name, args.db_user, args.db_password, args.quality_check)
        print(json.dumps({"status":"done","results":results}, ensure_ascii=False, indent=2))
    elif args.audit:
        os.makedirs(args.output_dir, exist_ok=True)
        subprocess.run(["python", str(_SCRIPT_DIR / "audit_report_generator.py"), "--input", args.audit,
                       "--format", "markdown", "--output", os.path.join(args.output_dir, "audit_report.md")])
        print(json.dumps({"status":"success","output_dir":args.output_dir}))
    else:
        parser.print_help()
if __name__ == "__main__":
    import re
    main()



