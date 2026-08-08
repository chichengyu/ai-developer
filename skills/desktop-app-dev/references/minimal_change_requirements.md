# Code hard requirements (代码开发硬性要求)

Canonical implementation checklist behind the `代码开发硬性要求` section
in `SKILL.md`. These rules apply whenever this skill touches existing
code; an item may be skipped only when the user explicitly asks for the
rewrite / refactor and the waiver is recorded in requirements.md.

## CODE-01 保留可用的原有逻辑

原有功能正常且任务未要求修改时，原实现保持不变；禁止无依据的重构、
重写或顺手优化。

## CODE-02 改动范围最小

只修改任务直接涉及的代码段/文件；不调整无关格式、命名、依赖、注释或
文件。

## CODE-03 增量扩展优先

新功能优先通过新增代码或既有扩展点实现；必须修改既有接口时保留兼容
路径并记录原因。

## CODE-04 行为变更显式记录

任何改变原行为、错误处理、边界条件或外部契约的修改，在 requirements.md
和任务卡片中写明原因与验收依据。

## CODE-05 原功能回归验证

交付前运行原有测试与冒烟验证，确认旧功能未回归；验证结果列入 Step 6
报告。

## Decision rules

- 原逻辑正常且需求未要求改动：保持不动。
- 改动可通过新增代码或既有扩展点实现：不要改旧代码。
- 必须修改旧代码：diff 保持最小，并解释为什么没有更小方案。
- 用户明确要求重写/重构：先在 requirements.md 记录豁免，再执行。
- 行为变更必须引用 requirements.md 和任务卡片。
