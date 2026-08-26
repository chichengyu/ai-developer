# Legacy agent manifest fields
The original `agents/openai.yaml` for this skill contained extra fields that the current Codex plugin-creator schema does not accept (`input_schema`, `triggers`, `output_example`). They are preserved here verbatim so the information stays available inside the bundled skill even after the schema cleanup. The active agent manifest in this directory keeps only the schema-allowed fields.
## input_schema
```yaml
input_schema:
  type: object
  required:
    - mode
    - risk_level
  properties:
    mode:
      type: string
      description: "工作模式：analyze（仅分析）/ code（编码落地）/ audit（审计汇报）"
      enum: [analyze, code, audit]
    risk_level:
      type: string
      description: "变更风险等级：high / low"
      enum: [high, low]
    project_path:
      type: string
      description: "Java 项目根路径（编译验证和分析时必需）"
    build_tool:
      type: string
      description: "构建工具: maven / gradle（自动检测）"
      enum: [maven, gradle]
```
## triggers
```yaml
triggers:
  keywords: ["Java", "Mapper", "Controller", "Service", "SQL", "DDL", "事务", "回滚", "审计"]
  file_patterns: ["*.java", "*.xml", "*.sql", "application-*.yml"]
```
## output_example
```yaml
output_example:
  markdown: |
    ## 1. 业务逻辑与调用链路分析
    ## 2. 潜在副作用与风险评估
    ## 3. 详细文件级改造步骤
    🔄【执行审计】- 技能：[名称] | 工具：[名称] | 读取文件：[路径]
```
