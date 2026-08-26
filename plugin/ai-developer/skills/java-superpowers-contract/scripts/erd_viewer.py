#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ERD Viewer (Python 版)
从 DatabaseQuery --get-relations 的输出生成可视化关系图 HTML。
用法：
  python erd_viewer.py --db mydb                          # 直接运行
  python erd_viewer.py --input relations.json             # 从已有JSON加载
  python erd_viewer.py --db mydb --output erd.html        # 保存到文件
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import json, sys, os, argparse, datetime
from pathlib import Path
try:
    from database_query import MySQLQuery
except ImportError:
    print("错误：缺少 pymysql 依赖。请执行: pip install -r requirements.txt")
    sys.exit(1)

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         max-width: 1200px; margin: 2em auto; padding: 0 1em; color: #1a1a2e; background: #f8f9fa; }}
  h1 {{ color: #0d6efd; border-bottom: 2px solid #0d6efd; padding-bottom: 0.3em; }}
  h2 {{ color: #198754; margin-top: 1.5em; }}
  .mermaid {{ background: white; padding: 1em; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
  table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
  th, td {{ border: 1px solid #dee2e6; padding: 0.5em; text-align: left; }}
  th {{ background: #e9ecef; }}
  tr:nth-child(even) {{ background: #f2f2f2; }}
  code {{ background: #e9ecef; padding: 0.2em 0.4em; border-radius: 3px; }}
  .stats {{ background: #e9ecef; padding: 1em; border-radius: 8px; margin: 1em 0; }}
</style>
</head>
<body>
<h1>&#x1f517; {title}</h1>
<p><strong>数据库:</strong> {db_name} | <strong>关系数:</strong> {rel_count} | <strong>生成时间:</strong> {gen_time}</p>

<h2>ER 图 (实体关系)</h2>
<div class="mermaid">
{mermaid_erd}
</div>

<h2>外键关系明细</h2>
<table>
<thead><tr><th>外键名</th><th>父表</th><th>父列</th><th>子表</th><th>子列</th><th>更新规则</th><th>删除规则</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>

<div class="stats">
<p><strong>表总数:</strong> {table_count} | <strong>外键约束数:</strong> {rel_count}</p>
</div>
<script>mermaid.initialize({{ startOnLoad: true, theme: "default" }});</script>
</body>
</html>'''

RULE_MAP = {0: "RESTRICT", 1: "CASCADE", 2: "SET NULL", 3: "NO ACTION", 4: "SET DEFAULT"}

def fetch_relations(host, port, db, user, password, ssl):
    q = MySQLQuery(host, port, db, user, password, ssl)
    q.connect()
    result = q.get_relations()
    q.close()
    return result

def generate_html(relations_data, db_name):
    rels = relations_data.get("relations", [])
    mermaid_erd = relations_data.get("mermaidErd", "erDiagram\n  %% No relationships found")
    mermaid_erd = mermaid_erd.replace("\\n", "\n").replace("\\\"", "\"")

    rows = []
    tables = set()
    for r in rels:
        tables.add(r.get("parentTable", ""))
        tables.add(r.get("childTable", ""))
        up = RULE_MAP.get(r.get("updateRule", 3), str(r.get("updateRule", "")))
        de = RULE_MAP.get(r.get("deleteRule", 3), str(r.get("deleteRule", "")))
        rows.append(f"<tr><td><code>{r.get('constraintName','')}</code></td>"
                    f"<td>{r.get('parentTable','')}</td><td><code>{r.get('parentColumn','')}</code></td>"
                    f"<td>{r.get('childTable','')}</td><td><code>{r.get('childColumn','')}</code></td>"
                    f"<td>{up}</td><td>{de}</td></tr>")

    return HTML_TEMPLATE.format(
        title=f"数据库关系图 - {db_name}",
        db_name=db_name,
        rel_count=len(rels),
        gen_time=datetime.datetime.now().isoformat(),
        mermaid_erd=mermaid_erd,
        rows="\n".join(rows),
        table_count=len(tables)
    )

def main():
    parser = argparse.ArgumentParser(description="ERD Viewer 关系图生成器")
    parser.add_argument("--host", default="localhost"); parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--db", default=os.environ.get("DB_NAME","")); parser.add_argument("--user", default="root")
    parser.add_argument("--password", default=os.environ.get("DB_PASSWORD","")); parser.add_argument("--ssl", default="false")
    parser.add_argument("--input", help="已有 --get-relations JSON 文件")
    parser.add_argument("--output", "-o", default="erd_view.html", help="输出的HTML文件路径")
    args = parser.parse_args()

    if args.input:
        with open(args.input) as f: data = json.load(f)
        db_name = data.get("relations", {}).get("database", data.get("database", "unknown"))
    elif args.db:
        db_name = args.db
        data = fetch_relations(args.host, args.port, args.db, args.user, args.password, args.ssl)
        data = data.get("relations", data)
    else:
        parser.print_help(); return

    html = generate_html(data, db_name)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)
    print(json.dumps({"status":"success","output":args.output,"relations_count":len(data.get("relations",[]))}))

if __name__ == "__main__": main()

