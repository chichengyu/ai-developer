#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SQL Explain Analyzer - Analyze query execution plans from any supported database.
Usage:
  python sql_explain_analyzer.py --db-type mysql --db mydb "SELECT * FROM user WHERE id = 1"
  python sql_explain_analyzer.py --db-type postgresql --db mydb "SELECT * FROM user"
  python sql_explain_analyzer.py --db-type sqlite --db mydb.db --input slow_query.log
"""
import json, sys, re, os, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
try:
    from db_engine import create_engine
except ImportError:
    print(json.dumps({"status":"error","message":"Need db_engine.py"})); sys.exit(1)

try:
    from cred_manager import CredentialManager
    CM = CredentialManager()
except ImportError:
    CM = None

def analyze_explain_json(explain_data):
    issues = []
    if isinstance(explain_data, dict):
        for key in ["key","possible_keys","Extra","type"]:
            val = explain_data.get(key,"")
            if key=="type" and val=="ALL": issues.append("Full table scan (type=ALL): add index")
            if key=="Extra":
                if "Using temporary" in str(val): issues.append("Using temporary table: optimize GROUP/ORDER BY")
                if "Using filesort" in str(val): issues.append("Using filesort: add sort index")
        if not explain_data.get("key") and explain_data.get("possible_keys"):
            issues.append(f"Possible keys unused: {explain_data['possible_keys']}")
        for child in explain_data.get("children",[]): issues.extend(analyze_explain_json(child))
        for sub in explain_data.get("attached_subqueries",[]): issues.extend(analyze_explain_json(sub))
    return issues

def run_explain(host, port, db, user, password, sql, ssl, db_type):
    engine = create_engine(db_type, host, port, db, user, password, ssl)
    engine.connect()
    result = engine.explain(sql)
    engine.close()
    return result

def main():
    parser = argparse.ArgumentParser(description="SQL Explain Query Plan Analyzer")
    parser.add_argument("--db-type", default="mysql", help="Database type: mysql/postgresql/sqlite/sqlserver/oracle")
    parser.add_argument("--host", default="localhost"); parser.add_argument("--port", type=int)
    parser.add_argument("--db", required=True); parser.add_argument("--user", default="root")
    parser.add_argument("--password", default=os.environ.get("DB_PASSWORD",""))
    parser.add_argument("--ssl", default="false", choices=["false","true","verify-ca"])
    parser.add_argument("--input", help="Slow query log file")
    parser.add_argument("sql", nargs="?", help="SQL to analyze")
    parser.add_argument("--profile", help="Saved profile name (from ~/.multi-db-analyzer/profiles.json)")
    args = parser.parse_args()
    # Resolve profile
    try:
        from cred_manager import CredentialManager
        CM = CredentialManager()
    except ImportError:
        CM = None
    if CM:
        resolved, _ = CM.resolve_profile_args(args)
        args.db_type = resolved.get("db_type", args.db_type)
        args.host = resolved.get("host", args.host)
        args.port = resolved.get("port", args.port)
        args.db = resolved.get("db", args.db)
        args.user = resolved.get("user", args.user)
        args.password = resolved.get("password", args.password)
        args.ssl = resolved.get("ssl", args.ssl)

    if args.input:
        with open(args.input) as f:
            for line in f:
                if re.search(r'(SELECT|INSERT|UPDATE|DELETE)\s', line, re.I):
                    print(f"Analyzing: {line.strip()[:80]}...")
                    out = run_explain(args.host, args.port, args.db, args.user, args.password, line.strip(), args.ssl, args.db_type)
                    data = json.loads(out) if isinstance(out, str) else out
                    issues = analyze_explain_json(data.get("explain",{}))
                    if issues: print("  Issues: " + "; ".join(issues))
                    else: print("  Status: Normal")
    elif args.sql:
        out = run_explain(args.host, args.port, args.db, args.user, args.password, args.sql, args.ssl, args.db_type)
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else: parser.print_help()
if __name__ == "__main__": main()
