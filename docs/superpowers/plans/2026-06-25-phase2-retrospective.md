# Phase 1 + Phase 2 工程回顾 (Retrospective)

> **范围**: Gateway 收敛 → MCP Client → Graph 骨架 → 接线 → LLM Tool Selection → 集成验收
> **最终状态**: 104/104 pass, MCP 主路径 L3 验收 7/7 通过
> **审查方式**: 批判性回顾，不礼貌性认可

---

## Wins

### 1. 三层路由模型（Layer A/B/C）扛住了复杂度

**做了什么**: `Gateway._check_mcp_eligibility()`(A) → `tool_filter_node`(B) → `tool_select_node`(C)，每层职责单一、可独立测试。

**为什么成功**: Layer A 和 B 是纯规则，不调 LLM，快速且可精确控制。Layer C 是唯一的 LLM 调用点，Step 4 从规则版切换到 LLM 版时，图结构、条件边、其他节点全部未变——只替换了一个节点的内部实现。这是架构隔离做对了的典型信号。

### 2. McpExecutor 作为优先级执行器的插入方式

**做了什么**: `McpExecutor(priority=0)` 插入现有 `LocalExecutor(1)` + `QueryAgentExecutor(2)` 链，Gateway 无需感知三个执行器的内部差异。

**为什么成功**: `QueryService`、`dispatch.py`、`orchestrator.py` 全部零改动。Gateway 新增 90 行代码，外部完全无感。这是"开闭原则"在 Python 项目中的实际落地。

### 3. MCP Server 协议适配的防御性设计

**做了什么**: `_post_rpc()` 统一处理 SSE 解析、session 管理、`structuredContent` 解包、`isError` 检测。当 MCP Server 响应格式从文档描述的简单 JSON 变成完整 MCP 2024-11-05 协议时，改动集中在 `mcp_client.py` 的 `_post_rpc()` 一个方法内。

**为什么成功**: 抽象层做对了——所有 RPC 调用（ping/call_tool/list_tools）都通过同一个入口，协议变化只影响一处。

### 4. 测试策略：mock 依赖链而非安装全部依赖

**做了什么**: `conftest.py` 的 `pytest_configure` 钩子注入 `sys.modules` mock，阻断 `numpy → aiomysql → sentence_transformers → llama_index` 导入链。

**为什么成功**: 104 条测试在裸 Python 3.13 环境下可运行，不需要安装 30+ 个项目依赖。测试速度保持在 ~30s 内。这比"安装全部依赖再跑测试"务实得多。

---

## Problems

### 1. MCP Guide 文档与 Server 实现严重不一致

**发生了什么**: Step 1 按 `docs/data-copilot-integration-guide.md` 实现了 `WmsMcpClient`——简单的 JSON-RPC POST，无 session。实际 MCP Server 运行的是完整的 MCP 2024-11-05 流式 HTTP 协议：`initialize` 握手 → SSE 响应解析 → `Mcp-Session-Id` header → `notifications/initialized`。Step 5 才发现这个问题，整个 client 的 `_post_rpc()`、`_ensure_session()`、`_parse_sse_body()` 都要重写。

**根因**: Guide 文档描述的是预期的简化接口，但 Server 实现的是完整 MCP 规范。开发时没有可用的 Server 做对照验证。

**教训**: 任何涉及外部服务的接入，第一天就要做连通性测试——哪怕只是 `curl` 一下看返回什么。不要基于文档假设协议。

### 2. 依赖地狱 — 每步都要 `pip install`

**发生了什么**: 测试环境是裸 Python 3.13。Phase 1 用 mock 绕过了。但 Step 5 做 L3 真实验证时，导入链触发了 `pydantic_settings → numpy → aiomysql → sentence_transformers → llama_index → chromadb → langchain` 整个依赖树。每步验证都要先 `pip install` 一个包，有时等几分钟。

**根因**: `data_query_gateway.py` 的模块级 import 触发了整个项目的依赖图。`conftest.py` 的 mock 只覆盖了测试，不覆盖真实运行。

**教训**: 应该在 Phase 1 就建立一个最小化的集成测试环境（Docker/venv），而不是到 Step 5 才发现缺了 8 个依赖。

### 3. Gateway 单例 + 配置热加载的冲突

**发生了什么**: `.env` 新增 `MCP_ENABLED=true` 和 `MCP_API_KEY=gk-...` 后，`get_gateway()` 单例已经用旧配置构造了 `McpExecutor`，`self._mcp_mgr` 持有空的 API Key。即使 `.env` 更新了，单例不重建。L3 测试时每次都要 `DataQueryGateway()` 新实例才能生效。

**根因**: `get_gateway()` 是模块级全局变量，`McpExecutor.__init__` 在构造时缓存了 `McpClientManager`。配置变更后需要重启进程。

**教训**: 这不是 bug——这是 Python 模块单例的正常行为。但应该在验收计划里写明"修改 `.env` 后需重启后端服务"。

### 4. `\b` 正则在中文字符串中静默失效

**发生了什么**: `_check_mcp_eligibility` 用 `\b\d{4,8}\b` 匹配 "502620的库存" 中的 SKU 编码。Python 3 默认 Unicode 模式下，`\b` 将中文字符视为 `\w`，"0的"之间无边界，正则静默不匹配。导致所有带实体的中文查询被误判为 `eligible=false`。

**根因**: Python 3 的 `re.UNICODE` 是默认的，但 `\b` 的 Unicode 行为与 ASCII 行为不同。这是一个经典的 Python 3 陷阱。

**教训**: 中文 NLP 场景下，永远不要用 `\b`。用 `(?<!\d)...(?!\d)` 替代。

### 5. `MCPAgentState` 缺少 `mcp_manager` 字段导致 LangGraph 丢弃 state key

**发生了什么**: `McpExecutor.execute()` 通过 `graph.ainvoke({"mcp_manager": self._mcp_mgr})` 传入 manager。但 `mcp_call_node` 读取 `state.get("mcp_manager")` 时为 `None`。原因是 `MCPAgentState` TypedDict 没有声明这个字段，LangGraph 在状态合并时丢弃了未知 key。

**根因**: LangGraph 的 `StateGraph(TypedDict)` 会按 schema 过滤 state。非 schema 字段可能在节点转换时丢失。这是一个 LangGraph 的隐含行为，文档没有充分警示。

**教训**: 所有通过 `graph.ainvoke()` 传入的额外字段，必须声明在 State TypedDict 中（或使用 `total=False` 并验证运行时行为）。

---

## Technical Debt

### 1. `conftest.py` 的 sys.modules mock（可接受但脆弱）

当前 20 个模块通过 `sys.modules` 注入 mock。如果项目新增或重命名模块，`conftest.py` 和 `_CLEANUP_KEYS` 需要同步更新。每次加一个新依赖都可能破坏测试。

**后续**: Phase 3 考虑用 `pytest-mock` 的 `mock.patch.dict` 替代，或建立基于 Docker 的测试环境。

### 2. Gateway 文件 770 行，混合 6 种职责

路由判断、eligibility、CircuitBreaker、三个 Executor、后处理、历史记录都在一个文件里。当前还可维护，但 Phase 3 加 Clarification Policy 后会失控。

**后续**: Phase 3 至少提取 `circuit_breaker.py` 和 `eligibility_policy.py`。

### 3. `_build_candidate_descriptions` 只用静态 Registry

`McpExecutor` 已经把真实的 MCP `list_tools()` 结果传入 state，但 `_build_candidate_descriptions` 只读 `_TOOL_BY_NAME` 静态 Registry。如果 MCP Server 升级了 Tool 参数，LLM 看到的描述就是过期的。

**后续**: Phase 3 改为优先使用 `state["tool_registry_raw"]`，Registry 作为 fallback。

### 4. `_get_client()` 仍是私有方法被外部调用

`mcp_call_node` 通过 `mgr._get_client()` 获取 client。虽然 Step 5.1 给 `McpClientManager` 加了公共 `call_tool()`，但 `_get_client()` 的 `_` 前缀意味着它仍是"私有但不得不暴露"的尴尬状态。

**后续**: Phase 3 将 `WmsMcpClient` 的连接管理完全封装在 `McpClientManager` 内部，外部只调 `call_tool()`。

---

## Recommended Refactors

### 1. 必须做: Gateway 拆分（Phase 3 前）

当前 `data_query_gateway.py` 的结构:
```
UnifiedQueryResult / RawQueryResult (90 行)
_classify_error / _is_retryable_error (45 行)
LocalExecutor (85 行)
QueryAgentExecutor (75 行)
McpExecutor (90 行)
CircuitBreaker (50 行)
DataQueryGateway (200 行: _check_mcp_eligibility + _execute_with_fallback + _post_process + 后处理)
```

建议 Phase 3 拆为:
```
core/data_query_gateway.py        → DataQueryGateway + Executor 协议 (150 行)
core/circuit_breaker.py           → CircuitBreaker (50 行)
core/mcp_eligibility_policy.py    → _check_mcp_eligibility (50 行)
```

三个 Executor 保留在 Gateway 文件中（它们与 Gateway 紧耦合，拆出去反而增加 import 复杂度）。

### 2. 建议做: 统一日志体系

当前 `mcp_client.py` 用标准 `logging`，Gateway 和 graph 用 `loguru`。两个日志系统无法通过同一个 handler 配置。建议 Phase 3 统一为 `loguru`（项目主流），或在 `mcp_client.py` 中加一个适配器。

### 3. 建议做: MCP eligibility 升级为 DomainClassifier 辅助

当前 `_check_mcp_eligibility` 用关键词列表做 domain 匹配。项目已有 `DomainClassifier`（embedding 余弦相似度），比关键词更准确。Phase 3 应该让 DomainClassifier 的 embedding 分类结果作为 Layer A 的 domain_hint 来源，关键词作为 fast path 预筛选。

---

## Architecture Update

### 需要更新的文档

| 文档 | 需要更新什么 |
|------|-------------|
| `data-query-convergence-design.md` | TO-BE 架构图与实际实现一致（Gateway 三层 executor 链） |
| `gateway-phase0-design.md` | `UnifiedQueryResult` 新增字段（`history_id`/`source`/`query_mode`/`tool_calls`） |
| `phase2-mcp-mvp-design.md` | Layer A/B/C 三层模型已实现；`_LlmToolSelector` 实际接口；MCP session 管理；`structuredContent` 解包 |
| `data-copilot-integration-guide.md` | **必须更新**: 实际 MCP Server 使用的是完整 MCP 2024-11-05 协议（SSE + session），不是简化 JSON-RPC；Python client 代码需要对应更新 |

### 不需要更新的文档

`phase1-implementation-plan.md` / `phase1.5-acceptance-report.md` — 历史基线，保留不动。

---

> **Retro 完成时间**: 2026-06-25
> **最终代码基线**: 104/104 pass, MCP L3 7/7 pass
