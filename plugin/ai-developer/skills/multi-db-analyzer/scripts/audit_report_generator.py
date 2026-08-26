#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Java + Superpowers 审计报告生成器 (Python 版)
=========================================
配置优先级：Python > Node.js > Java
对应契约第9节 — 全时执行审计汇报

能力：
  - 读取 JSON 审计数据（stdin 或文件）
  - 生成三大格式报告：JSON / Markdown / HTML
  - 自定义输出路径和报告标题
  - 追加审计条目到历史审计日志
  - 数据质量三指标分析（NULL率/空字符串率/哨兵值率）

用法：
  python audit_report_generator.py --input audit.json --format markdown --output report.md
  python audit_report_generator.py --input audit.json --format html --output report.html
  echo '{...}' | python audit_report_generator.py --stdin --format json
"""

import json
import sys
import os
import argparse
import datetime
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# ========== 配置管理 ==========
CONFIG_DIR = Path.home() / ".multi-db-analyzer-audit"
CONFIG_FILE = CONFIG_DIR / "config.json"
HISTORY_FILE = CONFIG_DIR / "audit_history.jsonl"


def ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"default_format": "markdown", "output_dir": str(Path.cwd())}


def save_config(config):
    ensure_config_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def append_history(audit_data):
    ensure_config_dir()
    record = {
        "timestamp": datetime.datetime.now().isoformat(),
        "sessionId": audit_data.get("sessionId", ""),
        "summary": audit_data.get("summary", {}),
    }
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_history(limit=50):
    records = []
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return records[-limit:]


# ========== 数据质量三指标分析 ==========
SENTINEL_VALUES = {"0", "-1", "1900-01-01", "1970-01-01", "9999-12-31", "-9999", ""}


def analyze_data_quality(column_name, null_count, total_count, empty_string_count=0, top_values=None):
    """
    数据质量三指标分析
    ① NULL率  ② 空字符串率  ③ 哨兵值异常率
    """
    if total_count == 0:
        return 0.0, 0.0, 0.0, 1.0, "空表"

    null_ratio = null_count / total_count if total_count > 0 else 0.0
    empty_string_ratio = empty_string_count / total_count if total_count > 0 else 0.0

    sentinel_count = 0
    if top_values:
        for tv in top_values:
            val = str(tv.get("value", ""))
            if val in SENTINEL_VALUES:
                sentinel_count += tv.get("count", 0)
    sentinel_value_ratio = sentinel_count / total_count if total_count > 0 else 0.0

    quality_score = 1.0 - (null_ratio * 0.4 + empty_string_ratio * 0.3 + sentinel_value_ratio * 0.3)
    quality_score = max(0.0, min(1.0, quality_score))

    warnings = []
    if null_ratio > 0.8:
        warnings.append(f"NULL率({null_ratio:.1%})过高: 潜在冗余字段")
    elif null_ratio > 0.2:
        warnings.append(f"NULL率({null_ratio:.1%})偏高: 建议补充默认值")

    if empty_string_ratio > 0.3:
        warnings.append(f"空字符串率({empty_string_ratio:.1%})过高: 字段设计可能存在问题")

    if sentinel_value_ratio > 0.1:
        warnings.append(f"哨兵值率({sentinel_value_ratio:.1%})异常: 业务层可能使用了哨兵值替代NULL")

    warning = "; ".join(warnings) if warnings else "正常"
    return null_ratio, empty_string_ratio, sentinel_value_ratio, round(quality_score, 4), warning


# ========== 审计数据读取 ==========
def read_audit_data(input_path=None, use_stdin=False):
    if use_stdin:
        raw = sys.stdin.read()
        if not raw.strip():
            print("错误: stdin 输入为空", file=sys.stderr)
            sys.exit(1)
        return json.loads(raw)
    elif input_path:
        with open(input_path, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return generate_sample_audit_data()


def generate_sample_audit_data():
    return {
        "sessionId": f"session_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "timestamp": datetime.datetime.now().isoformat(),
        "title": "示例审计报告",
        "skills": [
            "audit-report-generator [已有]",
            "multi-db-analyzer [已有]",
            "Brainstorming & Planning [已有]",
        ],
        "tools": ["fetch_codebase_ctx", "analyze_dependencies", "DatabaseQuery"],
        "filesRead": [
            {"path": "src/main/resources/application-dev.yml", "status": "[已有]"},
            {"path": "src/main/java/com/example/UserService.java", "status": "[已有]"},
            {"path": "src/main/java/com/example/UserController.java", "status": "[已有]"},
        ],
        "filesModified": [
            {"path": "src/main/java/com/example/UserController.java", "change": "新增校验逻辑 [新增]"},
            {"path": "src/main/resources/application-dev.yml", "change": "新增自定义配置项 [新增]"},
        ],
        "sqlExecuted": [
            {"sql": "ALTER TABLE user ADD COLUMN age INT DEFAULT 0 COMMENT '年龄'", "type": "DDL"},
            {"sql": "SELECT * FROM user WHERE status = 1 LIMIT 10", "type": "SELECT"},
        ],
        "dataQualityIssues": [
            {"table": "user", "column": "email", "nullRatio": 0.0234, "emptyStringRatio": 0.0156, "sentinelValueRatio": 0.0, "qualityScore": 0.98, "warning": "正常"},
            {"table": "user", "column": "phone", "nullRatio": 0.3512, "emptyStringRatio": 0.0230, "sentinelValueRatio": 0.0, "qualityScore": 0.85, "warning": "NULL率(35.1%)偏高: 建议补充默认值"},
        ],
        "summary": {
            "totalSkills": 3, "totalTools": 3, "totalFilesRead": 3,
            "totalFilesModified": 2, "totalSqlExecuted": 2, "totalQualityIssues": 2,
        },
    }


# ========== 报告生成 ==========
def generate_json_report(audit_data):
    report = {
        "reportType": "execution_audit",
        "generatedAt": datetime.datetime.now().isoformat(),
        "auditData": audit_data,
        "qualityAnalysis": {},
    }
    quality_issues = audit_data.get("dataQualityIssues", [])
    if quality_issues:
        report["qualityAnalysis"] = {
            "totalIssues": len(quality_issues),
            "criticalIssues": [qi for qi in quality_issues if qi.get("qualityScore", 1.0) < 0.6],
            "warnings": [qi for qi in quality_issues if 0.6 <= qi.get("qualityScore", 1.0) < 0.9],
            "details": quality_issues,
        }
    return json.dumps(report, ensure_ascii=False, indent=2)


def generate_markdown_report(audit_data):
    title = audit_data.get("title", "执行审计报告")
    ts = audit_data.get("timestamp", datetime.datetime.now().isoformat())
    session_id = audit_data.get("sessionId", "N/A")

    lines = [
        f"# 执行审计报告: {title}",
        "",
        f"- **会话ID**: {session_id}",
        f"- **时间戳**: {ts}",
        f"- **生成时间**: {datetime.datetime.now().isoformat()}",
        "",
        "## 1. 技能与工具调用",
        "",
        "### 加载的技能 (Skills)",
    ]
    for sk in audit_data.get("skills", []):
        lines.append(f"- {sk}")

    lines.extend(["", "### 调用的工具 (Tools)"])
    for t in audit_data.get("tools", []):
        lines.append(f"- `{t}`")

    lines.extend(["", "## 2. 文件访问记录", "", "### 读取的文件"])
    for fr in audit_data.get("filesRead", []):
        lines.append(f"- {fr.get('status', '[已有]')} `{fr['path']}`")

    lines.extend(["", "### 修改的文件"])
    for fm in audit_data.get("filesModified", []):
        lines.append(f"- `{fm['path']}` -> {fm.get('change', '')}")

    lines.extend(["", "## 3. SQL 执行记录"])
    for sq in audit_data.get("sqlExecuted", []):
        lines.append(f"- **[{sq.get('type', 'SQL')}]** `{sq['sql']}`")

    quality_issues = audit_data.get("dataQualityIssues", [])
    if quality_issues:
        lines.extend(["", "## 4. 数据质量三指标分析", ""])
        lines.append("| 表名 | 字段 | NULL率 | 空字符串率 | 哨兵值率 | 质量分 | 警告 |")
        lines.append("|------|------|--------|-----------|----------|--------|------|")
        for qi in quality_issues:
            lines.append(
                f"| {qi['table']} | {qi['column']} | "
                f"{qi.get('nullRatio', 0):.2%} | "
                f"{qi.get('emptyStringRatio', 0):.2%} | "
                f"{qi.get('sentinelValueRatio', 0):.2%} | "
                f"{qi.get('qualityScore', 1.0):.2f} | "
                f"{qi.get('warning', '正常')} |"
            )

    lines.extend(["", "## 5. 统计摘要", ""])
    s = audit_data.get("summary", {})
    lines.append(f"- **技能数**: {s.get('totalSkills', 0)}")
    lines.append(f"- **工具数**: {s.get('totalTools', 0)}")
    lines.append(f"- **读取文件**: {s.get('totalFilesRead', 0)}")
    lines.append(f"- **修改文件**: {s.get('totalFilesModified', 0)}")
    lines.append(f"- **SQL执行**: {s.get('totalSqlExecuted', 0)}")
    lines.append(f"- **质量异常**: {s.get('totalQualityIssues', 0)}")
    return "\n".join(lines)


def generate_html_report(audit_data):
    title = audit_data.get("title", "执行审计报告")
    s = audit_data.get("summary", {})

    def esc(text):
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{esc(title)}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       max-width: 960px; margin: 2em auto; padding: 0 1em; color: #1a1a2e; background: #f8f9fa; line-height: 1.7; }}
h1 {{ color: #0d6efd; border-bottom: 2px solid #0d6efd; padding-bottom: 0.3em; }}
h2 {{ color: #198754; margin-top: 1.5em; }}
table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
th, td {{ border: 1px solid #dee2e6; padding: 0.5em; text-align: left; }}
th {{ background: #e9ecef; }}
tr:nth-child(even) {{ background: #f2f2f2; }}
code {{ background: #e9ecef; padding: 0.2em 0.4em; border-radius: 3px; }}
.warning {{ color: #dc3545; font-weight: bold; }}
.normal {{ color: #198754; }}
.summary {{ background: #e9ecef; padding: 1em; border-radius: 8px; margin: 1em 0; }}
</style>
</head>
<body>
<h1>&#x1f504; {esc(title)}</h1>
<p><strong>会话ID:</strong> {esc(audit_data.get('sessionId', 'N/A'))}</p>
<p><strong>时间戳:</strong> {esc(audit_data.get('timestamp', ''))}</p>
<p><strong>生成时间:</strong> {datetime.datetime.now().isoformat()}</p>

<h2>1. 技能与工具调用</h2>
<h3>加载的技能</h3>
<ul>
"""
    for sk in audit_data.get("skills", []):
        html += f"  <li>{esc(sk)}</li>\n"

    html += """</ul>
<h3>调用的工具</h3>
<ul>
"""
    for t in audit_data.get("tools", []):
        html += f"  <li><code>{esc(t)}</code></li>\n"

    html += """</ul>
<h2>2. 文件访问记录</h2>
<h3>读取的文件</h3>
<ul>
"""
    for fr in audit_data.get("filesRead", []):
        html += f"  <li>{esc(fr.get('status', '[已有]'))} <code>{esc(fr['path'])}</code></li>\n"

    html += """</ul>
<h3>修改的文件</h3>
<ul>
"""
    for fm in audit_data.get("filesModified", []):
        html += f"  <li><code>{esc(fm['path'])}</code> &rarr; {esc(fm.get('change', ''))}</li>\n"

    html += """</ul>
<h2>3. SQL 执行记录</h2>
<ul>
"""
    for sq in audit_data.get("sqlExecuted", []):
        html += f"  <li><strong>[{esc(sq.get('type', 'SQL'))}]</strong> <code>{esc(sq['sql'])}</code></li>\n"

    html += """</ul>
"""
    quality_issues = audit_data.get("dataQualityIssues", [])
    if quality_issues:
        html += """<h2>4. 数据质量三指标分析</h2>
<table>
<tr><th>表名</th><th>字段</th><th>NULL率</th><th>空字符串率</th><th>哨兵值率</th><th>质量分</th><th>警告</th></tr>
"""
        for qi in quality_issues:
            wc = "warning" if qi.get("warning", "") != "正常" else "normal"
            html += (
                f"<tr><td>{esc(qi['table'])}</td><td>{esc(qi['column'])}</td>"
                f"<td>{qi.get('nullRatio', 0):.2%}</td>"
                f"<td>{qi.get('emptyStringRatio', 0):.2%}</td>"
                f"<td>{qi.get('sentinelValueRatio', 0):.2%}</td>"
                f"<td>{qi.get('qualityScore', 1.0):.2f}</td>"
                f'<td class="{wc}">{esc(qi.get("warning", "正常"))}</td></tr>\n'
            )
        html += "</table>\n"

    html += f"""<h2>5. 统计摘要</h2>
<div class="summary">
<p><strong>技能数:</strong> {s.get('totalSkills', 0)}</p>
<p><strong>工具数:</strong> {s.get('totalTools', 0)}</p>
<p><strong>读取文件:</strong> {s.get('totalFilesRead', 0)}</p>
<p><strong>修改文件:</strong> {s.get('totalFilesModified', 0)}</p>
<p><strong>SQL执行:</strong> {s.get('totalSqlExecuted', 0)}</p>
<p><strong>质量异常:</strong> {s.get('totalQualityIssues', 0)}</p>
</div>
</body>
</html>"""
    return html


# ========== 密码引号包裹与 SHOW DATABASES 指南 ==========
def password_quoting_guide():
    return json.dumps({
        "title": "MySQL密码含特殊字符的引号包裹方法",
        "methods": [
            {"method": "PowerShell单引号", "desc": "密码含$时使用单引号避免变量解析",
             "example": "java -cp .;mysql-connector.jar scripts.DatabaseQuery --password 'myP$sw0rd!2024' --get-schema"},
            {"method": "PowerShell双引号", "desc": "无特殊PS变量符号时可用双引号",
             "example": 'java -cp .;mysql-connector.jar scripts.DatabaseQuery --password "myP@ssw0rd!2024" --get-schema'},
            {"method": "环境变量法(推荐)", "desc": "通过环境变量传入避免shell解释",
             "example": '$env:DB_PASSWORD = "fT85{6M6mx!+ro(r1_Nw9qU.1q1(#Dny"\njava -cp .;mysql-connector.jar scripts.DatabaseQuery --get-schema'},
            {"method": "配置文件法(最安全)", "desc": "密码保存在~/.multi-db-analyzer-config.json",
             "example": "后续无需再传入密码参数"},
        ],
    }, ensure_ascii=False, indent=2)


def show_databases_guide():
    return json.dumps({
        "title": "SHOW DATABASES 快速列举所有库",
        "commands": [
            {"desc": "列出所有数据库", "sql": "SHOW DATABASES;"},
            {"desc": "切换目标数据库", "sql": "USE <数据库名>;"},
            {"desc": "通过DatabaseQuery执行",
             "command": 'java -cp <skill目录>;<mysql-connector.jar> scripts.DatabaseQuery "SHOW DATABASES"'},
        ],
        "useCases": ["多租户环境探索", "数据库盘点", "迁移前摸底"],
    }, ensure_ascii=False, indent=2)


# ========== 主入口 ==========
def main():
    parser = argparse.ArgumentParser(description="Java + Superpowers 审计报告生成器 (Python版)")
    parser.add_argument("--input", "-i", help="审计数据 JSON 文件路径")
    parser.add_argument("--stdin", action="store_true", help="从 stdin 读取审计数据")
    parser.add_argument("--format", "-f", choices=["json", "markdown", "html"], default="markdown", help="报告格式")
    parser.add_argument("--output", "-o", help="输出文件路径 (默认输出到stdout)")
    parser.add_argument("--title", "-t", default="执行审计报告", help="报告标题")
    parser.add_argument("--sample", action="store_true", help="生成示例审计报告")
    parser.add_argument("--history", action="store_true", help="查看历史审计记录")
    parser.add_argument("--password-guide", action="store_true", help="输出密码引号包裹指南")
    parser.add_argument("--show-databases-guide", action="store_true", help="输出SHOW DATABASES指南")
    parser.add_argument("--save-config", help="保存配置: format=json|markdown|html,output_dir=<路径>")
    parser.add_argument("--clear-config", action="store_true", help="清除配置")

    args = parser.parse_args()

    if args.save_config:
        cfg = {}
        for part in args.save_config.split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                cfg[k.strip()] = v.strip()
        config = load_config()
        config.update(cfg)
        save_config(config)
        print(json.dumps({"status": "config_saved", "config": config}, ensure_ascii=False))
        return

    if args.clear_config:
        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()
        print(json.dumps({"status": "config_cleared"}, ensure_ascii=False))
        return

    if args.password_guide:
        print(password_quoting_guide())
        return

    if args.show_databases_guide:
        print(show_databases_guide())
        return

    if args.history:
        records = read_history()
        print(json.dumps(records, ensure_ascii=False, indent=2))
        return

    audit_data = generate_sample_audit_data() if args.sample else read_audit_data(args.input, args.stdin)
    audit_data["title"] = audit_data.get("title", args.title)
    append_history(audit_data)

    if args.format == "json":
        content = generate_json_report(audit_data)
    elif args.format == "html":
        content = generate_html_report(audit_data)
    else:
        content = generate_markdown_report(audit_data)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(content)
        print(json.dumps({"status": "success", "format": args.format, "output": args.output}, ensure_ascii=False))
    else:
        print(content)


if __name__ == "__main__":
    main()
