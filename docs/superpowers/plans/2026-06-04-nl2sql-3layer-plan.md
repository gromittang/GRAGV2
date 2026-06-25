# NL2SQL 三层查询控制 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 NL2SQL 模块运行时动态读取 `spec/nl2sql/semantic-layer.md`，使 spec 文件成为查询策略的唯一控制面板。

**Architecture:** 在 `query_agent.py` 的 Schema 检索（Step 1）和 SQL 生成（Step 2）之间插入一个 spec 读取步骤，将 `semantic-layer.md` 和 `sql-rules.md` 的内容注入 prompt。编辑 spec → 保存 → 下一条查询立即生效，无需重启。

**Tech Stack:** Python 3, FastAPI, os.path

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `spec/nl2sql/semantic-layer.md` | 修改 | 补全空白业务规则（L1） |
| `backend/app/agents/query_agent.py` | 修改 | 新增 `_load_spec_context()` + 注入逻辑（L3） |
| `spec/system.md` | 修改 | 新增 NL2SQL 规范文件路由声明（L4） |
| `CLAUDE.md` | 新建 | 项目级开发指令，声明 spec 优先级 |

---

### Task 1: 补全 `semantic-layer.md` 空白规则

**Files:**
- Modify: `spec/nl2sql/semantic-layer.md`

- [ ] **Step 1: 补全"时间 → head表"规则**

当前文件第 80-85 行，"IF question contains: 时间" 下 `Prefer to join：` 留空。找到并替换：

Old:
```
IF question contains:

- 时间

Prefer to join：
```

New:
```
IF question contains:

- 时间
- 日期
- 月份
- 某天
- 最近

Prefer tables with "_head" suffix (header tables).

Reason: Head tables contain time fields (创建时间, 审核时间, 出库时间 etc.).
Body tables (with "_body" suffix) only contain line items without time info.

When time filtering is needed:
  - Prefer joining the corresponding _head table to get time fields
  - Use head table's time fields for WHERE / GROUP BY date conditions
```

- [ ] **Step 2: 补全"配送/调拨/运输 → dispatch"规则**

当前第 88-96 行 `Expand scope: sto_dispatch_calc` 后无说明。替换：

Old:
```
IF question contains:

- 配送
- 调拨
- 运输

Expand scope:

sto_dispatch_calc
```

New:
```
IF question contains:

- 配送
- 调拨
- 运输

Expand scope to include:

sto_dispatch_calc

Reason: 配送/调拨/运输场景的数据存储在 sto_dispatch_calc 表中，
该表不与出库主表直接关联，需要显式扩展检索范围。
```

- [ ] **Step 3: Commit**

```bash
git add spec/nl2sql/semantic-layer.md
git commit -m "docs(spec): 补全 semantic-layer.md 时间/配送规则

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: 修改 `query_agent.py` — 运行时 spec 读取

**Files:**
- Modify: `backend/app/agents/query_agent.py`

- [ ] **Step 1: 在文件顶部 import 区域添加 `os` 导入**

在 `query_agent.py` 第 5 行（`from typing import Dict, Any, List, Optional`）之后插入：

```python
import os
```

- [ ] **Step 2: 在模块级添加 `_load_spec_context()` 函数**

在 `query_agent.py` 第 13 行（`from app.agents.prompts_sql import INSIGHT_GENERATION_PROMPT`）之后、第 16 行（`class QueryAgent:`）之前插入：

```python

# spec 目录路径（项目根目录下的 spec/）
_SPEC_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "spec")
)


def _load_spec_context() -> str:
    """读取 spec 业务规则文件，返回注入 prompt 的上下文字符串。

    每次查询时动态读取，编辑 spec 文件后下一个查询立即生效。
    读取失败时静默降级，返回空字符串，不影响查询正常执行。
    """
    parts = []

    semantic_path = os.path.join(_SPEC_DIR, "nl2sql", "semantic-layer.md")
    if os.path.isfile(semantic_path):
        try:
            with open(semantic_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                parts.append(content)
        except Exception:
            pass

    sql_rules_path = os.path.join(_SPEC_DIR, "business-rules", "sql-rules.md")
    if os.path.isfile(sql_rules_path):
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

- [ ] **Step 3: 在 `query()` 方法中注入 spec 上下文**

在 `query()` 方法中，第 49 行 `schema_text = schema_result.get("schema_text", "")` 和第 51 行（空行，原为 Step 2 注释前）之间插入：

```python

            # Step 1.5: 加载 spec 业务规则，注入到 schema 上下文前方
            spec_context = _load_spec_context()
            if spec_context:
                schema_text = spec_context + "【可用表结构】\n" + schema_text
```

修改后该区域的完整代码应为：

```python
            schema_text = schema_result.get("schema_text", "")

            # Step 1.5: 加载 spec 业务规则，注入到 schema 上下文前方
            spec_context = _load_spec_context()
            if spec_context:
                schema_text = spec_context + "【可用表结构】\n" + schema_text

            # Step 2: SQL生成（使用LLM）
            from app.agents.prompts_sql import SQL_GENERATION_PROMPT
```

- [ ] **Step 4: 验证 spec 路径计算正确**

在项目根目录运行：

```bash
python -c "import os; f=os.path.join('D:\\WMSRAGV2\\backend\\app\\agents'); d=os.path.normpath(os.path.join(f,'..','..','..','spec')); print(d); print(os.path.isdir(d))"
```

Expected: 打印 spec 目录路径且 `True`

- [ ] **Step 5: 验证 spec 文件可读取**

```bash
python -c "
import os
spec_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath('backend/app/agents/query_agent.py')), '..', '..', '..', 'spec'))
semantic = os.path.join(spec_dir, 'nl2sql', 'semantic-layer.md')
print('semantic-layer.md exists:', os.path.isfile(semantic))
rules = os.path.join(spec_dir, 'business-rules', 'sql-rules.md')
print('sql-rules.md exists:', os.path.isfile(rules))
"
```

Expected: 两个文件都是 `True`

- [ ] **Step 6: Commit**

```bash
git add backend/app/agents/query_agent.py
git commit -m "feat(nl2sql): 运行时动态读取 spec 文件注入 SQL 生成 prompt

查询时读取 spec/nl2sql/semantic-layer.md 和 spec/business-rules/sql-rules.md，
编辑 spec 文件后下一个查询立即生效，无需重启服务。
读取失败时静默降级，不影响查询正常执行。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: 更新 `system.md` — NL2SQL 规范路由

**Files:**
- Modify: `spec/system.md`

- [ ] **Step 1: 在 system.md 末尾追加 NL2SQL 模块规范指引**

在文件末尾追加：

```markdown

## NL2SQL 模块规范指引

NL2SQL 模块运行时遵循以下规范文件（优先级从高到低）：

1. `spec/nl2sql/semantic-layer.md` — 业务概念到数据库表的映射规则（运行时动态加载）
2. `spec/business-rules/sql-rules.md` — SQL 安全与格式约束（运行时动态加载）
3. `spec/workflows/nl2sql-workflow.md` — 完整工作流参考

开发 NL2SQL 模块时，必须以上述文件为权威参考。
修改 `semantic-layer.md` 后无需重启服务，效果即时生效。
```

- [ ] **Step 2: Commit**

```bash
git add spec/system.md
git commit -m "docs(spec): system.md 新增 NL2SQL 模块规范路由声明

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: 创建 `CLAUDE.md` — 项目级开发指令

**Files:**
- Create: `CLAUDE.md`

- [ ] **Step 1: 创建 CLAUDE.md**

在项目根目录 D:\WMSRAGV2\ 创建 `CLAUDE.md`：

```markdown
# CLAUDE.md

## Spec 文件优先级

本项目的所有开发必须遵循 `spec/` 目录下的规范文件。在修改任何模块前，先阅读对应的 spec：

| 模块 | Spec 文件 |
|------|----------|
| NL2SQL（数据查询） | `spec/nl2sql/semantic-layer.md`, `spec/business-rules/sql-rules.md`, `spec/workflows/nl2sql-workflow.md` |
| RAG（知识库） | `spec/workflows/rag-workflow.md` |
| Chat（智能问答） | `spec/workflows/chat-workflow.md` |
| PM（方案工作室） | `spec/workflows/pmstudio-workflow.md` |
| 全局 | `spec/system.md` |

## 模块路由

| 模块 | 后端入口 | 前端入口 |
|------|---------|---------|
| NL2SQL | `backend/app/agents/query_agent.py` | `frontend/vue-app/src/views/QueryPage.vue` |
| 知识库 | `backend/app/api/documents.py` | `frontend/vue-app/src/views/KnowledgePage.vue` |
| 智能问答 | `backend/app/api/chat.py` | `frontend/vue-app/src/views/ChatPage.vue` |
| PM方案 | `backend/app/api/pm_solution.py` | `frontend/vue-app/src/views/PMStudioPage.vue` |

## 关键约定

- 后端 API 前缀: `/api/v1/{module}`
- 业务代码修改后，主动询问是否需要同步更新 `spec/` 下的对应规范文档
- NL2SQL 的语义层规则（`semantic-layer.md`）在运行时动态加载，修改后无需重启
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: 创建 CLAUDE.md 项目级开发指令

声明 spec 文件优先级和模块路由，确保 Claude Code 开发时始终参考规范。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: 端到端验证

- [ ] **Step 1: 启动后端服务**

```bash
cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8812 &
```

- [ ] **Step 2: 发起测试查询**

```bash
curl -s -X POST http://localhost:8812/api/v1/query/ \
  -H "Content-Type: application/json" \
  -d '{"question": "查询最近一周的库存变动"}' | python -m json.tool
```

- [ ] **Step 3: 验证 spec 上下文已注入**

检查后端日志或添加临时日志，确认 `_load_spec_context()` 返回了非空字符串。

也可以在后端 Python 中临时验证：
```python
# 在 _load_spec_context() 返回前加 print
print(f"[NL2SQL] Loaded spec context: {len(result)} chars")
```

- [ ] **Step 4: 验证热更新**

1. 在 `semantic-layer.md` 中临时加一行：`# TEST RULE: 所有查询必须使用 sto_test_table`
2. 再次发起查询
3. 检查 LLM 生成的 SQL 是否受新规则影响
4. 删除测试行

- [ ] **Step 5: 验证静默降级**

```bash
# 临时移动 semantic-layer.md
mv spec/nl2sql/semantic-layer.md spec/nl2sql/semantic-layer.md.bak

# 发起查询，确认不 crash
curl -s -X POST http://localhost:8812/api/v1/query/ \
  -H "Content-Type: application/json" \
  -d '{"question": "查询库存"}' | python -m json.tool

# 恢复
mv spec/nl2sql/semantic-layer.md.bak spec/nl2sql/semantic-layer.md
```

Expected: 查询正常返回，不会因文件缺失而报 500 错误。

---

## 自审清单

1. **Spec 覆盖**: 设计文档 5 个改动全部覆盖 — semantic-layer.md 补全 (Task 1), query_agent.py 修改 (Task 2), system.md 更新 (Task 3), CLAUDE.md 创建 (Task 4), 验证 (Task 5)
2. **无占位符**: 所有代码和命令都是完整的，无 TBD/TODO
3. **类型一致性**: `_load_spec_context()` 返回 `str`，调用方直接拼接字符串，无类型冲突
4. **路径一致性**: `_SPEC_DIR` 使用 `os.path.abspath(__file__)` 确保不受工作目录影响
