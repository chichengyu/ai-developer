#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ReqAnalyzer — 需求深度分析器 (Python 版)
对应契约第6节（两阶段工作流）+ 第15节（需求深度分析框架）。
将自然语言需求转化为结构化分析报告：影响范围、风险评估、实现步骤。

用法：
  python req_analyzer.py "新增用户年龄字段，支持按年龄分组统计"
  python req_analyzer.py --input requirement.txt --format html --output analysis.html
  python req_analyzer.py --input requirement.txt --format json --output analysis.json
"""
import json, sys, os, argparse, datetime, re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

OUTPUT_TEMPLATE = '''
{section1}

{section2}

{section3}
'''

MARKDOWN_TEMPLATE = """# 需求影响分析报告: {req_title}

{overview}

## 1. 业务逻辑与调用链路分析

{chain_analysis}

## 2. 潜在副作用与风险评估

{risk_assessment}

### 线程池与异步
{async_risk}

### 单元测试
{test_risk}

### 事务传播机制
{tx_risk}

## 3. 详细文件级改造步骤

{steps_table}

### SQL 变更
{sql_changes}

---

🔄【执行审计】
- 技能: {skills}
- 分析引擎: ReqAnalyzer v1.0
- 生成时间: {gen_time}
"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>需求影响分析报告 - {req_title}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;max-width:960px;margin:2em auto;padding:0 1em;color:#1a1a2e;background:#f8f9fa;line-height:1.7}}
h1{{color:#0d6efd;border-bottom:2px solid #0d6efd;padding-bottom:.3em}}
h2{{color:#198754;margin-top:1.5em;border-bottom:1px solid #dee2e6;padding-bottom:.2em}}
h3{{color:#6c757d}}
table{{border-collapse:collapse;width:100%;margin:1em 0}}
th,td{{border:1px solid #dee2e6;padding:.5em;text-align:left}}
th{{background:#e9ecef;font-weight:600}}tr:nth-child(even){{background:#f2f2f2}}
code{{background:#e9ecef;padding:.2em .4em;border-radius:3px;font-size:.9em}}
.summary{{background:#e9ecef;padding:1em;border-radius:8px;margin:1em 0}}
.warning{{color:#dc3545;font-weight:700}}.info{{color:#0d6efd}}
.risk-high{{color:#dc3545;font-weight:700}}.risk-mid{{color:#d97706}}.risk-low{{color:#198754}}
pre{{background:#1a1a2e;color:#f8f9fa;padding:1em;border-radius:6px;overflow-x:auto}}
</style></head><body>
<h1>&#x1f50d; 需求影响分析报告</h1>
<div class="summary"><strong>需求:</strong> {req_title}<br><strong>生成时间:</strong> {gen_time}<br><strong>影响层级:</strong> {layer_count}层 | <strong>建议步骤:</strong> {step_count}步</div>
<h2>1. 业务逻辑与调用链路分析</h2>{chain_analysis}
<h2>2. 潜在副作用与风险评估</h2>
<table><tr><th>维度</th><th>风险等级</th><th>说明</th></tr>
<tr><td>线程池与异步</td><td class="{async_cls}">{async_risk}</td><td>{async_detail}</td></tr>
<tr><td>单元测试</td><td class="{test_cls}">{test_risk}</td><td>{test_detail}</td></tr>
<tr><td>事务传播机制</td><td class="{tx_cls}">{tx_risk}</td><td>{tx_detail}</td></tr>
</table>
<h2>3. 详细文件级改造步骤</h2>
<table><thead><tr><th>步骤</th><th>层级</th><th>文件</th><th>改动内容</th></tr></thead><tbody>{steps_rows}</tbody></table>
<h3>SQL 变更</h3><pre><code>{sql_changes}</code></pre>
<div class="summary">&#x1f504;【执行审计】- 技能: {skills} | 分析引擎: ReqAnalyzer v1.0</div></body></html>"""

class ReqAnalyzer:
    ARCH_LAYERS = ["入口层(Controller/Endpoint)", "业务层(Service/AOP)", "数据层(Repository/Mapper)", "安全层(Security/Auth)", "异步层(Event/Message)"]

    def __init__(self, requirement, title=None):
        self.req = requirement
        self.title = title or requirement[:60] + ("..." if len(requirement) > 60 else "")
        self.impact_layers = self._analyze_layers()
        self.risk = self._assess_risk()
        self.sql = self._generate_sql()
        self.steps = self._generate_steps()

    def _analyze_layers(self):
        """自动分析需求影响到的架构层"""
        hits = []
        r = self.req.lower()
        # Controller层
        if any(w in r for w in ["接口","api","端点","请求","响应","rest","controller","端点","路由"]):
            hits.append(0)
        # Service层
        if any(w in r for w in ["业务","service","逻辑","计算","校验","验证","参数校验","validation","约束","格式检查"]):
            hits.append(1)
        # Repository层
        if any(w in r for w in ["数据","查询","sql","存储","表","字段","数据库","索引","实体"]) or re.search(r'增|删|改|查|写|读', r):
            hits.append(2)
        # 安全层
        if any(w in r for w in ["权限","认证","授权","加密","token","jwt","oauth","角色","权限","密码","登录","注册"]):
            hits.append(3)
        # 异步层
        if any(w in r for w in ["异步","消息","事件","队列","kafka","rabbit","mq","通知","邮件","批量","调度","cron","定时","延迟","重试","batch","schedule","retry"]):
            hits.append(4)
        return hits if hits else [1]  # 至少影响业务层

    def _assess_risk(self):
        """风险评估"""
        r = self.req.lower()
        risks = {
            "async": ("高" if any(w in r for w in ["异步","队列","kafka","并发"]) else
                     ("中" if any(w in r for w in ["事务","批量","大量"]) else "低")),
            "test": ("高" if any(w in r for w in ["重构","改","重写","替换"]) else
                    ("中" if any(w in r for w in ["新增","拓展","加"]) else "低")),
            "tx": ("高" if any(w in r for w in ["事务","跨库","分布式","回滚"]) else
                  ("中" if any(w in r for w in ["更新","修改","写"]) else "低")),
        }
        risk_details = {
            "async": ("异步处理超时/线程池耗尽" if risks["async"] == "高" else
                     ("事务边界内调用异步方法" if risks["async"] == "中" else "无异步调用")),
            "test": ("现有测试需全部重新验证" if risks["test"] == "高" else
                    ("需新增测试覆盖" if risks["test"] == "中" else "影响范围有限")),
            "tx": ("长事务导致连接池枯竭" if risks["tx"] == "高" else
                  ("API兼容性回滚风险" if risks["tx"] == "中" else "无事务风险")),
        }
        return risks, risk_details

    def _generate_steps(self):
        """生成改造步骤"""
        steps = []
        r = self.req
        has_db = 2 in self.impact_layers
        has_api = 0 in self.impact_layers
        has_service = 1 in self.impact_layers

        if has_db:
            steps.append({"step":1,"layer":"数据层","file":"数据库/实体类 [新增]","change":"新增/修改字段，新建表/索引","sql":self.sql})
        if has_api:
            steps.append({"step":len(steps)+1,"layer":"入口层","file":"XxxController.java [已有]","change":"新增/修改接口方法，添加入参校验","sql":""})
        if has_service:
            steps.append({"step":len(steps)+1,"layer":"业务层","file":"XxxService.java [已有]","change":"新增业务方法，遵循最小改动原则","sql":""})
        if 4 in self.impact_layers:
            steps.append({"step":len(steps)+1,"layer":"异步层","file":"XxxEventListener.java [已有]","change":"新增事件监听/消息发送","sql":""})

        if not steps:
            steps.append({"step":1,"layer":"综合","file":"[分析结论]","change":"无需代码变更，仅配置调整","sql":""})
        return steps

    def _generate_sql(self):
        """根据需求生成SQL变更语句"""
        r = self.req.lower()
        lines = ["-- 需求分析生成的SQL变更", f"-- 需求: {self.title}", ""]

        if "年龄" in r or "age" in r:
            lines.append("-- forward: 新增年龄字段（INSTANT级DDL，MySQL 8.0.12+）")
            lines.append("ALTER TABLE user ADD COLUMN age INT DEFAULT NULL COMMENT '年龄';")
            lines.append("-- rollback: ALTER TABLE user DROP COLUMN age;")
        if "手机" in r or "phone" in r or "mobile" in r:
            lines.append("-- forward: 新增手机号字段")
            lines.append("ALTER TABLE user ADD COLUMN phone VARCHAR(20) DEFAULT NULL COMMENT '手机号';")
            lines.append("-- rollback: ALTER TABLE user DROP COLUMN phone;")
        if "邮箱" in r or "email" in r:
            lines.append("-- forward: 新增邮箱字段")
            lines.append("ALTER TABLE user ADD COLUMN email VARCHAR(100) DEFAULT NULL COMMENT '邮箱';")
            lines.append("-- rollback: ALTER TABLE user DROP COLUMN email;")
        if "订单" in r or "order" in r:
            lines.append("-- forward: 创建索引")
            lines.append("CREATE INDEX idx_order_user_id ON order(user_id);")
            lines.append("-- rollback: DROP INDEX idx_order_user_id ON order;")

        if len(lines) <= 2:
            lines.append("-- 本次需求不涉及SQL变更")
            lines.append("-- 或：请人工审查后补充SQL语句")

        return "\n".join(lines)

    def __str__(self):
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_dict(self):
        return {
            "title": self.title,
            "requirement": self.req,
            "timestamp": datetime.datetime.now().isoformat(),
            "impactLayers": [self.ARCH_LAYERS[i] for i in self.impact_layers],
            "layersAffected": len(self.impact_layers),
            "riskAssessment": {
                "async": {"level": self.risk[0]["async"], "detail": self.risk[1]["async"]},
                "test": {"level": self.risk[0]["test"], "detail": self.risk[1]["test"]},
                "transaction": {"level": self.risk[0]["tx"], "detail": self.risk[1]["tx"]},
            },
            "steps": self.steps,
            "sql": self.sql,
        }

    def to_markdown(self):
        a = self.to_dict()
        return MARKDOWN_TEMPLATE.format(
            req_title = a["title"],
            overview = f"**需求原文:** {a['requirement']}\n\n**影响层级 ({a['layersAffected']}层):** {', '.join(a['impactLayers'])}",
            chain_analysis = self._chain_analysis_md(),
            risk_assessment = "根据4个维度评估本次变更风险：",
            async_risk = f"**{a['riskAssessment']['async']['level']}** - {a['riskAssessment']['async']['detail']}",
            test_risk = f"**{a['riskAssessment']['test']['level']}** - {a['riskAssessment']['test']['detail']}",
            tx_risk = f"**{a['riskAssessment']['transaction']['level']}** - {a['riskAssessment']['transaction']['detail']}",
            steps_table = self._steps_md(),
            sql_changes = f"```sql\n{a['sql']}\n```",
            skills = "multi-db-analyzer [已有], ReqAnalyzer [新增]",
            gen_time = a["timestamp"],
        )

    def to_html(self):
        a = self.to_dict()
        cls_map = {"高": "risk-high", "中": "risk-mid", "低": "risk-low"}
        steps_rows = "\n".join(
            f'<tr><td>{s["step"]}</td><td>{s["layer"]}</td><td><code>{s["file"]}</code></td><td>{s["change"]}</td></tr>'
            for s in a["steps"])

        return HTML_TEMPLATE.format(
            req_title = a["title"],
            gen_time = a["timestamp"],
            layer_count = a["layersAffected"],
            step_count = len(a["steps"]),
            chain_analysis = self._chain_analysis_html(),
            async_cls = cls_map.get(a["riskAssessment"]["async"]["level"], "info"),
            async_risk = a["riskAssessment"]["async"]["level"],
            async_detail = a["riskAssessment"]["async"]["detail"],
            test_cls = cls_map.get(a["riskAssessment"]["test"]["level"], "info"),
            test_risk = a["riskAssessment"]["test"]["level"],
            test_detail = a["riskAssessment"]["test"]["detail"],
            tx_cls = cls_map.get(a["riskAssessment"]["transaction"]["level"], "info"),
            tx_risk = a["riskAssessment"]["transaction"]["level"],
            tx_detail = a["riskAssessment"]["transaction"]["detail"],
            steps_rows = steps_rows,
            sql_changes = a["sql"],
            skills = "multi-db-analyzer [已有], ReqAnalyzer [新增]",
        )

    def _chain_analysis_md(self):
        lines = [f"本次需求 `{self.title}` 影响 **{len(self.impact_layers)}** 个架构层：\n"]
        for i in self.impact_layers:
            lines.append(f"- **{self.ARCH_LAYERS[i]}**: 需要新增/修改对应代码")
        if not self.impact_layers:
            lines.append("- 需求不涉及代码变更")
        return "\n".join(lines)

    def _chain_analysis_html(self):
        parts = [f'<p>本次需求 <strong>{self.title}</strong> 影响 <strong>{len(self.impact_layers)}</strong> 个架构层：</p><ul>']
        for i in self.impact_layers:
            parts.append(f'<li><strong>{self.ARCH_LAYERS[i]}</strong>: 需要新增/修改对应代码</li>')
        parts.append("</ul>")
        return "\n".join(parts)

    def _steps_md(self):
        lines = ["| 步骤 | 层级 | 文件 | 改动内容 |", "|------|------|------|----------|"]
        for s in self.steps:
            lines.append(f"| {s['step']} | {s['layer']} | `{s['file']}` | {s['change']} |")
        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="ReqAnalyzer 需求深度分析器")
    parser.add_argument("--input", "-i", help="需求描述文件(.txt)")
    parser.add_argument("--format", "-f", default="markdown", choices=["json","markdown","html"])
    parser.add_argument("--output", "-o", help="输出文件路径")
    parser.add_argument("req", nargs="*", help="需求描述文本")
    args = parser.parse_args()

    requirement = ""
    title = None
    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            requirement = f.read().strip()
        title = os.path.splitext(os.path.basename(args.input))[0]
    elif args.req:
        requirement = " ".join(args.req)

    if not requirement:
        parser.print_help()
        return

    analyzer = ReqAnalyzer(requirement, title)

    if args.format == "json":
        content = str(analyzer)
    elif args.format == "html":
        content = analyzer.to_html()
    else:
        content = analyzer.to_markdown()

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(content)
        print(json.dumps({"status":"success","output":args.output,"format":args.format,
                         "layers":len(analyzer.impact_layers),"steps":len(analyzer.steps)}))
    else:
        print(content)

if __name__ == "__main__":
    main()
