"""Tests for other utility scripts."""
import json, sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestAuditReport:
    def test_sample_data(self):
        from audit_report_generator import generate_sample_audit_data
        data = generate_sample_audit_data()
        assert "sessionId" in data
        assert "summary" in data

    def test_markdown_report(self):
        from audit_report_generator import generate_markdown_report
        data = {"title":"Test","sessionId":"s1","timestamp":"now","skills":["t1"],"tools":["t1"],
            "filesRead":[],"filesModified":[],"sqlExecuted":[],"dataQualityIssues":[],"summary":{}}
        md = generate_markdown_report(data)
        assert "Test" in md

    def test_html_report(self):
        from audit_report_generator import generate_html_report
        data = {"title":"Test","sessionId":"s1","timestamp":"now","skills":[],"tools":[],
            "filesRead":[],"filesModified":[],"sqlExecuted":[],"dataQualityIssues":[],"summary":{}}
        html = generate_html_report(data)
        assert "<!DOCTYPE html>" in html

    def test_data_quality_analysis(self):
        from audit_report_generator import analyze_data_quality
        nr, esr, svr, score, warn = analyze_data_quality("email",10,100,5,[{"value":"0","count":2}])
        assert 0 <= score <= 1
        assert nr == 0.1

    def test_password_guide(self):
        from audit_report_generator import password_quoting_guide
        guide = json.loads(password_quoting_guide())
        assert "title" in guide
        assert "methods" in guide


class TestCsvExporter:
    @patch("csv_exporter.create_engine")
    def test_export(self, mock_create):
        from csv_exporter import export_csv
        count = export_csv([{"a":1},{"a":2}], "test_output.csv")
        import os
        try: os.remove("test_output.csv")
        except: pass
        assert count == 2


class TestCicdHelper:
    def test_import(self):
        from cicd_helper import check_commit_message
        result = check_commit_message("feat(user): add age field")
        assert result["valid"] is True

    def test_invalid_commit(self):
        from cicd_helper import check_commit_message
        result = check_commit_message("random content")
        assert result["valid"] is False


class TestSkillBridge:
    @patch("skill_bridge.audit_report_generator")
    def test_convert(self, mock_audit):
        from skill_bridge import convert_analyze_to_audit
        data = {"status":"analyze_table_success","analysis":{"table":"user",
            "columns":[{"name":"email","nullRatio":0.1,"emptyStringCount":0,"distinctCount":50,"sentinelValueRatio":0.0,"qualityScore":0.95,"warning":"Normal"}]}}
        result = convert_analyze_to_audit(data)
        assert "dataQualityIssues" in result
        assert len(result["dataQualityIssues"]) == 1
