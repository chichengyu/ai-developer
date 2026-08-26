"""Shared test fixtures for multi-db-analyzer."""
import json, sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

_SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPT_DIR))


@pytest.fixture
def sample_schema_data():
    return {"status":"schema_success","schema":{"database":"testdb","tables":[
        {"name":"user","comment":"User table","engine":"InnoDB","estimatedRows":100,
         "columns":[{"name":"id","type":"bigint","nullable":False,"default":None,"comment":"ID"},
                    {"name":"username","type":"varchar(50)","nullable":False,"default":None,"comment":"Username"},
                    {"name":"email","type":"varchar(100)","nullable":True,"default":None,"comment":"Email"}],
         "primaryKey":["id"],"indexes":[{"name":"idx_email","column":"email","unique":False}]}]}}


@pytest.fixture
def sample_analyze_all_data():
    return {"status":"analyze_all_success","analysis":{"database":"testdb","tables":[
        {"name":"user","engine":"InnoDB","estimatedRows":100,"totalSizeMb":0.5,"columnCount":4,"comment":"User table"},
        {"name":"order","engine":"InnoDB","estimatedRows":50,"totalSizeMb":0.3,"columnCount":6,"comment":"Order table"}]}}


@pytest.fixture
def sample_relations():
    return {"database":"testdb","relations":[{"constraintName":"fk_order_user","parentTable":"user","parentColumn":"id",
        "childTable":"order","childColumn":"user_id","updateRule":0,"deleteRule":0}],
        "mermaidErd":"erDiagram\n  user ||--o{ order : \"has\""}


@pytest.fixture
def sample_audit_data():
    return {"sessionId":"test_session","timestamp":"2026-07-16T12:00:00","title":"Test Audit",
        "skills":["multi-db-analyzer"],"tools":["DatabaseQuery"],
        "filesRead":[{"path":"test.java","status":"[Present]"}],
        "filesModified":[{"path":"test.java","change":"Modified"}],
        "sqlExecuted":[{"sql":"SELECT 1","type":"SELECT"}],
        "dataQualityIssues":[{"table":"user","column":"email","nullRatio":0.1,"emptyStringRatio":0.0,
            "sentinelValueRatio":0.0,"qualityScore":0.95,"warning":"Normal"}],
        "summary":{"totalSkills":1,"totalTools":1,"totalFilesRead":1,
            "totalFilesModified":1,"totalSqlExecuted":1,"totalQualityIssues":0}}
