# NL2SQL 三层查询控制 + Spec 索引 设计文档

> **日期**: 2026-06-04
> **状态**: 待审查
> **负责模块**: `backend/app/agents/`

---

## 1. 问题陈述

当前 NL2SQL 模块的查询策略（表选择、业务规则）分散在两处：
- `backend/app/agents/prompts_sql.py`：硬编码的 SQL_GENERATION_PROMPT，含 6 条通用规则
- `spec/nl2sql/semantic-layer.md`：业务表映射规则，但**没有被任何代码读取**

改规则需要同时改 spec 和代码，spec 形同虚设。目标：让 spec 成为唯一真相源。

---

## 2. 架构设计

### 2.1 三层模型

| 层级 | 载体 | 作用 | 加载时机 |
|------|------|------|----------|
| **L1** | `spec/nl2sql/semantic-layer.md` | 业务表映射规则（自然语言 Markdown） | 维护者编写 |
| **L3** | `backend/app/agents/query_agent.py` | 运行时动态读取 L1 文件，注入 SQL_GENERATION_PROMPT | 每次查询 |
| **L4** | `spec/system.md` | 声明 NL2SQL 模块的规范文件优先级 | 开发者参考 |

L2（代码强制执行）暂不实施，后续根据 LLM 行为决定是否加入。

### 2.2 运行时数据流

```
用户提问 → query_agent.py
              │
              ├─ Step 1: SchemaManager.search_relevant_schema()
              │          → schema_text
              │
              ├─ [新增] Step 1.5: _load_spec_context()
              │    ├── open("spec/nl2sql/semantic-layer.md").read()
              │    ├── open("spec/business-rules/sql-rules.md").read()
              │    └── 返回包裹了标记的规范文本
              │
              ├─ schema_text = spec_context + "\n" + schema_text
              │
              └─ Step 2-5: 不变
```

### 2.3 开发时上下文

```
Claude Code 会话
  ├── codebase-memory MCP: 索引 spec/ 文件夹
  └── CLAUDE.md: 声明 spec 文件优先级
```

---

## 3. 详细改动

### 3.1 `query_agent.py` — 运行时 spec 读取

**位置**: 第 49 行 (`schema_text` 提取) 和第 52 行 (prompt 拼接) 之间

**新增函数**:

```python
import os

SPEC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "spec")

def _load_spec_context() -> str:
    """读取 spec 业务规则，注入到 SQL 生成提示词中"""
    parts = []

    semantic_path = os.path.join(SPEC_DIR, "nl2sql", "semantic-layer.md")
    if os.path.exists(semantic_path):
        try:
            with open(semantic_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                parts.append(content)
        except Exception:
            pass  # 静默降级：读取失败不影响查询

    sql_rules_path = os.path.join(SPEC_DIR, "business-rules", "sql-rules.md")
    if os.path.exists(sql_rules_path):
        try:
            with open(sql_rules_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                parts.append(content)
        except Exception:
            pass

    if not parts:
        return ""

    return "【业务规则 - 优先级高于表结构】\n\n" + "\n\n".join(parts) + "\n\n"
```

**注入方式**:

```python
# 在 query() 方法中，schema_text 提取后：
spec_context = _load_spec_context()
schema_text = spec_context + "【可用表结构】\n" + schema_text
```

### 3.2 `spec/nl2sql/semantic-layer.md` — 补全空白规则

当前文件中"IF question contains: 时间"和"配送/调拨/运输"规则留白，需补全。保持自然语言风格。

### 3.3 `spec/system.md` — 新增 NL2SQL 路由声明

在现有内容末尾添加：

```markdown
## NL2SQL 模块规范指引

NL2SQL 模块运行时遵循以下规范文件（优先级从高到低）：

1. `spec/nl2sql/semantic-layer.md` — 业务概念到数据库表的映射规则
2. `spec/business-rules/sql-rules.md` — SQL 安全与格式约束
3. `spec/workflows/nl2sql-workflow.md` — 完整工作流参考

开发 NL2SQL 模块时，必须以上述文件为权威参考。
```

### 3.4 `CLAUDE.md` — 新建项目级指令

声明开发时 Claude Code 的行为：

```markdown
# CLAUDE.md

## Spec 文件优先级

本项目的所有开发必须遵循 `spec/` 目录下的规范文件。在修改任何模块前，先阅读对应的 spec：

- NL2SQL: `spec/nl2sql/semantic-layer.md`, `spec/business-rules/sql-rules.md`
- RAG/知识库: `spec/workflows/rag-workflow.md`
- 智能问答: `spec/workflows/chat-workflow.md`
- PM方案: `spec/workflows/pmstudio-workflow.md`

## 模块路由

| 模块 | 后端路由 | 前端页面 |
|------|---------|---------|
| NL2SQL | `backend/app/agents/query_agent.py` | `frontend/src/views/QueryPage.vue` |
| 知识库 | `backend/app/api/documents.py` | `frontend/src/views/KnowledgePage.vue` |
| 智能问答 | `backend/app/api/chat.py` | `frontend/src/views/ChatPage.vue` |
| PM方案 | `backend/app/api/pm_solution.py` | `frontend/src/views/PMStudioPage.vue` |
```

### 3.5 确认 `.mcp.json` 配置

已有的 codebase-memory MCP 配置保持不变。如果 `codebase-memory-mcp.exe` 无法正常工作（当前文件类型异常），需排查或替换。

---

## 4. 验证方案

1. **运行时 spec 读取**: 修改 `semantic-layer.md` 添加临时规则，发起查询，确认 prompt 中包含新规则
2. **静默降级**: 临时重命名 `semantic-layer.md`，发起查询，确认查询正常执行（无 crash）
3. **热更新**: 修改 spec 文件后不重启服务，发起查询，确认立即生效
4. **开发时索引**: 确认 Claude Code 会话中能引用 spec 文件内容

---

## 5. 关键文件索引

| 文件 | 改动类型 |
|------|----------|
| `backend/app/agents/query_agent.py` | 修改：新增 `_load_spec_context()`，在 query() 中注入 |
| `spec/nl2sql/semantic-layer.md` | 修改：补全空白规则 |
| `spec/system.md` | 修改：新增 NL2SQL 路由声明 |
| `CLAUDE.md` | 新建：项目级开发指令 |
| `spec/business-rules/sql-rules.md` | 仅读取，不修改 |
