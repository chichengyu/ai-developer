#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Table Dependency Analyzer (Python 版)
从外键约束构建表依赖关系图：拓扑层级、循环依赖检测、影响链分析、可视化HTML。
用法：
  python table_dependency.py --db mydb                      # 直接运行
  python table_dependency.py --input relations.json         # 从JSON加载
  python table_dependency.py --db mydb --output deps.html   # 输出HTML
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import json, sys, os, argparse
from collections import defaultdict, deque
from pathlib import Path
try:
    from database_query import MySQLQuery
except ImportError:
    print("错误：缺少 pymysql 依赖。请执行: pip install -r requirements.txt")
    sys.exit(1)

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>表依赖关系图 - {db_name}</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
  body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;max-width:1200px;margin:2em auto;padding:0 1em;color:#1a1a2e;background:#f8f9fa;line-height:1.6}}
  h1{{color:#0d6efd;border-bottom:2px solid #0d6efd;padding-bottom:.3em}}
  h2{{color:#198754;margin-top:1.5em}}
  .mermaid{{background:#fff;padding:1em;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.1);overflow:auto}}
  table{{border-collapse:collapse;width:100%;margin:1em 0}}
  th,td{{border:1px solid #dee2e6;padding:.5em;text-align:left}}
  th{{background:#e9ecef}} tr:nth-child(even){{background:#f2f2f2}}
  code{{background:#e9ecef;padding:.2em .4em;border-radius:3px}}
  .stats{{background:#e9ecef;padding:1em;border-radius:8px;margin:1em 0}}
  .level-0{{background:#d4edda}} .level-1{{background:#fff3cd}} .level-2{{background:#f8d7da}} .level-3{{background:#cce5ff}}
  .circular{{color:#dc3545;font-weight:bold}}
  .summary-card{{display:inline-block;padding:.5em 1em;margin:.3em;border-radius:6px;font-size:.85em}}
</style></head><body>
<h1>&#x1f517; 表依赖关系图 - {db_name}</h1>
<p><strong>表总数:</strong> {table_count} | <strong>外键约束:</strong> {fk_count} | <strong>拓扑层级:</strong> {level_count}层 | <strong>环形依赖:</strong> {cycle_status}</p>

<div class="summary-card level-0">Leaf层(0): {l0}表</div>
<div class="summary-card level-1">中间层(1): {l1}表</div>
<div class="summary-card level-2">中间层(2+): {l2}表</div>
<div class="summary-card level-3">Root层: {root_count}表</div>

<h2>依赖关系 dag</h2>
<div class="mermaid">
{mermaid_dag}
</div>

<h2>表依赖明细</h2>
<table><thead><tr><th>表名</th><th>层级</th><th>依赖父表数</th><th>被依赖子表数</th><th>影响范围</th><th>依赖链</th></tr></thead><tbody>
{dep_rows}
</tbody></table>

<h2>环形依赖检测</h2>
{cycle_section}

<h2>影响分析</h2>
<table><thead><tr><th>表名</th><th>层级</th><th>修改影响</th></tr></thead><tbody>
{impact_rows}
</tbody></table>

<div class="stats"><p>生成时间: {gen_time} | 分析引擎: TableDependency</p></div>
<script>mermaid.initialize({{startOnLoad:true,theme:"default",flowchart:{{useMaxWidth:true}}}})</script></body></html>'''

def build_dependency_graph(relations):
    """从外键关系构建依赖图"""
    graph = defaultdict(set)  # 子表 -> {父表}
    reverse = defaultdict(set) # 父表 -> {子表}
    all_tables = set()
    
    for rel in relations:
        parent = rel.get("parentTable", "")
        child = rel.get("childTable", "")
        if parent and child:
            graph[child].add(parent)
            reverse[parent].add(child)
            all_tables.add(parent)
            all_tables.add(child)
    
    # 孤立表（无FK关系）
    return graph, reverse, all_tables

def topological_levels(graph, reverse, all_tables):
    """计算每个表的拓扑层级（0=叶子层，数字越大越靠近根）"""
    in_degree = {t: 0 for t in all_tables}
    for t in all_tables:
        in_degree[t] = len(graph.get(t, set()))
    
    queue = deque([t for t in all_tables if in_degree.get(t, 0) == 0])
    levels = {}
    level = 0
    
    while queue:
        for _ in range(len(queue)):
            t = queue.popleft()
            levels[t] = level
            for dep in reverse.get(t, set()):
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    queue.append(dep)
        level += 1
    
    # 环形依赖中的表设为 -1
    for t in all_tables:
        if t not in levels:
            levels[t] = -1
        elif len(graph.get(t, set())) == 0 and t not in levels:
            levels[t] = 0
    
    return levels

def detect_cycles(graph, all_tables):
    """DFS检测环形依赖"""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {t: WHITE for t in all_tables}
    cycles = []
    path = []
    
    def dfs(node):
        color[node] = GRAY
        path.append(node)
        for dep in graph.get(node, set()):
            if color.get(dep) == GRAY:
                # 找到环
                cycle_start = path.index(dep)
                cycles.append(path[cycle_start:] + [dep])
            elif color.get(dep) == WHITE:
                dfs(dep)
        path.pop()
        color[node] = BLACK
    
    for t in all_tables:
        if color.get(t) == WHITE:
            dfs(t)
    
    return cycles

def generate_mermaid_dag(graph, reverse, levels, cycles):
    """生成依赖关系 Mermaid 有向图"""
    lines = ["graph TD"]
    cycle_tables = set()
    for c in cycles:
        for t in c:
            cycle_tables.add(t)
    
    # 添加节点
    for t in sorted(levels.keys()):
        lvl = levels.get(t, 0)
        if t in cycle_tables:
            lines.append(f'  {t.replace("-","_")}["⚠️ {t}"]:::cycle')
        else:
            prefix = "L" + str(lvl)
            lines.append(f'  {t.replace("-","_")}["{t}"]')
    
    # 添加边
    for child, parents in graph.items():
        for parent in parents:
            lines.append(f'  {child.replace("-","_")} --> {parent.replace("-","_")}')
    
    if len(lines) == 1:
        lines.append('  %% No dependencies found')
    
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="表依赖关系分析器")
    parser.add_argument("--host", default="localhost"); parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--db", default=os.environ.get("DB_NAME",""))
    parser.add_argument("--user", default="root"); parser.add_argument("--password", default=os.environ.get("DB_PASSWORD",""))
    parser.add_argument("--ssl", default="false")
    parser.add_argument("--input", help="已有 --get-relations JSON 文件")
    parser.add_argument("--output", "-o", default="table_deps.html", help="输出HTML路径")
    parser.add_argument("--format", "-f", default="html", choices=["json","html","markdown"], help="输出格式")
    args = parser.parse_args()

    # 获取数据
    if args.input:
        with open(args.input) as f: raw = json.load(f)
        data = raw.get("relations", raw) if isinstance(raw, dict) else raw
        db_name = raw.get("database", args.db or "unknown") if isinstance(raw, dict) else args.db or "unknown"
    elif args.db:
        q = MySQLQuery(args.host, args.port, args.db, args.user, args.password, args.ssl)
        q.connect()
        res = q.get_relations()
        q.close()
        raw = res.get("relations", res)
        data = raw.get("relations", raw) if isinstance(raw, dict) else raw
        db_name = args.db
    else:
        parser.print_help(); return
    
    relations = data if isinstance(data, list) else data.get("relations", [])
    
    # 构建依赖图
    graph, reverse, all_tables = build_dependency_graph(relations)
    levels = topological_levels(graph, reverse, all_tables)
    cycles = detect_cycles(graph, all_tables)
    mermaid_dag = generate_mermaid_dag(graph, reverse, levels, cycles)
    
    # 统计
    level_dist = defaultdict(int)
    for t, l in levels.items():
        level_dist[l] += 1
    max_level = max(levels.values()) if levels else 0
    isolated = [t for t in all_tables if t not in graph and t not in reverse]
    
    # 生成行
    dep_rows = []
    impact_rows = []
    for t in sorted(levels.keys(), key=lambda x: (levels.get(x, 0), x)):
        l = levels.get(t, 0)
        parents = graph.get(t, set())
        children = reverse.get(t, set())
        
        # 影响范围：所有下游表
        downstream = set()
        stack = list(children)
        while stack:
            n = stack.pop()
            if n not in downstream:
                downstream.add(n)
                stack.extend(reverse.get(n, set()))
        
        lvl_str = f"L{l}" if l >= 0 else "CYCLE"
        is_cycle = l < 0
        row_class = f"level-{min(l,3)}" if l >= 0 else "circular"
        
        chain = " → ".join(sorted(parents)) if parents else "孤立表"
        if is_cycle: chain = "⚠️ 环形依赖"
        
        dep_rows.append(
            f'<tr class="{row_class}"><td>{"⚠️ " if is_cycle else ""}{t}</td>'
            f'<td>{lvl_str}</td><td>{len(parents)}</td><td>{len(children)}</td>'
            f'<td>{len(downstream)}张表</td><td><code>{chain}</code></td></tr>'
        )
        
        impact = " → ".join(sorted(downstream)) if downstream else "无下游依赖"
        impact_rows.append(
            f'<tr class="{row_class}"><td>{"⚠️ " if is_cycle else ""}{t}</td>'
            f'<td>{lvl_str}</td><td><code>{impact}</code></td></tr>'
        )
    
    cycle_section = ""
    if cycles:
        cycle_html = []
        for cycle in cycles:
            chain = " → ".join(cycle)
            cycle_html.append(f'<p class="circular">⚠️ 环形依赖: {chain}</p>')
        cycle_section = "\n".join(cycle_html)
    else:
        cycle_section = '<p class="text-success">✅ 未检测到环形依赖</p>'
    
    html = HTML_TEMPLATE.format(
        db_name=db_name,
        table_count=len(all_tables),
        fk_count=len(relations),
        level_count=max_level + 1,
        cycle_status=f"⚠️ {len(cycles)}处" if cycles else "✅ 无",
        l0=level_dist.get(0, 0),
        l1=level_dist.get(1, 0),
        l2=sum(level_dist.get(i,0) for i in range(2, max_level)),
        root_count=len([t for t,l in levels.items() if l >= 0 and l == max_level and not children]),
        mermaid_dag=mermaid_dag,
        dep_rows="\n".join(dep_rows),
        cycle_section=cycle_section,
        impact_rows="\n".join(impact_rows),
        gen_time=__import__("datetime").datetime.now().isoformat()
    )
    
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)
    
    result = {"status":"success","output":args.output,"tables":len(all_tables),"fks":len(relations),
              "levels":max_level+1,"cycles":len(cycles),"isolated":len(isolated)}
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__": main()

