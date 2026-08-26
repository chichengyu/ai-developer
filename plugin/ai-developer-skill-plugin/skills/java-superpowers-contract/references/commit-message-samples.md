# Git 提交信息规范参考

## 格式

```
<类型>(<范围>): <描述>
```

类型限定：`feat` / `fix` / `refactor` / `test` / `docs` / `chore`

## 示例

### feat（新功能）
```
feat(user): 新增用户年龄字段
feat(order): 支持按订单状态批量查询
feat(auth): 集成 OAuth2 微信登录
```

### fix（修复）
```
fix(payment): 修复金额精度溢出问题
fix(cart): 修复并发下单库存超卖
fix(mail): 修复附件中文名乱码
```

### refactor（重构，不改行为）
```
refactor(user): 抽取 UserValidator 校验逻辑
refactor(order): 统一状态机枚举定义
```

### test（测试）
```
test(user): 补充 UserService 单元测试
test(order): 添加并发下单集成测试
```

### docs（文档）
```
docs(api): 更新用户接口文档
docs(readme): 补充本地开发环境配置
```

### chore（杂项）
```
chore(deps): 升级 Spring Boot 3.2.0
chore(ci): 优化 Maven 构建缓存
```

## 规范说明

- 每个提交原子化：一个提交只做一件事
- 描述首字母小写，不要句号结尾
- 如果提交涉及数据库变更，描述中标注 `[DDL]` 前缀
- 如果提交需要回滚，在 body 中注明回滚方式

```
feat(user): 新增邮箱唯一约束 [DDL]

ALTER TABLE user ADD UNIQUE INDEX uk_email (email);
-- rollback: DROP INDEX uk_email ON user;
```
