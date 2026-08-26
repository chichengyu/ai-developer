# multi-db-analyzer Toolchain Documentation

## Overview
multi-db-analyzer provides a multi-database query and analysis toolkit supporting MySQL, PostgreSQL, SQLite, SQL Server, Oracle, and MariaDB through a unified Python abstraction layer.

## Script Overview

| Script | Function | Key Parameters |
|--------|----------|----------------|
| `database_query.py` | Core DB query engine | `--db-type`, `--db`, `--get-schema`, `--analyze-all`, `--analyze-table`, `--pr-report`, `--compare-entities` |
| `erd_viewer.py` | ER diagram HTML | `--db-type`, `--input`, `--output` |
| `sql_explain_analyzer.py` | SQL plan analysis | `--db-type`, `--input` (slow log), or inline SQL |
| `csv_exporter.py` | CSV export | `--db-type`, `--output`, or `--input` (JSON) |
| `table_dependency.py` | Dependency graph + HTML | `--db-type`, `--output`, `--format` |
| `req_analyzer.py` | Requirements analysis | `--input`, `--format`, `--output` |
| `audit_report_generator.py` | Audit report | `--input`, `--format` (json/md/html), `--output` |
| `skill_bridge.py` | Bridge to superpowers-contract | `--analyze-result`, `--db`, `--tables` |
| `cicd_helper.py` | CI/CD pre-commit hooks | `--audit`, `--output-dir`, `--pre-commit-install` |

## database_query.py Usage
Core multi-DB query engine. All commands use --db-type to select the database.

```bash
# MySQL
python scripts/database_query.py --db-type mysql --db mydb --get-schema
python scripts/database_query.py --db-type mysql --db mydb --analyze-all
python scripts/database_query.py --db-type mysql --db mydb --analyze-table user
# PostgreSQL
python scripts/database_query.py --db-type postgresql --db mydb --analyze-deep user
python scripts/database_query.py --db-type postgresql --db mydb --get-relations
# SQLite
python scripts/database_query.py --db-type sqlite --db mydb.db --table-deps
python scripts/database_query.py --db-type sqlite --db mydb.db --explain "SELECT * FROM user WHERE id = 1"
# SQL Server
python scripts/database_query.py --db-type sqlserver --db mydb "SELECT * FROM user LIMIT 5"
python scripts/database_query.py --db-type sqlserver --db mydb --pr-report
# Oracle
python scripts/database_query.py --db-type oracle --db orcl --pr-report user order
python scripts/database_query.py --db-type oracle --db orcl --compare-entities --entity-path ./src
```

## Other Scripts Usage (all support --db-type)

### erd_viewer.py
```bash
python scripts/erd_viewer.py --db-type mysql --db mydb --output erd.html
python scripts/erd_viewer.py --db-type postgresql --db mydb --output erd.html
python scripts/erd_viewer.py --db-type sqlite --db mydb.db --output erd.html
python scripts/erd_viewer.py --input relations.json --output erd.html
```

### csv_exporter.py
```bash
python scripts/csv_exporter.py --db-type mysql --db mydb "SELECT * FROM user" --output users.csv
python scripts/csv_exporter.py --db-type postgresql --db mydb "SELECT * FROM orders" --output orders.csv
python scripts/csv_exporter.py --input result.json --output export.csv
```

### sql_explain_analyzer.py
```bash
python scripts/sql_explain_analyzer.py --db-type mysql --db mydb "SELECT * FROM user WHERE id = 1"
python scripts/sql_explain_analyzer.py --db-type postgresql --db mydb "SELECT * FROM orders"
python scripts/sql_explain_analyzer.py --db-type sqlite --db mydb.db --input slow_queries.log
```

### table_dependency.py
```bash
python scripts/table_dependency.py --db-type mysql --db mydb --output deps.html
python scripts/table_dependency.py --db-type postgresql --db mydb --output deps.html
python scripts/table_dependency.py --input relations.json --output deps.html
```

### skill_bridge.py
```bash
python scripts/skill_bridge.py --db-type mysql --db mydb --tables user order --audit-format markdown
python scripts/skill_bridge.py --analyze-result analyze.json --audit-output audit_input.json
```

### audit_report_generator.py
```bash
python scripts/audit_report_generator.py --sample --format markdown --output report.md
```

## Database Support Matrix

| Feature | MySQL | PostgreSQL | SQLite | SQL Server | Oracle | MariaDB | TiDB |
|---------|-------|-----------|--------|-----------|--------|---------|------|
| get_schema | Full | Full | Basic | Full | Full | Full | Full |
| analyze_all | Full | Full | Basic | Full | Basic | Full | Full |
| analyze_table | Full | Full | Full | Basic | Basic | Full | Full |
| analyze_deep | Full | Basic | Basic | - | - | Basic | Full |
| get_relations | Full | Full | Full | Full | Full | Full | Full |
| table_deps | Full | Full | Full | Full | Full | Full | Full |
| explain | Full | Full | Basic | Basic | Basic | Full | Full |
| export_csv | Full | Full | Full | Full | Full | Full | Full |
| pr_report | Full | Basic | Basic | Basic | Basic | Basic | Basic |

| Feature | Redis | ES | MongoDB | InfluxDB | TDengine | Qdrant | Milvus | DolphinDB |
|---------|-------|-----|---------|----------|---------|--------|--------|-----------|
| get_schema | Key info | Index mapping | Collections | Buckets | DB list | Collections | Collections | Tables |
| analyze_all | Memory/stats | Cluster health | DB stats | Org stats | Instance stats | Collection info | Collection stats | DB stats |
| analyze_table | Type analysis | Index analysis | Collection deep | Measurement | STable/TB | Scroll points | Query entities | Table info |
| get_relations | - | - | - | - | - | - | - | - |
| table_deps | - | - | - | - | - | - | - | - |
| explain | - | Query DSL | Aggregation | Flux explain | SQL explain | - | - | Execution plan |
| export_csv | Full | Full | Full | Full | Full | Full | Full | Full |
| pr_report | Basic | Basic | Basic | Basic | Basic | Basic | Basic | Basic |

## Architecture
```mermaid
flowchart LR
    subgraph CLI[CLI Layer]
        DBQ[database_query.py]
        ERD[erd_viewer.py]
        CSV[csv_exporter.py]
        DEP[table_dependency.py]
        EXP[sql_explain_analyzer.py]
    end
    subgraph ABS[Abstraction Layer]
        ENG[db_engine.py]
        FT[Factory: create_engine()]
    end
    subgraph EDB[Database Engines]
        MY[MySQL/pymysql]
        MA[MariaDB/pymysql]
        PG[PostgreSQL/psycopg2]
        SL[SQLite/sqlite3]
        SS[SQL Server/pymssql]
        OR[Oracle/oracledb]
        TI[TiDB/pymysql]
    end
    subgraph NDB[NoSQL/TS/Vector Engines]
        RD[Redis/redis-py]
        ES[Elasticsearch/elasticsearch-py]
        MG[MongoDB/pymongo]
        IF[InfluxDB/influxdb-client]
        TD[TDengine/taos]
        QD[Qdrant/qdrant-client]
        MV[Milvus/pymilvus]
        DD[DolphinDB/dolphindb]
    end
    CLI --> ENG
    FT --> MY & MA & PG & SL & SS & OR & TI
    FT --> RD & ES & MG & IF & TD & QD & MV & DD
```

## Compatibility
Standalone analysis toolkit. No external skill dependencies.
