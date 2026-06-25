# 数据库规则 (NL2SQL)

## SQL安全规则

| 规则 | 说明 |
|------|------|
| 仅SELECT | 禁止 INSERT/UPDATE/DELETE/DROP/TRUNCATE/ALTER/CREATE |
| 禁止SELECT* | 必须指定具体字段 |
| 强制LIMIT | 最大100条，聚合查询除外 |
| 时间格式 | YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS |

## Schema匹配规则

- 语义搜索: Embedding相似度
- 自动匹配相似表名
- 未找到表时返回错误

## 数据转换规则

| MySQL类型 | 输出类型 |
|------|------|
| DECIMAL | float |
| bytes | string |

## 错误处理

| 场景 | HTTP | 说明 |
|------|------|------|
| 无相关表 | 400 | 无法找到相关数据库表 |
| SQL校验失败 | 400 | 安全检查拒绝 |
| 执行失败 | 400 | MySQL错误 |