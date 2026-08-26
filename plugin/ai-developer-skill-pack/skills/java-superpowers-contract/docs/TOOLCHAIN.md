# 工具链与需求分析

本契约附带 11 组 Python 工具，外部依赖仅 `pymysql`。安装：`pip install -r requirements.txt`。

## 工具列表

| 工具 | 作用 | 入口 |
|------|------|------|
| database_query | MySQL 数据库查询与分析（schema / 统计 / 数据质量 / 外键拓扑） | `python database_query.py` |
| audit_report_generator | 审计报告生成器（JSON / Markdown / HTML 三格式） | `python audit_report_generator.py` |
| req_analyzer | 需求深度分析：四层穿透 + 风险评估 + SQL 预生成 | `python req_analyzer.py` |
| sql_explain_analyzer | SQL 执行计划分析（全表扫描 / 索引使用 / 临时表） | `python sql_explain_analyzer.py` |
| csv_exporter | SQL 查询结果导出 CSV | `python csv_exporter.py` |
| erd_viewer | ER 图可视化 HTML 生成 | `python erd_viewer.py` |
| table_dependency | 表依赖拓扑 + 环形依赖检测 + 影响链分析 | `python table_dependency.py` |
| cicd_helper | CI/CD 集成：提交信息校验 / 数据质量检查 / 审计报告 | `python cicd_helper.py` |
| skill_bridge | 连接多数据库工具与审计报告的桥接工具 | `python skill_bridge.py` |
| java_compiler | Maven/Gradle 自动编译验证 | `python java_compiler.py --path .` |
| java_static_analyzer | 静态代码分析（Checkstyle/PMD/SpotBugs） | `python java_static_analyzer.py --path .` |

## 四层穿透分析模型

用于需求分析和影响评估，从四个层面穿透目标变更：

1. **入口层 (Controller)** — `@RestController`、接口定义、DTO 结构
2. **业务层 (Service/AOP)** — `@Transactional` 边界、`@Async`、自定义切面
3. **数据层 (Repository/Mapper)** — MyBatis/JPA、SQL 变更、Entity 变动
4. **异步层 (Event/Message)** — `@EventListener`、`@RabbitListener`、Kafka 等旁路逻辑

## 工具使用提示

### 从任意目录运行

所有脚本内置了路径修复（`sys.path.insert`），可以从项目根目录直接运行：
```bash
python scripts/database_query.py --db mydb --get-schema
```

### 数据库凭据

支持三种方式传入，按优先级从高到低：
1. 命令行参数：`--host localhost --db mydb --user root --password yourpass`
2. 环境变量（复制 `.env.example` 为 `.env` 后自动读取）
3. 配置文件 `~/.java-superpowers-config.json`

### Git pre-commit 钩子

自动校验提交信息格式，避免不合规的提交进入仓库：
```bash
python scripts/cicd_helper.py --pre-commit-install
```
该命令会在 `.git/hooks/pre-commit` 创建钩子脚本，每次 `git commit` 时自动执行。

## JDBC 连接参数（供 database_query 使用）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--host` | localhost | 数据库主机 |
| `--port` | 3306 | 端口 |
| `--db` | DB_NAME 环境变量 | 数据库名 |
| `--user` | root | 用户 |
| `--password` | DB_PASSWORD 环境变量 | 密码 |
| `--ssl` | false | SSL 模式 |
### 自动编译验证

变更后自动编译验证，确保 Java 代码无编译错误：
```bash
# 自动检测 Maven/Gradle 并编译
python scripts/java_compiler.py --path /path/to/project

# 指定构建工具（跳过自动检测）
python scripts/java_compiler.py --path /path/to/project --build-tool maven --verbose
```

### 静态代码分析

变更后运行代码质量检查：
```bash
# 运行所有工具（Checkstyle + PMD + SpotBugs）
python scripts/java_static_analyzer.py --path /path/to/project --summary

# 仅运行指定工具
python scripts/java_static_analyzer.py --path /path/to/project --tool checkstyle

# 保存结果为 JSON
python scripts/java_static_analyzer.py --path /path/to/project --output report.json
```

## CI/CD 流水线

GitHub PR 流程（`.github/workflows/java-superpowers-audit.yml`）：
1. Setup JDK 17 + Python
2. 自动检测 Maven/Gradle 并编译
3. 运行 JUnit 单元测试
4. 检查 Git 提交信息格式
5. 生成审计报告
6. 上传测试报告和审计结果
