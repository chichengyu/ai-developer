# multi-db-analyzer
Multi-DB query & analysis tool. Zero Java dependency.
**13 engines**: MySQL, MariaDB, PostgreSQL, SQLite, SQL Server, Oracle, TiDB, Redis, Elasticsearch, MongoDB, InfluxDB, TDengine, Qdrant/VectorDB.

## Quick Start
```
pip install pymysql          # Core (MySQL/MariaDB/TiDB)
python scripts/database_query.py --db-type mysql --db mydb --get-schema
python scripts/database_query.py --db-type postgresql --db mydb --analyze-all
python scripts/database_query.py --db-type sqlite --db mydb.db --analyze-table user
python scripts/database_query.py --db-type redis --host localhost --db 0 --analyze-all
```

## Supported Databases
| Type | DB | Driver | Install |
|------|-----|--------|---------|
| SQL | MySQL/MariaDB/TiDB | pymysql | pip install pymysql |
| | PostgreSQL | psycopg2 | pip install psycopg2-binary |
| | SQLite | sqlite3 | Built-in |
| | SQL Server | pymssql | pip install pymssql |
| | Oracle | oracledb | pip install oracledb |
| NoSQL | Redis | redis | pip install redis |
| | Elasticsearch | elasticsearch | pip install elasticsearch |
| | MongoDB | pymongo | pip install pymongo |
| TimeSeries | InfluxDB | influxdb-client | pip install influxdb-client |
| | TDengine | taos | pip install taos |
| VectorDB | Qdrant | qdrant-client | pip install qdrant-client |
| | Milvus | pymilvus | pip install pymilvus |
| TimeSeries | DolphinDB | dolphindb | pip install dolphindb |

## Common Parameters
| Parameter | Default | Description |
|-----------|---------|-------------|
| --db-type | required | DB type (ask user if not specified) |
| --host | auto | DB host |
| --port | auto | DB port |
| --db | DB_NAME env | DB name / file / Redis index |
| --user | auto | DB user |
| --password | DB_PASSWORD env | DB password / InfluxDB token |

Config auto-saved to ~/.multi-db-analyzer-config.json after first success.

## Universal Commands
| Command | Description |
|---------|-------------|
| --get-schema | List tables/indices/collections |
| --analyze-all | DB statistics |
| --analyze-table | Deep analysis |
| --explain | Query plan |
| <query> | Native command/query |
| --get-relations | FK topology (SQL) |
| --table-deps | Dependency graph |
| --export-csv | CSV export |
| --pr-report | PR report |

## Database-specific Examples
```
# MySQL: schema
python scripts/database_query.py --db-type mysql --db mydb --get-schema
# PostgreSQL: analysis
python scripts/database_query.py --db-type postgresql --db mydb --analyze-all
# Redis: keyspace stats
python scripts/database_query.py --db-type redis --host localhost --db 0 --analyze-all
# ES: list indices
python scripts/database_query.py --db-type elasticsearch --host localhost --get-schema
# MongoDB: collection analysis
python scripts/database_query.py --db-type mongodb --host localhost --db mydb --analyze-table users
# InfluxDB: buckets
python scripts/database_query.py --db-type influxdb --host localhost --db myorg --get-schema
# TDengine: query
python scripts/database_query.py --db-type tdengine --host localhost "SHOW DATABASES"
# Qdrant: collections
python scripts/database_query.py --db-type vectordb --host localhost --get-schema
# CSV export
python scripts/csv_exporter.py --db-type mysql --db mydb "SELECT * FROM user" --output users.csv
```

## Safety
Read-only (SELECT only for SQL). JSON output is escaped.

## Related
See SKILL.md and docs/TOOLCHAIN.md for details.
