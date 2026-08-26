#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DatabaseQuery — pure Python MySQL query & analysis tool.
Zero Java dependency. Direct pymysql connection for full MySQL deep analysis.

用法：
  python database_query.py --db mydb --get-schema
  python database_query.py --db mydb --analyze-table user
  python database_query.py --db mydb --table-deps
  python database_query.py --db mydb --analyze-deep user
  python database_query.py --db mydb "SELECT * FROM user LIMIT 5"
"""
import json, os, sys, argparse, csv, re, datetime
from collections import defaultdict, deque
from pathlib import Path

try:
    import pymysql
    import pymysql.cursors
except ImportError:
    print(json.dumps({"status":"error","message":"需要安装 pymysql: pip install pymysql"}))
    sys.exit(1)

CONFIG_PATH = Path.home() / ".java-superpowers-config.json"
SENTINEL_VALUES = {"0","-1","1900-01-01","1970-01-01","9999-12-31","-9999",""}


class MySQLQuery:
    """纯 Python 实现的核心数据库查询引擎"""

    def __init__(self, host="localhost", port=3306, db="", user="root", password="", ssl_mode="false"):
        self.host = host; self.port = int(port); self.db = db
        self.user = user; self.password = password; self.ssl_mode = ssl_mode
        self.conn = None

    def connect(self):
        ssl_arg = {} if self.ssl_mode == "false" else {"ca": None, "cert": None, "key": None}
        try:
            self.conn = pymysql.connect(
                host=self.host, port=self.port, database=self.db or None,
                user=self.user, password=self.password,
                charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=10,
                ssl=ssl_arg if self.ssl_mode != "false" else None)
            return True
        except Exception as e:
            print(json.dumps({"status":"error","message":str(e)}, ensure_ascii=False))
            return False

    def close(self):
        if self.conn: self.conn.close()

    def _fetch(self, sql, params=None):
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def _fetch_one(self, sql, params=None):
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    # ========== 1. --get-schema ==========
    def get_schema(self):
        catalog = self.db
        rows = self._fetch("""
            SELECT TABLE_NAME, TABLE_COMMENT, ENGINE, TABLE_ROWS, AUTO_INCREMENT,
                   CREATE_TIME, UPDATE_TIME
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME""", (catalog,))
        tables = []
        for r in rows:
            tbl = r["TABLE_NAME"]
            cols = self._fetch("""
                SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_COMMENT,
                       EXTRA, ORDINAL_POSITION, CHARACTER_MAXIMUM_LENGTH
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
                ORDER BY ORDINAL_POSITION""", (catalog, tbl))
            pk = self._fetch("""
                SELECT COLUMN_NAME FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_KEY='PRI'""", (catalog, tbl))
            idx = self._fetch("""
                SELECT INDEX_NAME, COLUMN_NAME, NON_UNIQUE, SEQ_IN_INDEX
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME!='PRIMARY'
                ORDER BY INDEX_NAME, SEQ_IN_INDEX""", (catalog, tbl))
            tables.append({
                "name": tbl, "comment": r["TABLE_COMMENT"] or "", "engine": r["ENGINE"] or "",
                "estimatedRows": r["TABLE_ROWS"], "autoIncrement": r["AUTO_INCREMENT"],
                "columns": [{"name":c["COLUMN_NAME"],"type":c["COLUMN_TYPE"],
                             "nullable":c["IS_NULLABLE"]=="YES","default":c["COLUMN_DEFAULT"],
                             "comment":c["COLUMN_COMMENT"] or ""} for c in cols],
                "primaryKey": [p["COLUMN_NAME"] for p in pk],
                "indexes": [{"name":x["INDEX_NAME"],"column":x["COLUMN_NAME"],
                             "unique":x["NON_UNIQUE"]==0} for x in idx]
            })
        return {"status":"schema_success","schema":{"database":catalog,"tables":tables}}

    # ========== 2. --analyze-all ==========
    def analyze_all(self):
        catalog = self.db
        rows = self._fetch("""
            SELECT TABLE_NAME, ENGINE, TABLE_ROWS, DATA_LENGTH, INDEX_LENGTH, TABLE_COMMENT
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE'
            ORDER BY TABLE_ROWS DESC""", (catalog,))
        tables = []
        for r in rows:
            col_count = self._fetch_one("SELECT COUNT(*) AS c FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
                                        (catalog, r["TABLE_NAME"]))["c"]
            dl = r["DATA_LENGTH"] or 0; il = r["INDEX_LENGTH"] or 0
            tables.append({
                "name":r["TABLE_NAME"], "engine":r["ENGINE"] or "",
                "estimatedRows":r["TABLE_ROWS"], "dataLengthBytes":dl,
                "indexLengthBytes":il, "totalSizeMb":round((dl+il)/1048576,2),
                "columnCount":col_count, "comment":r["TABLE_COMMENT"] or ""
            })
        return {"status":"analyze_all_success","analysis":{"database":catalog,"tables":tables}}

    # ========== 3. --analyze-table ==========
    def analyze_table(self, table):
        catalog = self.db; st = f"`{table}`"
        meta = self._fetch_one("""
            SELECT ENGINE, TABLE_ROWS, TABLE_COMMENT, DATA_LENGTH, INDEX_LENGTH,
                   AUTO_INCREMENT, ROW_FORMAT, CREATE_TIME, UPDATE_TIME, TABLE_COLLATION
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s""", (catalog, table))
        if not meta: return {"status":"error","message":f"表 {table} 不存在"}

        actual = self._fetch_one(f"SELECT COUNT(*) AS cnt FROM {st}")["cnt"]
        cols = self._fetch("SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_COMMENT, EXTRA, CHARACTER_MAXIMUM_LENGTH FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION", (catalog, table))

        columns = []
        for c in cols:
            cn = c["COLUMN_NAME"]; sc = f"`{cn}`"; ct = c["COLUMN_TYPE"]
            info = {"name":cn,"type":ct,"nullable":c["IS_NULLABLE"]=="YES","default":c["COLUMN_DEFAULT"],"comment":c["COLUMN_COMMENT"] or ""}

            # 基本统计
            try:
                stats = self._fetch_one(f"SELECT COUNT(DISTINCT {sc}) AS dc, SUM(CASE WHEN {sc} IS NULL THEN 1 ELSE 0 END) AS nc, COUNT(*) AS tc FROM {st}")
                if stats:
                    dc,nc,tc = stats["dc"],stats["nc"],stats["tc"]
                    info.update({"distinctCount":dc,"nullCount":nc,"nullRatio":round(nc/tc,4) if tc else 0})
            except: pass

            # 数值字段
            is_num = bool(re.match(r"(?i)(INT|TINYINT|SMALLINT|MEDIUMINT|BIGINT|FLOAT|DOUBLE|DECIMAL|NUMERIC|REAL)", ct))
            is_str = bool(re.match(r"(?i)(CHAR|VARCHAR|TEXT|MEDIUMTEXT|LONGTEXT|ENUM|SET)", ct))

            if is_num:
                try:
                    ns = self._fetch_one(f"SELECT MIN({sc}) AS mn, MAX({sc}) AS mx, AVG({sc}) AS av FROM {st}")
                    if ns: info.update({"min":str(ns["mn"] or ""),"max":str(ns["mx"] or ""),"avg":str(round(ns["av"],2) if ns["av"] else "")})
                except: pass

            if is_str:
                try:
                    sl = self._fetch_one(f"SELECT MIN(LENGTH({sc})) AS minLen, MAX(LENGTH({sc})) AS maxLen, AVG(LENGTH({sc})) AS avgLen FROM {st}")
                    if sl: info.update({"minLength":sl["minLen"],"maxLength":sl["maxLen"],"avgLength":round(sl["avgLen"],1) if sl["avgLen"] else 0})
                    # 空字符串率
                    es = self._fetch_one(f"SELECT COUNT(*) AS ec FROM {st} WHERE {sc} IS NOT NULL AND {sc}=''")
                    if es: info["emptyStringCount"]=es["ec"]
                except: pass

            # 哨兵值
            try:
                sv = self._fetch_one(f"SELECT COUNT(*) AS svc FROM {st} WHERE {sc} IS NOT NULL AND CAST({sc} AS CHAR) IN ('0','-1','1900-01-01','1970-01-01','9999-12-31','-9999','')")
                if sv:
                    tc = info.get("nullCount",0) + (info.get("distinctCount",0) or 0)
                    svr = round(sv["svc"]/max(tc,1),4) if tc else 0
                    info["sentinelValueCount"]=sv["svc"]; info["sentinelValueRatio"]=svr
            except: pass

            # 质量评分
            nr = info.get("nullRatio",0) or 0; esr = info.get("emptyStringCount",0)/max(info.get("nullCount",0)+info.get("distinctCount",0) or 1,1) if info.get("emptyStringCount") else 0
            svr = info.get("sentinelValueRatio",0) or 0
            qs = round(max(0, 1-nr*0.4-esr*0.3-svr*0.3),4)
            info["qualityScore"]=qs
            warns = []
            if nr>0.8: warns.append(f"NULL率({nr:.1%})过高: 潜在冗余字段")
            elif nr>0.2: warns.append(f"NULL率({nr:.1%})偏高: 建议补充默认值")
            if esr>0.3: warns.append(f"空字符串率({esr:.1%})过高")
            if svr>0.1: warns.append(f"哨兵值率({svr:.1%})异常")
            info["warning"]="; ".join(warns) if warns else "正常"

            columns.append(info)

        return {"status":"analyze_table_success","analysis":{
            "table":table,"engine":meta["ENGINE"] or "","estimatedRows":meta["TABLE_ROWS"],
            "actualRowCount":actual,"dataLengthBytes":meta["DATA_LENGTH"],"indexLengthBytes":meta["INDEX_LENGTH"],
            "totalSizeMb":round(((meta["DATA_LENGTH"] or 0)+(meta["INDEX_LENGTH"] or 0))/1048576,2),
            "comment":meta["TABLE_COMMENT"] or "","rowFormat":meta["ROW_FORMAT"] or "",
            "collation":meta["TABLE_COLLATION"] or "",
            "columns":columns
        }}

    # ========== 4. --get-relations ==========
    def get_relations(self):
        catalog = self.db
        rels = self._fetch("""
            SELECT rc.CONSTRAINT_NAME, rc.UPDATE_RULE, rc.DELETE_RULE,
                   kcu.TABLE_NAME AS child_table, kcu.COLUMN_NAME AS child_column,
                   kcu.REFERENCED_TABLE_NAME AS parent_table, kcu.REFERENCED_COLUMN_NAME AS parent_column
            FROM information_schema.REFERENTIAL_CONSTRAINTS rc
            JOIN information_schema.KEY_COLUMN_USAGE kcu
              ON rc.CONSTRAINT_NAME=kcu.CONSTRAINT_NAME AND rc.CONSTRAINT_SCHEMA=kcu.CONSTRAINT_SCHEMA
            WHERE rc.CONSTRAINT_SCHEMA=%s
            ORDER BY kcu.TABLE_NAME""", (catalog,))
        relations = []
        tables = set()
        for r in rels:
            relations.append({
                "constraintName":r["CONSTRAINT_NAME"],"parentTable":r["parent_table"],
                "parentColumn":r["parent_column"],"childTable":r["child_table"],
                "childColumn":r["child_column"],
                "updateRule":0 if r["UPDATE_RULE"]=="RESTRICT" else 1 if r["UPDATE_RULE"]=="CASCADE" else 2,
                "deleteRule":0 if r["DELETE_RULE"]=="RESTRICT" else 1 if r["DELETE_RULE"]=="CASCADE" else 2
            })
            tables.add(r["parent_table"]); tables.add(r["child_table"])

        # Mermaid ERD
        mermaid_parts = ["erDiagram"]
        seen = set()
        for r in relations:
            pk, ck = r["parentTable"], r["childTable"]
            if (pk,ck) not in seen:
                mermaid_parts.append(f"  {pk} ||--o{{ {ck} : \"has\"")
                seen.add((pk,ck))

        return {"status":"relations_success","relations":{
            "database":catalog,"relations":relations,"mermaidErd":"\\n".join(mermaid_parts)
        }}

    # ========== 5. --table-deps ==========
    def table_deps(self):
        rels = self.get_relations()["relations"]["relations"]
        graph = defaultdict(set); rev = defaultdict(set); all_tables = set()
        for r in rels:
            p,c = r["parentTable"],r["childTable"]
            graph[c].add(p); rev[p].add(c); all_tables.add(p); all_tables.add(c)

        # 拓扑层级
        in_deg = {t:len(graph.get(t,set())) for t in all_tables}
        q = deque([t for t in all_tables if in_deg[t]==0])
        levels = {}; lvl = 0
        while q:
            for _ in range(len(q)):
                t = q.popleft(); levels[t]=lvl
                for dep in rev.get(t,set()):
                    in_deg[dep]-=1
                    if in_deg[dep]==0: q.append(dep)
            lvl+=1
        for t in all_tables:
            if t not in levels: levels[t]=-1

        # 环形检测
        WHITE,GRAY,BLACK=0,1,2; color={t:WHITE for t in all_tables}; cycles=[]; path=[]
        def dfs(n):
            color[n]=GRAY; path.append(n)
            for dep in graph.get(n,set()):
                if color.get(dep)==GRAY:
                    idx=path.index(dep); cycles.append(" -> ".join(path[idx:]+[dep]))
                elif color.get(dep)==WHITE: dfs(dep)
            path.pop(); color[n]=BLACK
        for t in all_tables:
            if color[t]==WHITE: dfs(t)

        return {"status":"table_deps_success","deps":{
            "database":self.db,"tableCount":len(all_tables),
            "levels":{t:levels[t] for t in sorted(all_tables)},
            "relations":rels,"cycles":cycles,"maxLevel":lvl-1
        }}

    # ========== 6. --analyze-deep ==========
    def analyze_deep(self, table):
        st = f"`{table}`"
        meta = self._fetch_one("SELECT ENGINE,TABLE_ROWS,DATA_LENGTH,INDEX_LENGTH,AUTO_INCREMENT,ROW_FORMAT,TABLE_COLLATION FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",(self.db,table))
        if not meta: return {"status":"error","message":f"表 {table} 不存在"}
        actual = self._fetch_one(f"SELECT COUNT(*) AS cnt FROM {st}")["cnt"]

        cols = self._fetch("SELECT COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION",(self.db,table))
        columns = []
        for c in cols:
            cn=c["COLUMN_NAME"]; sc=f"`{cn}`"; ct=c["COLUMN_TYPE"]
            info={"name":cn,"type":ct,"nullable":c["IS_NULLABLE"]=="YES"}
            try:
                s=self._fetch_one(f"SELECT COUNT(DISTINCT {sc}) AS dc,SUM(CASE WHEN {sc} IS NULL THEN 1 ELSE 0 END) AS nc,COUNT(*) AS tc FROM {st}")
                if s: info.update({"distinctCount":s["dc"],"nullCount":s["nc"],"nullRatio":round(s["nc"]/max(s["tc"],1),4)})
            except: pass
            if re.match(r"(?i)(INT|TINYINT|SMALLINT|MEDIUMINT|BIGINT|FLOAT|DOUBLE|DECIMAL|NUMERIC|REAL)", ct):
                try:
                    ns=self._fetch_one(f"SELECT MIN({sc}) AS mn,MAX({sc}) AS mx,AVG({sc}) AS av,STDDEV({sc}) AS sd FROM {st}")
                    if ns: info.update({"min":str(ns["mn"]or""),"max":str(ns["mx"]or""),"avg":str(round(ns["av"],2)if ns["av"]else""),"stddev":str(round(ns["sd"],2)if ns["sd"]else"")})
                except: pass
            if re.match(r"(?i)(CHAR|VARCHAR|TEXT|MEDIUMTEXT|LONGTEXT|ENUM|SET)", ct):
                try:
                    sl=self._fetch_one(f"SELECT MIN(LENGTH({sc}))AS minLen,MAX(LENGTH({sc}))AS maxLen,AVG(LENGTH({sc}))AS avgLen FROM {st}")
                    if sl: info.update({"minLength":sl["minLen"],"maxLength":sl["maxLen"],"avgLength":round(sl["avgLen"],1)if sl["avgLen"]else 0})
                except: pass
            columns.append(info)

        # 索引
        idx_rows = self._fetch("SELECT INDEX_NAME,COLUMN_NAME,NON_UNIQUE FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME!='PRIMARY' ORDER BY INDEX_NAME,SEQ_IN_INDEX",(self.db,table))
        seen_idx={}
        for i in idx_rows:
            n=i["INDEX_NAME"]
            if n not in seen_idx: seen_idx[n]={"name":n,"unique":i["NON_UNIQUE"]==0,"columns":[]}
            if i["COLUMN_NAME"] not in seen_idx[n]["columns"]: seen_idx[n]["columns"].append(i["COLUMN_NAME"])
        indexes = list(seen_idx.values())

        return {"status":"analyze_deep_success","analysis":{
            "table":table,"engine":meta["ENGINE"]or"","estimatedRows":meta["TABLE_ROWS"],
            "actualRowCount":actual,"dataLengthBytes":meta["DATA_LENGTH"],
            "indexLengthBytes":meta["INDEX_LENGTH"],
            "autoIncrement":meta["AUTO_INCREMENT"],
            "rowFormat":meta["ROW_FORMAT"]or"","collation":meta["TABLE_COLLATION"]or"",
            "columns":columns,"indexes":indexes
        }}

    # ========== 7. --explain ==========
    def explain(self, sql):
        try:
            rows = self._fetch(f"EXPLAIN FORMAT=JSON {sql}")
            return {"status":"explain_success","sql":sql,"explain":rows[0] if rows else {}}
        except Exception as e:
            return {"status":"error","message":str(e)}

    # ========== 8. --export-csv ==========
    def export_csv(self, sql, output):
        with self.conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            if not rows:
                return {"status":"error","message":"无数据"}
            headers = list(rows[0].keys())
            with open(output, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(headers)
                for r in rows:
                    w.writerow([str(r.get(h,"")) for h in headers])
            return {"status":"export_csv_success","output":output,"rows":len(rows)}

    # ========== 9. Custom SQL ==========
    def execute(self, sql):
        with self.conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            return {"status":"success","data":rows}


# ========== 配置管理 ==========
def save_config(host, port, db, user, password):
    try:
        enc_pwd = base64.b64encode(password.encode()).decode() if password else ""
        cfg = {"host":host,"port":str(port),"db":db,"user":user,"password":enc_pwd}
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        return {"status":"config_saved","path":str(CONFIG_PATH)}
    except Exception as e:
        return {"status":"config_error","message":str(e)}

def load_config():
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if cfg.get("password","").startswith("#enc#"):
                cfg["password"] = decrypt_pwd(cfg["password"])
            else:
                try: cfg["password"] = base64.b64decode(cfg["password"]).decode()
                except: pass
            return cfg
        except: pass
    return {}

def clear_config():
    if CONFIG_PATH.exists(): CONFIG_PATH.unlink()
    return {"status":"config_cleared"}

def decrypt_pwd(enc):
    try:
        hex_data = enc[5:]
        return "".join(chr(int(hex_data[i:i+2],16)^0x5A) for i in range(0,len(hex_data),2))
    except: return enc


# ========== 主入口 ==========
def main():
    parser = argparse.ArgumentParser(description="DatabaseQuery — 纯Python MySQL分析工具")
    parser.add_argument("--host", default="localhost"); parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--db", default=os.environ.get("DB_NAME","")); parser.add_argument("--user", default="root")
    parser.add_argument("--password", default=os.environ.get("DB_PASSWORD",""))
    parser.add_argument("--ssl", default="false", choices=["false","true","verify-ca"])
    parser.add_argument("--get-schema", action="store_true"); parser.add_argument("--analyze-all", action="store_true")
    parser.add_argument("--analyze-table", nargs="?"); parser.add_argument("--analyze-deep", nargs="?")
    parser.add_argument("--get-relations", action="store_true"); parser.add_argument("--table-deps", action="store_true")
    parser.add_argument("--explain", nargs="?"); parser.add_argument("--export-csv", nargs="?")
    parser.add_argument("--output","-o"); parser.add_argument("--save-config", action="store_true")
    parser.add_argument("--clear-config", action="store_true")
    parser.add_argument("sql", nargs="*")
    args = parser.parse_args()

    # 配置管理
    if args.clear_config: print(json.dumps(clear_config())); return
    if args.save_config:
        print(json.dumps(save_config(args.host,args.port,args.db,args.user,args.password))); return

    # 加载已有配置
    cfg = load_config()
    if not args.db: args.db = cfg.get("db","")
    if not args.password: args.password = cfg.get("password","")
    if not args.host: args.host = cfg.get("host","localhost")
    if not args.port: args.port = int(cfg.get("port",3306))

    if not args.db: print(json.dumps({"status":"error","message":"需要指定 --db 或设置 DB_NAME 环境变量"})); return

    # 连接数据库
    q = MySQLQuery(args.host,args.port,args.db,args.user,args.password,args.ssl)
    if not q.connect(): return

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
        elif args.sql: result = q.execute(" ".join(args.sql))
        else: parser.print_help(); return
    finally:
        q.close()

    output = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.output and not args.export_csv:
        Path(args.output).write_text(output, encoding="utf-8")
        print(json.dumps({"status":"saved","output":args.output}))
    else:
        print(output)

    # 自动保存配置
    if result and result.get("status","").startswith("success") and not cfg:
        save_config(args.host,args.port,args.db,args.user,args.password)


if __name__ == "__main__":
    main()
def main():
