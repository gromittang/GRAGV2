# Phase 1 实施计划与变更清单

> **状态**: 施工任务书 — 审核后可直接进入编码
> **基线文档**:
> - `docs/superpowers/plans/2026-06-24-mcp-migration-analysis.md`
> - `docs/superpowers/plans/2026-06-24-data-query-convergence-design.md`
> - `docs/superpowers/plans/2026-06-24-gateway-phase0-design.md`
> **约束**: 不写代码，不进入实现，输出可直接执行的施工任务书

---

## 1. Phase 1 实施目标（重新确认）

### 1.1 允许做的

| # | 事项 | 说明 |
|---|------|------|
| ✅ | 新建 `DataQueryGateway` 骨架 | `core/data_query_gateway.py`，含 `execute()`、`_execute_with_fallback()`、`_post_process()` |
| ✅ | 新建 `UnifiedQueryResult` 基础结构 | Phase 1 最小字段集（见 3.2） |
| ✅ | 实现 `LocalExecutor` | 适配 `graph_nl2sql`，包裹现有 `ainvoke()` 调用 |
| ✅ | 实现 `QueryAgentExecutor` | 适配 `query_agent`，包裹现有 `query()` 调用 |
| ✅ | `QueryService.natural_query()` 改为调用 Gateway | 退化为薄适配器 |
| ✅ | `_translate_columns()` / `_save_history()` 收口到 Gateway 后处理 | 从 QueryService 迁移到 Gateway |
| ✅ | 删除 `use_langgraph` flag | 从 `config.py` 移除，Gateway 的 executor 优先级替代 |
| ✅ | `dispatch_to_nl2sql` 退化为 Gateway 适配器 | 函数保留但内部委托给 Gateway，不包含业务逻辑 |
| ✅ | `orchestrator.py` 的 NL2SQL 调用改为走 Gateway | 通过 dispatch 适配器间接调用 |

### 1.2 不允许做的

| # | 事项 | 原因 |
|---|------|------|
| ❌ | 不接 MCP | Phase 2 范围 |
| ❌ | 不新建 `graph_mcp.py` | Phase 2 范围 |
| ❌ | 不新建 `core/mcp_client.py` | Phase 2 范围 |
| ❌ | 不实现 CircuitBreaker | Phase 3 范围（MCP 接入后才有意义） |
| ❌ | 不实现完整 Clarification Policy | Phase 3 范围 |
| ❌ | 不修改 `QueryAgent` 内部逻辑 | 只加 `@deprecated` 标记 + 适配器包裹 |
| ❌ | 不重写 `graph_nl2sql` 内部逻辑 | 只通过 `LocalExecutor` 适配调用 |
| ❌ | 不做前端 source 展示改造 | Phase 4 范围 |
| ❌ | 不做复杂 Tool 选择 / 策略优化 | Phase 2+ 范围 |
| ❌ | 不修改 `executor.py` | 通过保持 DISPATCH_MAP 兼容避免改动 |

---

## 2. 文件级改造清单

### 2.1 新增文件

| 文件 | 说明 | 预估行数 |
|------|------|---------|
| `backend/app/core/data_query_gateway.py` | Gateway 骨架 + LocalExecutor + QueryAgentExecutor + UnifiedQueryResult | ~250 行 |

### 2.2 修改文件

#### 2.2.1 `backend/app/services/query_service.py`

| 变更 | 说明 |
|------|------|
| **删除** `natural_query()` 中的 `use_langgraph` 分支逻辑（第 48-54 行） | 替换为 `gateway.execute(question)` 调用 |
| **删除** `_query_via_langgraph()` 方法（第 93-131 行） | 逻辑迁移到 Gateway 的 `LocalExecutor` |
| **删除** `_translate_columns()` 方法（第 70-91 行） | 迁移到 Gateway 的 `_post_process()` |
| **删除** `_save_history()` 方法（第 189 行起） | 迁移到 Gateway 的 `_post_process()` |
| **保留** `natural_query()` 方法签名 | 退化为薄适配器：调 Gateway → 格式化 HTTP 响应 |
| **保留** `execute_sql()` 方法 | 不经过 Gateway（直接 SQL 执行，非 NL 查询） |
| **保留** `get_schema()` / `preview_table()` / `test_connection()` | Schema 管理操作，不属于 NL 查询 |
| **保留** `generate_insight()` / `search_schema()` / `get_table_fields()` | 辅助方法，保持原位 |
| **保留** `get_query_service()` 单例工厂 | 改为内部持有 Gateway 引用 |

**改造后 `natural_query()` 伪代码**:
```text
async def natural_query(self, question: str) -> Dict:
    gateway = get_gateway()
    result = await gateway.execute(question, self._session_id)
    # 将 UnifiedQueryResult 映射为现有 API 响应格式
    return {
        "success": result.success,
        "sql": result.sql or "",
        "results": result.rows,
        "columns": result.columns,
        "total": result.total,
        "insight": result.insight,
        "tables_used": ...,
        "confidence": result.confidence,
        "explanation": ...,
        "question": result.question,
        "session_id": self._session_id,
        "history_id": ...,
        "source": result.source,  # 新增字段
    }
```

#### 2.2.2 `backend/app/orchestrator/dispatch.py`

| 变更 | 说明 |
|------|------|
| **修改** `dispatch_to_nl2sql()` | 退化为 Gateway 适配器：内部调用 `gateway.execute()` → 映射为 `{sql, data, insight}` |
| **保留** `dispatch_to_rag()` | 不变 |
| **保留** `dispatch_to_pm()` | 不变 |
| **保留** `DISPATCH_MAP` | `"nl2sql"` 仍指向修改后的 `dispatch_to_nl2sql`（适配器） |

**改造后 `dispatch_to_nl2sql()` 伪代码**:
```text
async def dispatch_to_nl2sql(query: str) -> dict:
    from app.core.data_query_gateway import get_gateway
    gateway = get_gateway()
    result = await gateway.execute(query)
    if not result.success:
        raise RuntimeError(result.error_message or "NL2SQL 查询失败")
    return {
        "sql": result.sql or "",
        "data": {"columns": result.columns, "rows": result.rows, "total": result.total},
        "insight": result.insight,
    }
```

> **关键**: `dispatch_to_nl2sql` 函数名和返回格式不变 → `orchestrator.py` 和 `executor.py` 无需修改。

#### 2.2.3 `backend/app/core/config.py`

| 变更 | 说明 |
|------|------|
| **删除** `use_langgraph: bool = False` | Gateway 的 executor 优先级链替代了此 flag |

检查是否还有其他地方引用 `settings.use_langgraph`：
- `query_service.py` — 随本次改造删除
- 其他模块 — grep 确认无引用后安全删除

#### 2.2.4 `backend/app/agents/query_agent.py`

| 变更 | 说明 |
|------|------|
| **添加** `@deprecated` 标记 | 在类/模块文档字符串中注明 `@deprecated: 自 Phase 1 起由 DataQueryGateway 管理，QueryAgentExecutor 作为受限兜底` |
| **不修改** 任何内部逻辑 | 5 步管线、HARD_RULES、方法签名全部保持不动 |

#### 2.2.5 `backend/app/agents/graph_nl2sql.py`

| 变更 | 说明 |
|------|------|
| **不修改** 内部逻辑 | 6 个节点函数、`build_query_graph()`、`get_query_graph()` 全部保持不动 |
| **不修改** `ainvoke()` 调用方式 | LocalExecutor 通过 `graph.ainvoke({"question": ..., "user_context": {}})` 调用 |

#### 2.2.6 `backend/app/api/query.py`

| 变更 | 说明 |
|------|------|
| **不修改** 端点签名 | 所有 `@router.post("/")` 等端点保持不变 |
| **不修改** 请求/响应模型 | `QueryRequest`、返回格式保持不变 |
| **可能修改** 响应中新增 `source` 字段（可选） | 前端先不消费 |

#### 2.2.7 `backend/app/api/orchestrator.py`

| 变更 | 说明 |
|------|------|
| **不修改** | `dispatch_to_nl2sql()` 保持兼容，`orchestrator.py` 无需改动 |

#### 2.2.8 `backend/app/orchestrator/executor.py`

| 变更 | 说明 |
|------|------|
| **不修改** | `DISPATCH_MAP["nl2sql"]` 指向适配器，`executor.py` 无需改动 |

#### 2.2.9 `.env.example`

| 变更 | 说明 |
|------|------|
| **删除** `USE_LANGGRAPH` 相关行 | 如有 |

#### 2.2.10 测试文件

| 文件 | 变更 | 说明 |
|------|------|------|
| `backend/tests/test_gateway.py` | **新增** | Gateway/Executor 单元测试（见第 6 节） |
| `backend/tests/test_orchestrator_l2.py` | **修改** | 确认 L2 测试仍通过（dispatch 适配器兼容） |
| `backend/tests/test_orchestrator_router.py` | **不修改** | 单元测试不依赖 dispatch 实现细节 |

### 2.3 不变文件清单（确认不碰）

| 文件 | 原因 |
|------|------|
| `backend/app/core/schema_manager.py` | 被 LocalExecutor 使用，接口不变 |
| `backend/app/core/domain_classifier.py` | 被 LocalExecutor 使用，接口不变 |
| `backend/app/core/semantic_layer_loader.py` | 被 LocalExecutor 使用，接口不变 |
| `backend/app/core/semantic_rules.py` | 被 LocalExecutor 使用，接口不变 |
| `backend/app/core/sql_post_process.py` | 被 LocalExecutor 使用，接口不变 |
| `backend/app/core/db_mysql.py` | 被 LocalExecutor 使用，接口不变 |
| `backend/app/core/llm_manager.py` | 被各 Executor 使用，接口不变 |
| `backend/app/core/embedding.py` | 被 SchemaManager 使用，接口不变 |
| `backend/app/core/tracing.py` | Phase 4 扩展，Phase 1 不动 |
| `backend/app/agents/prompts_sql.py` | 被 LocalExecutor 使用，接口不变 |
| `backend/app/agents/tools_sql.py` | 被 LocalExecutor 使用，接口不变 |
| `backend/app/orchestrator/router.py` | 意图路由不变 |
| `backend/app/orchestrator/planner.py` | 仍然通过 DISPATCH_MAP 调用 nl2sql |
| `backend/app/models/query_history.py` | 被 Gateway `_post_process()` 调用 |
| `backend/app/models/query_feedback.py` | 不变 |
| 所有前端文件 | Phase 4 范围 |

---

## 3. Gateway 最小骨架设计（面向 Phase 1）

### 3.1 文件结构

```text
backend/app/core/data_query_gateway.py

class UnifiedQueryResult:
    """Phase 1 最小字段集"""
    # ... 见 3.2

class DataQueryExecutor(Protocol):
    """执行器接口（Phase 1: 鸭子类型，不强制 ABC）"""
    name: str
    priority: int
    async def execute(question: str, context: dict) -> RawQueryResult: ...
    async def is_available() -> bool: ...

class LocalExecutor:
    """适配 graph_nl2sql"""
    name = "local"
    priority = 1

class QueryAgentExecutor:
    """适配 query_agent"""
    name = "queryagent"
    priority = 2

class DataQueryGateway:
    """数据查询唯一入口"""

    # 公开方法
    async def execute(self, question: str, session_id: str = None) -> UnifiedQueryResult:
        ...

    # 内部方法
    def __init__(self): ...
    async def _execute_with_fallback(self, question: str, context: dict) -> RawQueryResult: ...
    async def _post_process(self, raw: RawQueryResult, question: str, session_id: str) -> UnifiedQueryResult: ...
    def _translate_columns(self, columns: list[str]) -> list[str]: ...
    async def _save_history(self, question: str, result: UnifiedQueryResult, session_id: str) -> int: ...
    async def _generate_insight(self, question: str, rows: list, columns: list) -> dict: ...

# 单例
def get_gateway() -> DataQueryGateway: ...
```

### 3.2 UnifiedQueryResult — Phase 1 最小字段集

| 字段 | Phase 1 状态 | 说明 |
|------|:----------:|------|
| `success` | **必须** | Phase 1 核心字段 |
| `source` | **必须** | `"local"` 或 `"queryagent"`（Phase 1 无 MCP） |
| `query_mode` | **必须** | `"sql"` 或 `"fallback"` |
| `question` | **必须** | 用户原始问题 |
| `normalized_question` | **stub** | Phase 1 填 `None`，Phase 3 实现 |
| `sql` | **必须** | 执行的 SQL |
| `tool_calls` | **stub** | Phase 1 填 `None`，Phase 2 MCP 接入后启用 |
| `columns` | **必须** | 已翻译为中文的列名 |
| `rows` | **必须** | 二维数组 |
| `total` | **必须** | 行数 |
| `insight` | **必须** | Phase 1 复用现有 `INSIGHT_GENERATION_PROMPT` |
| `confidence` | **必须** | 从 Executor 透传 |
| `clarification_needed` | **stub** | Phase 1 填 `False`，Phase 3 实现 |
| `clarification_question` | **stub** | Phase 1 填 `None` |
| `error_code` | **必须** | Phase 1 最小错误码（见 4.2） |
| `error_message` | **必须** | 用户可见的错误描述 |
| `trace_id` | **必须** | 从 `get_logger()` 获取当前 trace_id |
| `latency_ms` | **必须** | `time.perf_counter()` 计算 |

### 3.3 LocalExecutor 适配方式

**策略: 包裹现有调用，不重写内部逻辑。**

```text
class LocalExecutor:
    name = "local"
    priority = 1

    async def execute(question: str, context: dict) -> RawQueryResult:
        // 1. 获取现有的 graph_nl2sql 实例
        from app.agents.graph_nl2sql import get_query_graph
        graph = get_query_graph()

        // 2. 调用现有 ainvoke()，方式与 dispatch_to_nl2sql 完全一致
        raw = await graph.ainvoke({
            "question": question,
            "user_context": context.get("user_context", {}),
        })

        // 3. 将 graph_nl2sql 的返回格式映射为 RawQueryResult
        return RawQueryResult(
            success=raw.get("success", True),
            source="local",
            query_mode="sql",
            columns=raw.get("columns", []),           // 英文原始列名
            rows=raw.get("results", raw.get("rows", [])),
            total=raw.get("total", 0),
            sql=raw.get("sql"),
            confidence=raw.get("confidence"),
            insight=raw.get("insight"),
            clarification_needed=False,               // Phase 1 stub
            error_code=None if raw.get("success", True) else "sql_execution_error",
            error_message=raw.get("error"),
            is_retryable=_is_retryable_error(raw),    // 见第 4 节
            latency_ms=0,                              // Gateway 层统一计算
        )

    async def is_available() -> bool:
        return True  // Phase 1: LocalExecutor 始终可用
```

**关键**: `graph.ainvoke()` 的调用方式和参数与现有 `dispatch_to_nl2sql()` 完全一致（见 `dispatch.py` 第 31-45 行）。唯一区别是返回值的映射。

### 3.4 QueryAgentExecutor 适配方式

**策略: 包裹现有调用，不重写内部逻辑。**

```text
class QueryAgentExecutor:
    name = "queryagent"
    priority = 2

    async def execute(question: str, context: dict) -> RawQueryResult:
        // 1. 获取现有的 QueryAgent 实例
        from app.agents.query_agent import get_query_agent
        session_id = context.get("session_id", "default")
        agent = get_query_agent(session_id)

        // 2. 调用现有 query()，方式与 QueryService 完全一致
        raw = await agent.query(question)

        // 3. 映射为 RawQueryResult（格式同 LocalExecutor）
        return RawQueryResult(
            success=raw.get("success", True),
            source="queryagent",
            query_mode="fallback",
            columns=raw.get("columns", []),
            rows=raw.get("results", raw.get("rows", [])),
            total=raw.get("total", 0),
            sql=raw.get("sql"),
            confidence=raw.get("confidence"),
            insight=raw.get("insight"),
            clarification_needed=False,
            error_code=None if raw.get("success", True) else "sql_execution_error",
            error_message=raw.get("error"),
            is_retryable=False,   // QueryAgent 是最后一级，不再回退
            latency_ms=0,
        )

    async def is_available() -> bool:
        return True  // Phase 1: QueryAgent 始终可用（无准入控制）
```

### 3.5 Gateway._post_process() 流程

```text
async def _post_process(raw: RawQueryResult, question: str, session_id: str) -> UnifiedQueryResult:
    // 1. 字段翻译（从 QueryService 迁移）
    translated_columns = self._translate_columns(raw.columns)

    // 2. 洞察生成（如果 Executor 未返回）
    if raw.success and not raw.insight and raw.rows:
        raw.insight = await self._generate_insight(question, raw.rows[:10], raw.columns)

    // 3. 历史记录（从 QueryService 迁移）
    history_id = None
    if session_id:
        history_id = await self._save_history(question, result, session_id)

    // 4. 组装 UnifiedQueryResult
    return UnifiedQueryResult(
        success=raw.success,
        source=raw.source,
        query_mode=raw.query_mode,
        question=question,
        normalized_question=None,
        sql=raw.sql,
        tool_calls=None,
        columns=translated_columns,
        rows=raw.rows,
        total=raw.total,
        insight=raw.insight,
        confidence=raw.confidence,
        clarification_needed=False,
        clarification_question=None,
        error_code=raw.error_code,
        error_message=raw.error_message,
        trace_id=get_current_trace_id(),
        latency_ms=...,
    )
```

---

## 4. 回退策略（仅限 Phase 1 的最小版本）

### 4.1 简化回退规则

Phase 1 不实现完整的 QueryAgent 准入控制（那是 Phase 3 的事），但需要有一个最小保护规则，避免 QueryAgent 掩盖 LocalExecutor 的真实问题。

```text
LocalExecutor 失败 → 判断是否允许回退到 QueryAgent:

┌──────────────────────────┬──────────┬──────────────────────┐
│ LocalExecutor 失败原因    │ 允许回退? │ 理由                  │
├──────────────────────────┼──────────┼──────────────────────┤
│ graph 编译/序列化异常     │    ✅    │ QueryAgent 不依赖      │
│ (langgraph_error)        │          │ LangGraph，可能成功     │
├──────────────────────────┼──────────┼──────────────────────┤
│ LLM API 不可用           │    ❌    │ QueryAgent 也用同一     │
│ (llm_api_error)          │          │ LLM，回退无意义         │
├──────────────────────────┼──────────┼──────────────────────┤
│ MySQL 连接失败            │    ❌    │ QueryAgent 也用同一     │
│ (db_connection_failed)   │          │ MySQL，回退无意义       │
├──────────────────────────┼──────────┼──────────────────────┤
│ SQL 安全违规              │    ❌    │ 安全错误不回退          │
│ (sql_security_violation) │          │                       │
├──────────────────────────┼──────────┼──────────────────────┤
│ Schema 搜索无结果         │    ✅    │ QueryAgent 可能选不同   │
│ (schema_not_found)       │          │ 的表，值得尝试          │
├──────────────────────────┼──────────┼──────────────────────┤
│ SQL 执行错误              │    ✅    │ QueryAgent 可能生成     │
│ (sql_execution_error)    │          │ 不同的 SQL              │
├──────────────────────────┼──────────┼──────────────────────┤
│ 其他/未知错误             │    ✅    │ 保守策略：尝试一次      │
│ (internal_error)         │          │                       │
└──────────────────────────┴──────────┴──────────────────────┘
```

### 4.2 Phase 1 最小 error_code 集合

| error_code | 回退 | 说明 |
|-----------|:---:|------|
| `langgraph_error` | ✅ | LangGraph 运行时异常 |
| `llm_api_error` | ❌ | LLM 不可用 |
| `db_connection_failed` | ❌ | MySQL 不可用 |
| `sql_security_violation` | ❌ | SQL 安全校验失败 |
| `sql_execution_error` | ✅ | SQL 执行错误 |
| `schema_not_found` | ✅ | 无匹配表 |
| `internal_error` | ✅ | 未分类错误 |

### 4.3 `_is_retryable_error()` 判定函数

```text
def _is_retryable_error(raw: dict) -> bool:
    """根据 LocalExecutor 的原始返回判断是否允许回退到 QueryAgent"""
    error_msg = str(raw.get("error", "")).lower()

    // 不回退的情况
    if any(kw in error_msg for kw in ["api key", "api_key", "llm", "openai", "deepseek"]):
        return False  // LLM 问题，QueryAgent 也无法解决
    if any(kw in error_msg for kw in ["mysql", "database", "connection", "连接"]):
        return False  // MySQL 问题，QueryAgent 也无法解决
    if any(kw in error_msg for kw in ["drop", "delete", "insert", "update", "禁止", "安全"]):
        return False  // 安全问题

    // 允许回退
    return True
```

---

## 5. 兼容与回滚方案

### 5.1 API 兼容性

| 接口 | 兼容策略 |
|------|---------|
| `POST /api/v1/query/` | 请求/响应格式**不变**。`QueryService.natural_query()` 内部改为调 Gateway，但返回的 dict 结构保持一致 |
| `POST /api/v1/query/execute` | **不变**。`execute_sql()` 不走 Gateway |
| `POST /api/v1/orchestrator/chat` | **不变**。`dispatch_to_nl2sql()` 保持函数签名和返回格式兼容 |
| `DISPATCH_MAP["nl2sql"]` | **不变**。指向适配器函数，返回值格式不变 |

### 5.2 快速回滚方案

如果 Gateway 接入后出现问题，回滚只需两步：

```text
Step 1: 恢复 QueryService.natural_query() 旧实现
  → 从 git 恢复 query_service.py 到改动前的版本
  → 或通过配置开关：保留旧方法为 _natural_query_legacy()，Gateway 出问题时切回

Step 2: 恢复 dispatch_to_nl2sql() 旧实现
  → 从 git 恢复 dispatch.py 到改动前的版本

回滚窗口: < 5 分钟（两个文件 revert）
```

### 5.3 双写验证（推荐过渡方案）

在 Phase 1 部署后的观察期内（建议 3-5 天），Gateway 执行的同时将结果与旧路径对比：

```text
async def natural_query(self, question: str):
    // 主路径：走 Gateway
    result = await gateway.execute(question, session_id)

    // 影子路径：异步跑旧路径，比较结果（仅记录差异，不影响返回）
    asyncio.create_task(self._shadow_compare(question, result))

    return self._format_response(result)

async def _shadow_compare(self, question, gateway_result):
    """影子模式：对比 Gateway 和旧路径结果，记录差异到日志"""
    old_result = await self._natural_query_legacy(question)
    if old_result["success"] != gateway_result.success:
        _log.warning("Gateway vs legacy diff: success mismatch")
    if old_result.get("sql") != gateway_result.sql:
        _log.info("Gateway vs legacy diff: SQL differs")
```

> **双写模式是可选的安全网**，如果团队对 Gateway 改动有信心可以跳过。但建议至少在 staging 环境启用。

### 5.4 关键 Case 对照清单

部署前需跑通的 12 条黄金 Case（见第 6.3 节），Gateway 和旧路径的结果必须一致。

---

## 6. Phase 1 测试计划

### 6.1 L1：Gateway / Executor 单元测试

**文件**: `backend/tests/test_gateway.py`

| 测试用例 | 覆盖点 | 验证方式 |
|---------|--------|---------|
| `test_local_executor_success` | LocalExecutor 正常返回 | mock `graph_nl2sql.ainvoke()` 返回成功数据，验证 `RawQueryResult.success=True` |
| `test_local_executor_failure_retryable` | LocalExecutor 失败 + 允许回退 | mock 返回 `langgraph_error`，验证 `is_retryable=True`，Gateway 尝试 QueryAgentExecutor |
| `test_local_executor_failure_non_retryable` | LocalExecutor 失败 + 不允许回退 | mock 返回 `llm_api_error`，验证 `is_retryable=False`，Gateway 直接返回失败 |
| `test_queryagent_executor_success` | QueryAgentExecutor 正常返回 | mock `query_agent.query()` 返回成功数据 |
| `test_fallback_chain_local_to_queryagent` | 完整回退链 | LocalExecutor mock 失败 → Gateway 回退到 QueryAgentExecutor → 成功 |
| `test_fallback_chain_all_fail` | 全部失败 | LocalExecutor + QueryAgentExecutor 都 mock 失败 → `success=False` |
| `test_post_process_translate_columns` | 字段翻译 | 英文列名 → 中文列名 |
| `test_post_process_save_history` | 历史记录 | 验证 `_save_history()` 被调用且参数正确 |
| `test_post_process_generate_insight` | 洞察生成 | Executor 未返回 insight → Gateway 补生成 |
| `test_unified_result_all_fields` | 返回结构完整性 | 验证 UnifiedQueryResult 的所有 Phase 1 必须字段非 None |

### 6.2 L2：现有链路回归

| 测试 | 覆盖点 | 使用现有测试 |
|------|--------|------------|
| `test_orchestrator_router.py` 全部通过 | 意图路由不退化 | ✅ 现有测试 |
| `test_orchestrator_l2.py` 全部通过 | dispatch 适配器兼容 | ✅ 现有测试（可能需要微调 mock） |
| QueryPage 手动测试 | `POST /api/v1/query/` 正常返回 | 手动 |
| OrchestratorPage 手动测试 | `POST /api/v1/orchestrator/chat` 正常返回 | 手动 |
| 历史记录检查 | `GET /api/v1/query/history/all` 有 Gateway 产生的记录 | 手动 |

### 6.3 行为一致性清单（12 条黄金 Case）

部署前，对每条 Case 分别调用 Gateway 和旧路径，对比结果。**所有 Case 的结果必须一致。**

| # | 问题 | 类型 | 关注点 |
|---|------|------|--------|
| C1 | `"502620的库存情况"` | 简单库存查询 | SQL 相同、行数相同、列名相同 |
| C2 | `"最近的出库记录"` | 出库查询 | SQL 相同、结果非空 |
| C3 | `"商品502620的基本信息"` | 商品查询 | 跨表 JOIN 正确 |
| C4 | `"上个月的入库单"` | 时间过滤 | 时间范围处理一致 |
| C5 | `"各仓库库存汇总"` | 聚合查询 | GROUP BY 正确、结果排序一致 |
| C6 | `"库存预警"` | 分析查询 | 阈值逻辑一致 |
| C7 | `"ZZZ999不存在的商品"` | 无结果 | `success=True, total=0`，不报错 |
| C8 | `"查询库存锁定情况"` | 锁定表查询 | HARD_RULES 正确触发 |
| C9 | `"502620在良品仓的批次分布"` | 多条件过滤 | 所有 WHERE 条件正确 |
| C10 | `"有哪些拣货位设置了补货策略"` | 仓库配置查询 | 多表关联正确 |
| C11 | `""` (空字符串) | 边界 | Phase 1: 行为与旧路径一致 |
| C12 | `"你好"` | 非查询 | Phase 1: 行为与旧路径一致 |

**验证方法**:
```text
for each case:
    gateway_result = await gateway.execute(question)
    legacy_result = await query_service._natural_query_legacy(question)
    assert gateway_result.success == legacy_result["success"]
    assert gateway_result.total == legacy_result.get("total", 0)
    assert len(gateway_result.columns) == len(legacy_result.get("columns", []))
    // SQL 可能因 LIMIT 注入等原因略有差异，做宽松比较
    assert core_sql_similar(gateway_result.sql, legacy_result.get("sql", ""))
```

---

## 7. 实施顺序（按 commit 切分）

### Step 1: 新增 Gateway 骨架和 UnifiedQueryResult

| 项目 | 内容 |
|------|------|
| **改哪些文件** | 新增 `backend/app/core/data_query_gateway.py`（仅 `UnifiedQueryResult` + `RawQueryResult` + `DataQueryExecutor` Protocol + `DataQueryGateway` 类骨架） |
| **不改什么** | 不注册任何 Executor，Gateway 的 `execute()` 暂时抛出 `NotImplementedError` |
| **验收点** | 文件可 import，类可实例化，无语法错误 |
| **风险点** | 极低 — 纯新增，不影响任何现有路径 |

### Step 2: 接入 LocalExecutor

| 项目 | 内容 |
|------|------|
| **改哪些文件** | `core/data_query_gateway.py`（实现 `LocalExecutor`、`_execute_with_fallback()` 的单 Executor 版本、`_translate_columns()` 迁移、`_save_history()` 迁移、`_post_process()`） |
| **不改什么** | 不修改 `graph_nl2sql.py`、不接入 QueryAgentExecutor |
| **验收点** | `LocalExecutor.execute()` 能成功调用 `graph_nl2sql` 并返回 `RawQueryResult`；`_translate_columns()` 输出与迁移前一致；`_save_history()` 写入与迁移前一致 |
| **风险点** | `_translate_columns()` 和 `_save_history()` 迁移需确保调用 `SchemaManager` 和 `models/query_history` 的方式与迁移前完全一致 |

### Step 3: 接入 QueryAgentExecutor + 简化回退链

| 项目 | 内容 |
|------|------|
| **改哪些文件** | `core/data_query_gateway.py`（实现 `QueryAgentExecutor`、`_is_retryable_error()`、更新 `_execute_with_fallback()` 为双 Executor 回退链） |
| **不改什么** | 不修改 `query_agent.py` 内部逻辑（只加 deprecated 标记） |
| **验收点** | LocalExecutor 失败 + `is_retryable=True` → 自动回退到 QueryAgentExecutor；LocalExecutor 失败 + `is_retryable=False` → 不调用 QueryAgentExecutor，直接返回错误 |
| **风险点** | `is_retryable` 判断基于错误消息关键词，可能有漏判。保守策略：不确定时允许回退（宁可多回退一次，不要漏掉） |

### Step 4: 改 QueryService

| 项目 | 内容 |
|------|------|
| **改哪些文件** | `services/query_service.py`（`natural_query()` 改为调 Gateway；删除 `_query_via_langgraph()`、`_translate_columns()`、`_save_history()`；删除 `use_langgraph` 引用） |
| **不改什么** | `execute_sql()`、`get_schema()`、`preview_table()` 等保留不动 |
| **验收点** | `POST /api/v1/query/` 返回格式与改造前一致（12 条黄金 Case 全通过）；`_translate_columns()` 和 `_save_history()` 不再在 QueryService 中定义（lint 检查） |
| **风险点** | QueryService 的 `_natural_query_legacy()` 如果保留为双写影子，注意不要被正常路径调用；响应格式中的 `source` 是新增字段，确认前端不会因未知字段报错 |

### Step 5: 改 Orchestrator dispatch

| 项目 | 内容 |
|------|------|
| **改哪些文件** | `orchestrator/dispatch.py`（`dispatch_to_nl2sql()` 改为 Gateway 适配器） |
| **不改什么** | `DISPATCH_MAP` 不变、`dispatch_to_rag()` 不变、`dispatch_to_pm()` 不变、`orchestrator.py` 不变、`executor.py` 不变 |
| **验收点** | `POST /api/v1/orchestrator/chat` 的 NL2SQL 响应与改造前一致；OrchestratorPage 的混合查询（hybrid）包含 nl2sql step 时行为不变 |
| **风险点** | `dispatch_to_nl2sql()` 返回的 `{sql, data, insight}` 格式需与旧版精确一致，否则 executor.py 的 `_run_synthesis()` 可能解析失败 |

### Step 6: 删除 use_langgraph + 补测试 + 回归

| 项目 | 内容 |
|------|------|
| **改哪些文件** | `core/config.py`（删除 `use_langgraph`）；`backend/tests/test_gateway.py`（新增 L1 测试）；`.env.example`（删除 `USE_LANGGRAPH`）；`query_service.py`（确认 `use_langgraph` 引用已清除） |
| **不改什么** | 现有测试文件不动（除非需要微调 mock） |
| **验收点** | grep `use_langgraph` 全项目无引用；L1 测试 10 条全部通过；L2 测试 `test_orchestrator_router.py` + `test_orchestrator_l2.py` 通过；12 条黄金 Case 对照通过 |
| **风险点** | 可能有其他文件引用 `settings.use_langgraph`，需全项目 grep 确认 |

---

## 附录 A: 实施顺序依赖图

```
Step 1 (Gateway 骨架)
  │
  ▼
Step 2 (LocalExecutor)
  │
  ▼
Step 3 (QueryAgentExecutor + 回退链)
  │
  ├──────────────┐
  ▼              ▼
Step 4          Step 5
(QueryService)  (dispatch)
  │              │
  └──────┬───────┘
         ▼
Step 6 (flag 删除 + 测试 + 回归)
```

> Step 4 和 Step 5 互不依赖，可以并行开发。但建议先完成 Step 4 再 Step 5，因为 Step 5 的 `dispatch_to_nl2sql()` 依赖 Gateway 已完成。

## 附录 B: Phase 1 不做的确认清单

| 不做的事项 | 放到哪个 Phase |
|-----------|-------------|
| MCP 接入 (`graph_mcp.py`, `mcp_client.py`) | Phase 2 |
| CircuitBreaker | Phase 2 |
| MCP Tool 选择 Prompt | Phase 2 |
| 完整 Clarification Policy (L1+L2) | Phase 3 |
| QueryAgent 准入条件（6 条判定规则） | Phase 3 |
| 统一 Error Taxonomy（18 种 error_code） | Phase 3 |
| 前端 source 标记、clarification UI | Phase 4 |
| Tracing span 扩展 `mcp.*` | Phase 4 |
| Eval 扩展 `mcp_queries.json` | Phase 4 |
| QueryAgent 删除 | Phase 4（或更晚） |

---

> **文档版本**: v1.0
> **设计完成时间**: 2026-06-24
> **关联文档**:
> - `docs/superpowers/plans/2026-06-24-mcp-migration-analysis.md`
> - `docs/superpowers/plans/2026-06-24-data-query-convergence-design.md`
> - `docs/superpowers/plans/2026-06-24-gateway-phase0-design.md`
> **下一步**: 审核 Phase 1 任务书，确认后按 Step 1~6 顺序进入编码
