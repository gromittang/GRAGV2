# ADR-002: NL2SQL 语义层强制查询规则

## 背景

NL2SQL 模块使用三层架构处理自然语言查询：

1. **语义层** (`semantic-layer.md`) — 业务概念到数据库表的 MUST USE 映射
2. **Embedding 搜索** — BGE 语义相似度匹配，从 7904 条 schema text 中取 top-10
3. **LLM 生成** (deepseek-chat) — 接收 prompt，生成 SQL

问题场景：用户查询"帮我查下库存大于2000的商品有哪些"：

- `semantic-layer.md` 明确指定：`MUST USE sto_stock_batch_yyyymm_org AS PRIMARY TABLE`
- Embedding 搜索返回 `sto_stock_yyyymm_org`（空表，0行），`sto_stock_batch_yyyymm_org`（正确表，2890行）排名较低
- LLM 在"业务规则优先级高"和"只能使用可用表"之间选择了后者，生成 SQL 使用空表 → 无结果

根因：语义层规则仅作为 prompt 文本参考，无程序化强制执行。prompt 内部"业务规则优先"与"只能使用可用表"自相矛盾。

## 决策

采用**双路互补**策略：

1. **代码硬执行**（本 ADR）：在 `query_agent.py` 中维护 `_HARD_RULES` 字典，手工指定需要硬保证的关键词→表名映射。当前仅 "库存" 一条规则命中时硬执行，程序化强制注入优先表到"可用表结构"，标记为 `【优先表】`

2. **spec 软辅助**（保留不变）：`semantic-layer.md` 完整内容仍注入 LLM prompt，作为其余规则的业务语义参考

### 硬执行 vs 软辅助的分界

- **硬执行**（`_HARD_RULES`）：当 embedding 搜索可能漏掉正确表，且表选择错误会导致空结果的关键规则。目前只有 "库存 → sto_stock_batch_yyyymm_org"
- **软辅助**（semantic-layer.md 文本）：其余 MUST USE 规则通过 spec_context 注入 prompt，由 LLM 自行决策

新增硬规则时，在 `_HARD_RULES` 字典中添加关键词映射即可，无需修改其他文件。

### 实现细节

- **`_HARD_RULES`**：`{"关键词": ["表名"]}` 字典，大小写不敏感子串匹配
- **匹配**：`_match_semantic_rules(question)` — 遍历检查
- **注入**：在 `query()` Step 1.6 中，从 `schema_manager.get_tables_schema_text()` 获取强制表完整 schema，以 `【优先表】` 标记前置插入 prompt
- **提示词**：更新 `SQL_GENERATION_PROMPT`，增加"表选择规则"部分，明确优先表必须优先使用

### 涉及文件

| 文件 | 改动 |
|------|------|
| `backend/app/agents/query_agent.py` | 新增 `_HARD_RULES` 字典 + `_match_semantic_rules()`，修改 `query()` 强制注入 |
| `backend/app/core/schema_manager.py` | 新增 `get_tables_schema_text()` 公开方法 |
| `backend/app/agents/prompts_sql.py` | 新增"表选择规则"说明 |
| `backend/app/core/db_mysql.py` | 新增 Decimal→float 序列化（附带修复） |

## 理由

1. **可靠性** — 代码保证优先表一定出现在"可用表结构"中，不受 embedding 排序影响，LLM 必然看到该表
2. **精准性** — 手工维护 `_HARD_RULES`，只对已验证存在 embedding→LLM 断裂风险的规则做硬执行，避免过度干预 LLM 决策
3. **兼容性** — spec 文本注入保留，LLM 仍可获得完整业务语义上下文；代码只做关键表的"存在性"保证
4. **可追溯** — `_HARD_RULES` 字典一目了然，新增规则需人工评审确认必要性

## 影响

- 查询"库存"关键词时，`sto_stock_batch_yyyymm_org` 被标记为优先表并排在"可用表结构"最前面
- "仓位"、"用户"等其他语义层规则仍走软辅助路径，不改动
- 优先表可能与其他表在 prompt 中出现两次（优先区 + 普通区），重复出现反而强化 LLM 关注
- 关键词匹配是子串包含检查（大小写不敏感），"库存盘点"等也会命中，这是预期行为
- Decimal 序列化修复（`_serialize_row()`）额外解决了 MySQL 数值类型无法 JSON 序列化的问题

## 替代方案

| 方案 | 缺点 |
|------|------|
| 纯 prompt 优化（不写硬代码） | 依赖 LLM 理解能力，deepseek-chat 不可靠 |
| 自动解析 semantic-layer.md 所有 MUST USE | 过度干预，把未经验证的规则也硬执行了 |
| spec 文件改为 JSON 配置 | 引入新格式，spec 不可读 |
| 提高 embedding top_k | 引入更多噪声表，不保证解决表选择问题 |

## 状态

已采纳。实施于 2026-06-05。

## 验证

查询"帮我查下库存大于2000的商品有哪些"：

- **修复前**：SQL 使用 `sto_stock_yyyymm_org`（空表）→ 0 条结果
- **修复后**：SQL 使用 `sto_stock_batch_yyyymm_org`（正确表）→ 46 条结果
