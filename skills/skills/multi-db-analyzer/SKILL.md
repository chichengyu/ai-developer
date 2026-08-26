---
name: multi-db-analyzer
description: Pure Python multi-DB query & analysis tool. SQL (MySQL,PostgreSQL,SQLite,SQL Server,Oracle,MariaDB,TiDB) + NoSQL (Redis,ES,MongoDB) + TimeSeries (InfluxDB,TDengine) + VectorDB (Qdrant). Schema, data quality, FK topology, explain, HTML reports.
---

## Overview
multi-db-analyzer is a pure Python multi-database analysis tool using a unified abstraction layer (db_engine.py + db_engine_extras.py). Supports 13+ database engines with zero Java dependency. Provides schema scanning, data quality analysis, FK topology, and execution plan analysis.

## Supported Databases (13 engines)

| Type | Database | Driver | Params |
|------|----------|--------|--------|
| SQL | MySQL | pymysql | --host --port(3306) --db --user --password |
| | MariaDB | pymysql | --host --port(3306) --db --user --password |
| | PostgreSQL | psycopg2 | --host --port(5432) --db --user --password |
| | SQLite | sqlite3 | --db (file path) |
| | SQL Server | pymssql | --host --port(1433) --db --user --password |
| | Oracle | oracledb | --host --port(1521) --db(service) --user --password |
| | TiDB | pymysql | --host --port(4000) --db --user |
| NoSQL | Redis | redis-py | --host --port(6379) --db(0-15) |
| | Elasticsearch | elasticsearch-py | --host --port(9200) |
| | MongoDB | pymongo | --host --port(27017) --db --user --password |
| TimeSeries | InfluxDB | influxdb-client | --host --port(8086) --db(org) --password(token) |
| | TDengine | taos | --host --port(6030) --db --user --password |
| VectorDB | Qdrant | qdrant-client | --host --port(6333) |
| | Milvus | pymilvus | --host --port(19530) --db --user |
| | DolphinDB | dolphindb | --host --port(8848) --user --password |

## Quick Install
Core (+MySQL/MariaDB/TiDB): pip install pymysql
PostgreSQL: pip install psycopg2-binary
SQL Server: pip install pymssql
Oracle: pip install oracledb
Redis: pip install redis
Elasticsearch: pip install elasticsearch
MongoDB: pip install pymongo
InfluxDB: pip install influxdb-client
TDengine: pip install taos
Qdrant: pip install qdrant-client
SQLite: built-in (no install)

## Quick Start Examples
MySQL: python scripts/database_query.py --db-type mysql --db mydb --get-schema
PostgreSQL: python scripts/database_query.py --db-type postgresql --db mydb --analyze-all
SQLite: python scripts/database_query.py --db-type sqlite --db mydb.db --analyze-table user
Redis: python scripts/database_query.py --db-type redis --host localhost --db 0 --analyze-all
ES: python scripts/database_query.py --db-type elasticsearch --host localhost --get-schema
MongoDB: python scripts/database_query.py --db-type mongodb --host localhost --db mydb --analyze-table users
InfluxDB: python scripts/database_query.py --db-type influxdb --host localhost --db myorg --get-schema
TDengine: python scripts/database_query.py --db-type tdengine --host localhost "SHOW DATABASES"
Qdrant: python scripts/database_query.py --db-type vectordb --host localhost --get-schema

## Parameters (all commands)
| Parameter | Default | Description |
|-----------|---------|-------------|
| --db-type | required | DB type. Options: mysql/mariadb/postgresql/sqlite/sqlserver/oracle/tidb/redis/elasticsearch/mongodb/influxdb/tdengine/vectordb |
| --host | auto | DB host |
| --port | auto | Port (default per DB type) |
| --db | DB_NAME env | DB name / file path / Redis DB index |
| --user | auto | DB user |
| --password | DB_PASSWORD env | DB password / InfluxDB token |
| --ssl | false | SSL mode |

Config auto-saved to ~/.multi-db-analyzer-config.json after first successful connection.

## Universal Commands (adapted per DB type)
| Command | Description |
|---------|-------------|
| --get-schema | List all tables/indices/collections with metadata |
| --analyze-all | Full database statistics |
| --analyze-table T | Deep analysis of a table/index/collection |
| --analyze-deep T | Extended analysis (SQL DBs only) |
| --get-relations | FK/cross-reference topology (SQL + MongoDB) |
| --table-deps | Dependency graph (SQL DBs only) |
| --explain SQL | Query execution plan (varies by DB) |
| --export-csv SQL | Export to CSV (SQL DBs only) |
| --pr-report | PR report with snapshots (SQL DBs only) |
| --compare-entities | Java entity comparison (SQL DBs only) |
| <query/command> | Execute native query/command |

## Architecture
scripts/
  db_engine.py          # Core SQL engines + abstraction + factory
  db_engine_extras.py   # Extended engines (NoSQL, TS, Vector)
  database_query.py     # CLI entry point (wrapper)
  erd_viewer.py, csv_exporter.py, table_dependency.py, ...

## Safety
- Read-only for SQL DBs (SELECT only)
- JSON output is escaped

## Compatibility
Standalone multi-DB analysis tool. No external skill dependencies.
