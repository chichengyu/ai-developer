# 审计报告示例

## 示例输出（Markdown）

```markdown
# 执行审计报告: 数据质量审计 - user

- **会话ID**: session_20260716_120000
- **时间戳**: 2026-07-16T12:00:00

## 1. 技能与工具调用

### 加载的技能
 - multi-db-analyzer [已有]
- multi-db-analyzer [已有]

### 调用的工具
- `DatabaseQuery`
- `SkillBridge`

## 2. 数据质量三指标分析

| 表名 | 字段 | NULL率 | 空字符串率 | 哨兵值率 | 质量分 | 警告 |
|------|------|--------|-----------|----------|--------|------|
| user | email | 2.34% | 1.56% | 0.00% | 0.98 | 正常 |
| user | phone | 35.12% | 2.30% | 0.00% | 0.85 | NULL率(35.1%)偏高: 建议补充默认值 |

## 3. 统计摘要

- **技能数**: 2
- **工具数**: 2
- **质量异常**: 1
```

## 数据质量三指标

1. **NULL率**: 字段为 NULL 的比例。>80% 说明剩余字段可能存在冗余
2. **空字符串率**: 字段为空字符串的比例。>30% 说明字段设计可能存在问题
3. **哨兵值率**: 使用特殊值（0, -1, 1900-01-01, 1970-01-01, 9999-12-31）代替 NULL 的比例。>10% 说明业务层可能使用了哨兵值

质量评分 = 1.0 - (NULL率 * 0.4 + 空字符串率 * 0.3 + 哨兵值率 * 0.3)
*** Add File: C:\Users\admin\.codex\skills\multi-db-analyzer\references\commit-message-samples.md
# Git 提交信息规范

## 格式

```
<type>(<scope>): <subject>

<body>
```

## Type 类型

| 类型 | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修复 |
| `refactor` | 重构（非功能/修复）|
| `perf` | 性能优化 |
| `style` | 代码格式（非逻辑变动）|
| `test` | 测试相关 |
| `docs` | 文档相关 |
| `chore` | 构建/工具/依赖 |
| `db` | 数据库变更 |

## 示例

```
feat(user): 新增年龄字段，支持按年龄分组统计

- user 表新增 age 字段 (INT DEFAULT NULL COMMENT '年龄')
- 新增 UserService.getAgeDistribution() 方法
- 新增 GET /api/users/age-distribution 接口
- 新增单元测试覆盖年龄统计逻辑

DB: ALTER TABLE user ADD COLUMN age INT DEFAULT NULL COMMENT '年龄';
Rollback: ALTER TABLE user DROP COLUMN age;
```

```
fix(order): 修复订单状态查询索引失效问题

- order 表 status 字段添加索引 idx_order_status
- 修复状态查询全表扫描问题

DB: CREATE INDEX idx_order_status ON `order`(status);
Rollback: DROP INDEX idx_order_status ON `order`;
```

```
refactor(payment): 抽离支付网关调用为独立策略模式

- 提取 PaymentStrategy 接口
- 实现 AlipayStrategy / WechatPayStrategy
- 保持原业务接口不变
```
*** Add File: C:\Users\admin\.codex\skills\multi-db-analyzer\references\gitignore-template.md
# Java 项目 .gitignore 模板

```gitignore
# Compiled class file
*.class

# Maven
target/
*.war
*.jar
*.zip
*.tar.gz

# Gradle
.gradle/
build/

# IDE
.idea/
*.iml
.vscode/
*.swp
*.swo
*~
.project
.classpath
.settings/

# OS
Thumbs.db
.DS_Store

# Logs
*.log
logs/

# Env
.env
application-local.yml
application-local.properties

# DB
*.db
*.sqlite

# Temp
tmp/
temp/
*.tmp
```
*** Add File: C:\Users\admin\.codex\skills\multi-db-analyzer\references\quality-metrics-guide.md
# 数据质量三指标评估指南

## 指标定义

### 1. NULL 率
字段为 NULL 的记录占总记录数的比例。

- **正常**: < 20%
- **偏高**: 20% - 80%
- **过高**: > 80%（字段可能冗余）

### 2. 空字符串率
字段为空字符串（''）的记录占非 NULL 记录的比例。

- **正常**: < 10%
- **偏高**: 10% - 30%
- **过高**: > 30%（字段设计可能存在问题）

### 3. 哨兵值率
使用哨兵值（0, -1, 1900-01-01, 1970-01-01, 9999-12-31, -9999 等）代替 NULL 的比例。

- **正常**: < 5%
- **偏高**: 5% - 10%
- **异常**: > 10%（业务层可能使用了哨兵值替代 NULL）

## 质量评分

```
质量评分 = 1.0 - (NULL率 * 0.4 + 空字符串率 * 0.3 + 哨兵值率 * 0.3)
```

- **>= 0.9**: 优秀
- **0.7 - 0.9**: 良好
- **0.5 - 0.7**: 需关注
- **< 0.5**: 需整改

## 使用方式

```bash
# 单表分析（含质量评分）
python scripts/database_query.py --db mydb --analyze-table user

# 批量审计（配合 skill_bridge）
python scripts/skill_bridge.py --db mydb --tables user order payment --audit-format html
```
