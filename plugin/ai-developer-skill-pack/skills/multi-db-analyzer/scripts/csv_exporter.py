#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CSV Exporter - Export SQL query results to CSV from any supported database.
Usage:
  python csv_exporter.py --db-type mysql --db mydb "SELECT * FROM user" --output users.csv
  python csv_exporter.py --db-type sqlite --db mydb.db "SELECT * FROM user" --output users.csv
  python csv_exporter.py --input result.json --output output.csv
"""
import json, csv, sys, os, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
try:
    from db_engine import create_engine
except ImportError:
    print(json.dumps({"status":"error","message":"Need db_engine.py"})); sys.exit(1)

def export_csv(data, output_path):
    if not data: return 0
    headers = list(data[0].keys()) if isinstance(data[0], dict) else []
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(headers)
        for row in data: w.writerow([str(row.get(h,"")) for h in headers] if isinstance(row,dict) else row)
    return len(data)

def main():
    parser = argparse.ArgumentParser(description="CSV Exporter Tool")
    parser.add_argument("--db-type", default="mysql", help="Database type: mysql/postgresql/sqlite/sqlserver/oracle")
    parser.add_argument("--host", default="localhost"); parser.add_argument("--port", type=int)
    parser.add_argument("--db", required=True); parser.add_argument("--user", default="root")
    parser.add_argument("--password", default=os.environ.get("DB_PASSWORD",""))
    parser.add_argument("--ssl", default="false")
    parser.add_argument("--input", help="Existing JSON result file")
    parser.add_argument("sql", nargs="?", help="SQL query")
    parser.add_argument("--output", "-o", default="export.csv", help="Output CSV file path")
    parser.add_argument("--profile", help="Saved profile name (from ~/.multi-db-analyzer/profiles.json)")
    args = parser.parse_args()
    # Resolve profile
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
        with open(args.input) as f: data = json.load(f)
        if isinstance(data,dict): data = data.get("data", data)
        count = export_csv(data, args.output)
        print(json.dumps({"status":"success","output":args.output,"rows":count}))
    elif args.sql:
        engine = create_engine(args.db_type, args.host, args.port, args.db, args.user, args.password, args.ssl)
        engine.connect()
        result = engine.export_csv(args.sql, args.output)
        engine.close()
        print(json.dumps(result, ensure_ascii=False))
    else: parser.print_help()
if __name__ == "__main__": main()
try:
    from cred_manager import CredentialManager
    CM = CredentialManager()
except ImportError:
    CM = None
