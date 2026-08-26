# Git Worktree 隔离 .gitignore 模板

配合 java-superpowers-contract 的 git worktree 隔离方案使用。
将此文件放到 worktree 根目录，确保非 dev 环境的配置文件不会被意外提交。

```gitignore
# ============================
# 环境配置 - 只保留 dev
# ============================
src/main/resources/application-prod.yml
src/main/resources/application-staging.yml
src/main/resources/application-test.yml
src/main/resources/application-uat.yml
src/main/resources/bootstrap-prod.yml
src/main/resources/bootstrap-staging.yml

# ============================
# 密钥与凭证
# ============================
*.p12
*.jks
*.key
*.pem
*.cer
secrets/
credentials/

# ============================
# 本地运行时文件
# ============================
.env
.env.local
*.log

# ============================
# IDE 与构建缓存
# ============================
.idea/
*.iml
.vscode/
.settings/
.project
.classpath
target/
build/
*.class
```

### 使用方式

在 `git worktree add` 之后，将以上内容复制到 worktree 根目录的 `.gitignore` 中。
配合 `git sparse-checkout` 物理隔离，从文件系统层面杜绝误改生产配置。
