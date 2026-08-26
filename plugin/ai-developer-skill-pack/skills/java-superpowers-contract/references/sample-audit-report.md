# 审计报告示例

```json
{
"sessionId": "019f6af8-bbab-7bf3-819f-8c4c98f990bd",
"timestamp": "2026-07-16T14:30:00+08:00",
"skills": ["java-superpowers-contract", "database-query-tool"],
"tools": ["req_analyzer", "database_query"],
"filesRead": [
"src/main/java/com/example/service/UserService.java [已有]",
"src/main/java/com/example/entity/User.java [已有]"
],
"filesModified": [
"src/main/java/com/example/entity/User.java [新增字段 age]",
"src/main/resources/db/migration/V20260716_01__add_user_age.sql [新增]"
],
"sqlExecuted": [
"ALTER TABLE user ADD COLUMN age INT DEFAULT NULL COMMENT '年龄' -- rollback: ALTER TABLE user DROP COLUMN age;"
],
"riskAssessment": [
"事务: UserService.registerUser() 含 @Transactional, 新增字段不影响现有事务边界",
"异步: 无 @Async 或事件监听器涉及 user 表",
"测试: UserServiceTest 需补充 age 字段断言"
]
}
```

## Markdown 格式

```markdown
## 执行审计
- Session: 019f6af8-bbab-7bf3-819f-8c4c98f990bd
- 技能: java-superpowers-contract, database-query-tool
- 工具: req_analyzer, database_query
- 读取文件: UserService.java [已有], User.java [已有]
- 修改文件: User.java [新增字段 age], V20260716_01__add_user_age.sql [新增]
- SQL: ALTER TABLE user ADD COLUMN age INT ... [回滚已就绪]
- 风险: 测试需补充断言, 无事务/异步影响
```

## HTML 格式

用 `audit_report_generator.py --input audit.json --format html` 生成含样式的独立 HTML。
