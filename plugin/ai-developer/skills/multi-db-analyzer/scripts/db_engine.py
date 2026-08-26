#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Database Engine Abstraction Layer - MySQL, PostgreSQL, SQLite, SQL Server, Oracle, MariaDB."""
from abc import ABC, abstractmethod
import json, os, re, csv, datetime, sys
from collections import defaultdict, deque
from pathlib import Path

class DatabaseEngine(ABC):
    """Abstract base class for all database engines."""
    def __init__(self, host="", port=0, db="", user="", password="", ssl_mode="false"):
        self.host = host; self.port = int(port) if str(port).isdigit() else 0
        self.db = db; self.user = user; self.password = password
        self.ssl_mode = ssl_mode; self.conn = None; self._engine_name = "abstract"
    @abstractmethod
    def connect(self): ...
    def close(self):
        if self.conn:
            try: self.conn.close()
            except: pass
            self.conn = None
    @abstractmethod
    def _query(self, sql, params=None): ...
    @abstractmethod
    def _query_one(self, sql, params=None): ...
    @abstractmethod
    def _quote_ident(self, name): ...
    @abstractmethod
    def get_schema(self): ...
    @abstractmethod
    def analyze_all(self): ...
    @abstractmethod
    def analyze_table(self, table): ...
    @abstractmethod
    def get_relations_raw(self): ...
    @abstractmethod
    def explain(self, sql): ...
    @abstractmethod
    def execute(self, sql): ...

    def get_relations(self):
        raw = self.get_relations_raw()
        relations = []
        tables = set()
        for r in raw:
            relations.append({"constraintName": r.get("constraintName",""), "parentTable": r.get("parentTable",""),
                "parentColumn": r.get("parentColumn",""), "childTable": r.get("childTable",""),
                "childColumn": r.get("childColumn",""), "updateRule": r.get("updateRule",3),
                "deleteRule": r.get("deleteRule",3)})
            tables.add(r.get("parentTable","")); tables.add(r.get("childTable",""))
        mermaid_parts = ["erDiagram"]; seen = set()
        for r in relations:
            pk, ck = r["parentTable"], r["childTable"]
            if (pk,ck) not in seen:
                mermaid_parts.append(f"  {pk} ||--o{{ {ck} : \"has\""); seen.add((pk,ck))
        return {"status":"relations_success","relations":{"database":self.db,"relations":relations,"mermaidErd":"\\n".join(mermaid_parts)}}

    def table_deps(self):
        rels = self.get_relations()["relations"]["relations"]
        graph, rev, all_tables = defaultdict(set), defaultdict(set), set()
        for r in rels:
            p,c=r["parentTable"],r["childTable"]; graph[c].add(p); rev[p].add(c)
            all_tables.add(p); all_tables.add(c)
        in_deg = {t:len(graph.get(t,set())) for t in all_tables}
        q = deque([t for t in all_tables if in_deg.get(t,0)==0]); levels,lvl = {},0
        while q:
            for _ in range(len(q)):
                t = q.popleft(); levels[t] = lvl
                for dep in rev.get(t,set()):
                    in_deg[dep]-=1
                    if in_deg[dep]==0: q.append(dep)
            lvl+=1
        for t in all_tables:
            if t not in levels: levels[t]=-1
        W,G,B=0,1,2; color={t:W for t in all_tables}; cycles=[]; path=[]
        def dfs(n):
            color[n]=G; path.append(n)
            for dep in graph.get(n,set()):
                if color.get(dep)==G:
                    idx=path.index(dep); cycles.append(" -> ".join(path[idx:]+[dep]))
                elif color.get(dep)==W: dfs(dep)
            path.pop(); color[n]=B
        for t in all_tables:
            if color.get(t)==W: dfs(t)
        return {"status":"table_deps_success","deps":{"database":self.db,"tableCount":len(all_tables),
            "levels":{t:levels[t] for t in sorted(all_tables)},"relations":rels,"cycles":cycles,"maxLevel":lvl-1}}

    def analyze_deep(self, table):
        base = self.analyze_table(table)
        if base.get("status","").startswith("error"): return base
        a = base.get("analysis",{})
        try: a["indexes"] = self._get_index_info(table, self.db)
        except: a["indexes"] = []
        return {"status":"analyze_deep_success","analysis":a}
    def _get_index_info(self, table, schema): return []

    def export_csv(self, sql, output):
        result = self.execute(sql)
        rows = result.get("data",[])
        if not rows: return {"status":"error","message":"No data returned"}
        headers = list(rows[0].keys()) if isinstance(rows[0],dict) else []
        with open(output,"w",newline="",encoding="utf-8-sig") as f:
            w=csv.writer(f); w.writerow(headers)
            for r in rows:
                w.writerow([str(r.get(h,"")) for h in headers] if isinstance(r,dict) else r)
        return {"status":"export_csv_success","output":output,"rows":len(rows)}

    def pr_report(self, tables=None):
        all_data = self.analyze_all()
        tbl_list = all_data.get("analysis",{}).get("tables",[])
        if tables:
            tset = set(t.strip() for t in tables if t.strip())
            tbl_list = [t for t in tbl_list if t["name"] in tset]
        lines = [f"# PR Report - {self.db}",f"Generated: {datetime.datetime.now().isoformat()}","",
            "## Table Structure Summary","",
            "| Table | Engine | Est.Rows | Actual | Cols | FK | Idx | Size(MB) | Comment |",
            "|-------|--------|---------|--------|------|----|-----|---------|---------|"]
        for t in tbl_list:
            lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                t["name"],t.get("engine","-"),t.get("estimatedRows","-"),t.get("actualRowCount","-"),
                t.get("columnCount","-"),t.get("fkCount","-"),t.get("indexCount","-"),
                t.get("totalSizeMb","-"),t.get("comment","")))
        return {"status":"pr_report_success","report":{"database":self.db,"tables":tbl_list,"markdown":"\n".join(lines)}}

    def compare_entities(self, entity_path):
        entities = _parse_java_entities(entity_path)
        if not entities: return {"status":"error","message":"No @Entity classes found in "+entity_path}
        db_tables = {}
        try:
            schema = self.get_schema()
            for t in schema.get("schema",{}).get("tables",[]):
                db_tables[t["name"]] = {"exists":True,"columns":{c["name"]:True for c in t.get("columns",[])}}
        except: pass
        comparisons = []
        for ent in entities:
            tn = ent.get("tableName",ent.get("className",""))
            fields = []
            for f in ent.get("fields",[]):
                cn = f.get("columnName",f.get("fieldName",""))
                fields.append({"fieldName":f["fieldName"],"fieldType":f.get("fieldType","String"),
                    "columnName":cn,"inDatabase":tn in db_tables and cn in db_tables[tn]["columns"]})
            comparisons.append({"entityName":ent.get("className",""),"entityFile":ent.get("filePath",""),
                "tableName":tn,"mappedTableExists":tn in db_tables,"fields":fields})
        return {"status":"compare_entities_success","comparisons":comparisons}

_JAVA_TYPE_MAP = {"String":"varchar","Integer":"int","int":"int","Long":"bigint","long":"bigint",
    "BigDecimal":"decimal","Double":"double","Float":"float","Boolean":"tinyint","boolean":"tinyint",
    "Date":"datetime","LocalDateTime":"datetime","LocalDate":"date","LocalTime":"time"}

def _parse_java_entities(entity_path):
    path = Path(entity_path)
    if not path.exists(): return []
    jfs = list(path.rglob("*.java")) if path.is_dir() else ([path] if path.suffix==".java" else [])
    entities = []
    for jf in jfs:
        text = jf.read_text(encoding="utf-8")
        if "@Entity" not in text: continue
        cm = re.search(r"(?:public\s+)?(?:abstract\s+)?class\s+(\w+)",text)
        if not cm: continue
        cn = cm.group(1)
        tm = re.search(r'@Table\s*\(\s*name\s*=\s*"([^"]+)"',text)
        tn = tm.group(1) if tm else cn.lower()
        fields, cc = [], None
        for line in text.split("\n"):
            s = line.strip()
            col_m = re.search(r'@Column\s*\(\s*name\s*=\s*"([^"]+)"',s)
            if col_m: cc = col_m.group(1); continue
            fm = re.match(r'private\s+(\S+)\s+(\w+)\s*;',s)
            if fm:
                fields.append({"fieldName":fm.group(2),"fieldType":fm.group(1),"columnName":cc or fm.group(2)})
                cc = None
        entities.append({"className":cn,"tableName":tn,"filePath":str(jf),"fields":fields})
    return entities

class MySQLEngine(DatabaseEngine):
    def __init__(self, host="localhost", port=3306, db="", user="root", password="", ssl_mode="false"):
        super().__init__(host,port,db,user,password,ssl_mode); self._engine_name="mysql"
    def connect(self):
        try: import pymysql, pymysql.cursors
        except: print(json.dumps({"status":"error","message":"MySQL: pip install pymysql"})); return False
        try:
            sa = {} if self.ssl_mode=="false" else {"ca":None,"cert":None,"key":None}
            self.conn = pymysql.connect(host=self.host,port=self.port,database=self.db or None,user=self.user,
                password=self.password,charset="utf8mb4",cursorclass=pymysql.cursors.DictCursor,connect_timeout=10,
                ssl=sa if self.ssl_mode!="false" else None)
            return True
        except Exception as e: print(json.dumps({"status":"error","message":str(e)},ensure_ascii=False)); return False
    def _query(self,sql,params=None):
        with self.conn.cursor() as cur: cur.execute(sql,params); return cur.fetchall()
    def _query_one(self,sql,params=None):
        with self.conn.cursor() as cur: cur.execute(sql,params); return cur.fetchone()
    def _quote_ident(self,name): return f"`{name}`"
    def get_schema(self):
        c = self.db
        rows = self._query("SELECT TABLE_NAME,TABLE_COMMENT,ENGINE,TABLE_ROWS,AUTO_INCREMENT,CREATE_TIME,UPDATE_TIME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME",(c,))
        tables = []
        for r in rows:
            t=r["TABLE_NAME"]
            cols=self._query("SELECT COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,COLUMN_COMMENT,EXTRA,ORDINAL_POSITION,CHARACTER_MAXIMUM_LENGTH FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION",(c,t))
            pk=self._query("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_KEY='PRI'",(c,t))
            idx=self._query("SELECT INDEX_NAME,COLUMN_NAME,NON_UNIQUE,SEQ_IN_INDEX FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME!='PRIMARY' ORDER BY INDEX_NAME,SEQ_IN_INDEX",(c,t))
            tables.append({"name":t,"comment":r["TABLE_COMMENT"]or"","engine":r["ENGINE"]or"","estimatedRows":r["TABLE_ROWS"],"autoIncrement":r["AUTO_INCREMENT"],
                "columns":[{"name":x["COLUMN_NAME"],"type":x["COLUMN_TYPE"],"nullable":x["IS_NULLABLE"]=="YES","default":x["COLUMN_DEFAULT"],"comment":x["COLUMN_COMMENT"]or""} for x in cols],
                "primaryKey":[p["COLUMN_NAME"] for p in pk],"indexes":[{"name":i["INDEX_NAME"],"column":i["COLUMN_NAME"],"unique":i["NON_UNIQUE"]==0} for i in idx]})
        return {"status":"schema_success","schema":{"database":c,"tables":tables}}
    def analyze_all(self):
        c=self.db
        rows=self._query("SELECT TABLE_NAME,ENGINE,TABLE_ROWS,DATA_LENGTH,INDEX_LENGTH,TABLE_COMMENT FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_ROWS DESC",(c,))
        tables=[]
        for r in rows:
            cc=self._query_one("SELECT COUNT(*) AS c FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",(c,r["TABLE_NAME"]))["c"]
            dl,il=r["DATA_LENGTH"]or 0,r["INDEX_LENGTH"]or 0
            tables.append({"name":r["TABLE_NAME"],"engine":r["ENGINE"]or"","estimatedRows":r["TABLE_ROWS"],"dataLengthBytes":dl,"indexLengthBytes":il,"totalSizeMb":round((dl+il)/1048576,2),"columnCount":cc,"comment":r["TABLE_COMMENT"]or""})
        return {"status":"analyze_all_success","analysis":{"database":c,"tables":tables}}
    def analyze_table(self,table):
        c=self.db; qi=self._quote_ident(table)
        meta=self._query_one("SELECT ENGINE,TABLE_ROWS,TABLE_COMMENT,DATA_LENGTH,INDEX_LENGTH,AUTO_INCREMENT,ROW_FORMAT,CREATE_TIME,UPDATE_TIME,TABLE_COLLATION FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",(c,table))
        if not meta: return {"status":"error","message":f"Table {table} not found"}
        actual=self._query_one(f"SELECT COUNT(*) AS cnt FROM {qi}")["cnt"]
        cols=self._query("SELECT COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,COLUMN_COMMENT,EXTRA,CHARACTER_MAXIMUM_LENGTH FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION",(c,table))
        columns=[]
        for col in cols:
            cn=col["COLUMN_NAME"]; qc=self._quote_ident(cn); ct=col["COLUMN_TYPE"]
            info={"name":cn,"type":ct,"nullable":col["IS_NULLABLE"]=="YES","default":col["COLUMN_DEFAULT"],"comment":col["COLUMN_COMMENT"]or""}
            try:
                st=self._query_one(f"SELECT COUNT(DISTINCT {qc}) AS dc,SUM(CASE WHEN {qc} IS NULL THEN 1 ELSE 0 END) AS nc,COUNT(*) AS tc FROM {qi}")
                if st: info.update({"distinctCount":st["dc"],"nullCount":st["nc"],"nullRatio":round(st["nc"]/st["tc"],4) if st["tc"] else 0})
            except: pass
            is_num=bool(re.match(r"(?i)(INT|TINYINT|SMALLINT|MEDIUMINT|BIGINT|FLOAT|DOUBLE|DECIMAL|NUMERIC|REAL)",ct))
            is_str=bool(re.match(r"(?i)(CHAR|VARCHAR|TEXT|MEDIUMTEXT|LONGTEXT|ENUM|SET)",ct))
            if is_num:
                try:
                    ns=self._query_one(f"SELECT MIN({qc}) AS mn,MAX({qc}) AS mx,AVG({qc}) AS av FROM {qi}")
                    if ns: info.update({"min":str(ns["mn"]or""),"max":str(ns["mx"]or""),"avg":str(round(ns["av"],2)if ns["av"]else"")})
                except: pass
            if is_str:
                try:
                    sl=self._query_one(f"SELECT MIN(LENGTH({qc})) AS minLen,MAX(LENGTH({qc})) AS maxLen,AVG(LENGTH({qc})) AS avgLen FROM {qi}")
                    if sl: info.update({"minLength":sl["minLen"],"maxLength":sl["maxLen"],"avgLength":round(sl["avgLen"],1)if sl["avgLen"]else 0})
                    es=self._query_one(f"SELECT COUNT(*) AS ec FROM {qi} WHERE {qc} IS NOT NULL AND {qc}=''")
                    if es: info["emptyStringCount"]=es["ec"]
                except: pass
            try:
                sv=self._query_one(f"SELECT COUNT(*) AS svc FROM {qi} WHERE {qc} IS NOT NULL AND CAST({qc} AS CHAR) IN ('0','-1','1900-01-01','1970-01-01','9999-12-31','-9999','')")
                if sv:
                    dm=max(info.get("distinctCount",1),1)
                    info["sentinelValueCount"]=sv["svc"]; info["sentinelValueRatio"]=round(sv["svc"]/dm,4)
            except: pass
            nr=info.get("nullRatio",0)or 0
            esr=(info.get("emptyStringCount",0)or 0)/max(info.get("nullCount",0)+(info.get("distinctCount",0)or 1),1)
            svr=info.get("sentinelValueRatio",0)or 0
            qs=round(max(0,1-nr*0.4-esr*0.3-svr*0.3),4); info["qualityScore"]=qs
            w=[]
            if nr>0.8: w.append(f"NULL ratio ({nr:.1%}) too high: potentially redundant field")
            elif nr>0.2: w.append(f"NULL ratio ({nr:.1%}) elevated: consider default value")
            if esr>0.3: w.append(f"Empty string ratio ({esr:.1%}) too high")
            if svr>0.1: w.append(f"Sentinel value ratio ({svr:.1%}) abnormal")
            info["warning"]="; ".join(w) if w else "Normal"
            columns.append(info)
        return {"status":"analyze_table_success","analysis":{"table":table,"engine":meta["ENGINE"]or"","estimatedRows":meta["TABLE_ROWS"],"actualRowCount":actual,
            "dataLengthBytes":meta["DATA_LENGTH"],"indexLengthBytes":meta["INDEX_LENGTH"],"totalSizeMb":round(((meta["DATA_LENGTH"]or 0)+(meta["INDEX_LENGTH"]or 0))/1048576,2),
            "comment":meta["TABLE_COMMENT"]or"","rowFormat":meta["ROW_FORMAT"]or"","collation":meta["TABLE_COLLATION"]or"","columns":columns}}
    def get_relations_raw(self):
        return self._query("SELECT rc.CONSTRAINT_NAME AS constraintName,rc.UPDATE_RULE AS updateRuleRaw,rc.DELETE_RULE AS deleteRuleRaw,"
            "kcu.TABLE_NAME AS childTable,kcu.COLUMN_NAME AS childColumn,kcu.REFERENCED_TABLE_NAME AS parentTable,kcu.REFERENCED_COLUMN_NAME AS parentColumn "
            "FROM information_schema.REFERENTIAL_CONSTRAINTS rc JOIN information_schema.KEY_COLUMN_USAGE kcu "
            "ON rc.CONSTRAINT_NAME=kcu.CONSTRAINT_NAME AND rc.CONSTRAINT_SCHEMA=kcu.CONSTRAINT_SCHEMA WHERE rc.CONSTRAINT_SCHEMA=%s ORDER BY kcu.TABLE_NAME",(self.db,))
    def explain(self,sql):
        try: rows=self._query(f"EXPLAIN FORMAT=JSON {sql}"); return {"status":"explain_success","sql":sql,"explain":rows[0]if rows else{}}
        except Exception as e: return {"status":"error","message":str(e)}
    def execute(self,sql): rows=self._query(sql); return {"status":"success","data":rows}
    def _get_index_info(self,table,schema):
        ir=self._query("SELECT INDEX_NAME,COLUMN_NAME,NON_UNIQUE FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME!='PRIMARY' ORDER BY INDEX_NAME,SEQ_IN_INDEX",(schema,table))
        seen={}
        for i in ir:
            n=i["INDEX_NAME"]
            if n not in seen: seen[n]={"name":n,"unique":i["NON_UNIQUE"]==0,"columns":[]}
            if i["COLUMN_NAME"] not in seen[n]["columns"]: seen[n]["columns"].append(i["COLUMN_NAME"])
        return list(seen.values())

class MariaDBEngine(MySQLEngine):
    def __init__(self,host="localhost",port=3306,db="",user="root",password="",ssl_mode="false"):
        super().__init__(host,port,db,user,password,ssl_mode); self._engine_name="mariadb"

class PostgreSQLEngine(DatabaseEngine):
    def __init__(self,host="localhost",port=5432,db="",user="postgres",password="",ssl_mode="false"):
        super().__init__(host,port,db,user,password,ssl_mode); self._engine_name="postgresql"
    def connect(self):
        try: import psycopg2, psycopg2.extras
        except: print(json.dumps({"status":"error","message":"PostgreSQL: pip install psycopg2-binary"})); return False
        try:
            self.conn=psycopg2.connect(host=self.host,port=self.port,dbname=self.db,user=self.user,password=self.password,connect_timeout=10)
            self.conn.autocommit=True; return True
        except Exception as e: print(json.dumps({"status":"error","message":str(e)},ensure_ascii=False)); return False
    def _query(self,sql,params=None):
        cur=self.conn.cursor(cursor_factory=__import__("psycopg2").extras.RealDictCursor)
        try: cur.execute(sql,params); return [dict(r) for r in cur.fetchall()]
        finally: cur.close()
    def _query_one(self,sql,params=None): r=self._query(sql,params); return r[0] if r else None
    def _quote_ident(self,name): return f'"{name}"'
    def get_schema(self):
        c=self.db
        rows=self._query("SELECT table_name FROM information_schema.tables WHERE table_catalog=%s AND table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name",(c,))
        tables=[]
        for r in rows:
            t=r["table_name"]
            cols=self._query("SELECT column_name,data_type||COALESCE('('||character_maximum_length||')','') AS full_type,is_nullable,column_default FROM information_schema.columns WHERE table_catalog=%s AND table_schema='public' AND table_name=%s ORDER BY ordinal_position",(c,t))
            pk=self._query("SELECT kcu.column_name FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name AND tc.table_schema=kcu.table_schema WHERE tc.table_catalog=%s AND tc.table_schema='public' AND tc.table_name=%s AND tc.constraint_type='PRIMARY KEY'",(c,t))
            idx=self._query("SELECT indexname AS index_name,indexdef AS index_def FROM pg_indexes WHERE schemaname='public' AND tablename=%s ORDER BY indexname",(t,))
            pi=[]
            for i in idx:
                mm=re.search(r"\((.*?)\)",i["index_def"]); cp=mm.group(1)if mm else""
                pi.append({"name":i["index_name"],"column":cp,"unique":"UNIQUE"in i["index_def"].upper()})
            tables.append({"name":t,"comment":"","engine":"PostgreSQL","estimatedRows":None,"autoIncrement":None,
                "columns":[{"name":x["column_name"],"type":x["full_type"],"nullable":x["is_nullable"]=="YES","default":x["column_default"],"comment":""}for x in cols],
                "primaryKey":[p["column_name"]for p in pk],"indexes":pi})
        return {"status":"schema_success","schema":{"database":c,"tables":tables}}
    def analyze_all(self):
        rows=self._query("SELECT relname AS table_name,n_live_tup AS estimated_rows,pg_total_relation_size(relid) AS total_size FROM pg_stat_user_tables ORDER BY n_live_tup DESC")
        tables=[]
        for r in rows:
            cc=self._query_one("SELECT COUNT(*) AS c FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",(r["table_name"],))
            tables.append({"name":r["table_name"],"engine":"PostgreSQL","estimatedRows":r["estimated_rows"],"totalSizeMb":round((r["total_size"]or 0)/1048576,2),"columnCount":cc["c"]if cc else 0,"comment":""})
        return {"status":"analyze_all_success","analysis":{"database":self.db,"tables":tables}}
    def analyze_table(self,table):
        qi=self._quote_ident(table)
        meta=self._query_one("SELECT n_live_tup AS estimated_rows,pg_total_relation_size(relid) AS total_size FROM pg_stat_user_tables WHERE relname=%s",(table,))
        actual=self._query_one(f"SELECT COUNT(*) AS cnt FROM {qi}")["cnt"]
        cols=self._query("SELECT column_name,data_type||COALESCE('('||character_maximum_length||')','') AS full_type,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",(table,))
        columns=[]
        for c_ in cols:
            cn=c_["column_name"]; qc=self._quote_ident(cn); ct=c_["full_type"]
            info={"name":cn,"type":ct,"nullable":c_["is_nullable"]=="YES","default":c_["column_default"],"comment":""}
            try:
                st=self._query_one(f"SELECT COUNT(DISTINCT {qc}) AS dc,SUM(CASE WHEN {qc} IS NULL THEN 1 ELSE 0 END) AS nc,COUNT(*) AS tc FROM {qi}")
                if st: info.update({"distinctCount":st["dc"],"nullCount":st["nc"],"nullRatio":round(st["nc"]/st["tc"],4)if st["tc"]else 0})
            except: pass
            is_num=bool(re.match(r"(?i)(INT|INTEGER|SMALLINT|BIGINT|FLOAT|DOUBLE|DECIMAL|NUMERIC|REAL|SERIAL)",ct))
            is_str=bool(re.match(r"(?i)(CHAR|VARCHAR|TEXT|ENUM)",ct))
            if is_num:
                try:
                    ns=self._query_one(f"SELECT MIN({qc}) AS mn,MAX({qc}) AS mx,AVG({qc}) AS av FROM {qi}")
                    if ns: info.update({"min":str(ns["mn"]or""),"max":str(ns["mx"]or""),"avg":str(round(ns["av"],2)if ns["av"]else"")})
                except: pass
            if is_str:
                try:
                    sl=self._query_one(f"SELECT MIN(LENGTH({qc})) AS minLen,MAX(LENGTH({qc})) AS maxLen,AVG(LENGTH({qc})) AS avgLen FROM {qi}")
                    if sl: info.update({"minLength":sl["minLen"],"maxLength":sl["maxLen"],"avgLength":round(sl["avgLen"],1)if sl["avgLen"]else 0})
                    es=self._query_one(f"SELECT COUNT(*) AS ec FROM {qi} WHERE {qc} IS NOT NULL AND {qc}=''")
                    if es: info["emptyStringCount"]=es["ec"]
                except: pass
            nr=info.get("nullRatio",0)or 0; esr=(info.get("emptyStringCount",0)or 0)/max(info.get("nullCount",0)+(info.get("distinctCount",0)or 1),1)
            qs=round(max(0,1-nr*0.4-esr*0.3),4); info["qualityScore"]=qs; info["warning"]="Normal"
            columns.append(info)
        return {"status":"analyze_table_success","analysis":{"table":table,"engine":"PostgreSQL","estimatedRows":meta["estimated_rows"]if meta else 0,
            "actualRowCount":actual,"totalSizeMb":round((meta["total_size"]or 0)/1048576,2)if meta and meta.get("total_size")else 0,"comment":"","columns":columns}}
    def get_relations_raw(self):
        return self._query("SELECT tc.constraint_name AS constraintName,kcu.table_name AS childTable,kcu.column_name AS childColumn,"
            "ccu.table_name AS parentTable,ccu.column_name AS parentColumn,0 AS updateRule,0 AS deleteRule "
            "FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu "
            "ON tc.constraint_name=kcu.constraint_name JOIN information_schema.constraint_column_usage ccu "
            "ON tc.constraint_name=ccu.constraint_name WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_schema='public'")
    def explain(self,sql):
        try: rows=self._query(f"EXPLAIN (FORMAT JSON) {sql}"); return {"status":"explain_success","sql":sql,"explain":rows[0]if rows else{}}
        except Exception as e: return {"status":"error","message":str(e)}
    def execute(self,sql): rows=self._query(sql); return {"status":"success","data":rows}

class SQLiteEngine(DatabaseEngine):
    def __init__(self,host="",port=0,db="",user="",password="",ssl_mode="false"):
        super().__init__(host,port,db,user,password,ssl_mode); self._engine_name="sqlite"
    def connect(self):
        import sqlite3
        try:
            self.conn=sqlite3.connect(self.db or ":memory:")
            self.conn.row_factory=sqlite3.Row; self.conn.execute("PRAGMA foreign_keys=ON"); return True
        except Exception as e: print(json.dumps({"status":"error","message":str(e)},ensure_ascii=False)); return False
    def _query(self,sql,params=None):
        cur=self.conn.cursor()
        try: cur.execute(sql,params); return [dict(r) for r in cur.fetchall()]
        finally: cur.close()
    def _query_one(self,sql,params=None): r=self._query(sql,params); return r[0] if r else None
    def _quote_ident(self,name): return f'"{name}"'
    def get_schema(self):
        tr=self._query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables=[]
        for r in tr:
            t=r["name"]; qi=self._quote_ident(t)
            cr=self._query(f"PRAGMA table_info({qi})")
            cols=[]; pk_names=[]
            for c in cr:
                cols.append({"name":c["name"],"type":c["type"]or"TEXT","nullable":not c["notnull"],"default":c["dflt_value"],"comment":""})
                if c["pk"]: pk_names.append(c["name"])
            ir=self._query(f"PRAGMA index_list({qi})")
            ii=[]
            for ix in ir:
                if ix["name"].startswith("sqlite_autoindex"): continue
                det=self._query(f"PRAGMA index_info({self._quote_ident(ix['name'])})")
                ic=[d["name"] for d in det]
                ii.append({"name":ix["name"],"column":",".join(ic),"unique":bool(ix["unique"])})
            tables.append({"name":t,"comment":"","engine":"SQLite","estimatedRows":None,"autoIncrement":None,"columns":cols,"primaryKey":pk_names,"indexes":ii})
        return {"status":"schema_success","schema":{"database":self.db or":memory:","tables":tables}}
    def analyze_all(self):
        raw=self._query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables=[]
        for r in raw:
            t=r["name"]; qi=self._quote_ident(t)
            cc=self._query_one(f"SELECT COUNT(*) AS c FROM pragma_table_info('{t}')")or{"c":0}
            rc=self._query_one(f"SELECT COUNT(*) AS cnt FROM {qi}")or{"cnt":0}
            tables.append({"name":t,"engine":"SQLite","estimatedRows":rc["cnt"],"totalSizeMb":0,"columnCount":cc["c"],"comment":""})
        return {"status":"analyze_all_success","analysis":{"database":self.db or":memory:","tables":tables}}
    def analyze_table(self,table):
        qi=self._quote_ident(table)
        actual=self._query_one(f"SELECT COUNT(*) AS cnt FROM {qi}")["cnt"]
        cr=self._query(f"PRAGMA table_info({qi})")
        columns=[]
        for c in cr:
            cn=c["name"]; qc=self._quote_ident(cn); ct=c["type"]or"TEXT"
            info={"name":cn,"type":ct,"nullable":not c["notnull"],"default":c["dflt_value"],"comment":""}
            try:
                st=self._query_one(f"SELECT COUNT(DISTINCT {qc}) AS dc,SUM(CASE WHEN {qc} IS NULL THEN 1 ELSE 0 END) AS nc,COUNT(*) AS tc FROM {qi}")
                if st and st["tc"]: info.update({"distinctCount":st["dc"],"nullCount":st["nc"],"nullRatio":round(st["nc"]/st["tc"],4)})
            except: pass
            is_num=bool(re.match(r"(?i)(INT|INTEGER|SMALLINT|BIGINT|FLOAT|DOUBLE|DECIMAL|NUMERIC|REAL)",ct))
            is_str=bool(re.match(r"(?i)(CHAR|VARCHAR|TEXT|CLOB)",ct))
            if is_num:
                try:
                    ns=self._query_one(f"SELECT MIN({qc}) AS mn,MAX({qc}) AS mx,AVG({qc}) AS av FROM {qi}")
                    if ns: info.update({"min":str(ns["mn"]or""),"max":str(ns["mx"]or""),"avg":str(round(ns["av"],2)if ns["av"]else"")})
                except: pass
            if is_str:
                try:
                    sl=self._query_one(f"SELECT MIN(LENGTH({qc})) AS minLen,MAX(LENGTH({qc})) AS maxLen,AVG(LENGTH({qc})) AS avgLen FROM {qi}")
                    if sl: info.update({"minLength":sl["minLen"],"maxLength":sl["maxLen"],"avgLength":round(sl["avgLen"],1)if sl["avgLen"]else 0})
                    es=self._query_one(f"SELECT COUNT(*) AS ec FROM {qi} WHERE {qc} IS NOT NULL AND {qc}=''")
                    if es: info["emptyStringCount"]=es["ec"]
                except: pass
            nr=info.get("nullRatio",0)or 0; esr=(info.get("emptyStringCount",0)or 0)/max(info.get("nullCount",0)+(info.get("distinctCount",0)or 1),1)
            qs=round(max(0,1-nr*0.4-esr*0.3),4); info["qualityScore"]=qs; info["warning"]="Normal"
            columns.append(info)
        return {"status":"analyze_table_success","analysis":{"table":table,"engine":"SQLite","estimatedRows":actual,"actualRowCount":actual,"totalSizeMb":0,"comment":"","columns":columns}}
    def get_relations_raw(self):
        raw=self._query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        relations=[]
        for r in raw:
            tbl=r["name"]; fks=self._query(f"PRAGMA foreign_key_list({self._quote_ident(tbl)})")
            for fk in fks:
                relations.append({"constraintName":f"fk_{tbl}_{fk['id']}","parentTable":fk["table"],"parentColumn":fk["to"],
                    "childTable":tbl,"childColumn":fk["from"],"updateRule":fk.get("on_update",3),"deleteRule":fk.get("on_delete",3)})
        return relations
    def explain(self,sql):
        try: rows=self._query(f"EXPLAIN QUERY PLAN {sql}"); return {"status":"explain_success","sql":sql,"explain":rows}
        except Exception as e: return {"status":"error","message":str(e)}
    def execute(self,sql): rows=self._query(sql); return {"status":"success","data":rows}

class SQLServerEngine(DatabaseEngine):
    def __init__(self,host="localhost",port=1433,db="",user="sa",password="",ssl_mode="false"):
        super().__init__(host,port,db,user,password,ssl_mode); self._engine_name="sqlserver"
    def connect(self):
        try: import pymssql
        except: print(json.dumps({"status":"error","message":"SQL Server: pip install pymssql"})); return False
        try:
            self.conn=pymssql.connect(server=self.host,port=self.port,database=self.db,user=self.user,password=self.password,timeout=10)
            return True
        except Exception as e: print(json.dumps({"status":"error","message":str(e)},ensure_ascii=False)); return False
    def _query(self,sql,params=None):
        cur=self.conn.cursor(as_dict=True)
        try: cur.execute(sql,params or[]); return [dict(r) for r in cur.fetchall()]
        finally: cur.close()
    def _query_one(self,sql,params=None): r=self._query(sql,params); return r[0] if r else None
    def _quote_ident(self,name): return f"[{name}]"
    def get_schema(self):
        c=self.db
        rows=self._query("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_CATALOG=%s AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME",(c,))
        tables=[]
        for r in rows:
            t=r["TABLE_NAME"]
            cols=self._query("SELECT COLUMN_NAME,DATA_TYPE+COALESCE('('+CAST(CHARACTER_MAXIMUM_LENGTH AS VARCHAR)+')','') AS full_type,IS_NULLABLE,COLUMN_DEFAULT FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_CATALOG=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION",(c,t))
            pk=self._query("SELECT kcu.COLUMN_NAME FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu ON tc.CONSTRAINT_NAME=kcu.CONSTRAINT_NAME WHERE tc.TABLE_CATALOG=%s AND tc.TABLE_NAME=%s AND tc.CONSTRAINT_TYPE='PRIMARY KEY'",(c,t))
            tables.append({"name":t,"comment":"","engine":"SQL Server","estimatedRows":None,"autoIncrement":None,
                "columns":[{"name":x["COLUMN_NAME"],"type":x["full_type"],"nullable":x["IS_NULLABLE"]=="YES","default":x["COLUMN_DEFAULT"],"comment":""}for x in cols],
                "primaryKey":[p["COLUMN_NAME"]for p in pk],"indexes":[]})
        return {"status":"schema_success","schema":{"database":c,"tables":tables}}
    def analyze_all(self):
        rows=self._query("SELECT t.name AS table_name,p.rows AS estimated_rows,(SUM(a.total_pages)*8) AS total_size_kb FROM sys.tables t INNER JOIN sys.indexes i ON t.object_id=i.object_id INNER JOIN sys.partitions p ON i.object_id=p.object_id AND i.index_id=p.index_id INNER JOIN sys.allocation_units a ON p.partition_id=a.container_id WHERE t.is_ms_shipped=0 GROUP BY t.name,p.rows ORDER BY p.rows DESC")
        tables=[]
        for r in rows:
            cc=self._query_one("SELECT COUNT(*) AS c FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=%s",(r["table_name"],))
            tables.append({"name":r["table_name"],"engine":"SQL Server","estimatedRows":r["estimated_rows"],"totalSizeMb":round((r["total_size_kb"]or 0)/1024,2),"columnCount":cc["c"]if cc else 0,"comment":""})
        return {"status":"analyze_all_success","analysis":{"database":self.db,"tables":tables}}
    def analyze_table(self,table):
        qi=self._quote_ident(table)
        actual=self._query_one(f"SELECT COUNT(*) AS cnt FROM {qi}")["cnt"]
        cds=self._query("SELECT COLUMN_NAME,DATA_TYPE+COALESCE('('+CAST(CHARACTER_MAXIMUM_LENGTH AS VARCHAR)+')','') AS full_type,IS_NULLABLE,COLUMN_DEFAULT FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=%s ORDER BY ORDINAL_POSITION",(table,))
        columns=[]
        for c in cds:
            cn=c["COLUMN_NAME"]; qc=self._quote_ident(cn); ct=c["full_type"]
            info={"name":cn,"type":ct,"nullable":c["IS_NULLABLE"]=="YES","default":c["COLUMN_DEFAULT"],"comment":""}
            try:
                st=self._query_one(f"SELECT COUNT(DISTINCT {qc}) AS dc,SUM(CASE WHEN {qc} IS NULL THEN 1 ELSE 0 END) AS nc,COUNT(*) AS tc FROM {qi}")
                if st and st["tc"]: info.update({"distinctCount":st["dc"],"nullCount":st["nc"],"nullRatio":round(st["nc"]/st["tc"],4)})
            except: pass
            columns.append(info)
        return {"status":"analyze_table_success","analysis":{"table":table,"engine":"SQL Server","estimatedRows":actual,"actualRowCount":actual,"totalSizeMb":0,"comment":"","columns":columns}}
    def get_relations_raw(self):
        return self._query("SELECT fk.name AS constraintName,tp.name AS parentTable,refc.name AS parentColumn,t.name AS childTable,c.name AS childColumn FROM sys.foreign_keys fk JOIN sys.foreign_key_columns fkc ON fk.object_id=fkc.constraint_object_id JOIN sys.tables tp ON fk.referenced_object_id=tp.object_id JOIN sys.columns refc ON fkc.referenced_object_id=refc.object_id AND fkc.referenced_column_id=refc.column_id JOIN sys.tables t ON fk.parent_object_id=t.object_id JOIN sys.columns c ON fkc.parent_object_id=c.object_id AND fkc.parent_column_id=c.column_id")
    def explain(self,sql):
        try: self._query(f"SET SHOWPLAN_XML ON;{sql};SET SHOWPLAN_XML OFF"); return {"status":"explain_success","sql":sql,"explain":"See SET SHOWPLAN_XML output"}
        except Exception as e: return {"status":"error","message":str(e)}
    def execute(self,sql): rows=self._query(sql); return {"status":"success","data":rows}

class OracleEngine(DatabaseEngine):
    def __init__(self,host="localhost",port=1521,db="",user="",password="",ssl_mode="false"):
        super().__init__(host,port,db,user,password,ssl_mode); self._engine_name="oracle"
    def connect(self):
        try: import oracledb
        except: print(json.dumps({"status":"error","message":"Oracle: pip install oracledb"})); return False
        try:
            dsn=oracledb.makedsn(self.host,self.port,service_name=self.db)
            self.conn=oracledb.connect(user=self.user,password=self.password,dsn=dsn); return True
        except Exception as e: print(json.dumps({"status":"error","message":str(e)},ensure_ascii=False)); return False
    def _query(self,sql,params=None):
        cur=self.conn.cursor()
        try: cur.execute(sql,params or{}); cols=[d[0] for d in cur.description]if cur.description else[]; return [dict(zip(cols,row))for row in cur.fetchall()]
        finally: cur.close()
    def _query_one(self,sql,params=None): r=self._query(sql,params); return r[0] if r else None
    def _quote_ident(self,name): return f'"{name.upper()}"'
    def get_schema(self):
        o=self.user.upper()
        rows=self._query("SELECT TABLE_NAME FROM ALL_TABLES WHERE OWNER=:owner ORDER BY TABLE_NAME",{"owner":o})
        tables=[]
        for r in rows:
            t=r["TABLE_NAME"]
            cols=self._query("SELECT COLUMN_NAME,DATA_TYPE||COALESCE('('||DATA_LENGTH||')','') AS full_type,NULLABLE,DATA_DEFAULT,COMMENTS FROM ALL_TAB_COLUMNS c LEFT JOIN ALL_COL_COMMENTS m ON c.TABLE_NAME=m.TABLE_NAME AND c.COLUMN_NAME=m.COLUMN_NAME AND c.OWNER=m.OWNER WHERE c.OWNER=:owner AND c.TABLE_NAME=:tbl ORDER BY COLUMN_ID",{"owner":o,"tbl":t})
            pk=self._query("SELECT cols.COLUMN_NAME FROM ALL_CONSTRAINTS cons JOIN ALL_CONS_COLUMNS cols ON cons.CONSTRAINT_NAME=cols.CONSTRAINT_NAME WHERE cons.OWNER=:owner AND cons.TABLE_NAME=:tbl AND cons.CONSTRAINT_TYPE='P'",{"owner":o,"tbl":t})
            tables.append({"name":t,"comment":"","engine":"Oracle","estimatedRows":None,"autoIncrement":None,
                "columns":[{"name":x["COLUMN_NAME"],"type":x["full_type"],"nullable":x["NULLABLE"]=="Y","default":x["DATA_DEFAULT"],"comment":x.get("COMMENTS")or""}for x in cols],
                "primaryKey":[p["COLUMN_NAME"]for p in pk],"indexes":[]})
        return {"status":"schema_success","schema":{"database":self.db,"tables":tables}}
    def analyze_all(self):
        o=self.user.upper()
        rows=self._query("SELECT TABLE_NAME,NUM_ROWS AS estimated_rows FROM ALL_TABLES WHERE OWNER=:owner ORDER BY NUM_ROWS DESC NULLS LAST",{"owner":o})
        tables=[]
        for r in rows:
            cc=self._query_one("SELECT COUNT(*) AS c FROM ALL_TAB_COLUMNS WHERE OWNER=:owner AND TABLE_NAME=:tbl",{"owner":o,"tbl":r["TABLE_NAME"]})
            tables.append({"name":r["TABLE_NAME"],"engine":"Oracle","estimatedRows":r["estimated_rows"],"totalSizeMb":0,"columnCount":cc["c"]if cc else 0,"comment":""})
        return {"status":"analyze_all_success","analysis":{"database":self.db,"tables":tables}}
    def analyze_table(self,table):
        o=self.user.upper(); qi=self._quote_ident(table)
        actual=self._query_one(f"SELECT COUNT(*) AS cnt FROM {qi}")["cnt"]
        cols=self._query("SELECT COLUMN_NAME,DATA_TYPE||COALESCE('('||DATA_LENGTH||')','') AS full_type,NULLABLE,DATA_DEFAULT FROM ALL_TAB_COLUMNS WHERE OWNER=:owner AND TABLE_NAME=:tbl ORDER BY COLUMN_ID",{"owner":o,"tbl":table})
        columns=[]
        for c in cols:
            cn=c["COLUMN_NAME"]; qc=self._quote_ident(cn); ct=c["full_type"]
            info={"name":cn,"type":ct,"nullable":c["NULLABLE"]=="Y","default":c["DATA_DEFAULT"],"comment":""}
            try:
                st=self._query_one(f"SELECT COUNT(DISTINCT {qc}) AS dc,SUM(CASE WHEN {qc} IS NULL THEN 1 ELSE 0 END) AS nc,COUNT(*) AS tc FROM {qi}")
                if st and st["tc"]: info.update({"distinctCount":st["dc"],"nullCount":st["nc"],"nullRatio":round(st["nc"]/st["tc"],4)})
            except: pass
            columns.append(info)
        return {"status":"analyze_table_success","analysis":{"table":table,"engine":"Oracle","estimatedRows":actual,"actualRowCount":actual,"totalSizeMb":0,"comment":"","columns":columns}}
    def get_relations_raw(self):
        o=self.user.upper()
        return self._query("SELECT cons.CONSTRAINT_NAME AS constraintName,cons.TABLE_NAME AS childTable,cols.COLUMN_NAME AS childColumn,cons2.TABLE_NAME AS parentTable,cols2.COLUMN_NAME AS parentColumn FROM ALL_CONSTRAINTS cons JOIN ALL_CONS_COLUMNS cols ON cons.CONSTRAINT_NAME=cols.CONSTRAINT_NAME JOIN ALL_CONSTRAINTS cons2 ON cons.R_CONSTRAINT_NAME=cons2.CONSTRAINT_NAME JOIN ALL_CONS_COLUMNS cols2 ON cons2.CONSTRAINT_NAME=cols2.CONSTRAINT_NAME AND cols2.POSITION=cols.POSITION WHERE cons.OWNER=:owner AND cons.CONSTRAINT_TYPE='R'",{"owner":o})
    def explain(self,sql):
        try:
            self._query(f"EXPLAIN PLAN SET STATEMENT_ID='db_query' FOR {sql}")
            plan=self._query("SELECT LPAD(' ',2*LEVEL)||OPERATION||' '||OPTIONS||' '||OBJECT_NAME AS plan_step FROM PLAN_TABLE WHERE STATEMENT_ID='db_query' START WITH ID=0 CONNECT BY PRIOR ID=PARENT_ID")
            return {"status":"explain_success","sql":sql,"explain":plan}
        except Exception as e: return {"status":"error","message":str(e)}
    def execute(self,sql): rows=self._query(sql); return {"status":"success","data":rows}

ENGINE_REGISTRY = {"mysql":MySQLEngine,"mariadb":MariaDBEngine,"postgresql":PostgreSQLEngine,"pgsql":PostgreSQLEngine,"postgres":PostgreSQLEngine,"sqlite":SQLiteEngine,"sqlite3":SQLiteEngine,"sqlserver":SQLServerEngine,"mssql":SQLServerEngine,"oracle":OracleEngine}
ENGINE_DISPLAY = {"mysql":"MySQL","mariadb":"MariaDB","postgresql":"PostgreSQL","sqlite":"SQLite","sqlserver":"SQL Server","oracle":"Oracle"}
ENGINE_DEFAULTS = {"mysql":{"host":"localhost","port":3306,"user":"root"},"mariadb":{"host":"localhost","port":3306,"user":"root"},"postgresql":{"host":"localhost","port":5432,"user":"postgres"},"pgsql":{"host":"localhost","port":5432,"user":"postgres"},"postgres":{"host":"localhost","port":5432,"user":"postgres"},"sqlite":{"host":"","port":0,"user":""},"sqlite3":{"host":"","port":0,"user":""},"sqlserver":{"host":"localhost","port":1433,"user":"sa"},"mssql":{"host":"localhost","port":1433,"user":"sa"},"oracle":{"host":"localhost","port":1521,"user":""}}

def create_engine(db_type="mysql", host=None, port=None, db=None, user=None, password="", ssl_mode="false"):
    dtype = db_type.lower().replace("-","").replace("_","")
    if dtype not in ENGINE_REGISTRY: raise ValueError(f"Unsupported database type: {db_type}. Available: {', '.join(sorted(ENGINE_DISPLAY.keys()))}")
    d = ENGINE_DEFAULTS.get(dtype, {})
    host = host if host is not None else d.get("host","localhost")
    port = port if port is not None else d.get("port",0)
    user = user if user is not None else d.get("user","")
    return ENGINE_REGISTRY[dtype](host=host,port=port,db=db,user=user,password=password,ssl_mode=ssl_mode)

def list_supported_engines(): return list(ENGINE_DISPLAY.keys())
def get_engine_display_name(db_type):
    dtype = db_type.lower().replace("-","").replace("_","")
    return ENGINE_DISPLAY.get(dtype, db_type)
def get_engine_display_name(db_type):
    dtype = db_type.lower().replace("-","").replace("_","")
    return ENGINE_DISPLAY.get(dtype, db_type)

# === Load extra engines (NoSQL, TiDB, time-series, vector DBs) ===
try:
    from db_engine_extras import EXTRA_ENGINES, EXTRA_DISPLAY, EXTRA_DEFAULTS, EXTRA_IMPORTS
    ENGINE_REGISTRY.update(EXTRA_ENGINES)
    ENGINE_DISPLAY.update(EXTRA_DISPLAY)
    ENGINE_DEFAULTS.update(EXTRA_DEFAULTS)
except ImportError:
    pass
