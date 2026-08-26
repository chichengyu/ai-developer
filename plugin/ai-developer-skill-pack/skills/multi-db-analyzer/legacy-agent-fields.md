# Legacy agent manifest fields
The original `agents/openai.yaml` for this skill contained extra fields that the current Codex plugin-creator schema does not accept (`triggers`, `input_schema`, `output_example`). They are preserved here verbatim so the information stays available inside the bundled skill even after the schema cleanup. The active agent manifest in this directory keeps only the schema-allowed fields.
## triggers
```yaml
triggers:
  - keyword: "database query"
    patterns:
      - "analyze.*database"
      - "table.*schema"
      - "MySQL.*query"
      - "PostgreSQL.*analyze"
      - "SQLite.*analyze"
      - "SQL Server.*query"
      - "Oracle.*analyze"
      - "TiDB.*query"
      - "Redis.*query"
      - "Elasticsearch.*query"
      - "MongoDB.*query"
      - "InfluxDB.*query"
      - "TDengine.*query"
      - "vector.*database.*query"
      - "Qdrant.*query"
      - "time series.*query"
      - "NoSQL.*analyze"
      - "data quality.*assessment"
      - "foreign key.*relationship"
      - "SQL.*execution plan"
    skill_ref: multi-db-analyzer
```
## input_schema
```yaml
input_schema:
  type: object
  properties:
    db_type:
      type: string
      description: "REQUIRED: Database type. Codex MUST ask the user if not specified. NO default type is ever assumed. Options: mysql/mariadb/postgresql/sqlite/sqlserver/oracle/tidb/redis/elasticsearch/mongodb/influxdb/tdengine/vectordb/milvus/dolphindb"
    host:
      type: string
      description: "REQUIRED: Database host. Codex MUST ask the user if not specified."
    port:
      type: integer
      description: "Database port (optional, defaults per DB type)"
    db:
      type: string
      description: "Database name / file path (SQLite) / Redis DB index"
    user:
      type: string
      description: "REQUIRED: Database user. Codex MUST ask the user if not specified."
    password:
      type: string
      description: "REQUIRED: Database password. Codex MUST ask the user if not specified (unless using saved profile)."
    command:
      type: string
      description: "Command: --get-schema, --analyze-all, --analyze-table <table>, --get-relations, --explain <SQL>"
  required:
    - db_type
    - host
    - user
    - password
    - command
```
## output_example
```yaml
output_example:
  markdown: |
    | Table | Engine | Est.Rows | Size(MB) | Cols | Comment |
    |------|--------|---------|---------|------|--------|
    | user | InnoDB | 1024 | 16.00 | 12 | User table |
    | order | InnoDB | 5120 | 128.00 | 8 | Order table |
  json: |
    {
      "status": "analyze_all_success",
      "analysis": {
        "database": "mydb",
        "tables": [{"name":"user","engine":"InnoDB","estimatedRows":1024,"totalSizeMb":16.0,"columnCount":12}]
      }
    }
```
