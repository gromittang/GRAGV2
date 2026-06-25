# Step 1 ~ Step 3.1 阶段性工程 Code Review

> **审查范围**: Step 1 (mcp_client) → Step 2 (graph_mcp 骨架) → Step 3 (Gateway 接线) → Step 3.1 (修复)
> **审查时间**: 2026-06-25
> **测试基线**: 94/94 pass
> **审查人**: Claude Code — 企业高级后端架构师视角

---

## 1. 总体结论

**当前质量评级：可接受（Good），具备进入 Step 4 的条件，但有 3 个 P0 项必须在 Step 4 编码前修复。**

整体来看，Step 1~3.1 的架构方向是正确的：

- MCP 接线方案干净——`McpExecutor` 以最高优先级插入现有执行器链，向下兼容 LocalExecutor 和 QueryAgentExecutor，未破坏已有行为
- 三层路由模型（Layer A eligibility / Layer B tool family / Layer C tool selection）在代码中体现清晰，且 Layer A/B 已实现为纯规则层（不调 LLM），Layer C 当前为规则版占位，Step 4 替换为 LLM 时接口不变
- 错误处理链路完整——MCP 错误码 → `_is_mcp_error_retryable` → Gateway 回退决策 → CircuitBreaker 计数，整条链可追溯
- 测试覆盖从 57 条增长到 94 条，且新增的 7 条 McpExecutor 测试覆盖了关键路径

**但存在 3 个结构性问题需要在 Step 4 前解决**，否则会在后续迭代中被放大：

| # | 问题 | 严重度 | 为什么必须在 Step 4 前修 |
|---|------|:-----:|------------------------|
| S1 | `mcp_call_node` 每次调用创建新 `McpClientManager` + 访问私有 `_get_client()` | P0 | Step 4 引入 LLM Tool Selection 后调用频率增加，性能退化明显 |
| S2 | `CircuitBreaker.record_failure()` 无差别计数——未使用 `is_circuit_breaker_error` 过滤 | P0 | 当前 `_execute_with_fallback` 在外部做了过滤，但如果未来有其他调用方直接调 `record_failure()`，所有错误都会被计入 |
| S3 | Gateway 文件已达 ~775 行，混合了 6 种职责 | P1 | Step 4 增加 LLM Tool Selection 逻辑后还会膨胀，当前不拆分的话后续重构成本更高 |

**建议：先执行 Step 3.2（修复 S1+S2，预计 < 30 行），再进入 Step 4。**

---

## 2. 架构审查

### 2.1 Gateway 职责评估

当前 `data_query_gateway.py` (~775 行) 承载了以下职责：

| 职责 | 位置 | 行数 | 评估 |
|------|------|:---:|------|
| 统一结果模型 | `UnifiedQueryResult` / `RawQueryResult` | ~90 行 | ✅ 合理 — 这是 Gateway 的核心契约 |
| 错误分类 | `_classify_error` / `_is_retryable_error` | ~45 行 | ✅ Phase 1 遗留，仍被 Local/QueryAgent 使用 |
| MCP 错误回退判断 | `_is_mcp_error_retryable` | ~14 行 | ⚠️ 与 `mcp_client.is_retryable_mcp_error()` 功能重叠 |
| Eligibility 判断 | `_check_mcp_eligibility` | ~42 行 | ⚠️ Phase 2 新增，目前规则简单可留在 Gateway；Phase 3 增加 clarification 后应提取 |
| 熔断器 | `CircuitBreaker` | ~38 行 | ⚠️ 当前仅 MCP 使用，可留在 Gateway；如果有第二个外部服务接入则应提取 |
| 执行器 | `McpExecutor` / `LocalExecutor` / `QueryAgentExecutor` | ~270 行 | ⚠️ 三个 Executor 都在同一个文件。McpExecutor 可考虑独立文件，但与 Gateway 紧耦合，暂不拆分也可接受 |
| 编排 + 回退 | `_execute_with_fallback` | ~55 行 | ✅ 这是 Gateway 的核心逻辑 |
| 后处理 | `_post_process` / `_translate_columns` / `_save_history` / `_generate_insight` | ~110 行 | ⚠️ 后处理逻辑独立性强，但当前与 Gateway 耦合不深；Phase 3 增加 clarification 后再考虑提取 |

**结论：Gateway 目前处于"可接受但需要关注"的边界。** Phase 2 内不需要拆分，但 Phase 3 引入 Clarification Policy + 完整 error taxonomy 后，建议至少提取：
- `eligibility_policy.py`（Layer A 规则 + clarification 判断）
- `circuit_breaker.py`（如果后续有第二个外部服务需要熔断）
- `_is_mcp_error_retryable` → 合并到 `mcp_client.is_retryable_mcp_error()`

### 2.2 graph_mcp 职责评估

`graph_mcp.py` (~435 行) 职责清晰：

| 组件 | 职责 | 评估 |
|------|------|:---:|
| Tool Registry (`_MCP_TOOLS`) | 15 个 Tool 的 domain/family 映射 | ✅ 显式声明，Layer B 的纯规则输入 |
| `tool_filter_node` | Layer B: domain → 候选 Tool 名列表 | ✅ 纯规则，无副作用 |
| `tool_select_node` | Layer C: 规则版 Tool 选择 + 参数提取 | ✅ Step 3 占位，Step 4 替换 |
| `mcp_call_node` | 调用 MCP Server | ✅ 但实现有封装泄漏问题（见 S1） |
| `result_format_node` | MCP 返回 → 统一格式 | ✅ 两种格式均处理 |
| 图构建 + 条件边 | LangGraph 编排 | ✅ 结构清晰 |

**评估：职责清晰，没有越界。** `graph_mcp.py` 只做"MCP 查询编排"——接收 domain_hint → 过滤候选 → 选择 Tool → 调用 → 格式化。不涉及 Gateway 的路由/回退/后处理逻辑。

### 2.3 三个 Executor 边界评估

| 维度 | McpExecutor | LocalExecutor | QueryAgentExecutor |
|------|-----------|-------------|-------------------|
| 输入 | question + context | question + context | question + context |
| 输出 | `RawQueryResult` | `RawQueryResult` | `RawQueryResult` |
| 内部实现 | `graph_mcp.ainvoke()` | `graph_nl2sql.ainvoke()` | `agent.query()` |
| 是否有逻辑重复 | 无 — 各自调用不同的后端 | — | — |
| 耦合程度 | 与 graph_mcp 耦合（正常） | 与 graph_nl2sql 耦合（正常） | 与 query_agent 耦合（正常） |

**评估：三个 Executor 边界清晰，无逻辑重复，无不当耦合。** 各自通过 `ainvoke()` / `query()` 调用对应的后端，对 Gateway 暴露统一的 `(question, context) → RawQueryResult` 接口。

---

## 3. 错误处理与回退链审查

### 3.1 MCP Eligibility 规则评估

当前规则：`有业务关键词 AND（analytics/product domain OR 有数字实体）`

**优势**：
- 规则简单，可解释，无 LLM 开销
- 保守策略：不确定时不走 MCP，宁可让 LocalExecutor 处理

**脆弱点**：

| 场景 | 风险 |
|------|------|
| 关键词匹配依赖精确中文词汇（如"临期"而非"快过期"） | 用户口语化表达可能不匹配 |
| entity 识别仅支持数字编码 | "牛奶的库存"（SKU 名而非编码）会被拦截 |
| domain 映射只取第一个匹配 | "入库的商品"可能被 product 抢先匹配，而非 inbound |

**建议**：Step 4 不做 eligibility 大改——当前规则作为"快速预筛选"是合理的。Step 4 的 LLM Tool Selection 天然能做更精确的判断（LLM 可以理解"快过期" = 临期 = get_stock_warning）。保持 Layer A 规则简单，让 Layer C (LLM) 做精细判断。

### 3.2 回退规则评估

| 错误码 | 回退? | Breaker 计数? | 评估 |
|--------|:----:|:-----------:|------|
| `mcp_unavailable` / `mcp_timeout` | ✅ | ✅ | ✅ 正确 — 服务故障可回退 |
| `mcp_auth_error` | ✅ | ✅ | ⚠️ 首次回退合理，但应限制连续 auth error 次数（如 5 次后永久跳过直至人工介入） |
| `tool_selection_failed` / `tool_validation_failed` | ✅ | ❌ | ✅ 正确 — 业务错误不回退到 Local 是正确的 |
| `sql_security_violation` | ❌ | ❌ | ✅ 正确 — 安全问题不应绕过 |
| `mcp_disabled` | ❌ | ❌ | ✅ 正确 — 主动配置关闭 |
| 未知错误 | ✅ | ❌ | ⚠️ "保守回退"对未知错误是合理的，但应记录 WARNING 并标记 `source="mcp"` 让运维可发现 |

### 3.3 CircuitBreaker 评估

**当前设计可接受但有两个不足**：

1. **粒度问题**：全局 breaker，所有 Tool 共享。如果单个 Tool 频繁超时（如 `query_stock_flow` 数据量大），会导致整个 MCP 被熔断。Phase 2 MVP 可接受（MCP 是单点服务），Phase 3 建议增加 per-Tool 错误计数（不计入全局 breaker）。

2. **HALF_OPEN 状态下的请求无保护**：`allow_request()` 在 HALF_OPEN 状态直接返回 True，没有限制试探次数。如果 MCP 仍在故障中，HALF_OPEN 状态下可能有多个并发请求同时试探 MCP。Phase 2 可接受，Phase 3 建议增加"试探窗口内只允许 1 个请求"的限制。

3. **`record_failure()` 未使用 `is_circuit_breaker_error` 过滤**（见 S2）。

### 3.4 MCP 失败被掩盖的风险

**当前缓解措施足够**：
- `source` 字段区分 `"mcp"` / `"local"` / `"queryagent"`—运维可通过日志统计 source 分布
- CircuitBreaker 在连续 3 次服务级故障后 OPEN，避免每次都尝试 MCP
- `mcp_auth_error` 记录 ERROR 级别日志

**建议增加**：Step 4 在 Gateway 日志中增加 `mcp_bypass_reason` 字段（`not_eligible` / `circuit_open` / `unavailable` / `tool_failed`），方便运维区分"MCP 主动不选"和"MCP 选了但失败"。

---

## 4. 测试体系审查

### 4.1 当前 94 条测试覆盖分析

| 测试套件 | 条数 | 覆盖层次 | 覆盖质量 |
|---------|:---:|---------|:-------:|
| `test_mcp_client.py` | 25 | L1 — 客户端层 | ✅ 充分：所有方法、错误路径、边界 |
| `test_mcp_graph.py` | 31 | L1 — 图节点层 | ✅ 充分：Registry、节点函数、编译、约束验证 |
| `test_gateway.py` | 38 | L1+L2 — Gateway 层 | ⚠️ 基本充分但缺少 MCP 集成场景 |

### 4.2 测试缺口

| # | 缺口 | 严重度 | 说明 |
|---|------|:-----:|------|
| G1 | **MCP 成功但返回异常格式**（如 items 为空列表、items 中的 dict 缺少字段） | P1 | `result_format_node` 有单元测试覆盖正常格式，未覆盖异常 items |
| G2 | **CircuitBreaker 完整状态流转**（CLOSED→fail→fail→fail→OPEN→wait→HALF_OPEN→success→CLOSED） | P1 | 当前只测试了 OPEN 跳过场景，未测试完整生命周期 |
| G3 | **Gateway + graph_mcp 集成测试**（非 mock 的端到端） | P2 | 需要真实 MCP Server，当前环境不支持 |
| G4 | **前端返回结构兼容测试**（`QueryService.natural_query()` 的 dict 格式→`UnifiedQueryResult`→dict 的完整映射） | P2 | 已有 row format conversion 单元测试，缺少完整链路 |
| G5 | **`_check_mcp_eligibility` 的 false positive 回归测试**（不应 eligible 但被误判为 eligible） | P1 | 当前只测试了 false negative 修复，未测试 false positive |

### 4.3 Step 4 前必须补的测试

| # | 测试 | 优先级 |
|---|------|:-----:|
| T1 | `result_format_node` 处理 items 为空列表、items[0] 为空 dict、items 中字段不一致 | P0 |
| T2 | CircuitBreaker 三态流转完整测试 | P0 |
| T3 | `tool_select_node` LLM 返回 null / 返回 format error / 返回不存在的 tool name | P0（Step 4 引入时补） |

---

## 5. Step 4 风险预警

### 5.1 Step 4 最容易把哪里搞坏

**最大风险：`tool_select_node` 替换为 LLM 后，参数提取质量不可控。**

当前规则版 `_extract_params_rule_based()` 虽然覆盖有限但行为确定。LLM 替换后可能出现：
- **幻觉参数**：LLM 编造不存在的 SKU 编码填入 `sku_code`
- **参数遗漏**：LLM 忽略 Tool 的必填参数
- **返回格式异常**：LLM 不按 JSON schema 返回

**当前代码对这些问题有一定防御**：
- MCP Server 的 `VALIDATION_ERROR` 可拦截参数错误
- `mcp_call_node` 的 try/except 捕获所有异常
- 参数错误 → `is_retryable=True` → 回退 LocalExecutor

**但缺陷是**：LLM 返回 null（无法选择）→ `selected_tool=""` → `mcp_call_node` 返回 `TOOL_SELECTION_FAILED` → 回退 Local。这个路径是正确的，但**没有区分"LLM 真的无法选择"和"LLM 调用本身失败（API 错误）"**。后者应记录更高级别的告警。

### 5.2 当前结构是否适合接入 LLM Tool Selection

**适合。** `tool_select_node` 是 LangGraph 的一个独立节点，输入输出契约已定义：
- 输入：`question` + `candidate_tool_names`（由 Layer B 提供）
- 输出：`selected_tool` + `tool_arguments`

Step 4 只需替换该节点的内部实现，不需要改动图结构、条件边或其他节点。风险隔离良好。

### 5.3 是否应该先做抽象层

**不需要在 Step 4 前做重抽象。** 当前结构已经足够清晰：

- `tool_filter_node` = Tool Family Router（已完成）
- `tool_select_node` = Tool Selector + Param Extractor（Step 4 替换）
- `mcp_call_node` = Tool Executor（已完成）
- `result_format_node` = Result Mapper（已完成）

Step 4 的作用域仅限于 `tool_select_node` 内部。不需要引入 `ToolSelector` / `ParamExtractor` 等抽象层——这会增加复杂度而目前只有一个实现者（LLM）。

**但有一个例外**：如果 Step 4 要在 `_check_mcp_eligibility`（Layer A）和 `tool_select_node`（Layer C）之间增加一层 **"LLM 也可以 override eligibility"** 的逻辑，请单独设计一个 `_resolve_mcp_decision()` 方法而不是把逻辑散落在 Gateway 的 `execute()` 中。当前建议：Layer A 保持纯规则，Layer C 的 LLM 选择结果如果为 null 则自动回退 Local，不需要 Layer A 和 Layer C 互相 override。

### 5.4 绝对不能直接塞进 graph_mcp.py 的内容

| 禁止项 | 原因 | 应该放在哪 |
|--------|------|----------|
| LLM 调用的重试/超时逻辑 | 属于基础设施，不是图编排逻辑 | `McpExecutor` 或独立的 `LlmToolSelector` |
| MCP 结果缓存 | 跨请求状态，不应由单次图执行管理 | Gateway 层或独立缓存层 |
| Clarification 判断逻辑 | 属于 Phase 3 的 Gateway 前置处理，不是 MCP 图的一部分 | Gateway `execute()` 中的 `_check_clarification()` |
| 多 Tool 并行编排 | Phase 2 明确不做，如果要做应该在 Gateway 层做 fan-out，不是图内部 | Gateway 或 Planner |

---

## 6. 必改项 / 建议项清单

### Blocking Issues（阻塞进入 Step 4）

| # | 问题 | 严重度 | 为什么阻塞 | 建议修复 | 修复时机 |
|---|------|:-----:|-----------|---------|:------:|
| **S1** | `mcp_call_node` 每次调用创建新 `McpClientManager`，并访问私有 `_get_client()` | P0 | Step 4 LLM 调用频率增加后，每个 MCP 请求创建新的 httpx 连接 → 性能退化；访问私有方法破坏封装 | `McpExecutor.__init__` 创建 `McpClientManager` 单例；`mcp_call_node` 通过 `context` 接收 manager；暴露 `call_tool()` 公共方法 | Step 3.2 |
| **S2** | `CircuitBreaker.record_failure()` 导入了 `is_circuit_breaker_error` 但未使用 | P0 | 代码意图模糊，未来维护者可能误以为 breaker 内部做了过滤；实际上过滤在外部(`_execute_with_fallback`)。如果未来有第二个调用方，可能因未过滤而出错 | 将过滤逻辑移入 `record_failure(error_code)`，调用方改为 `breaker.record_failure(error_code)` | Step 3.2 |
| **S3** | `_is_mcp_error_retryable()` 与 `mcp_client.is_retryable_mcp_error()` 功能重叠，且 Gateway 版本多处理了 `mcp_disabled` 和 `sql_security_violation` | P0 | 两处重复定义，未来修改回退规则时容易漏改一处 → 行为不一致 | 将 `mcp_disabled` 和 `sql_security_violation` 加入 `mcp_client._RETRYABLE_ERRORS` 的排除逻辑；Gateway 直接调用 `is_retryable_mcp_error()` | Step 3.2 |

### Improvement Suggestions（可进入 Step 4，但建议优化）

| # | 问题 | 严重度 | 建议 | 建议时机 |
|---|------|:-----:|------|:------:|
| I1 | `_check_mcp_eligibility` 关键词匹配只取第一个命中的 domain（如"入库的商品"可能被 product 抢先匹配） | P2 | 改为收集所有匹配 domain，优先选择更具体的（如 inbound > product） | Phase 3 |
| I2 | Gateway 缺少 `mcp_bypass_reason` 统一字段，区分"未选 MCP"的原因 | P1 | 在 `UnifiedQueryResult` 或日志中增加 `mcp_bypass_reason`（`not_eligible` / `circuit_open` / `unavailable`） | Step 4 |
| I3 | `McpExecutor.is_available()` 每次调用都做 `ping()`（30s 缓存在 McpClientManager 层），但仍会创建新 McpClientManager | P1 | 随 S1 修复一并处理：复用 McpClientManager 实例 | Step 3.2 |
| I4 | CircuitBreaker HALF_OPEN 状态无试探次数限制 | P2 | 增加 `_half_open_attempts` 计数，HALF_OPEN 状态最多允许 1 次试探 | Phase 3 |
| I5 | Gateway 文件 775 行，混合 6 种职责 | P2 | Phase 3 提取 eligibility_policy / circuit_breaker 独立模块 | Phase 3 |
| I6 | 缺少 `mcp_bypass_reason` 统计日志，运维难以区分"MCP 主动不选"和"MCP 选了但失败" | P1 | 在 Gateway 日志中增加 bypass_reason | Step 4 |
| I7 | `result_format_node` 的 items 格式映射依赖 `items[0].keys()` 推断列名——如果第一条 items 缺少某些字段而后续 item 有，列名不完整 | P2 | 收集所有 items 的 keys 的并集 | Phase 3 |

---

## 附录：建议的 Step 3.2 最小修复计划

在进入 Step 4 之前，建议执行一次小修复迭代（预计改动 < 40 行）：

| 修复 | 文件 | 改动 |
|------|------|:---:|
| S1: McpExecutor 持有 McpClientManager 单例 | `data_query_gateway.py` | McpExecutor `__init__` 创建 manager；`execute()` / `is_available()` 复用；`mcp_call_node` 通过 context 接收 client |
| S2: CircuitBreaker.record_failure 接受 error_code 参数 | `data_query_gateway.py` | `record_failure(error_code)` 内部调用 `is_circuit_breaker_error` 过滤 |
| S3: 合并回退判断逻辑到 mcp_client | `mcp_client.py` + `data_query_gateway.py` | Gateway 删除 `_is_mcp_error_retryable`，改为调 `is_retryable_mcp_error` |
| T1: result_format 异常格式测试 | `test_mcp_graph.py` | +15 行 |
| T2: CircuitBreaker 三态流转测试 | `test_gateway.py` | +30 行 |

---

> **审查结论**: 可以进入 Step 4，但建议先执行 Step 3.2（修复 S1/S2/S3，补 T1/T2 测试，预计 1 个回合）。
> **文档版本**: v1.0
> **审查完成时间**: 2026-06-25
