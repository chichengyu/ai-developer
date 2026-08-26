"""Tests for erd_viewer.py."""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from erd_viewer import generate_html, fetch_relations


def test_generate_html(sample_relations):
    """Test HTML generation from relations data."""
    html = generate_html(sample_relations, "testdb")
    assert "<!DOCTYPE html>" in html
    assert "testdb" in html
    assert "fk_order_user" in html


@patch("erd_viewer.create_engine")
def test_fetch_relations(mock_create):
    """Test fetch_relations with mocked create_engine."""
    mock_engine = MagicMock()
    mock_engine.get_relations.return_value = {"relations": {"database": "testdb", "relations": []}}
    mock_create.return_value = mock_engine

    result = fetch_relations("localhost", 3306, "testdb", "root", "pass", "false", "mysql")
    assert result["relations"]["database"] == "testdb"
    mock_engine.connect.assert_called_once()
    mock_engine.close.assert_called_once()
