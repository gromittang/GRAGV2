# Phase 2 / Step 4: LLM Tool Selection 实施计划

> **状态**: 冻结设计 — 审核后进入编码
> **基线**:
> - Phase 2 设计: `docs/superpowers/plans/2026-06-24-phase2-mcp-mvp-design.md` (v1.1)
> - Step 3.2 完成: `docs/superpowers/plans/2026-06-25-stage-gate-review.md`
> - 设计决策: 上一轮 LLM Tool Selection 设计讨论 (2026-06-25)
> **当前测试基线**: 94/94 pass

---

## 1. 目标与边界

### 1.1 目标

将 `tool_select_node` 从当前的规则版选择器替换为 **LLM Tool Selection**，实现：

1. **LLM 从候选 Tool 集中选择最合适的 1 个 Tool** — 替代当前的"盲选第一个"逻辑
2. **LLM 从用户问题中提取参数** — 替代当前的 `_extract_params_rule_based()` 正则提取
3. **LLM 无法选择时正确回退 LocalExecutor** — 保持现有回退链路不变
4. **McpExecutor 调用链不受影响** — 只替换 `tool_select_node` 的内部实现

### 1.2 Phase 2 Step 4 明确不做什么

| 不做 | 原因 |
|------|------|
| ❌ 不做 Clarification — LLM 选不出来直接回退，不追问 | Phase 3 |
| ❌ 不做 `execute_sql_readonly` 自动兜底 | Phase 2 约束，主路径是 15 个预构建 Tool |
| ❌ 不做 LLM 调用失败的重试/超时策略优化 | 基础设施层职责，Phase 3 |
| ❌ 不做 LLM 返回结果的缓存 | 过早优化 |
| ❌ 不修改 Gateway 的路由/回退逻辑 | 只改 graph_mcp |
| ❌ 不修改前端 | Phase 4 |

---

## 2. 设计决策回顾

| # | 决策 | 结论 |
|---|------|------|
| D1 | LLM Tool Selection 放哪里 | `graph_mcp.py` 内部，提取 `_LlmToolSelector` 辅助类（~60行），不建新文件 |
| D2 | 参数提取和澄清是否分开 | Step 4 一次 LLM 调用同时完成 Tool 选择 + 参数提取；澄清是 Phase 3 的独立节点 |
| D3 | 多候选决策策略 | 一次 LLM 调用，Prompt 写清优先级规则，让其自主判断 |
| D4 | LLM 选不出来 → 回退还是澄清 | Phase 2 回退 LocalExecutor（`tool_selection_failed → is_retryable=True`） |
| D5 | 空结果 vs 不支持 | 空结果 = `success=True` 不回退；不支持 = 回退 Local。当前已正确实现，Step 4 不动 |

---

## 3. 架构设计

### 3.1 `_LlmToolSelector` 类

```text
位置: graph_mcp.py 内部（tool_select_node 之前）

class _LlmToolSelector:
    def __init__(self, llm=None):
        self._llm = llm or get_llm()

    def select(self, question: str, candidates: list[str],
               domain_hint: str) -> ToolSelectionResult:
        """
        1. 构建候选 Tool 描述文本（从 Tool Registry 查 inputSchema）
        2. 填充 MCP_TOOL_SELECT_PROMPT
        3. 调用 LLM
        4. 解析返回的 JSON
        5. 校验: tool_name 在 candidates 中
        6. 返回 ToolSelectionResult
        """

@dataclass
class ToolSelectionResult:
    success: bool           # LLM 是否成功选择
    tool_name: str          # 选中的 Tool 名（失败时为空）
    arguments: dict         # 提取的参数
    confidence: float       # LLM 置信度 (0.0-1.0)，可选
    reason: str             # 失败原因（Phase 3 用于区分澄清/回退）
```

### 3.2 改造后的 `tool_select_node`

```text
async def tool_select_node(state: MCPAgentState) -> dict:
    candidates = state.get("candidate_tool_names", [])
    question = state.get("question", "")
    domain_hint = state.get("domain_hint", "")

    if not candidates:
        return {"selected_tool": "", "tool_arguments": {},
                "error": "tool_select_node: 无候选 Tool"}

    selector = _get_llm_selector()  # 单例，复用 LLM 连接
    result = selector.select(question, candidates, domain_hint)

    if result.success:
        return {"selected_tool": result.tool_name,
                "tool_arguments": result.arguments,
                "confidence": result.confidence}
    else:
        return {"selected_tool": "",
                "tool_arguments": {},
                "error": f"LLM Tool Selection 失败: {result.reason}",
                "selection_reason": result.reason}  # Phase 3 使用
```

### 3.3 改造后的 `MCP_TOOL_SELECT_PROMPT`

```text
System:
你是 WMS 数据查询 Tool 选择器。根据用户问题，从候选 Tool 中选择最合适的 **1 个**。

规则:
1. 只从候选列表中选，不要编造 Tool 名称
2. 参数值必须从用户问题中提取，不要编造
3. 优先选择必填参数能从问题中提取到的 Tool
4. 如果多个 Tool 都能匹配，选最具体的
5. 如果必填参数无法从问题中提取，返回 null

候选 Tool 列表（已按领域过滤）:
{tool_descriptions}

用户问题: {user_question}
领域提示: {domain_hint}

输出 JSON:
{{"tool": "<tool_name>", "args": {{"param1": "value1", ...}}}}
如果无法选择: null
```

变化（相比 Step 2 占位 Prompt）：
- 增加了"必填参数提取优先级"规则
- 增加了 null 场景说明
- 格式不变（单 Tool JSON 对象）

---

## 4. 修改文件清单

### 4.1 修改文件

| 文件 | 变更 | 说明 |
|------|------|------|
| `backend/app/agents/graph_mcp.py` | **修改** | 新增 `_LlmToolSelector` 类 + `ToolSelectionResult` dataclass；重写 `tool_select_node`；删除 `_extract_params_rule_based()`；更新文档注释 |
| `backend/app/agents/prompts_sql.py` | **修改** | 更新 `MCP_TOOL_SELECT_PROMPT`（增加优先级规则、null 说明） |
| `backend/tests/test_mcp_graph.py` | **修改** | 更新 `tool_select_node` 相关测试；新增 LLM 选择成功/失败/null 场景测试 |

### 4.2 不修改的文件

| 文件 | 原因 |
|------|------|
| `data_query_gateway.py` | McpExecutor 接收 graph 返回的方式不变 —只变 graph 内部实现 |
| `mcp_client.py` | 不变 |
| `query_service.py` / `dispatch.py` | 不变 |
| `agent_state.py` | `MCPAgentState` 字段不变（`selected_tool`/`tool_arguments` 保留） |
| 所有测试文件（除 test_mcp_graph.py） | 不变 |

---

## 5. `_LlmToolSelector` 实现细节

### 5.1 `select()` 方法流程

```text
def select(question, candidates, domain_hint) → ToolSelectionResult:

    # 1. 构建候选 Tool 描述
    tool_descriptions = _build_candidate_descriptions(candidates)
    # 输出格式:
    #   • query_inventory_by_sku: 按 SKU 查库存分布 [必填: sku_code]
    #     参数: sku_code: string *必填*, limit: integer — 返回行数上限

    # 2. 填充 Prompt
    prompt = MCP_TOOL_SELECT_PROMPT.format(
        tool_descriptions=tool_descriptions,
        user_question=question,
        domain_hint=domain_hint,
    )

    # 3. 调用 LLM
    response = self._llm.invoke(prompt)
    content = response.content if hasattr(response, 'content') else str(response)

    # 4. 解析 JSON
    import re, json
    json_match = re.search(r'\{[\s\S]*\}', content)
    if not json_match:
        return ToolSelectionResult(success=False, reason="LLM 返回格式异常(非JSON)")

    parsed = json.loads(json_match.group(0))

    # 5. 校验
    tool_name = parsed.get("tool", "")
    if not tool_name:
        return ToolSelectionResult(success=False, reason="LLM 无法选择合适的 Tool")

    if tool_name not in candidates:
        _log.warning("LLM 选择了不在候选列表中的 Tool: %s, candidates=%s",
                     tool_name, candidates)
        return ToolSelectionResult(success=False,
                                   reason=f"LLM 选择了未知 Tool: {tool_name}")

    # 6. 返回
    return ToolSelectionResult(
        success=True,
        tool_name=tool_name,
        arguments=parsed.get("args", {}),
        confidence=1.0,
    )
```

### 5.2 `_build_candidate_descriptions()` 辅助函数

从 Tool Registry 中提取候选 Tool 的描述和 inputSchema，格式化为 Prompt 友好文本。

```text
def _build_candidate_descriptions(candidate_names: list[str]) -> str:
    lines = []
    for name in candidate_names:
        reg = _TOOL_BY_NAME.get(name, {})
        desc = reg.get("description", name)
        schema = reg.get("input_schema", {})
        required = schema.get("required", [])
        params = []
        for pname, pinfo in schema.get("properties", {}).items():
            req_mark = " *必填*" if pname in required else ""
            params.append(f"{pname}: {pinfo.get('type', 'any')}{req_mark}")
        lines.append(f"• {name}: {desc}")
        if params:
            lines.append(f"  参数: {', '.join(params)}")
        if required:
            lines.append(f"  必填: {', '.join(required)}")
    return "\n".join(lines)
```

> **注意**: 当前 Tool Registry 的 Tool 条目只有 `name`/`domain`/`family`，没有 `description` 和 `inputSchema`。需要在 Registry 中补充这些信息（从 MCP Guide 第 2 节抄录 15 个 Tool 的 description 和必填参数信息），或改为从 `McpClientManager.list_tools()` 获取真实 Tool 描述。

**建议 Step 4 采用混合方案**：
1. 优先从 `state["tool_registry_raw"]`（McpExecutor 可以预先调 `list_tools()` 获取真实描述）
2. Registry 中的 `description`/`inputSchema` 作为 fallback
3. `McpExecutor.execute()` 中已传 `"tool_registry_raw": []` — Step 4 改为调用 `self._mcp_mgr.get_tools()` 填充

### 5.3 单例管理

```text
_llm_selector: Optional[_LlmToolSelector] = None

def _get_llm_selector() -> _LlmToolSelector:
    global _llm_selector
    if _llm_selector is None:
        _llm_selector = _LlmToolSelector()
    return _llm_selector
```

复用 LLM 连接，避免每次 tool_select_node 执行时创建新的 LLM 实例。

---

## 6. 删除内容

| 删除项 | 文件 | 原因 |
|--------|------|------|
| `_extract_params_rule_based()` | `graph_mcp.py` | LLM 替代正则参数提取 |
| 旧版 `tool_select_node` 中的规则选择逻辑 | `graph_mcp.py` | 完全替换为 `_LlmToolSelector.select()` |

> `_extract_params_rule_based()` 的调用方仅 `tool_select_node` 一处，删除安全。

---

## 7. 测试计划

### 7.1 新增测试

| # | 测试 | 覆盖场景 |
|---|------|---------|
| T1 | `test_llm_selector_success` | mock LLM 返回正确 JSON → `ToolSelectionResult.success=True` |
| T2 | `test_llm_selector_returns_null` | mock LLM 返回 `null` → `success=False, reason` 非空 |
| T3 | `test_llm_selector_unknown_tool` | mock LLM 返回不在候选列表中的 Tool → `success=False` |
| T4 | `test_llm_selector_malformed_json` | mock LLM 返回非 JSON → `success=False` |
| T5 | `test_llm_selector_extracts_params` | 验证 LLM 返回的 `args` 被正确透传 |
| T6 | `test_tool_select_node_with_llm_success` | 端到端: tool_select_node 调用 LLM → 正确映射 state |
| T7 | `test_tool_select_node_with_llm_failure` | LLM 失败 → `selected_tool="", error` 非空 |

### 7.2 修改的现有测试

| 测试 | 变更 |
|------|------|
| `test_tool_select_node_step3_rule` | **删除** — 规则版选择器已移除 |
| `test_tool_select_node_empty_candidates` | 保留 — 逻辑不变（无候选 → 不调 LLM，直接返回 error） |

### 7.3 不变测试

- `test_mcp_client.py` 全部 25 条
- `test_gateway.py` 全部 38 条（Gateway 不感知 tool_select_node 内部变化）
- `test_mcp_graph.py` 中 Tool Registry / tool_filter / mcp_call / result_format 相关测试全部保留

---

## 8. 实施顺序（2 个小步）

### Step 4a: `_LlmToolSelector` + `_build_candidate_descriptions`

| 项目 | 内容 |
|------|------|
| **改哪些文件** | `graph_mcp.py`（新增 `ToolSelectionResult`、`_LlmToolSelector`、`_build_candidate_descriptions`、`_get_llm_selector`）；Tool Registry 补充 `description`/`inputSchema`；`prompts_sql.py`（更新 `MCP_TOOL_SELECT_PROMPT`） |
| **不改什么** | 不改 `tool_select_node`（仍用规则版，但增加注释标记） |
| **验收点** | `_LlmToolSelector.select()` 可通过 mock LLM 独立测试；`_build_candidate_descriptions` 格式化输出正确 |
| **风险点** | Tool Registry 补充信息来自 MCP Guide 文档，可能与真实 MCP Server 返回不一致 → 混合方案：优先用真实 `list_tools()` 结果 |

### Step 4b: 替换 `tool_select_node` + 清理

| 项目 | 内容 |
|------|------|
| **改哪些文件** | `graph_mcp.py`（重写 `tool_select_node`；删除 `_extract_params_rule_based`）；`McpExecutor.execute()`（填充 `tool_registry_raw` 为真实 Tool 列表） |
| **不改什么** | Gateway、mcp_client、其他模块 |
| **验收点** | `tool_select_node` 通过 mock LLM 返回正确 state；L1+L2 全部通过；Phase 1 黄金 Case 无退化 |
| **风险点** | LLM Prompt 质量 → 需要在 staging 环境用真实 LLM 调优 |

---

## 9. 验收标准

| 标准 | 目标 | 测量方式 |
|------|------|---------|
| LLM Tool 选择准确率 | ≥ 85%（在 15 类高频查询中选对 Tool） | E2E 测试集 |
| LLM 返回 `null` 时正确回退 | 100%（回退到 LocalExecutor） | mock LLM 返回 null |
| LLM 返回非法 Tool 名时拒绝 | 100%（不调用 MCP，直接回退） | mock LLM 返回虚假 Tool |
| Phase 1+2 回归 | 94 条测试无退化 | 全量测试 |

---

## 10. 风险与缓解

| 风险 | 严重度 | 缓解 |
|------|:-----:|------|
| LLM Prompt 质量不足，选择准确率低 | 中 | staging 环境用真实 MCP Tool 列表调优 prompt；Phase 2 目标 ≥ 85% |
| LLM 返回的 JSON 格式不稳定 | 中 | `_LlmToolSelector.select()` 内有格式校验 + try/except；格式异常 → 回退 Local |
| LLM 编造参数值（幻觉 SKU） | 低 | MCP Server 的 `VALIDATION_ERROR` 可拦截 → 回退 Local；不影响数据安全 |
| Tool Registry 信息不完整 | 中 | 混合方案：优先真实 `list_tools()`，Registry 作为 fallback |
| LLM 调用增加延迟（~2s） | 低 | 仅 MCP 路径增加一次 LLM 调用；失败时回退 Local（也有 LLM 调用）；整体延迟不显著增加 |

---

> **文档版本**: v1.0
> **设计完成时间**: 2026-06-25
> **关联文档**:
> - `docs/superpowers/plans/2026-06-24-phase2-mcp-mvp-design.md`
> - `docs/superpowers/plans/2026-06-25-stage-gate-review.md`
> **下一步**: 审核设计，确认后进入 Step 4a 编码
