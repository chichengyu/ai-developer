#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skill Bridge (Python 版)
DatabaseQuery 与审计报告生成器的桥接工具：
将 DatabaseQuery 输出自动转换为审计报告生成器输入。
用法：
  python skill_bridge.py --analyze-result analyze_result.json --audit-output audit_input.json
  python skill_bridge.py --db mydb --tables user order --audit-format markdown --output combined_report.md
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
_SCRIPT_DIR = Path(__file__).resolve().parent

import json, sys, os, argparse, datetime
from pathlib import Path
try:
    from database_query import MySQLQuery
except ImportError:
    print("错误：缺少 pymysql 依赖。请执行: pip install -r requirements.txt")
    sys.exit(1)

QUALITY_WARN_THRESHOLDS = {"nullRatio": 0.2, "emptyStringRatio": 0.3, "sentinelValueRatio": 0.1}

def convert_analyze_to_audit(analyze_data, session_id=None, skills=None, tools=None):
    if isinstance(analyze_data, str):
        with open(analyze_data) as f: analyze_data = json.loads(f.read())
    analysis = analyze_data.get("analysis", analyze_data)
    columns = analysis.get("columns", [])
    table_name = analysis.get("table", "unknown")
    quality_issues = []
    for col in columns:
        warnings = []
        col_name = col.get("name", "unknown")
        nr = col.get("nullRatio", 0)
        esr = col.get("emptyStringRatio", 0)
        svr = col.get("sentinelValueRatio", 0)
        try: nr = float(nr)
        except: nr = 0
        try: esr = float(esr)
        except: esr = 0
        try: svr = float(svr)
        except: svr = 0
        if nr > QUALITY_WARN_THRESHOLDS["nullRatio"]:
            warnings.append(f"NULL率({nr:.1%})偏高")
        if esr > QUALITY_WARN_THRESHOLDS["emptyStringRatio"]:
            warnings.append(f"空字符串率({esr:.1%})过高")
        if svr > QUALITY_WARN_THRESHOLDS["sentinelValueRatio"]:
            warnings.append(f"哨兵值率({svr:.1%})异常")
        qs = 1.0 - min(nr*0.4, 0.4) - min(esr*0.3, 0.3) - min(svr*0.3, 0.3)
        quality_issues.append({
            "table": table_name, "column": col_name,
            "nullRatio": round(nr,4), "emptyStringRatio": round(esr,4),
            "sentinelValueRatio": round(svr,4), "qualityScore": round(max(0,qs),4),
            "warning": "; ".join(warnings) if warnings else "正常"
        })
    audit_data = {
        "sessionId": session_id or f"bridge_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "timestamp": datetime.datetime.now().isoformat(),
        "title": f"数据质量审计 - {table_name}",
        "skills": skills or ["DatabaseQuery [已有]", "java-superpowers-contract [已有]"],
        "tools": tools or ["DatabaseQuery", "SkillBridge"],
        "filesRead": [], "filesModified": [], "sqlExecuted": [],
        "dataQualityIssues": quality_issues,
        "summary": {"totalSkills": 2, "totalTools": 2, "totalFilesRead": 0,
                    "totalFilesModified": 0, "totalSqlExecuted": 0,
                    "totalQualityIssues": len([q for q in quality_issues if q["warning"] != "正常"])}
    }
    return audit_data

def main():
    parser = argparse.ArgumentParser(description="Skill Bridge 技能桥接工具")
    parser.add_argument("--analyze-result", help="DatabaseQuery --analyze-table 的JSON结果文件")
    parser.add_argument("--audit-output", default="audit_input.json", help="输出的审计JSON文件")
    parser.add_argument("--audit-format", choices=["json","markdown","html"], default="markdown")
    parser.add_argument("--output", default="combined_report", help="最终报告文件（不含扩展名）")
    parser.add_argument("--db", help="数据库名（直接运行分析用）")
    parser.add_argument("--tables", nargs="+", help="要分析的表名列表")
    parser.add_argument("--host", default="localhost"); parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default=os.environ.get("DB_PASSWORD",""))
    args = parser.parse_args()

    if args.analyze_result:
        audit_data = convert_analyze_to_audit(args.analyze_result)
        with open(args.audit_output, "w") as f:
            json.dump(audit_data, f, ensure_ascii=False, indent=2)
        # 运行时生成报告
        report_path = f"{args.output}.{args.audit_format}"
        subprocess.run(["python", str(_SCRIPT_DIR / "audit_report_generator.py"), "--input", args.audit_output,
                       "--format", args.audit_format, "--output", report_path])
        print(json.dumps({"status":"success","audit_data":args.audit_output,"report":report_path}))
    elif args.db and args.tables:
        # 直接分析表并生成审计报告
        all_issues = []
        q = MySQLQuery(args.host, args.port, args.db, args.user, args.password)
        q.connect()
        for table in args.tables:
            data = q.analyze_table(table)
            audit = convert_analyze_to_audit(data, session_id=f"bridge_{table}")
            all_issues.extend(audit["dataQualityIssues"])
        q.close()
        combined_audit = {
            "sessionId": f"bridge_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "timestamp": datetime.datetime.now().isoformat(),
            "title": f"数据质量审计 - {', '.join(args.tables)}",
            "skills": ["DatabaseQuery [已有]", "java-superpowers-contract [已有]"],
            "tools": ["DatabaseQuery", "SkillBridge"],
            "filesRead": [], "filesModified": [], "sqlExecuted": [],
            "dataQualityIssues": all_issues,
            "summary": {"totalSkills": 2, "totalTools": 2, "totalFilesRead": 0,
                        "totalFilesModified": 0, "totalSqlExecuted": 0,
                        "totalQualityIssues": len([q for q in all_issues if q["warning"] != "正常"])}
        }
        with open(args.audit_output, "w") as f:
            json.dump(combined_audit, f, ensure_ascii=False, indent=2)
        report_path = f"{args.output}.{args.audit_format}"
        subprocess.run(["python", str(_SCRIPT_DIR / "audit_report_generator.py"), "--input", args.audit_output,
                       "--format", args.audit_format, "--output", report_path])
        print(json.dumps({"status":"success","tables":args.tables,"issues":len(all_issues),"report":report_path}))
    else:
        parser.print_help()
if __name__ == "__main__": main()



