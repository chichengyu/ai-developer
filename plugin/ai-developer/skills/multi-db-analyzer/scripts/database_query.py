#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DatabaseQuery - Multi-DB Query Engine. Supports MySQL, PostgreSQL, SQLite, SQL Server, Oracle, MariaDB.
Usage:
  python database_query.py --db-type mysql --db mydb --get-schema
  python database_query.py --db-type sqlite --db mydb.db --analyze-all
  python database_query.py --db-type postgresql --db mydb --analyze-table user
  python database_query.py --db-type mysql --db mydb "SELECT * FROM user LIMIT 5"
"""
import json, os, sys, argparse, datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from db_engine import create_engine, list_supported_engines, get_engine_display_name
except ImportError:
    print(json.dumps({"status":"error","message":"Need db_engine.py in same directory. See db_engine.py"}))
    sys.exit(1)
try:
    from cred_manager import CredentialManager
except ImportError:
    CredentialManager = None

CM = CredentialManager

CONFIG_PATH = Path.home() / ".multi-db-analyzer-config.json"

class DatabaseQuery:
    """Multi-DB query engine wrapper around db_engine.DatabaseEngine."""
    def __init__(self, host="localhost", port=3306, db="", user="root", password="", ssl_mode="false"):
        self.host = host; self.port = int(port)
        self.db = db; self.user = user
        self.password = password or os.environ.get("DB_PASSWORD", ""); self.ssl_mode = ssl_mode
        self._engine = None

    def connect(self, db_type="mysql"):
        self._engine = create_engine(db_type=db_type, host=self.host, port=self.port,
            db=self.db, user=self.user, password=self.password, ssl_mode=self.ssl_mode)
        return self._engine.connect()

    def close(self):
        if self._engine: self._engine.close()

    def __getattr__(self, name):
        if self._engine and hasattr(self._engine, name):
            return getattr(self._engine, name)
        return super().__getattribute__(name)

MySQLQuery = DatabaseQuery

def save_config(host, port, db, user, password, db_type="mysql"):
    try:
        cfg = {"db_type":db_type,"host":host,"port":str(port),"db":db,"user":user,"password":password}
        Path(CONFIG_PATH).parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        return {"status":"config_saved","path":str(CONFIG_PATH)}
    except Exception as e: return {"status":"config_error","message":str(e)}

def load_config():
    if CONFIG_PATH.exists():
        try: return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except: pass
    return {}

def clear_config():
    if CONFIG_PATH.exists(): CONFIG_PATH.unlink()
    return {"status":"config_cleared"}

def main():
    parser = argparse.ArgumentParser(description="DatabaseQuery - Multi-DB Query & Analysis Tool")
    engine_list = ", ".join(list_supported_engines())
    parser.add_argument("--db-type", help=f"REQUIRED: Database type. {engine_list}")
    parser.add_argument("--host", help="Database host. REQUIRED if not using profile.")
    parser.add_argument("--port", type=int)
    parser.add_argument("--db", default=os.environ.get("DB_NAME",""))
    parser.add_argument("--user", help="Database user. REQUIRED if not using profile.")
    parser.add_argument("--password", default=os.environ.get("DB_PASSWORD",""), help="Database password. REQUIRED if not using profile.")
    parser.add_argument("--ssl", default="false", choices=["false","true","verify-ca"])
    parser.add_argument("--get-schema", action="store_true")
    parser.add_argument("--analyze-all", action="store_true")
    parser.add_argument("--analyze-table", nargs="?")
    parser.add_argument("--analyze-deep", nargs="?")
    parser.add_argument("--get-relations", action="store_true")
    parser.add_argument("--table-deps", action="store_true")
    parser.add_argument("--explain", nargs="?")
    parser.add_argument("--export-csv", nargs="?")
    parser.add_argument("--pr-report", nargs="*")
    parser.add_argument("--compare-entities", action="store_true")
    parser.add_argument("--entity-path", default=".")
    parser.add_argument("--output","-o")
    parser.add_argument("--save-config", action="store_true")
    parser.add_argument("--clear-config", action="store_true")
    parser.add_argument("--profile", help="Use a saved profile (from ~/.multi-db-analyzer/profiles.json)")
    parser.add_argument("--save-profile", help="Save current connection as a named profile")
    parser.add_argument("--list-profiles", action="store_true", help="List all saved profiles")
    parser.add_argument("--delete-profile", help="Delete a named profile")
    parser.add_argument("--set-default-profile", help="Set a profile as default")
    parser.add_argument("sql", nargs="*")
    args = parser.parse_args()

    if args.clear_config: print(json.dumps(clear_config())); return
    if args.list_profiles:
        if CM:
            print(json.dumps(CM.list_profiles(), ensure_ascii=False, indent=2))
        else:
            print(json.dumps({"status":"error","message":"cred_manager.py not available"}))
        return
    if args.delete_profile:
        if CM:
            print(json.dumps(CM.delete_profile(args.delete_profile), ensure_ascii=False))
        else:
            print(json.dumps({"status":"error","message":"cred_manager.py not available"}))
        return
    if args.set_default_profile:
        if CM:
            print(json.dumps(CM.set_default(args.set_default_profile), ensure_ascii=False))
        else:
            print(json.dumps({"status":"error","message":"cred_manager.py not available"}))
        return
   if args.save_config:
       print(json.dumps(save_config(args.host, args.port or 3306, args.db, args.user, args.password, args.db_type)))
       return
    if args.save_profile:
        if CM:
            print(json.dumps(CM.save_profile(
                args.save_profile, args.db_type, args.host,
                args.port or 3306, args.db, args.user, args.password, args.ssl
            ), ensure_ascii=False))
        else:
            print(json.dumps({"status":"error","message":"cred_manager.py not available"}))
        return

    cfg = load_config()
    profile_data = None
    resolved_profile = args.profile or os.environ.get("DB_PROFILE", "")
    if resolved_profile:
        if CM:
            profile_data = CM.load_profile(resolved_profile)
            if not profile_data:
                print(json.dumps({"status":"error","message":f"Profile '{resolved_profile}' not found"}))
                if CM:
                    profiles = CM.list_profiles()
                    if profiles:
                        print(json.dumps({"available_profiles": [p["name"] for p in profiles]}, ensure_ascii=False))
                return
        else:
            print(json.dumps({"status":"error","message":"cred_manager.py not available, cannot load profiles"}))
            return
    elif not resolved_profile and CM:
        default_name = CM.get_default()
        if default_name:
            profile_data = CM.load_profile(default_name)
            resolved_profile = default_name

    # Apply profile overrides (profile values are overridden by explicit args)
    if profile_data:
        if not args.db_type and profile_data.get("db_type"):
            pass  # db_type applied during resolution below
        if not args.host:
            args.host = profile_data.get("host", args.host)
        if not args.port:
            args.port = int(profile_data.get("port", 0))
        if not args.db:
            args.db = profile_data.get("db", "")
        if not args.user:
            args.user = profile_data.get("user", args.user)
        if not args.password:
            args.password = profile_data.get("password", "")
        if args.ssl == "false":
            args.ssl = profile_data.get("ssl_mode", "false")

    dt_from_cfg = cfg.get("db_type", "")
    dt_from_env = os.environ.get("DB_TYPE", "")
    resolved_db_type = args.db_type
    if not resolved_db_type and profile_data and profile_data.get("db_type"):
        resolved_db_type = profile_data["db_type"]
    if not resolved_db_type and dt_from_cfg:
        resolved_db_type = dt_from_cfg
    if not resolved_db_type and dt_from_env:
        resolved_db_type = dt_from_env
    if not resolved_db_type:
        print(json.dumps({"status":"error","message":"REQUIRED: Please specify --db-type. Options: "+", ".join(list_supported_engines())}))
        return
    if not args.db: args.db = cfg.get("db", "")
    if not args.password: args.password = cfg.get("password", "")
    if not args.host: args.host = cfg.get("host", "")
    if not args.port: args.port = int(cfg.get("port", 0))

    if not resolved_db_type:
        print(json.dumps({"status":"error","message":"Database type required. Use --db-type. Supported: "+", ".join(list_supported_engines())}))
        return

    if resolved_db_type not in list_supported_engines():
        print(json.dumps({"status":"error","message":f"Unsupported db-type '{resolved_db_type}'. Supported: "+", ".join(list_supported_engines())}))
        return

    if not args.db:
        print(json.dumps({"status":"error","message":"Please specify --db or set DB_NAME env var"}))
        return

    q = DatabaseQuery(args.host, args.port, args.db, args.user, args.password, args.ssl)
    if not q.connect(resolved_db_type): return

    result = None
    try:
        if args.get_schema: result = q.get_schema()
        elif args.analyze_all: result = q.analyze_all()
        elif args.analyze_table: result = q.analyze_table(args.analyze_table)
        elif args.analyze_deep: result = q.analyze_deep(args.analyze_deep)
        elif args.get_relations: result = q.get_relations()
        elif args.table_deps: result = q.table_deps()
        elif args.explain: result = q.explain(args.explain)
        elif args.export_csv: result = q.export_csv(args.export_csv, args.output or "export.csv")
        elif args.pr_report is not None: result = q.pr_report(args.pr_report)
        elif args.compare_entities: result = q.compare_entities(args.entity_path or ".")
        elif args.sql: result = q.execute(" ".join(args.sql))
        else: parser.print_help(); return
    finally:
        try: q.close()
        except: pass

    output = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.output and not args.export_csv:
        Path(args.output).write_text(output, encoding="utf-8")
        print(json.dumps({"status":"saved","output":args.output}))
    else:
        print(output)

   if result and result.get("status","").startswith("success") and not cfg:
        if CM and resolved_profile:
            # Already using a profile, update its password
            pass
        elif CM:
            # Auto-save as a profile named after db_type
            auto_name = f"{resolved_db_type}-{args.host or 'local'}"
            CM.save_profile(auto_name, resolved_db_type, args.host, args.port or 3306, args.db, args.user, args.password, args.ssl)
        else:
            save_config(args.host, args.port, args.db, args.user, args.password, resolved_db_type)

if __name__ == "__main__":
    main()
