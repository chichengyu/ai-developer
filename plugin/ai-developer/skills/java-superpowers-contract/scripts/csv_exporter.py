#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV Exporter (Python 版)
将 SQL 查询结果导出为 CSV 文件。
用法：
  python csv_exporter.py --host localhost --db mydb "SELECT * FROM user" --output users.csv
  python csv_exporter.py --input result.json --output output.csv
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import json, csv, sys, os, argparse
try:
    from database_query import MySQLQuery
except ImportError:
    print("错误：缺少 pymysql 依赖。请执行: pip install -r requirements.txt")
    sys.exit(1)

def export_csv(data, output_path):
    if not data: return 0
    headers = list(data[0].keys()) if isinstance(data[0], dict) else []
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for row in data:
            writer.writerow([str(row.get(h, "")) for h in headers] if isinstance(row, dict) else row)
    return len(data)

def main():
    parser = argparse.ArgumentParser(description="CSV Exporter 导出工具")
    parser.add_argument("--host", default="localhost"); parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--db", required=True); parser.add_argument("--user", default="root")
    parser.add_argument("--password", default=os.environ.get("DB_PASSWORD", ""))
    parser.add_argument("--ssl", default="false")
    parser.add_argument("--input", help="已有JSON结果文件")
    parser.add_argument("sql", nargs="?", help="SQL查询语句")
    parser.add_argument("--output", "-o", default="export.csv", help="输出CSV文件路径")
    args = parser.parse_args()
    if args.input:
        with open(args.input) as f: data = json.load(f)
        if isinstance(data, dict): data = data.get("data", data)
        count = export_csv(data, args.output)
        print(json.dumps({"status":"success","output":args.output,"rows":count}))
    elif args.sql:
        q = MySQLQuery(args.host, args.port, args.db, args.user, args.password, args.ssl)
        q.connect()
        result = q.export_csv(args.sql, args.output)
        q.close()
        print(json.dumps(result, ensure_ascii=False))
    else:
        parser.print_help()
if __name__ == "__main__": main()

