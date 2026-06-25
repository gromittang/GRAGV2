# Phase 2 / Step 3 Code Review 报告

> **审查范围**: `data_query_gateway.py` / `graph_mcp.py` / `mcp_client.py` / `agent_state.py` / 相关测试
> **审查时间**: 2026-06-24
> **测试基线**: 87/87 pass

---

## A. 总体结论

**Step 3 的实现质量：良好。架构方向正确，但存在 2 个必须修复的阻塞问题和若干需要在 Step 4 前处理的边界缺陷。**

核心判断：
- MCP 接线方案整体合理，`McpExecutor` 作为最高优先级执行器插入 Gateway 的设计干净
- 三层路由模型（Layer A/B/C）的职责边界在代码中得到了正确体现
- 回退链和 CircuitBreaker 的基本骨架正确
- **但 MCP eligibility 规则过于保守会导致大量 false negative**（本应走 MCP 的查询被挡在门外）
- **存在 1 处代码重复 bug** 和一个 **CircuitBreaker 语义混淆点**

**建议：先修复 2 个阻塞问题（预计改动 < 30 行），再进入 Step 4。**

---

## B. Blocking / Critical Issues（阻塞 / 严重问题）

### B1. [P0] `_execute_with_fallback()` 存在重复代码块

**位置**: `data_query_gateway.py` 第 626-632 行

```python
if not result.is_retryable:
    _log.info("Executor {} 错误不可回退，终止回退链", executor.name)
    break

if not result.is_retryable:       # ← 完全重复的代码块
    _log.info("Executor {} 错误不可回退，终止回退链", executor.name)
    break
```

**影响**: 逻辑上无害（idempotent），但表明存在合并/编辑错误。如果未来有人在两个块之间插入代码，会引入隐蔽 bug。

**修复**: 删除第二个重复块。1 行改动。

**优先级**: P0 — 进入 Step 4 前必须修复。

---

### B2. [P0] MCP Eligibility 规则过于保守 — 分析域 / 商品域 / 聚合查询被系统性误杀

**位置**: `data_query_gateway.py` `_check_mcp_eligibility()` 第 540-580 行

当前规则：`eligible = (有业务关键词) AND (有实体)`。其中"实体"定义为数字编码（SKU/库位/批次号/单号）。

**这个规则会导致以下查询被错误地判定为 `eligible=false`，直接跳过 MCP 走 LocalExecutor：**

| 被误杀的查询 | 应走的 MCP Tool | 被误杀的原因 |
|------------|---------------|------------|
| "有没有快过期的商品" | `get_stock_warning` | 无数字实体 — 但该 Tool 无必填参数 |
| "各 SKU 库存总量" | `get_inventory_summary` | 无数字实体 — 但该 Tool 无必填参数 |
| "哪些库存超过90天没动" | `get_slow_moving_inventory` | 无数字实体 — 但该 Tool 无必填参数 |
| "最近的入库单" | `query_inbound_order` | 无数字实体 — 但该 Tool 全参数可选 |
| "商品信息" | `query_product` | 无数字实体 — 但该 Tool 全参数可选 |
| "出库统计" | `query_outbound_order` | 无数字实体 — 但该 Tool 全参数可选 |

**这些恰是 MCP 预构建 Tool 最能发挥优势的高频场景。如果被资格判定挡住，Phase 2 的 MCP 命中率将远低于设计目标（80%）。**

**根因**: `_check_mcp_eligibility()` 的实体识别逻辑基于一个错误假设——"所有 MCP 查询都需要数字实体（SKU/单号等）"。但实际上 15 个 Tool 中有 8 个全参数可选或无必填数字参数。

**修复方案**（最小改动，预计 ~15 行）:

在 `_check_mcp_eligibility()` 中增加一个"无需实体"的 domain 白名单：

```text
_NO_ENTITY_REQUIRED_DOMAINS = {"analytics", "product"}

# 修改判定逻辑:
if not has_entity and domain_hint not in _NO_ENTITY_REQUIRED_DOMAINS:
    return {"eligible": False, "reason": "missing_entity", ...}
```

分析域（analytics）的 4 个 Tool 和商品域（product）的 3 个 Tool 在无实体时也可正常执行。入库/出库域仍需实体（否则全表扫描数据量巨大）。

**优先级**: P0 — 进入 Step 4 前必须修复。否则 Phase 2 验收时 MCP 命中率无法达标。

---

## C. Non-blocking Improvements（非阻塞优化项）

### C1. [P1] CircuitBreaker.record_failure() 中导入了 `is_circuit_breaker_error` 但未使用

**位置**: `data_query_gateway.py` 第 474-480 行

```python
def record_failure(self):
    from app.core.mcp_client import is_circuit_breaker_error  # ← 导入但未使用
    self._failure_count += 1
    ...
```

**影响**: 无功能影响（调用方已在外部过滤），但造成混淆——读者会以为 `record_failure()` 内部做了过滤。

**修复**: 删除无用 import，或改为在 `record_failure(error_code)` 内部做过滤（让调用方更简洁）。推荐后者：在 `_execute_with_fallback` 中直接 `breaker.record_failure(error_code)` 而不用外部判断。

**优先级**: P1 — 建议 Step 4 前修复，避免后续维护者误解。

---

### C2. [P1] McpExecutor.is_available() 每次调用创建新的 McpClientManager

**位置**: `data_query_gateway.py` 第 407-420 行

```python
async def is_available(self) -> bool:
    ...
    mgr = McpClientManager(base_url=..., api_key=..., timeout=...)
    available = await mgr.is_available()
    await mgr.close()
    return available
```

**影响**: 每次 Gateway 查询（包括 `_execute_with_fallback` 的循环）都会创建新的 `McpClientManager` → 新的 `WmsMcpClient` → 新的 `httpx.AsyncClient`。在 MCP 不可用时，这会额外增加连接超时等待时间。

**修复**: 将 `McpClientManager` 提升为 `McpExecutor` 的实例属性，在 `__init__` 中创建，复用连接。

```python
class McpExecutor:
    def __init__(self):
        settings = get_settings()
        self._mcp_mgr = McpClientManager(
            base_url=settings.mcp_base_url,
            api_key=settings.mcp_api_key,
            timeout=settings.mcp_timeout,
        )

    async def is_available(self) -> bool:
        if not get_settings().mcp_enabled:
            return False
        return await self._mcp_mgr.is_available()
```

注意：这需要确认 `get_settings()` 在 `McpExecutor()` 构造时可用。当前 `_register_executors()` 在 `Gateway.__init__()` 中调用，此时 config 应该已加载。

**优先级**: P1 — 建议 Step 4 前修复。影响 MCP 不可用时的响应延迟。

---

### C3. [P2] Gateway 行数增长趋势（当前 ~777 行）

`data_query_gateway.py` 当前包含：
- 3 个数据类（UnifiedQueryResult / RawQueryResult / Insight / ToolCall）
- 2 个独立函数（_classify_error / _is_retryable_error）
- 3 个 Executor 类（Local / QueryAgent / MCP）
- 1 个 CircuitBreaker 类
- 1 个 _is_mcp_error_retryable 函数
- 1 个 DataQueryGateway 类（含 8 个方法）

**当前评估**: Phase 2 MVP 阶段可以接受此复杂度。所有新增代码都与"数据查询入口"直接相关，暂不构成 God Object。

**后续建议**（Phase 3/4，非当前必须）:
- `CircuitBreaker` 可提取为 `core/circuit_breaker.py`（如其被其他服务复用）
- `_check_mcp_eligibility` 可提取为 `core/mcp_eligibility_policy.py`
- `_is_mcp_error_retryable` 与 `mcp_client.py` 的 `is_retryable_mcp_error` 存在功能重叠，应统一

**优先级**: P2 — Phase 3 考虑，Phase 2 不需要。

---

### C4. [P2] `_is_mcp_error_retryable()` 与 `mcp_client.is_retryable_mcp_error()` 功能重复

**位置**: `data_query_gateway.py:423` vs `mcp_client.py:84`

两个函数做几乎相同的事——判断 MCP 错误是否可回退。Gateway 版本增加了 `mcp_disabled` 和 `sql_security_violation` 的显式排除。但 `mcp_client` 版本没有包含这两个码（它们是合理的——`mcp_disabled` 确实不应回退，`sql_security_violation` 也不应）。

**建议**: 将 Gateway 版本的增强逻辑合并到 `mcp_client.is_retryable_mcp_error()` 中，Gateway 直接调用后者。消除重复。

**优先级**: P2 — Phase 3 统一 Error Taxonomy 时处理。

---

## D. 测试缺口清单

### D.1 当前测试覆盖总结

| 层级 | 文件 | 覆盖内容 | 缺失 |
|------|------|---------|------|
| L1-Client | `test_mcp_client.py` (25条) | WmsMcpClient 所有方法、错误处理 | 覆盖充分 ✅ |
| L1-Graph | `test_mcp_graph.py` (31条) | Tool Registry、节点函数、图编译 | 覆盖充分 ✅ |
| L1-Gateway | `test_gateway.py` (31条) | LocalExecutor、QueryAgentExecutor、回退链、错误分类 | **缺少 McpExecutor 相关测试** ❌ |

### D.2 测试缺口清单

| # | 缺口 | 严重度 | 说明 |
|---|------|:-----:|------|
| G1 | **Gateway 中 McpExecutor 成功路径未测试** | P0 | `test_gateway.py` 没有任何测试覆盖 `source="mcp"` 的成功场景 |
| G2 | **MCP eligibility 跳过逻辑未测试** | P0 | 没有测试验证 `eligible=false` → 跳过 McpExecutor → 走 LocalExecutor |
| G3 | **CircuitBreaker 跳过 MCP 未测试** | P0 | 没有测试验证 Breaker OPEN → 跳过 MCP 的完整链路 |
| G4 | **MCP 可回退失败 → LocalExecutor 接管未测试** | P1 | `test_fallback_to_queryagent` 覆盖了 Local→QueryAgent 回退，但没有 MCP→Local 回退的测试 |
| G5 | **MCP 不可回退失败 → 不回退未测试** | P1 | 如 `mcp_disabled` 或 `sql_security_violation` → 直接返回错误 |
| G6 | **MCP 结果格式映射未在 Gateway 级别测试** | P1 | `result_format_node` 在 graph 级别有测试，但 Gateway 级别的 `_post_process` + MCP 结果的完整链没有 |
| G7 | **_check_mcp_eligibility 规则覆盖不全** | P1 | 只测试了"有实体+关键词=eligible"，没有测试分析域/商品域豁免、false negative/positive 场景 |

### D.3 补测试建议（最小集）

**P0 — 进入 Step 4 前必须补**（预计 3-4 条测试，~80 行）:

```text
test_mcp_executor_success_via_gateway
  模拟: McpExecutor.is_available()=True, graph_mcp.ainvoke 返回成功
  验证: result.source == "mcp", result.success == True

test_mcp_not_eligible_skips_to_local
  模拟: _check_mcp_eligibility 返回 eligible=false 的问题
  验证: McpExecutor 未被调用, LocalExecutor 被调用, source == "local"

test_circuit_breaker_open_skips_mcp
  模拟: CircuitBreaker 状态设为 OPEN
  验证: McpExecutor 被跳过, 日志包含 "CircuitBreaker OPEN"
```

**P1 — 建议 Step 4 完成后补**（预计 3-4 条测试）:

```text
test_mcp_fails_retryable_falls_back_to_local
  模拟: McpExecutor 返回 mcp_unavailable (is_retryable=True)
  验证: LocalExecutor 被调用, source == "local"

test_mcp_fails_non_retryable_does_not_fallback
  模拟: McpExecutor 返回 sql_security_violation (is_retryable=False)
  验证: 不回退, 直接返回错误

test_mcp_result_format_through_gateway
  模拟: McpExecutor 返回 items 格式数据
  验证: _post_process 正确翻译列名、写入历史、补生成 insight
```

---

## E. Step 3 是否越界做了 Step 4 的工作

### 审查结论：**未越界，是合理的 Step 3 桥接实现。**

详细分析：

| 组件 | Step 3 实现 | Step 4 目标 | 替换难度 |
|------|-----------|-----------|:------:|
| `tool_select_node` | 规则版：单候选直接选 + 正则提取参数 | LLM + `MCP_TOOL_SELECT_PROMPT` | **低** — 替换节点函数内部实现，接口不变 |
| `_extract_params_rule_based()` | 正则提取 SKU/库位/批次号/单号 | 由 LLM 替代 | **低** — Step 4 直接删除此函数 |
| `mcp_call_node` | 完整实现 ✅ | 不变 | — |
| `result_format_node` | 完整实现 ✅ | 不变 | — |

**关键判断**:
1. `_extract_params_rule_based()` 是与 `tool_select_node` 紧耦合的内部函数，Step 4 删除 `tool_select_node` 的规则版实现时会一并移除
2. 接口契约清晰：`tool_select_node` 的输入输出（`candidate_tool_names` → `selected_tool + tool_arguments`）保持不变
3. 当前实现使得 Step 3 接线可以端到端验证，而不需要等到 Step 4 的 LLM 接入

**无需现在调整。** Step 4 只需要替换 `tool_select_node` 的内部实现。

---

## F. 建议的下一步流程

### 推荐：Step 3.1 (最小修复) → Step 4

先执行一个 **Step 3.1 修复迭代**（只修 P0 阻塞问题，预计 < 30 行改动），然后进入 Step 4。

**Step 3.1 修复清单**:

| # | 修复项 | 文件 | 改动量 |
|---|--------|------|:-----:|
| F1 | 删除 `_execute_with_fallback()` 重复代码块 | `data_query_gateway.py` | -2 行 |
| F2 | `_check_mcp_eligibility()` 增加 domain 实体豁免 | `data_query_gateway.py` | +8 行 |
| F3 | 补 P0 测试（McpExecutor 成功/跳过/CircuitBreaker） | `test_gateway.py` | +80 行 |

**不在此迭代中修复的内容**（延后到 Step 4 或 Phase 3）:
- C1-C4 非阻塞优化项
- G4-G7 测试缺口（P1 级别）
- Gateway 拆分重构

---

> **Review 完成时间**: 2026-06-24
> **审查人**: Claude Code (Tech Lead)
> **关联文档**:
> - `docs/superpowers/plans/2026-06-24-phase2-mcp-mvp-design.md`
> - `docs/superpowers/plans/2026-06-24-phase2-step3-code-review.md`
