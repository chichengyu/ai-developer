#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extended database engines: TiDB, Redis, Elasticsearch, MongoDB, InfluxDB, TDengine, VectorDB (Qdrant, Milvus), DolphinDB."""
import json, re, os

try:
    from db_engine import DatabaseEngine, MySQLEngine
except ImportError:
    # When imported standalone
    from abc import ABC, abstractmethod
    class DatabaseEngine(ABC):
        def __init__(self,**kw): pass
        def connect(self): return False
    class MySQLEngine: pass


# ==============================
# 1. TiDB (MySQL-compatible)
# ==============================
class TiDBEngine(MySQLEngine):
    def __init__(self, host="localhost", port=4000, db="", user="root", password="", ssl_mode="false"):
        super().__init__(host, port, db, user, password, ssl_mode)
        self._engine_name = "tidb"
    def connect(self):
        try: import pymysql, pymysql.cursors
        except:
            print(json.dumps({"status":"error","message":"TiDB: pip install pymysql"})); return False
        try:
            self.conn = pymysql.connect(host=self.host,port=self.port,database=self.db or None,user=self.user,
                password=self.password,charset="utf8mb4",cursorclass=pymysql.cursors.DictCursor,connect_timeout=10)
            return True
        except Exception as e:
            print(json.dumps({"status":"error","message":str(e)},ensure_ascii=False)); return False
    def get_relations_raw(self):
        return self._query("SELECT TABLE_NAME AS childTable,COLUMN_NAME AS childColumn,"
            "REFERENCED_TABLE_NAME AS parentTable,REFERENCED_COLUMN_NAME AS parentColumn,"
            "CONSTRAINT_NAME AS constraintName FROM information_schema.KEY_COLUMN_USAGE "
            "WHERE TABLE_SCHEMA=%s AND REFERENCED_TABLE_NAME IS NOT NULL",(self.db,))


# ==============================
# 2. Redis
# ==============================
class RedisEngine(DatabaseEngine):
    def __init__(self, host="localhost", port=6379, db="0", user="", password="", ssl_mode="false"):
        super().__init__(host,port,db,user,password,ssl_mode); self._engine_name="redis"
    def connect(self):
        try: import redis
        except: print(json.dumps({"status":"error","message":"Redis: pip install redis"})); return False
        try:
            self.conn = redis.Redis(host=self.host,port=self.port,db=int(self.db or 0),password=self.password or None,
                decode_responses=True, socket_timeout=5)
            self.conn.ping(); return True
        except Exception as e: print(json.dumps({"status":"error","message":str(e)},ensure_ascii=False)); return False
    def _query(self,cmd,params=None):
        c=cmd.upper().strip()
        if c=="INFO": d=self.conn.info(); return [{"section":k,"value":json.dumps(v,default=str)if isinstance(v,dict)else str(v)} for k,v in d.items()]
        elif c.startswith("KEYS"):
            p=cmd[4:].strip() or "*"
            return [{"key":k} for k in self.conn.keys(p)]
        elif c.startswith("SCAN"): return [{"key":k} for k in self.conn.scan_iter()]
        elif c=="DBSIZE": return [{"dbsize":self.conn.dbsize()}]
        elif c=="MEMORY USAGE" or c.startswith("MEMORY"):
            parts=cmd.split()
            if len(parts)>=3:
                return [{"key":parts[2],"usage_bytes":self.conn.memory_usage(parts[2])or 0}]
            return [{"info":str(self.conn.info("memory"))}]
        else:
            try:
                parts=cmd.split(); op=parts[0].upper() if parts else ""; key=parts[1] if len(parts)>1 else ""
                if op=="GET" and key: return [{"key":key,"value":self.conn.get(key) or "(nil)"}]
                elif op=="TYPE" and key: return [{"key":key,"type":self.conn.type(key)}]
                elif op=="TTL" and key: return [{"key":key,"ttl":self.conn.ttl(key)}]
                elif op=="EXISTS" and key: return [{"key":key,"exists":bool(self.conn.exists(key))}]
                elif op=="STRLEN" and key: return [{"key":key,"length":self.conn.strlen(key)}]
                elif op=="HGETALL" and key:
                    h=self.conn.hgetall(key); return [{"key":key,"field":k,"value":v} for k,v in h.items()] or [{"key":key,"info":"(empty)"}]
                elif op=="HLEN" and key: return [{"key":key,"fields":self.conn.hlen(key)}]
                elif op=="HGET" and key: return [{"key":key,"field":parts[2] if len(parts)>2 else "","value":self.conn.hget(key,parts[2]) if len(parts)>2 else "(no field)"}]
                elif op=="HEXISTS" and key: return [{"key":key,"field":parts[2] if len(parts)>2 else "","exists":self.conn.hexists(key,parts[2]) if len(parts)>2 else False}]
                elif op=="HKEYS" and key: return [{"field":k} for k in self.conn.hkeys(key)]
                elif op=="HVALS" and key: return [{"value":v} for v in self.conn.hvals(key)]
                elif op=="LRANGE" and key:
                    s=int(parts[2]) if len(parts)>2 else 0; e=int(parts[3]) if len(parts)>3 else -1
                    return [{"index":i,"value":v} for i,v in enumerate(self.conn.lrange(key,s,e))]
                elif op=="LLEN" and key: return [{"key":key,"length":self.conn.llen(key)}]
                elif op=="SMEMBERS" and key: return [{"member":m} for m in self.conn.smembers(key)]
                elif op=="SCARD" and key: return [{"key":key,"count":self.conn.scard(key)}]
                elif op=="SISMEMBER" and key: return [{"key":key,"member":parts[2] if len(parts)>2 else "","is_member":self.conn.sismember(key,parts[2]) if len(parts)>2 else False}]
                elif op=="ZRANGE" and key:
                    s=int(parts[2]) if len(parts)>2 else 0; e=int(parts[3]) if len(parts)>3 else -1
                    ws="withscores" in cmd.lower()
                    if ws: return [{"rank":i,"member":m,"score":s} for i,(m,s) in enumerate(self.conn.zrange(key,s,e,withscores=True,score_cast_func=float))]
                    return [{"rank":i,"member":m} for i,m in enumerate(self.conn.zrange(key,s,e))]
                elif op=="ZCARD" and key: return [{"key":key,"count":self.conn.zcard(key)}]
                elif op=="ZCOUNT" and key: return [{"key":key,"min":parts[2] if len(parts)>2 else "-inf","max":parts[3] if len(parts)>3 else "+inf","count":self.conn.zcount(key,parts[2] if len(parts)>2 else "-inf",parts[3] if len(parts)>3 else "+inf")}]
                elif op=="DEL" and key: return [{"deleted":self.conn.delete(key)}]
                elif op=="PING": return [{"response":"PONG"}]
                elif op=="SET" and key: self.conn.set(key," ".join(parts[2:])); return [{"status":"OK","key":key}]
                elif op=="SETEX" and key: self.conn.setex(key,int(parts[2]) if len(parts)>2 else 3600," ".join(parts[3:])); return [{"status":"OK","key":key}]
                elif op=="LPUSH" and key: return [{"key":key,"length":self.conn.lpush(key," ".join(parts[2:]))}]
                elif op=="RPUSH" and key: return [{"key":key,"length":self.conn.rpush(key," ".join(parts[2:]))}]
                elif op=="SADD" and key: return [{"key":key,"added":self.conn.sadd(key,parts[2]) if len(parts)>2 else 0}]
                elif op=="ZADD" and key: return [{"key":key,"added":self.conn.zadd(key,{parts[3]:float(parts[2])}) if len(parts)>3 else 0}]
                else:
                    r=self.conn.execute_command(cmd)
                    if isinstance(r,dict): return [{"key":k,"value":str(v)} for k,v in r.items()]
                    if isinstance(r,(list,tuple)): return [{"index":i,"value":str(v)} for i,v in enumerate(r)]
                    return [{"result":str(r)}]
            except Exception as e:
                return [{"error":f"Command failed: {cmd[:100]}: {str(e)}"}]
    def _export_csv(self, sql, output):
        """Export Redis command results to CSV."""
        result = self.execute(sql)
        rows = result.get("data", [])
        if not rows:
            return {"status":"error","message":"No data returned from Redis"}
        import csv
        headers = list(rows[0].keys()) if rows else []
        with open(output, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(headers)
            for r in rows:
                w.writerow([str(r.get(h, "")) for h in headers])
        return {"status":"export_csv_success","output":output,"rows":len(rows)}
    def _query_one(self,cmd,params=None):
        r=self._query(cmd); return r[0] if r else None
    def _quote_ident(self,n): return n
    def get_schema(self):
        info=self.conn.info()
        total_keys=sum(info.get(f"db{i}",{}).get("keys",0) for i in range(16))
        return {"status":"schema_success","schema":{"database":f"redis://{self.host}:{self.port}/{self.db}",
            "tables":[{"name":f"db{i}","comment":str(info.get(f"db{i}",{})),"engine":"Redis","estimatedRows":info.get(f"db{i}",{}).get("keys",0)}for i in range(16)if info.get(f"db{i}",{}).get("keys",0)>0]+
            [{"name":"__server__","comment":f"{info.get('redis_version','')} uptime:{info.get('uptime_in_seconds',0)}s","engine":"Redis","estimatedRows":total_keys}]}}
    def analyze_all(self):
        info=self.conn.info()
        return {"status":"analyze_all_success","analysis":{"database":f"redis://{self.host}:{self.port}/{self.db}","tables":[
            {"name":"keyspace","engine":"Redis","estimatedRows":info.get("db0",{}).get("keys",0),"totalSizeMb":round((info.get("used_memory",0)or 0)/1048576,2),"comment":f"hits:{info.get('keyspace_hits',0)} misses:{info.get('keyspace_misses',0)}"},
            {"name":"server","engine":"Redis","estimatedRows":0,"comment":f"ver:{info.get('redis_version','')} mode:{info.get('redis_mode','')} os:{info.get('os','')} uptime:{info.get('uptime_in_seconds',0)}s"},
            {"name":"memory","engine":"Redis","estimatedRows":0,"totalSizeMb":round((info.get('used_memory',0)or 0)/1048576,2),"comment":f"peak:{round((info.get('used_memory_peak',0)or 0)/1048576,2)}MB frag:{info.get('mem_fragmentation_ratio','')}"},
            {"name":"clients","engine":"Redis","estimatedRows":info.get('connected_clients',0),"comment":f"blocked:{info.get('blocked_clients',0)}"}]}}
    def analyze_table(self,pattern):
        keys=list(self.conn.scan_iter(match=pattern,count=1000))
        return {"status":"analyze_table_success","analysis":{"table":pattern,"engine":"Redis","actualRowCount":len(keys),
            "estimatedRows":len(keys),"columns":[{"name":"key","type":"string"},{"name":"type","type":"string"},{"name":"ttl","type":"int"}],
            "sample":[{"key":k,"type":self.conn.type(k),"ttl":self.conn.ttl(k)}for k in keys[:20]]}}
    def get_relations_raw(self): return []
    def explain(self,cmd):
        return {"status":"explain_success","sql":cmd,"explain":[{"plan":"Redis command","note":"Redis does not provide query plans. Use SLOWLOG GET to review slow commands."}]}
    def execute(self,cmd):
        try: return {"status":"success","data":self._query(cmd)}
       except Exception as e: return {"status":"error","message":str(e)}


# ==============================
# 3. Elasticsearch
# ==============================
class ElasticsearchEngine(DatabaseEngine):
    def __init__(self, host="localhost", port=9200, db="", user="", password="", ssl_mode="false"):
        super().__init__(host,port,db,user,password,ssl_mode); self._engine_name="elasticsearch"
    def connect(self):
        try: from elasticsearch import Elasticsearch
        except: print(json.dumps({"status":"error","message":"Elasticsearch: pip install elasticsearch"})); return False
        try:
            scheme="https"if self.ssl_mode!="false"else"http"
            auth=(self.user,self.password)if self.user else None
            self.conn=Elasticsearch([f"{scheme}://{self.host}:{self.port}"],http_auth=auth,timeout=10)
            return self.conn.ping()
        except Exception as e: print(json.dumps({"status":"error","message":str(e)},ensure_ascii=False)); return False
    def _query(self,body,params=None):
        import requests
        url=f"http://{self.host}:{self.port}/{body}"if not body.startswith("http")else body
        r=requests.get(url,auth=(self.user,self.password)if self.user else None,timeout=10)
        return [r.json()]if isinstance(r.json(),dict)else r.json()
    def _query_one(self,body,params=None):
        r=self._query(body); return r[0] if r else None
    def _quote_ident(self,n): return n
    def get_schema(self):
        cat=self._query("_cat/indices?format=json&bytes=b")
        tables=[]
        for idx in (cat if isinstance(cat,list)else[]):
            tables.append({"name":idx.get("index",""),"engine":"Elasticsearch","estimatedRows":int(idx.get("docs.count",0)or 0),
                "totalSizeMb":round(int(idx.get("store.size",0)or 0)/1048576,2),"comment":f"health:{idx.get('health','')} status:{idx.get('status','')}"})
        return {"status":"schema_success","schema":{"database":f"es://{self.host}:{self.port}","tables":tables}}
    def analyze_all(self):
        import requests
        health=requests.get(f"http://{self.host}:{self.port}/_cluster/health",auth=(self.user,self.password)if self.user else None).json()
        return {"status":"analyze_all_success","analysis":{"database":f"es://{self.host}:{self.port}","tables":[
            {"name":"cluster","engine":"Elasticsearch","estimatedRows":health.get("number_of_nodes",0),"comment":f"status:{health.get('status','')} nodes:{health.get('number_of_nodes',0)} data:{health.get('active_shards',0)}/{health.get('unassigned_shards',0)}"},
            {"name":"indices","engine":"Elasticsearch","estimatedRows":health.get("active_shards",0),"comment":f"indices fetched via _cat/indices"}]}}
    def analyze_table(self,index):
        import requests
        stats=requests.get(f"http://{self.host}:{self.port}/{index}/_stats",auth=(self.user,self.password)if self.user else None).json()
        mapping=requests.get(f"http://{self.host}:{self.port}/{index}/_mapping",auth=(self.user,self.password)if self.user else None).json()
        all_s={}
        for idx_name,idx_data in mapping.items():
            props=idx_data.get("mappings",{}).get("properties",{})
            for fname,finfo in props.items():
                all_s[fname]=finfo.get("type","unknown")
        idx_stats=stats.get("indices",{}).get(index,{})
        total=idx_stats.get("total",{})
        return {"status":"analyze_table_success","analysis":{"table":index,"engine":"Elasticsearch",
            "estimatedRows":total.get("docs",{}).get("count",0),"actualRowCount":total.get("docs",{}).get("count",0),
            "totalSizeMb":round((total.get("store",{}).get("size_in_bytes",0)or 0)/1048576,2),
            "columns":[{"name":n,"type":t,"nullable":True,"comment":""}for n,t in all_s.items()],"indexes":list(all_s.keys())}}
    def get_relations_raw(self): return []
    def explain(self,body):
        return {"status":"explain_success","sql":body,"explain":[{"plan":"Elasticsearch query","note":"Use _search?explain=true for detailed explanation."}]}
    def execute(self,body):
        try: return {"status":"success","data":self._query(body)}
        except Exception as e: return {"status":"error","message":str(e)}


# ==============================
# 4. MongoDB
# ==============================
class MongoDBEngine(DatabaseEngine):
    def __init__(self, host="localhost", port=27017, db="", user="", password="", ssl_mode="false"):
        super().__init__(host,port,db,user,password,ssl_mode); self._engine_name="mongodb"
    def connect(self):
        try: from pymongo import MongoClient
        except: print(json.dumps({"status":"error","message":"MongoDB: pip install pymongo"})); return False
        try:
            uri=f"mongodb://{self.host}:{self.port}/"
            if self.user: uri=f"mongodb://{self.user}:{self.password}@{self.host}:{self.port}/"
            self.client=MongoClient(uri,serverSelectionTimeoutMS=5000)
            self.client.admin.command('ping')
            self._db=self.client.get_database(self.db)if self.db else None
            return True
        except Exception as e: print(json.dumps({"status":"error","message":str(e)},ensure_ascii=False)); return False
    def _query(self,cmd,params=None):
        if self._db:
            if cmd.upper().strip()=="LIST COLLECTIONS":
                return [{"name":c}for c in self._db.list_collection_names()]
            return [{"result":"Run 'python database_query.py --db-type mongodb ...' for queries"}]
        if cmd.upper()=="SHOW DATABASES"or cmd.upper()=="LIST DATABASES":
            return [{"name":d["name"]}for d in self.client.list_databases()]
        return [{"result":"connected. use --db <database> to select"}]
    def _query_one(self,cmd,params=None):
        r=self._query(cmd); return r[0] if r else None
    def _quote_ident(self,n): return f'"{n}"'
    def get_schema(self):
        cols=self._db.list_collection_names()if self._db else[]
        tables=[]
        for cname in cols:
            stats=self._db.command("collstats",cname)
            sample=self._db[cname].find_one()
            fields=list(sample.keys())if sample else["_id"]
            tables.append({"name":cname,"engine":"MongoDB","estimatedRows":stats.get("count",0),
                "totalSizeMb":round((stats.get("size",0)or 0)/1048576,2),"comment":"",
                "columns":[{"name":f,"type":str(type(sample[f]).__name__)if sample and f in sample else"unknown","nullable":True}for f in fields]})
        return {"status":"schema_success","schema":{"database":self.db or f"mongodb://{self.host}:{self.port}","tables":tables}}
    def analyze_all(self):
        cols=self._db.list_collection_names()if self._db else[]
        tables=[]
        for cname in cols:
            s=self._db.command("collstats",cname)
            tables.append({"name":cname,"engine":"MongoDB","estimatedRows":s.get("count",0),
                "totalSizeMb":round((s.get("size",0)or 0)/1048576,2),"comment":f"avgObjSize:{s.get('avgObjSize','')} nindexes:{s.get('nindexes',0)}"})
        return {"status":"analyze_all_success","analysis":{"database":self.db,"tables":tables}}
    def analyze_table(self,collection):
        stats=self._db.command("collstats",collection)if self._db else{}
        indexes=list(self._db[collection].list_indexes())if self._db else[]
        sample=self._db[collection].find_one()if self._db else{}
        return {"status":"analyze_table_success","analysis":{"table":collection,"engine":"MongoDB",
            "estimatedRows":stats.get("count",0),"actualRowCount":stats.get("count",0),
            "totalSizeMb":round((stats.get("size",0)or 0)/1048576,2),
            "columns":[{"name":k,"type":str(type(v).__name__),"nullable":True}for k,v in sample.items()],
            "indexes":[{"name":i.get("name"),"unique":i.get("unique",False),"columns":list(i.get("key",{}).keys())}for i in indexes]}}
    def get_relations_raw(self): return []
    def explain(self,query):
        try:
            if not self._db: return {"status":"error","message":"No database selected"}
            parts=query.strip().split(".",2)
            if len(parts)>=2:
                coll=parts[0]; result=self._db[coll].find(parts[1]if len(parts)>1 else{}).explain()
                return {"status":"explain_success","sql":query,"explain":result}
            return {"status":"explain_success","sql":query,"explain":[{"plan":"Use 'collection.filter' syntax for explain"}]}
        except Exception as e: return {"status":"error","message":str(e)}
    def execute(self,query):
        try:
            parts=query.strip().split(".")
            if len(parts)==2:
                coll,cmd=parts
                if cmd=="find"or cmd=="find_all":
                    docs=list(self._db[coll].find().limit(100))
                    return {"status":"success","data":[dict(d,_id=str(d["_id"]))for d in docs]}
                elif cmd.startswith("find("):
                    docs=list(self._db[coll].find().limit(100))
                    return {"status":"success","data":[dict(d,_id=str(d["_id"]))for d in docs]}
                import ast; filter_kw = {}
                try: 
                    fpart=cmd[cmd.index("(")+1:cmd.rindex(")")] if "(" in cmd and ")" in cmd else ""
                    if fpart.strip(): filter_kw=ast.literal_eval("{"+fpart+"}") if "{" in fpart else ast.literal_eval(fpart)
                except: filter_kw={}
                cursor=self._db[coll].find(filter_kw)
                if ".limit(" in cmd: cursor=cursor.limit(int(parts[-1].replace(")","").split("(")[-1]) if parts[-1].replace(")","").split("(")[-1].strip().isdigit() else 100)
                return {"status":"success","data":[dict(d,_id=str(d["_id"]))for d in cursor.limit(200)]}
            elif len(parts)>=2 and parts[1].startswith("aggregate"):
                import ast; pipeline=fpart=cmd[cmd.index("(")+1:cmd.rindex(")")] if "(" in cmd and ")" in cmd else "[]"
                try: pipeline=ast.literal_eval(pipeline)
                except: pipeline=[]
                return {"status":"success","data":[dict(r,_id=str(r.get("_id","")))for r in self._db[coll].aggregate(pipeline)[:200]]}
            elif len(parts)>=2 and parts[1].startswith(("count","countDocuments","estimatedDocumentCount")):
                cnt=self._db[coll].count_documents({})
                return {"status":"success","data":[{"collection":coll,"count":cnt}]}
            elif len(parts)>=2 and parts[1].startswith("distinct"):
                f=cmd[cmd.index("(")+1:cmd.rindex(")")] if "(" in cmd and ")" in cmd else ""
                vals=self._db[coll].distinct(f.strip().strip("'\"")) if f.strip() else []
                return {"status":"success","data":[{"collection":coll,"field":f.strip().strip("'\""),"value":v}for v in vals]}
            elif len(parts)>=2 and parts[1].startswith(("list_indexes","indexes","index")):
                return {"status":"success","data":[{"name":i["name"],"key":str(i["key"]),"unique":i.get("unique",False)}for i in self._db[coll].list_indexes()]}
            return {"status":"success","data":[{"collections":self._db.list_collection_names()}]}
            return {"status":"success","data":[{"databases":self.client.list_database_names()}]}
        except Exception as e: return {"status":"error","message":str(e)}


# ==============================
# 5. InfluxDB (Time Series)
# ==============================
class InfluxDBEngine(DatabaseEngine):
    def __init__(self, host="localhost", port=8086, db="", user="", password="", ssl_mode="false"):
        super().__init__(host,port,db,user,password,ssl_mode); self._engine_name="influxdb"
    def connect(self):
        try: from influxdb_client import InfluxDBClient
        except: print(json.dumps({"status":"error","message":"InfluxDB: pip install influxdb-client"})); return False
        try:
            token=self.password or os.environ.get("INFLUX_TOKEN","")
            url=f"{'https'if self.ssl_mode!='false'else 'http'}://{self.host}:{self.port}"
            self.conn=InfluxDBClient(url=url,token=token,org=self.db,timeout=10000)
            self.health=self.conn.health()
            self.buckets_api=self.conn.buckets_api()
            return True
        except Exception as e: print(json.dumps({"status":"error","message":str(e)},ensure_ascii=False)); return False
    def _query(self,flux,params=None):
        try:
            tables=self.conn.query_api().query(flux)
            results=[]
            for table in tables:
                for record in table.records:
                    d=record.values.copy()
                    results.append({k:str(v)for k,v in d.items()})
            return results
        except Exception as e: return [{"error":str(e)}]
    def _query_one(self,flux,params=None):
        r=self._query(flux); return r[0] if r else None
    def _quote_ident(self,n): return f'"{n}"'
    def get_schema(self):
        buckets=list(self.buckets_api.find_buckets().buckets)if hasattr(self,'buckets_api')else[]
        tables=[]
        for b in buckets:
            r=self._query(f'import "influxdata/influxdb/v1"\nv1.measurementTagValues(bucket:"{b.name}",tag:"_measurement")')
            tables.append({"name":b.name,"engine":"InfluxDB","estimatedRows":0,"comment":f"type:{b.type} desc:{b.description or''} retention:{b.rp or'auto'}","columns":[{"name":r.get("_value","")or"measurement","type":"string"}for r in r]})
        return {"status":"schema_success","schema":{"database":self.db or"default","tables":tables}}
    def analyze_all(self):
        r=self._query('import "influxdata/influxdb/v1"\nv1.tagValues(bucket:"_tasks",tag:"status")')
        return {"status":"analyze_all_success","analysis":{"database":self.db or"default","tables":[
            {"name":"buckets","engine":"InfluxDB","estimatedRows":len(self.buckets_api.find_buckets().buckets)if hasattr(self,'buckets_api')else 0}]}}
    def analyze_table(self,bucket):
        r=self._query(f'import "influxdata/influxdb/v1"\nv1.measurementTagValues(bucket:"{bucket}",tag:"_measurement")')
        measurements=[row.get("_value","")for row in r]
        return {"status":"analyze_table_success","analysis":{"table":bucket,"engine":"InfluxDB",
            "actualRowCount":len(measurements),
            "columns":[{"name":m,"type":"measurement"}for m in measurements[:50]]}}
    def get_relations_raw(self): return []
    def explain(self,flux):
        return {"status":"explain_success","sql":flux,"explain":[{"plan":"InfluxDB Flux query analysis not directly available via API"}]}
    def execute(self,flux):
        try: return {"status":"success","data":self._query(flux)}
        except Exception as e: return {"status":"error","message":str(e)}


# ==============================
# 6. TDengine (国产时序数据库)
# ==============================
class TDengineEngine(DatabaseEngine):
    def __init__(self, host="localhost", port=6030, db="", user="root", password="taosdata", ssl_mode="false"):
        super().__init__(host,port,db,user,password,ssl_mode); self._engine_name="tdengine"
    def connect(self):
        try: import taos
        except: print(json.dumps({"status":"error","message":"TDengine: pip install taos"})); return False
        try:
            self.conn=taos.connect(host=self.host,port=self.port,database=self.db or None,user=self.user,password=self.password,timeout=5)
            return True
        except Exception as e: print(json.dumps({"status":"error","message":str(e)},ensure_ascii=False)); return False
    def _query(self,sql,params=None):
        cur=self.conn.cursor()
        try:
            cur.execute(sql)
            cols=[d[0]for d in cur.description]if cur.description else[]
            return [dict(zip(cols,row))for row in cur.fetchall()]
        finally: cur.close()
    def _query_one(self,sql,params=None):
        r=self._query(sql); return r[0] if r else None
    def _quote_ident(self,name): return f"`{name}`"
    def get_schema(self):
        dbs=self._query("SHOW DATABASES")
        tables=[]
        for d in dbs:
            dn=d.get("name","")
            if dn and dn!="information_schema":
                stables=self._query(f"SHOW STABLES IN {self._quote_ident(dn)}")
                for s in stables:
                    tables.append({"name":s.get("table_name",""),"engine":"TDengine","estimatedRows":s.get("rows",0),
                        "comment":f"type:SUPER_TABLE in {dn}","columns":[]})
                tbs=self._query(f"SHOW TABLES IN {self._quote_ident(dn)}")
                for t in tbs:
                    tables.append({"name":t.get("table_name",""),"engine":"TDengine","estimatedRows":t.get("rows",0),
                        "comment":f"type:TABLE in {dn}","columns":[]})
        return {"status":"schema_success","schema":{"database":self.db or"all","tables":tables}}
    def analyze_all(self):
        dbs=self._query("SHOW DATABASES")
        tables=[]
        for d in dbs:
            tables.append({"name":d.get("name",""),"engine":"TDengine","estimatedRows":d.get("rows",0)or 0,
                "comment":f"created:{d.get('create_time','')}","totalSizeMb":0})
        return {"status":"analyze_all_success","analysis":{"database":self.db or"all","tables":tables}}
    def analyze_table(self,table):
        qi=self._quote_ident(table)
        try:
            desc=self._query(f"DESCRIBE {qi}")
            rc=self._query_one(f"SELECT COUNT(*) AS cnt FROM {qi}")or{"cnt":0}
            return {"status":"analyze_table_success","analysis":{"table":table,"engine":"TDengine",
                "estimatedRows":rc.get("cnt",0),"actualRowCount":rc.get("cnt",0),"columns":[
                    {"name":d.get("Field",""),"type":d.get("Type",""),"nullable":d.get("Null","")=="YES"}for d in desc]}}
        except Exception as e: return {"status":"error","message":str(e)}
    def get_relations_raw(self): return []
    def explain(self,sql):
        try:
            r=self._query(f"EXPLAIN {sql}")
            return {"status":"explain_success","sql":sql,"explain":r}
        except Exception as e: return {"status":"error","message":str(e)}
    def execute(self,sql):
        try: rows=self._query(sql); return {"status":"success","data":rows}
        except Exception as e: return {"status":"error","message":str(e)}


# ==============================
# 7. VectorDB (Qdrant)
# ==============================
class VectorDBEngine(DatabaseEngine):
    def __init__(self, host="localhost", port=6333, db="", user="", password="", ssl_mode="false"):
        super().__init__(host,port,db,user,password,ssl_mode); self._engine_name="vectordb"
    def connect(self):
        try: from qdrant_client import QdrantClient
        except: print(json.dumps({"status":"error","message":"VectorDB: pip install qdrant-client"})); return False
        try:
            pref="https"if self.ssl_mode!="false"else"http"
            self.conn=QdrantClient(url=f"{pref}://{self.host}:{self.port}",timeout=5)
            self.conn.get_collections()
            return True
        except Exception as e: print(json.dumps({"status":"error","message":str(e)},ensure_ascii=False)); return False
    def _query(self,cmd,params=None):
        import requests
        url=f"{'https'if self.ssl_mode!='false'else'http'}://{self.host}:{self.port}"
        parts=cmd.strip().split()
        endpoint=parts[0]if parts else"collections"
        try:
            r=requests.get(f"{url}/{endpoint}",auth=(self.user,self.password)if self.user else None,timeout=5)
            return [r.json()]if isinstance(r.json(),dict)else r.json()
        except Exception as e: return [{"error":str(e)}]
    def _query_one(self,cmd,params=None):
        r=self._query(cmd); return r[0] if r else None
    def _quote_ident(self,n): return n
    def get_schema(self):
        cols=self.conn.get_collections()
        tables=[]
        for c in cols.collections:
            info=self.conn.get_collection(c.name)
            cfg=info.config
            dims=cfg.params.vectors.size if cfg.params and cfg.params.vectors else 0
            tables.append({"name":c.name,"engine":"Qdrant","estimatedRows":info.points_count,
                "comment":f"vectors:{dims}d distance:{cfg.params.vectors.distance if cfg.params and cfg.params.vectors else ''}","columns":[]})
        return {"status":"schema_success","schema":{"database":f"qdrant://{self.host}:{self.port}","tables":tables}}
    def analyze_all(self):
        cols=self.conn.get_collections()
        tables=[]
        for c in cols.collections:
            info=self.conn.get_collection(c.name)
            tables.append({"name":c.name,"engine":"Qdrant","estimatedRows":info.points_count,
                "totalSizeMb":round((info.points_count*384*4)/1048576,2)if info.points_count else 0})
        return {"status":"analyze_all_success","analysis":{"database":"qdrant","tables":tables}}
    def analyze_table(self,collection):
        info=self.conn.get_collection(collection)
        cfg=info.config
        dims=cfg.params.vectors.size if cfg.params and cfg.params.vectors else 0
        return {"status":"analyze_table_success","analysis":{"table":collection,"engine":"Qdrant",
            "estimatedRows":info.points_count,"actualRowCount":info.points_count,
            "columns":[{"name":"id","type":"point_id"},{"name":"vector","type":f"float[{dims}]"},{"name":"payload","type":"json"}],
            "indexes":[{"name":f"{dims}d_{cfg.params.vectors.distance}","columns":["vector"]}]if cfg.params and cfg.params.vectors else[]}}
    def get_relations_raw(self): return []
    def explain(self,query):
        return {"status":"explain_success","sql":query,"explain":[{"plan":"Vector search uses HNSW/IVF index for approximate nearest neighbor search."}]}
    def execute(self,collection):
        try:
            scroll=self.conn.scroll(collection_name=collection,limit=100)
            points=scroll[0]if scroll else[]
            return {"status":"success","data":[{"id":str(p.id),"vector":list(p.vector)[:4]if p.vector else[],"payload":p.payload}for p in points[:50]]}
        except Exception as e: return {"status":"error","message":str(e)}


# ==============================
# 8. Milvus (Vector DB)
# ==============================
class MilvusEngine(DatabaseEngine):
    def __init__(self, host="localhost", port=19530, db="default", user="", password="", ssl_mode="false"):
        super().__init__(host,port,db,user,password,ssl_mode); self._engine_name="milvus"
    def connect(self):
        try: from pymilvus import connections
        except: print(json.dumps({"status":"error","message":"Milvus: pip install pymilvus"})); return False
        try:
            connections.connect(host=self.host,port=self.port,alias="default",
                user=self.user or None,password=self.password or None,db_name=self.db or "default")
            self._has_pymilvus = True
            return True
        except Exception as e: print(json.dumps({"status":"error","message":str(e)},ensure_ascii=False)); return False
    def _query(self,cmd,params=None):
        from pymilvus import utility, Collection
        c=cmd.upper().strip()
        if c=="LIST COLLECTIONS":
            return [{"name":n} for n in utility.list_collections()]
        elif c.startswith("COLLECTION") or c.startswith("DESCRIBE"):
            parts=cmd.split()
            if len(parts)>=2:
                coll=Collection(parts[1])
                return [{"name":coll.name,"schema":str(coll.schema),"description":coll.description,"num_entities":coll.num_entities}]
        elif c.startswith("QUERY"):
            parts=cmd.split(maxsplit=1)
            if len(parts)>=2:
                import ast
                try: expr=ast.literal_eval(parts[1])
                except: expr={"limit":100}
                return utility.query(expr)
        else:
            try:
                info=utility.get_server_info()
                return [{"key":k,"value":str(v)} for k,v in info.items()]
            except: pass
        return [{"result":"ok"}]
    def _query_one(self,cmd,params=None): r=self._query(cmd); return r[0] if r else None
    def _quote_ident(self,n): return n
    def get_schema(self):
        from pymilvus import utility
        cols=utility.list_collections()
        tables=[]
        for cname in cols:
            try:
                from pymilvus import Collection
                coll=Collection(cname)
                schema=coll.schema
                tables.append({"name":cname,"engine":"Milvus","estimatedRows":coll.num_entities,
                    "comment":f"dim:{getattr(schema,'dim','auto')} desc:{coll.description or''}",
                    "columns":[{"name":f.name,"type":str(f.dtype),"nullable":True} for f in schema.fields] if schema else []})
            except: tables.append({"name":cname,"engine":"Milvus","estimatedRows":0})
        return {"status":"schema_success","schema":{"database":f"milvus://{self.host}:{self.port}/{self.db}","tables":tables}}
    def analyze_all(self):
        from pymilvus import utility
        cols=utility.list_collections()
        tables=[]
        for cname in cols:
            try:
                from pymilvus import Collection
                coll=Collection(cname)
                n=coll.num_entities
                tables.append({"name":cname,"engine":"Milvus","estimatedRows":n,"totalSizeMb":round(n*384*4/1048576,2) if n else 0})
            except: tables.append({"name":cname,"engine":"Milvus","estimatedRows":0})
        return {"status":"analyze_all_success","analysis":{"database":"milvus","tables":tables}}
    def analyze_table(self,collection):
        from pymilvus import Collection
        try:
            coll=Collection(collection)
            schema=coll.schema
            return {"status":"analyze_table_success","analysis":{"table":collection,"engine":"Milvus",
                "estimatedRows":coll.num_entities,"actualRowCount":coll.num_entities,
                "columns":[{"name":f.name,"type":str(f.dtype),"nullable":True} for f in schema.fields] if schema else [],
                "indexes":[{"name":"vector_index","columns":["vector"]}]}}
        except Exception as e: return {"status":"error","message":str(e)}
    def get_relations_raw(self): return []
    def explain(self,query):
        return {"status":"explain_success","sql":query,"explain":[{"plan":"Milvus uses IVF_FLAT, HNSW, or AUTOINDEX for ANN search."}]}
    def execute(self,collection):
        try:
            from pymilvus import Collection
            coll=Collection(collection)
            coll.load()
            results=coll.query(expr="",output_fields=["*"],limit=100)
            return {"status":"success","data":[dict(r,id=str(r.get("id",""))) for r in results]}
        except Exception as e: return {"status":"error","message":str(e)}


# ==============================
# 9. DolphinDB (Time Series)
# ==============================
class DolphinDBEngine(DatabaseEngine):
    def __init__(self, host="localhost", port=8848, db="", user="admin", password="123456", ssl_mode="false"):
        super().__init__(host,port,db,user,password,ssl_mode); self._engine_name="dolphindb"
    def connect(self):
        try: import dolphindb as ddb
        except: print(json.dumps({"status":"error","message":"DolphinDB: pip install dolphindb"})); return False
        try:
            self.conn=ddb.session()
            self.conn.connect(host=self.host,port=self.port,user=self.user,password=self.password)
            return True
        except Exception as e: print(json.dumps({"status":"error","message":str(e)},ensure_ascii=False)); return False
    def _query(self,sql,params=None):
        try:
            df=self.conn.run(sql)
            import pandas as pd
            if isinstance(df,pd.DataFrame):
                df=df.fillna("").astype(str).reset_index()
                return df.to_dict(orient="records")
            return [{"result":str(df)}]
        except Exception as e: return [{"error":str(e)}]
    def _query_one(self,sql,params=None): r=self._query(sql); return r[0] if r else None
    def _quote_ident(self,name): return f'"{name}"'
    def get_schema(self):
        try:
            return {"status":"schema_success","schema":{"database":self.db or "default","tables":[{"name":"_dolphindb_","engine":"DolphinDB","estimatedRows":0,"comment":"Use SHOW TABLES or run native DolphinDB query"}]}}
        except Exception as e: return {"status":"error","message":str(e)}
    def analyze_all(self):
        return {"status":"analyze_all_success","analysis":{"database":self.db or "default","tables":[{"name":"dolphindb","engine":"DolphinDB","estimatedRows":0}]}}
    def analyze_table(self,table):
        return {"status":"analyze_table_success","analysis":{"table":table,"engine":"DolphinDB","estimatedRows":0,"actualRowCount":0,"columns":[]}}
    def get_relations_raw(self): return []
    def explain(self,sql):
        try:
            plan=self.conn.run(f"getExecutionPlan({sql})")
            return {"status":"explain_success","sql":sql,"explain":[{"plan":str(plan)}]}
        except Exception as e: return {"status":"error","message":str(e)}
    def execute(self,sql):
        try: data=self._query(sql); return {"status":"success","data":data}
        except Exception as e: return {"status":"error","message":str(e)}
# ==============================
# Extra Engine Registries (moved to end)
# (Imported by db_engine.py at module end)
# ==============================
EXTRA_ENGINES = {
    "tidb": TiDBEngine,
    "redis": RedisEngine,
    "elasticsearch": ElasticsearchEngine,
    "es": ElasticsearchEngine,
    "mongodb": MongoDBEngine,
    "mongo": MongoDBEngine,
    "influxdb": InfluxDBEngine,
    "influx": InfluxDBEngine,
    "tdengine": TDengineEngine,
    "td": TDengineEngine,
    "vectordb": VectorDBEngine,
    "qdrant": VectorDBEngine,
    "milvus": MilvusEngine,
    "dolphindb": DolphinDBEngine,
    "ddb": DolphinDBEngine,
}
EXTRA_DISPLAY = {
    "tidb": "TiDB", "redis": "Redis", "elasticsearch": "Elasticsearch",
    "mongodb": "MongoDB", "influxdb": "InfluxDB",
    "tdengine": "TDengine", "vectordb": "Qdrant/VectorDB",
    "milvus": "Milvus", "dolphindb": "DolphinDB",
}
EXTRA_DEFAULTS = {
    "tidb": {"host":"localhost","port":4000,"user":"root"},
    "redis": {"host":"localhost","port":6379,"user":""},
    "elasticsearch": {"host":"localhost","port":9200,"user":""},
    "es": {"host":"localhost","port":9200,"user":""},
    "mongodb": {"host":"localhost","port":27017,"user":""},
    "mongo": {"host":"localhost","port":27017,"user":""},
    "influxdb": {"host":"localhost","port":8086,"user":""},
    "influx": {"host":"localhost","port":8086,"user":""},
    "tdengine": {"host":"localhost","port":6030,"user":"root"},
    "td": {"host":"localhost","port":6030,"user":"root"},
    "vectordb": {"host":"localhost","port":6333,"user":""},
    "qdrant": {"host":"localhost","port":6333,"user":""},
    "milvus": {"host":"localhost","port":19530,"user":""},
    "dolphindb": {"host":"localhost","port":8848,"user":"admin"},
    "ddb": {"host":"localhost","port":8848,"user":"admin"},
}
EXTRA_IMPORTS = {
    "tidb": "pymysql", "redis": "redis",
    "elasticsearch": "elasticsearch", "es": "elasticsearch",
    "mongodb": "pymongo", "mongo": "pymongo",
    "influxdb": "influxdb_client", "influx": "influxdb_client",
    "tdengine": "taos", "td": "taos",
    "vectordb": "qdrant_client", "qdrant": "qdrant_client",
    "milvus": "pymilvus",
    "dolphindb": "dolphindb",
    "ddb": "dolphindb",
}
"""Required pip packages for each extra engine."""
