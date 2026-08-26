#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ERD Viewer - Generate visual relationship diagrams from any supported database.
Usage:
  python erd_viewer.py --db-type mysql --db mydb
  python erd_viewer.py --db-type sqlite --db mydb.sqlite --output erd.html
  python erd_viewer.py --input relations.json --output erd.html
"""
import json, sys, os, argparse, datetime
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

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
HTML_TEMPLATE = (TEMPLATE_DIR / "erd_template.html").read_text(encoding="utf-8")

RULE_MAP = {0:"RESTRICT",1:"CASCADE",2:"SET NULL",3:"NO ACTION",4:"SET DEFAULT"}

def fetch_relations(host, port, db, user, password, ssl, db_type="mysql"):
    engine = create_engine(db_type, host, port, db, user, password, ssl)
    engine.connect()
    result = engine.get_relations()
    engine.close()
    return result

def generate_html(relations_data, db_name):
    rels = relations_data.get("relations", [])
    mermaid_erd = relations_data.get("mermaidErd", "erDiagram\n  %% No relationships found")
    mermaid_erd = mermaid_erd.replace("\\n","\n").replace('\\"','"')
    rows = []; tables = set()
    for r in rels:
        tables.add(r.get("parentTable","")); tables.add(r.get("childTable",""))
        up = RULE_MAP.get(r.get("updateRule",3), str(r.get("updateRule","")));
        de = RULE_MAP.get(r.get("deleteRule",3), str(r.get("deleteRule","")))
        rows.append(f"<tr><td><code>{r.get('constraintName','')}</code></td>"
            f"<td>{r.get('parentTable','')}</td><td><code>{r.get('parentColumn','')}</code></td>"
            f"<td>{r.get('childTable','')}</td><td><code>{r.get('childColumn','')}</code></td>"
            f"<td>{up}</td><td>{de}</td></tr>")
    return HTML_TEMPLATE.format(title=f"Database Relationship Diagram - {db_name}", db_name=db_name,
        rel_count=len(rels), gen_time=datetime.datetime.now().isoformat(),
        mermaid_erd=mermaid_erd, rows="\n".join(rows), table_count=len(tables))

def main():
    parser = argparse.ArgumentParser(description="ERD Viewer - Relationship Diagram Generator")
    parser.add_argument("--db-type", default="mysql", help="Database type: mysql/postgresql/sqlite/sqlserver/oracle")
    parser.add_argument("--host", default="localhost"); parser.add_argument("--port", type=int)
    parser.add_argument("--db", default=os.environ.get("DB_NAME",""))
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default=os.environ.get("DB_PASSWORD",""))
    parser.add_argument("--ssl", default="false")
    parser.add_argument("--input", help="Existing --get-relations JSON file")
    parser.add_argument("--output", "-o", default="erd_view.html", help="Output HTML file")
    parser.add_argument("--profile", help="Saved profile name (from ~/.multi-db-analyzer/profiles.json)")
    args = parser.parse_args()

    if args.input:
        with open(args.input) as f: data = json.load(f)
        db_name = data.get("relations",{}).get("database", data.get("database","unknown"))
    elif args.db:
        resolved, _ = CM.resolve_profile_args(args) if CM else (vars(args), None)
        db_name = resolved.get("db", args.db)
        data = fetch_relations(resolved.get("host", args.host), resolved.get("port", args.port), resolved.get("db", args.db), resolved.get("user", args.user), resolved.get("password", args.password), resolved.get("ssl", args.ssl), resolved.get("db_type", args.db_type))
        data = data.get("relations", data)
    else:
        parser.print_help(); return

    html = generate_html(data, db_name)
    with open(args.output, "w", encoding="utf-8") as f: f.write(html)
    print(json.dumps({"status":"success","output":args.output,"relations_count":len(data.get("relations",[]))}))

if __name__ == "__main__": main()
