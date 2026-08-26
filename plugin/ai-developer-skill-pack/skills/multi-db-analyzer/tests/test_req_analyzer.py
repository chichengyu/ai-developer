"""Tests for req_analyzer.py."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from req_analyzer import ReqAnalyzer


class TestReqAnalyzer:
    def test_layer_detection_controller(self):
        """Test controller layer detection."""
        analyzer = ReqAnalyzer("新增一个REST API接口，查询用户列表")
        assert 0 in analyzer.impact_layers  # Controller

    def test_layer_detection_service(self):
        """Test business layer detection."""
        analyzer = ReqAnalyzer("优化订单计算逻辑")
        assert 1 in analyzer.impact_layers

    def test_layer_detection_database(self):
        """Test data layer detection."""
        analyzer = ReqAnalyzer("user表新增age字段")
        assert 2 in analyzer.impact_layers

    def test_layer_detection_security(self):
        """Test security layer detection."""
        analyzer = ReqAnalyzer("添加角色权限管理功能")
        assert 3 in analyzer.impact_layers

    def test_layer_detection_async(self):
        """Test async layer detection."""
        analyzer = ReqAnalyzer("使用Kafka处理订单消息")
        assert 4 in analyzer.impact_layers

    def test_risk_assessment(self):
        analyzer = ReqAnalyzer("重构支付模块，替换底层实现")
        risks = analyzer.risk[0]
        assert risks["test"] in ["高", "中", "低"]

    def test_sql_generation_age(self):
        analyzer = ReqAnalyzer("新增用户年龄字段")
        assert "age" in analyzer.sql.lower() or "年龄" in analyzer.sql

    def test_sql_generation_order(self):
        analyzer = ReqAnalyzer("优化订单查询性能")
        assert "index" in analyzer.sql.lower() or "索引" in analyzer.sql

    def test_sql_generation_permission(self):
        analyzer = ReqAnalyzer("添加角色权限管理")
        assert "role_permission" in analyzer.sql

    def test_sql_generation_schedule(self):
        analyzer = ReqAnalyzer("添加定时任务调度功能")
        assert "scheduled_task" in analyzer.sql or "cron" in analyzer.sql

    def test_output_json(self):
        analyzer = ReqAnalyzer("测试需求分析")
        output = str(analyzer)
        assert "title" in output
        assert "requirement" in output
        assert "impactLayers" in output
        assert "riskAssessment" in output
        assert "steps" in output

    def test_output_markdown(self):
        analyzer = ReqAnalyzer("测试需求分析")
        md = analyzer.to_markdown()
        assert "影响范围" in md or "需求影响" in md

    def test_output_html(self):
        analyzer = ReqAnalyzer("测试需求分析")
        html = analyzer.to_html()
        assert "<!DOCTYPE html>" in html or "<html" in html

    def test_to_dict(self):
        analyzer = ReqAnalyzer("测试")
        d = analyzer.to_dict()
        assert isinstance(d, dict)
        assert "title" in d
        assert "steps" in d
