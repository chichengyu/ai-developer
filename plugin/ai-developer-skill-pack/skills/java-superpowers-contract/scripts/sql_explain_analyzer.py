
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL Explain Analyzer (Python 版)
分析 MySQL 查询执行计划，识别全表扫描、索引使用、临时表等性能瓶颈。
用法：
  python sql_explain_analyzer.py --host localhost --db mydb "SELECT * FROM user WHERE id = 1"
  python sql_explain_analyzer.py --input slow_query.log
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import json, sys, re, os, argparse
from pathlib import Path
try:
    from database_query import MySQLQuery
except ImportError:
    print("错误：缺少 pymysql 依赖。请执行: pip install -r requirements.txt")
    sys.exit(1)

def analyze_explain_json(explain_data):
    issues = []
    if isinstance(explain_data, dict):
        for key in ["key", "possible_keys", "Extra", "type"]:
            val = explain_data.get(key, "")
            if key == "type" and val == "ALL": issues.append("全表扫描 (type=ALL): 需要添加索引")
            if key == "Extra":
                if "Using temporary" in str(val): issues.append("使用了临时表 (Using temporary): 考虑优化GROUP/ORDER BY")
                if "Using filesort" in str(val): issues.append("使用了文件排序 (Using filesort): 需要添加排序索引")
                if "Using index condition" not in str(val) and explain_data.get("type") == "ref": pass
        if not explain_data.get("key") and explain_data.get("possible_keys"):
            issues.append(f"存在可能索引但未使用: {explain_data['possible_keys']}")
        for child in explain_data.get("children", []): issues.extend(analyze_explain_json(child))
        for child in explain_data.get("attached_subqueries", []): issues.extend(analyze_explain_json(child))
    return issues

def run_explain(host, port, db, user, password, sql, ssl_mode):
    q = MySQLQuery(host, port, db, user, password, ssl_mode)
    q.connect()
    result = q.explain(sql)
    q.close()
    return result

def main():
    parser = argparse.ArgumentParser(description="SQL Explain 查询计划分析器")
    parser.add_argument("--host", default="localhost"); parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--db", required=True, help="数据库名"); parser.add_argument("--user", default="root")
    parser.add_argument("--password", default=os.environ.get("DB_PASSWORD", ""))
    parser.add_argument("--ssl", default="false", choices=["false","true","verify-ca"])
    parser.add_argument("--input", help="慢查询日志文件")
    parser.add_argument("sql", nargs="?", help="待分析的SQL语句")
    args = parser.parse_args()
    if args.input:
        with open(args.input) as f:
            for line in f:
                if re.search(r'(SELECT|INSERT|UPDATE|DELETE)\s', line, re.I):
                    print(f"分析: {line.strip()[:80]}...")
                    out = run_explain(args.host, args.port, args.db, args.user, args.password, line.strip(), args.ssl)
                    data = json.loads(out)
                    issues = analyze_explain_json(data.get("explain", {}))
                    if issues: print("  问题: " + "; ".join(issues))
                    else: print("  状态: 正常")
    elif args.sql:
        out = run_explain(args.host, args.port, args.db, args.user, args.password, args.sql, args.ssl)
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        parser.print_help()
if __name__ == "__main__": main()

