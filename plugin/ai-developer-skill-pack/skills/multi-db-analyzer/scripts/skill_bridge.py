#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skill Bridge - Convert DatabaseQuery output to audit report input.
Converts DatabaseQuery output to audit report input.
Usage:
  python skill_bridge.py --analyze-result analyze.json --audit-output audit_input.json
  python skill_bridge.py --db-type mysql --db mydb --tables user order --audit-format markdown
"""
import json, sys, os, argparse, datetime, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from db_engine import create_engine, get_engine_display_name
except ImportError:
    print(json.dumps({"status":"error","message":"Need db_engine.py"})); sys.exit(1)

try:
    from cred_manager import CredentialManager
    CM = CredentialManager()
except ImportError:
    CM = None

QUALITY_WARN = {"nullRatio":0.2,"emptyStringRatio":0.3,"sentinelValueRatio":0.1}

def convert_analyze_to_audit(analyze_data, session_id=None, skills=None, tools=None):
    if isinstance(analyze_data, str):
        with open(analyze_data) as f: analyze_data = json.load(f)
    analysis = analyze_data.get("analysis", analyze_data)
    columns = analysis.get("columns", [])
    table_name = analysis.get("table", "unknown")
    quality_issues = []
    for col in columns:
        cn = col.get("name","unknown")
        nr = float(col.get("nullRatio",0) or 0)
        esr = float(col.get("emptyStringRatio",0) or 0)
        svr = float(col.get("sentinelValueRatio",0) or 0)
        warnings = []
        if nr > QUALITY_WARN["nullRatio"]: warnings.append(f"NULL ratio ({nr:.1%}) elevated")
        if esr > QUALITY_WARN["emptyStringRatio"]: warnings.append(f"Empty string ratio ({esr:.1%}) too high")
        if svr > QUALITY_WARN["sentinelValueRatio"]: warnings.append(f"Sentinel value ({svr:.1%}) abnormal")
        qs = round(max(0, 1-min(nr*0.4,0.4)-min(esr*0.3,0.3)-min(svr*0.3,0.3)), 4)
        quality_issues.append({"table":table_name,"column":cn,"nullRatio":round(nr,4),
            "emptyStringRatio":round(esr,4),"sentinelValueRatio":round(svr,4),
            "qualityScore":qs,"warning":"; ".join(warnings) if warnings else "Normal"})
    audit = {"sessionId":session_id or f"bridge_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "timestamp":datetime.datetime.now().isoformat(),"title":f"Data Quality Audit - {table_name}",
        "skills":skills or ["DatabaseQuery [Present]","AuditReportGenerator [Present]"],
        "tools":tools or ["DatabaseQuery","SkillBridge"],"filesRead":[],"filesModified":[],
        "sqlExecuted":[],"dataQualityIssues":quality_issues,
        "summary":{"totalSkills":2,"totalTools":2,"totalFilesRead":0,"totalFilesModified":0,
            "totalSqlExecuted":0,"totalQualityIssues":len([q for q in quality_issues if q["warning"]!="Normal"])}}
    return audit

def main():
    parser = argparse.ArgumentParser(description="Skill Bridge Tool")
    parser.add_argument("--analyze-result", help="DatabaseQuery --analyze-table JSON result file")
    parser.add_argument("--audit-output", default="audit_input.json")
    parser.add_argument("--audit-format", choices=["json","markdown","html"], default="markdown")
    parser.add_argument("--output", default="combined_report")
    parser.add_argument("--db-type", default="mysql")
    parser.add_argument("--db", help="Database name")
    parser.add_argument("--tables", nargs="+")
    parser.add_argument("--host", default="localhost"); parser.add_argument("--port", type=int)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default=os.environ.get("DB_PASSWORD",""))
    args = parser.parse_args()

    if args.analyze_result:
        audit_data = convert_analyze_to_audit(args.analyze_result)
        with open(args.audit_output,"w") as f: json.dump(audit_data,f,ensure_ascii=False,indent=2)
        report_path = f"{args.output}.{args.audit_format}"
        subprocess.run([sys.executable, str(Path(__file__).parent/"audit_report_generator.py"),
            "--input", args.audit_output, "--format", args.audit_format, "--output", report_path])
        print(json.dumps({"status":"success","audit_data":args.audit_output,"report":report_path}))
    elif args.db and args.tables:
        all_issues = []
        engine = create_engine(args.db_type, args.host, args.port, args.db, args.user, args.password)
        engine.connect()
        for table in args.tables:
            data = engine.analyze_table(table)
            audit = convert_analyze_to_audit(data, session_id=f"bridge_{table}")
            all_issues.extend(audit["dataQualityIssues"])
        engine.close()
        combined = {"sessionId":f"bridge_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "timestamp":datetime.datetime.now().isoformat(),"title":f"Data Quality Audit - {', '.join(args.tables)}",
            "skills":["DatabaseQuery [Present]","AuditReportGenerator [Present]"],
            "tools":["DatabaseQuery","SkillBridge"],"filesRead":[],"filesModified":[],
            "sqlExecuted":[],"dataQualityIssues":all_issues,
            "summary":{"totalSkills":2,"totalTools":2,"totalFilesRead":0,"totalFilesModified":0,
                "totalSqlExecuted":0,"totalQualityIssues":len([q for q in all_issues if q["warning"]!="Normal"])}}
        with open(args.audit_output,"w") as f: json.dump(combined,f,ensure_ascii=False,indent=2)
        report_path = f"{args.output}.{args.audit_format}"
        subprocess.run([sys.executable, str(Path(__file__).parent/"audit_report_generator.py"),
            "--input", args.audit_output, "--format", args.audit_format, "--output", report_path])
        print(json.dumps({"status":"success","tables":args.tables,"issues":len(all_issues),"report":report_path}))
    else: parser.print_help()
if __name__ == "__main__": main()
