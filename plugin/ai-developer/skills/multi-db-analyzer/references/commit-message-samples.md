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
