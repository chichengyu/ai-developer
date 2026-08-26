"""Tests for database_query.py - core multi-DB query engine."""
import json, sys, os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from database_query import DatabaseQuery, save_config, load_config, clear_config


class TestDatabaseQuery:
    """Test DatabaseQuery class."""

    def test_init_defaults(self):
        q = DatabaseQuery()
        assert q.host == "localhost"
        assert q.db == ""
        assert q.user == "root"
        assert q._engine is None

    def test_init_custom(self):
        q = DatabaseQuery(host="192.168.1.1", port=3307, db="mydb", user="admin", password="secret", ssl_mode="true")
        assert q.host == "192.168.1.1"
        assert q.port == 3307
        assert q.db == "mydb"
        assert q.password == "secret"
        assert q.ssl_mode == "true"

    @patch("database_query.create_engine")
    def test_connect_delegates(self, mock_create_engine):
        mock_engine = MagicMock()
        mock_engine.connect.return_value = True
        mock_create_engine.return_value = mock_engine
        q = DatabaseQuery(db="testdb")
        result = q.connect("mysql")
        assert result is True
        assert q._engine is not None
        mock_create_engine.assert_called_once()

    @patch("database_query.create_engine")
    def test_delegate_method(self, mock_create_engine):
        mock_engine = MagicMock()
        mock_engine.connect.return_value = True
        mock_engine.get_schema.return_value = {"status":"schema_success","schema":{"database":"testdb","tables":[]}}
        mock_create_engine.return_value = mock_engine
        q = DatabaseQuery(db="testdb")
        q.connect("mysql")
        result = q.get_schema()
        assert result["status"] == "schema_success"
        assert result["schema"]["database"] == "testdb"

    def test_close(self):
        q = DatabaseQuery(db="testdb")
        q._engine = MagicMock()
        q.close()
        q._engine.close.assert_called_once()

    def test_backward_compatibility(self):
        from database_query import MySQLQuery
        q = MySQLQuery()
        assert isinstance(q, DatabaseQuery)


class TestConfigFunctions:
    def test_save_config_new(self):
        with patch("database_query.CONFIG_PATH", new_callable=MagicMock) as mock_cfg:
            with patch("pathlib.Path.write_text"):
                result = save_config("localhost", 3306, "testdb", "root", "pass", "mysql")
                assert result["status"] == "config_saved"

    def test_clear_config(self):
        with patch("database_query.CONFIG_PATH", new_callable=MagicMock) as mock_cfg:
            with patch.object(Path, "unlink") as mock_unlink:
                result = clear_config()
                assert result["status"] == "config_cleared"
