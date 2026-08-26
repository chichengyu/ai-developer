# 压缩模式参考
 
 本文档通过 before/after 对比展示各任务类型的标准压缩模式。
 所有示例遵循 SKILL.md 中 R1-R14 规则，**after 侧的叙述行数均控制在 R7 上限内**。

## 示例 1：单文件修改
**before (50 tokens)**
> 我看了下 UserController.java 第 42 行的代码，发现 email 校验少了个空指针判断。我来加上这个判断吧，修改如下：

**after (0 tokens, 直接给 diff)**
```diff
UserController.java:42 + if (email == null) return;
```

## 示例 2：Bug 修复
**before (80 tokens)**
> 我分析了 UserService.java 的 login 方法，发现当 password 为 null 时会抛出 NullPointerException。这是因为第 88 行调用 password.equals() 时没有判空。解决方法是在调用前加上判空处理，如果 password 为 null 则直接返回错误结果。

**after (1 line, root cause + fix)**
```
UserService.java:88 NPE when password is null → + if (password == null) return false;
```

## 示例 3：代码审查
**before (180 tokens)**
> 我对 OrderController.java 做了代码审查，发现了以下几个问题：1. 第 32 行使用了 @Autowired 字段注入，不推荐使用，建议改为构造器注入。2. 第 67 行的 createOrder 方法没有 @Transactional 注解，可能导致数据不一致。3. 第 103 行直接返回了实体对象，应该改为返回 DTO。整体来看代码质量还可以，主要是这几个小问题需要改进。

**after (3 lines, 每 issue 一行)**
```
[1] OrderController.java:32 @Autowired → 构造器注入
[2] OrderController.java:67 缺 @Transactional
[3] OrderController.java:103 返回 Entity → 应返回 DTO
```

## 示例 4：分析报告
**before (300 tokens)**
> 我对 user 表进行了全面分析。该表共有 6 个字段：id、name、email、phone、status、created_at。其中 id 是自增主键，email 有唯一索引，status 有普通索引。数据量约 12000 行，占用 2.3MB 空间。从数据质量来看，email 的 NULL 率为 5.2%，空字符串率为 0.3%，哨兵值率为 0%；phone 的 NULL 率为 68.3%，属于冗余字段；status 的哨兵值率为 12.1%，存在业务层使用 0 作为哨兵值的情况。整体质量评分 87 分。

**after (5 lines, 表格/列表)**
```
user 表 | 6 字段 | 12K 行 | 2.3MB
字段     | NULL率  | 空串率  | 哨兵率 | 评估
email    | 5.2%    | 0.3%    | 0%     | 正常
phone    | 68.3%   | 2.1%    | 0%     | 冗余字段
status   | 0%      | 0%      | 12.1%  | 哨兵值异常
质量评分: 87/100
```

## 示例 5：多文件修改
**before (120 tokens)**
> 这个需求需要在 UserController 中新增一个 getUserProfile 接口，然后在 UserService 中实现对应的业务逻辑，最后在 UserRepository 中添加对应的数据库查询方法。涉及三个文件的修改，改动如下：

**after (1 line, 概括改动范围)**
```
3 files: UserController +GET /users/{id}/profile, UserService +getUserProfile(), UserRepository +findProfileByUserId()
```

## 示例 6：架构建议
**before (200 tokens)**
> 针对当前系统架构，我建议引入 Redis 缓存层来缓解数据库压力。具体来说，可以在 Service 层和 Repository 层之间添加一个 CacheManager 抽象层，使用 Spring Cache 注解 @Cacheable 来管理热点数据的缓存。这样做的优点是：1. 减少数据库查询次数 2. 降低响应延迟 3. 通过注解方式对业务代码侵入小。需要注意的是缓存失效策略和缓存穿透问题需要额外处理。

**after (3 lines, 直接给结论)**
```
建议: Service → @Cacheable 抽象层 → Redis
+ 降低 DB 查询 60-80%, 侵入小
! 需处理: 缓存穿透/雪崩/失效策略
```

## 示例 7：教学解释
**before (350 tokens)**
> @Transactional 是 Spring 声明式事务管理的核心注解。它的工作原理是通过 AOP 代理在方法执行前后自动开启和提交/回滚事务。当方法正常返回时提交事务，当方法抛出 RuntimeException 或 Error 时回滚事务。它有几个关键属性：propagation 控制事务传播行为，默认 REQUIRED；isolation 控制隔离级别，默认数据库级别；rollbackFor 指定哪些异常触发回滚；timeout 指定超时时间。需要注意的是，@Transactional 只在被 Spring AOP 代理的外部调用时生效，同一类中的方法自调用会失效。

**after (10 lines, 结论 + 核心解释)**
```
@Transactional = AOP 代理托管事务边界
■ 正常返回 → commit | ■ 抛 RuntimeException → rollback
■ 自调用(this.method()) 失效 — 代理不拦截

关键属性:
propagation=REQUIRED(默认) | isolation=DEFAULT | rollbackFor | timeout

陷阱:
- 自调用失效 | - 方法必须是 public | - 异常被 catch 后不触发回滚
```

## 示例 8：Java 特化压缩模式

### 8.1 Spring 注解压缩
```
# before (40 tokens)
> Controller 层使用 @RestController 注解，依赖注入使用构造器方式，事务管理使用 @Transactional

# after (5 tokens)
@RestController / 构造器注入 / @Transactional
```

### 8.2 MyBatis/JPQL 引用
```
# before
> 在 UserMapper.xml 中，id 为 findActiveUsers 的查询语句需要加一个 status 条件过滤

# after
UserMapper.xml#findActiveUsers + status 条件
```

### 8.3 方法签名压缩
```
# before
> 在 UserService 接口中新增一个分页查询方法，参数是 Pageable 和 String keyword，返回值是 Page<UserDTO>

# after
UserService + Page<UserDTO> searchUsers(Pageable, String)
```

### 8.4 异常链路压缩
```
# before
> 该方法会抛出 IllegalArgumentException、DataAccessException 和 BusinessException 三种异常

# after
throws IAE | DAE | BizException
```

## 压缩效果基准

| 任务类型 | 原始 token | 压缩后 token | 压缩比 |
|---------|-----------|-------------|--------|
| 单文件修改 | 50 | 0 | 100% |
| Bug 修复 | 80 | 8 | 90% |
| 代码审查 | 180 | 35 | 81% |
| 分析报告 | 300 | 60 | 80% |
| 多文件修改 | 120 | 20 | 83% |
| 架构建议 | 200 | 40 | 80% |
| 教学解释 | 350 | 70 | 80% |
| Java 注解引用 | 40 | 5 | 88% |

## 常见反模式对照

| ❌ 反模式 | ✅ 压缩模式 |
|----------|------------|
| "我看了下代码发现…" | 直接输出 diff/结论 |
| "我来帮你修改一下吧" | 直接修改，零说明 |
| "首先、其次、最后" | 表格/列表扁平输出 |
| "该方法的优点是…" | 只留结论，跳过评价 |
| "如您所知…" | 用户已知不重复 |
| "如果您需要更多细节…" | 不主动问，等追问 |
| "整体来看，还不错" | 零评价，只给事实 |
| 完整代码块 | diff 或单行引用 |
| 段落式描述 | 表格/单行/代码 |
