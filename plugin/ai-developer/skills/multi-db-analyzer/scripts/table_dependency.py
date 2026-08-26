#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Table Dependency Analyzer - Build dependency graphs from FK constraints.
Supports MySQL, PostgreSQL, SQLite, SQL Server, Oracle.
Usage:
  python table_dependency.py --db-type mysql --db mydb --output deps.html
  python table_dependency.py --db-type sqlite --db mydb.db
  python table_dependency.py --input relations.json
"""
import json, sys, os, argparse, datetime
from collections import defaultdict, deque
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
HTML_TEMPLATE = (TEMPLATE_DIR / "table_deps_template.html").read_text(encoding="utf-8")

def build_dependency_graph(relations):
    graph, rev, all_tables = defaultdict(set), defaultdict(set), set()
    for rel in relations:
        p, c = rel.get("parentTable",""), rel.get("childTable","")
        if p and c: graph[c].add(p); rev[p].add(c); all_tables.add(p); all_tables.add(c)
    return graph, rev, all_tables

def topological_levels(graph, rev, all_tables):
    in_deg = {t: len(graph.get(t,set())) for t in all_tables}
    q = deque([t for t in all_tables if in_deg.get(t,0)==0])
    levels, lvl = {}, 0
    while q:
        for _ in range(len(q)):
            t = q.popleft(); levels[t] = lvl
            for dep in rev.get(t,set()): in_deg[dep]-=1
            if in_deg[dep]==0: q.append(dep)
        lvl += 1
    for t in all_tables:
        if t not in levels: levels[t] = -1
    return levels

def detect_cycles(graph, all_tables):
    W,G,B=0,1,2; color={t:W for t in all_tables}; cycles=[]; path=[]
    def dfs(n):
        color[n]=G; path.append(n)
        for dep in graph.get(n,set()):
            if color.get(dep)==G:
                idx=path.index(dep); cycles.append(path[idx:]+[dep])
            elif color.get(dep)==W: dfs(dep)
        path.pop(); color[n]=B
    for t in all_tables:
        if color.get(t)==W: dfs(t)
    return cycles

def generate_mermaid_dag(graph, rev, levels, cycles):
    lines = ["graph TD"]
    cycle_tables = set()
    for c in cycles:
        for t in c: cycle_tables.add(t)
    for t in sorted(levels.keys()):
        if t in cycle_tables: lines.append(f'  {t.replace("-","_")}["&#9888; {t}"]:::cycle')
        else: lines.append(f'  {t.replace("-","_")}["{t}"]')
    for child, parents in graph.items():
        for parent in parents: lines.append(f'  {child.replace("-","_")} --> {parent.replace("-","_")}')
    if len(lines)==1: lines.append("  %% No dependencies")
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="Table Dependency Analyzer")
    parser.add_argument("--db-type", default="mysql", help="Database type")
    parser.add_argument("--host", default="localhost"); parser.add_argument("--port", type=int)
    parser.add_argument("--db", default=os.environ.get("DB_NAME",""))
    parser.add_argument("--user", default="root"); parser.add_argument("--password", default=os.environ.get("DB_PASSWORD",""))
    parser.add_argument("--ssl", default="false")
    parser.add_argument("--profile", help="Saved profile name (from ~/.multi-db-analyzer/profiles.json)")
    parser.add_argument("--input", help="Existing --get-relations JSON file")
    parser.add_argument("--output","-o", default="table_deps.html")
    parser.add_argument("--format","-f", default="html", choices=["json","html","markdown"])
    parser.add_argument("--profile", help="Saved profile name")
    args = parser.parse_args()
    if CM:
        resolved, _ = CM.resolve_profile_args(args)
        for k in ["db_type","host","port","db","user","password","ssl"]:
            setattr(args, k, resolved.get(k, getattr(args, k, None)))
    if args.input:
        with open(args.input) as f: raw = json.load(f)
        data = raw.get("relations",raw) if isinstance(raw,dict) else raw
        db_name = raw.get("database",args.db or "unknown") if isinstance(raw,dict) else (args.db or "unknown")
    elif args.db:
        engine = create_engine(args.db_type, args.host, args.port, args.db, args.user, args.password, args.ssl)
        engine.connect(); res = engine.get_relations(); engine.close()
        raw = res.get("relations",res)
        data = raw.get("relations",raw) if isinstance(raw,dict) else raw
        db_name = args.db
    else: parser.print_help(); return
    relations = data if isinstance(data,list) else data.get("relations",[])
    graph, rev, all_tables = build_dependency_graph(relations)
    levels = topological_levels(graph, rev, all_tables)
    cycles = detect_cycles(graph, all_tables)
    mermaid_dag = generate_mermaid_dag(graph, rev, levels, cycles)
    level_dist = defaultdict(int)
    for t,l in levels.items(): level_dist[l] += 1
    max_level = max(levels.values()) if levels else 0
    dep_rows = []; impact_rows = []
    for t in sorted(levels.keys(), key=lambda x:(levels.get(x,0),x)):
        l = levels.get(t,0); parents = graph.get(t,set()); children = rev.get(t,set())
        downstream = set(); stack = list(children)
        while stack:
            n = stack.pop()
            if n not in downstream: downstream.add(n); stack.extend(rev.get(n,set()))
        lvl_str = f"L{l}" if l>=0 else "CYCLE"
        rc = f"level-{min(l,3)}" if l>=0 else "circular"
        chain = " -> ".join(sorted(parents)) if parents else "Isolated"
        if l<0: chain = "&#9888; Circular"
        dep_rows.append(f'<tr class="{rc}"><td>{"&#9888; " if l<0 else ""}{t}</td><td>{lvl_str}</td><td>{len(parents)}</td><td>{len(children)}</td><td>{len(downstream)} tables</td><td><code>{chain}</code></td></tr>')
        impact = " -> ".join(sorted(downstream)) if downstream else "No downstream"
        impact_rows.append(f'<tr class="{rc}"><td>{"&#9888; " if l<0 else ""}{t}</td><td>{lvl_str}</td><td><code>{impact}</code></td></tr>')
    cycle_section = ""
    if cycles:
        for cycle in cycles: cycle_section += f'<p class="circular">&#9888; Circular dependency: {" -> ".join(cycle)}</p>\n'
    else: cycle_section = '<p class="text-success">&#10004; No circular dependencies detected</p>'
    html = HTML_TEMPLATE.format(db_name=db_name, table_count=len(all_tables), fk_count=len(relations),
        level_count=max_level+1, cycle_status=f"&#9888; {len(cycles)}" if cycles else "&#10004; None",
        l0=level_dist.get(0,0), l1=level_dist.get(1,0), l2=sum(level_dist.get(i,0) for i in range(2,max_level)),
        root_count=len([t for t,l in levels.items() if l>=0 and l==max_level and not children]),
        mermaid_dag=mermaid_dag, dep_rows="\n".join(dep_rows), cycle_section=cycle_section,
        impact_rows="\n".join(impact_rows), gen_time=datetime.datetime.now().isoformat())
    with open(args.output, "w", encoding="utf-8") as f: f.write(html)
    result = {"status":"success","output":args.output,"tables":len(all_tables),"fks":len(relations),
        "levels":max_level+1,"cycles":len(cycles)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
if __name__ == "__main__": main()
