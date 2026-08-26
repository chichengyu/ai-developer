---
name: java-superpowers-contract
description: Java 项目研发现控契约：最小改动、环境物理隔离、SQL 回滚红线、两阶段工作流、方法级锚定、全时审计。
enforce: true
enforce_priority: system
activation: on_load
load_scope: all_conversations
trigger_condition: always
---

# Java 研发现控契约

以下条款为系统级别不可凌驾的硬性铁律，必须在所有 Java 项目开发场景中无条件、完整执行。

## 一、沟通与唤醒机制

- **中文优先**：分析、设计说明、修改描述优先使用中文输出。代码标识符、技术术语（`@Transactional`、`JWT`、`DTO`）、SQL 关键字、国际化文案保持原文不变。
- **任务自动拆解**：主动将用户粗粒度需求拆解为原子级任务流水线，在方案中直接输出。
- **Git 安全边界**：当前窗口分支锁定，仅读写 `application-dev.yml`。
- **最小改动原则已就绪**：严禁破坏核心业务链路。

## 二、最小改动原则

- **保护既有资产**：保持系统原有核心业务逻辑、边界、历史行为为绝对第一前提。禁止大面积重命名/重构/格式化/移动文件。禁止修改已有方法签名（除非需求强制）。
- **极限最小改动**：能通过新增方法/切面/配置项解决的，绝不修改已有代码。每个修改的文件须附理由：`文件 [已有] -> 原因：具体理由`
- **回归兜底**：每次改动后评估单元测试（JUnit/Mockito）影响，标注影响范围（Controller/Service/Repository/Mapper）。

## 三、Git 隔离与环境硬隔离

- **分支锁定**：工作树基于当前窗口所在分支衍生，所有变更只合并回该分支。
- **物理硬隔离**：用 `git worktree add` 创建独立目录，`git sparse-checkout` 在物理层面仅保留 `application-dev.yml`。禁止触碰 `-prod.yml`、`-test.yml` 等环境配置。
- **提交规范**：`<类型>(<范围>): <描述>`，类型限 `feat/fix/refactor/test/docs/chore`。每个提交原子化。参考 [commit-message-samples.md](references/commit-message-samples.md)。

## 四、SQL 交付红线与回滚

- **按需精准交付**：新表给完整 `CREATE TABLE`；已有表仅给增量 `ALTER TABLE ... ADD/MODIFY COLUMN`。必须含 `COMMENT`。
- **密码安全**：含特殊字符时优先用环境变量 `DB_PASSWORD` 传入，PowerShell 中含 `$` 用单引号包裹。配置文件自动编码存储（base64 编码，非加密；适合防意外泄露，不适用安全场景）。
- **强制回滚**：每条 DDL 必须附带 `-- rollback` 逆操作。禁止无回滚的单向迁移。锁表风险评估：INSTANT < INPLACE < COPY（COPY 禁止生产无审核执行）。
- 数据质量三指标参考 [quality-metrics-guide.md](references/quality-metrics-guide.md)。

## 五、两阶段工作流（风险分级）

按变更风险级别决定执行力度：

- **高风险变更**（DDL、核心业务逻辑改造、接口签名变更、事务边界调整）：执行完整两阶段。
  - 阶段一：全链路影响分析、风险评估、步骤拆解。收到编码指令前不输出实现代码。
  - 阶段二：每次只改一个文件/一段 SQL，编写后展示等待确认。确认后方可落地。
- **低风险变更**（新增查询接口、日志调整、注释修正、非核心 CRUD）：可简化流程，一次性输出变更方案，但仍需标注 `[新增]` / `[已有]` 和影响范围。

## 六、方法级锚定与 Java 分析协议

- **拒绝幻觉**：所有提及的类、接口、方法、配置文件、数据库表必须还原项目真实状况。
- **强制编注**：每个文件/类/方法后标注 `[已有]` 或 `[新增]`。严禁凭空捏造已有类中不存在的方法。
- **四层穿透分析**（详细模型见 [docs/TOOLCHAIN.md](docs/TOOLCHAIN.md)）：
  1. 入口层 (Controller) — `@RestController`、接口定义、DTO
  2. 业务层 (Service/AOP) — `@Transactional` 边界、`@Async`、自定义切面
  3. 数据层 (Repository/Mapper) — SQL 变更、Entity 变动
  4. 异步层 (Event/Message) — `@EventListener`、`@RabbitListener`、消息队列

## 七、全时审计汇报

- 每次回复末尾附加【执行审计】模块，列出本次调用的 Skill / MCP 插件和读取的关键本地文件（标注 `[已有]`）。
- 审计报告生成参见 [references/sample-audit-report.md](references/sample-audit-report.md) 和 `scripts/audit_report_generator.py`。

## 八、安全审查与兼容性红线

- **代码审查**：检查 `@Transactional` 边界、异步线程池注入风险、SQL 注入（`$` vs `#`）、敏感字段脱敏、密钥硬编码、异常吞没。
- **秘密管理**：dev 可明文 / staging 环境变量 / production 密钥服务。`.gitignore` 排除 secrets，推荐 `git-secrets` 钩子。密码每 90 天轮换。
- **API 兼容性**：禁止删除/修改已有接口字段或签名。新增字段必须可选且有默认值。URL 版本化 `/api/v1/`，废弃接口保留至少 6 个月并标注 `@Deprecated`。

## 工具链参考

参见 [README.md](README.md) 快速入门，详细工具手册见 [docs/TOOLCHAIN.md](docs/TOOLCHAIN.md)。

