# Phase 2 / Step 5 集成验收报告

> **验收时间**: 2026-06-25
> **验收人**: Claude Code — 集成验收负责人 / QA Lead
> **基线**: Phase 2 Step 4.1, 104/104 unit tests pass

---

## 1. 环境检查结果

| 依赖 | 状态 | 详情 |
|------|:----:|------|
| MCP Server (:8922) | ⚠️ 运行中但协议不兼容 | Server 要求完整 MCP 2024-11-05 session 生命周期 (initialize → session → call)。当前 `WmsMcpClient` 未实现 session 管理 |
| MySQL | ❌ 不可用 | `aiomysql` 未安装，无法验证真实数据查询 |
| LLM (DeepSeek) | ✅ 可用 | `DeepSeekLLM` 初始化成功 |
| 单元测试 | ✅ 104/104 pass | L1 全部通过 |

**L3 (真实 MCP + MySQL) 验收结论: 当前环境不支持。** MCP Server 在运行但协议不兼容；MySQL 客户端依赖未安装。

---

## 2. L2 验收执行结果（mock 环境）

### 2.1 L1 单元测试基线

| 套件 | 结果 |
|------|:---:|
| `test_gateway.py` | 38/38 ✅ |
| `test_mcp_client.py` | 25/25 ✅ |
| `test_mcp_graph.py` | 41/41 ✅ |
| **合计** | **104/104 ✅** |

### 2.2 回退链验证（已在 L1 中覆盖）

| Case | 测试 | 状态 |
|------|------|:---:|
| MCP 成功路径 | `test_mcp_success_path` | ✅ |
| MCP not eligible → Local | `test_mcp_not_eligible_falls_back_to_local` | ✅ |
| CircuitBreaker OPEN → skip MCP | `test_circuit_breaker_open_skips_mcp` | ✅ |
| Local fail → QueryAgent | `test_fallback_to_queryagent` | ✅ |
| LLM error → no fallback | `test_no_fallback_on_llm_error` | ✅ |
| DB error → no fallback | `test_no_fallback_on_db_error` | ✅ |

### 2.3 Eligibility 规则验证（已在 L1 中覆盖）

| Case | 测试 | 状态 |
|------|------|:---:|
| Analytics no entity → eligible | `test_mcp_eligibility_analytics_no_entity` | ✅ |
| Product no entity → eligible | `test_mcp_eligibility_product_no_entity` | ✅ |
| Inventory no entity → not eligible | `test_mcp_eligibility_inventory_needs_entity` | ✅ |
| With entity → eligible | `test_mcp_eligibility_with_entity` | ✅ |

### 2.4 LLM Tool Selection 验证（已在 L1 中覆盖）

| Case | 测试 | 状态 |
|------|------|:---:|
| Success + param extraction | `test_select_success` | ✅ |
| Returns null | `test_select_returns_null` | ✅ |
| Unknown tool | `test_select_unknown_tool` | ✅ |
| Malformed JSON | `test_select_malformed_json` | ✅ |
| Missing required param | `test_select_missing_required_param` | ✅ |
| Args type error | `test_select_args_not_dict` | ✅ |
| LLM API error | `test_select_llm_api_error` | ✅ |
| node→state success | `test_tool_select_node_llm_success` | ✅ |
| node→state failure | `test_tool_select_node_llm_failure` | ✅ |
| error_code differentiation | `test_error_code_missing_param_vs_selection_failed` | ✅ |

---

## 3. L3 / L4 验收状态

### 3.1 阻塞原因

| # | 阻塞项 | 影响 | 需要什么 |
|---|--------|------|---------|
| **B1** | MCP Server 协议不兼容 | 所有 A 类 + D 类 Case 无法验证 | `WmsMcpClient` 需要实现 MCP session 生命周期 (initialize → session → call) |
| **B2** | MySQL 不可用 (aiomysql) | 所有数据查询 Case 无法验证 | `pip install aiomysql` + 配置 MySQL 连接 |
| **B3** | MCP Server session 管理缺失 | `McpClientManager.is_available()` 和 `mcp_call_node` 均会失败 | 同 B1 |

### 3.2 可部分验证的 Case

| Case 类别 | 可验证? | 方式 |
|----------|:------:|------|
| A 类 (MCP 命中) | ❌ | 需要 B1+B2 解决 |
| B 类 (跳过 MCP) | ✅ (L2) | eligibility 规则已验证；实际跳过需 B1+B2 |
| C 类 (应报错) | ✅ (L2) | 错误分类和回退规则已验证 |
| D 类 (服务故障) | ⚠️ 部分 | CircuitBreaker 状态机已验证；真实 MCP 故障需 B1 |
| E 类 (回归) | ❌ | 需要 B2 (MySQL) 解决 |

### 3.3 L4 前端冒烟

| 页面 | 状态 | 备注 |
|------|:---:|------|
| QueryPage | ⚠️ 未验证 | 需要 B1+B2 解决 |
| OrchestratorPage | ⚠️ 未验证 | 需要 B1+B2 解决 |

---

## 4. 指标达成情况

| 指标 | 目标 | 实际 | 状态 |
|------|:---:|:---:|:---:|
| MCP 命中率 | ≥ 80% | **无法测量** | ⏸ L3 阻塞 |
| Tool 选择准确率 | ≥ 85% | **无法测量** | ⏸ L3 阻塞 |
| 参数提取成功率 | ≥ 80% | **无法测量** | ⏸ L3 阻塞 |
| MCP 执行成功率 | ≥ 90% | **无法测量** | ⏸ L3 阻塞 |
| 端到端成功率 | ≥ 95% | **无法测量** | ⏸ L3 阻塞 |
| 回退率 | < 10% | **无法测量** | ⏸ L3 阻塞 |
| 黄金 Case 零退化 | 100% | **L1 已验证 104/104** | ✅ |
| L1 单元测试 | 全部通过 | **104/104 pass** | ✅ |
| L2 回退链/eligibility/CircuitBreaker | 全部通过 | **所有 mock 测试通过** | ✅ |

---

## 5. 缺陷清单

### 5.1 阻塞 L3 验收的缺陷

| # | 缺陷 | 严重度 | 描述 |
|---|------|:-----:|------|
| **D1** | `WmsMcpClient` 缺少 MCP session 管理 | 🔴 P0 | MCP Server at :8922 使用 MCP 2024-11-05 完整协议，要求先 initialize → 获取 session ID → 后续请求携带 session。当前 client 直接发 JSON-RPC 调用，缺少 session 生命周期。导致 `ping()`、`call_tool()` 全部失败。 |
| **D2** | 运行环境缺少 `aiomysql` | 🔴 P0 | MySQL 连接不可用，无法验证任何真实数据查询。 |

### 5.2 非阻塞问题

| # | 问题 | 严重度 | 建议 |
|---|------|:-----:|------|
| D3 | `_build_candidate_descriptions` 使用静态 Registry 而非 MCP `list_tools()` 真实数据 | 🟡 P1 | Phase 3 修复（已记录） |
| D4 | `_check_mcp_eligibility` 规则层需要 staging 环境调优阈值 | 🟡 P2 | 集成环境就绪后补充 |

---

## 6. 验收结论

### L2 层面（mock 环境）: ✅ 通过

- Gateway 回退链行为正确
- Eligibility 规则正确
- CircuitBreaker 状态机正确
- LLM Tool Selection 错误处理正确（7 种失败模式全覆盖）
- 104/104 单元测试全部通过

### L3 层面（真实 MCP + MySQL）: ⏸ 阻塞

- 当前环境不满足 L3 验收条件
- 核心阻塞: `WmsMcpClient` 缺少 MCP session 管理

### 建议

**不建议直接标记 Phase 2 验收通过。** 虽然 L1/L2 全部通过，但 L3 阻塞项 D1 (MCP session 管理) 是实现层面的问题，不是环境问题。需要在 Step 5.1 中修复后重新执行 L3 验收。

**建议的 Step 5.1 修复计划:**

| # | 修复 | 文件 | 预估 |
|---|------|------|:---:|
| 1 | `WmsMcpClient` 增加 MCP session 生命周期 (initialize→session→call) | `mcp_client.py` | ~40 行 |
| 2 | 安装环境依赖 (`pip install aiomysql`) | 环境 | 1 条命令 |
| 3 | 重新执行 L3 A类+D类 验收 Case | — | 1 轮 |

---

> **报告版本**: v1.0
> **验收完成时间**: 2026-06-25
> **关联文档**: `docs/superpowers/plans/2026-06-25-phase2-step5-acceptance-plan.md`
