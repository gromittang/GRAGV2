# Phase 2 / Step 5: 集成验收设计与执行规划

> **角色**: 集成验收负责人 / QA Lead + 架构负责人
> **基线**: Phase 2 Step 4.1 完成，104/104 pass
> **目标**: 确认 MCP 主路径可用、回退链正确、零退化

---

## 1. 验收目标

### 1.1 功能验收
确认 MCP 主路径对 15 个预构建 Tool 覆盖的高频查询**真正可用**：
- LLM 能正确选择 Tool + 提取参数
- MCP Server 调用成功返回数据
- 结果格式兼容 QueryPage / OrchestratorPage

### 1.2 兼容性验收
确认 MCP 接入**未破坏**现有功能：
- QueryPage 自然语言查询行为不变
- OrchestratorPage 智能助手数据查询链路不变
- 查询历史、字段翻译、洞察生成行为不变
- `mcp_enabled=False` 时系统行为与 Phase 1 完全一致

### 1.3 回退链验收
确认三级回退链行为正确：
- MCP 不可用 → LocalExecutor 自动接管
- MCP 不适合 → 跳过 MCP → LocalExecutor
- LocalExecutor 失败 → QueryAgentExecutor 兜底
- 不可回退的错误（安全违规/主动关闭）→ 不回退

### 1.4 稳定性 / 容错验收
确认异常场景处理正确：
- MCP Server 宕机/超时/鉴权失败 → 不阻塞服务
- CircuitBreaker 正确熔断和恢复
- 单次查询失败不影响后续查询

### 1.5 效果验收
确认 MCP 方案的实际效果：
- Tool 选择准确率
- 参数提取成功率
- MCP 路径的端到端成功率

---

## 2. 验收范围

| 模块 | 验收内容 | 验收方式 |
|------|---------|:------:|
| `DataQueryGateway` | eligibility 判断、executor 选择、回退编排、后处理 | L2 + L3 |
| `McpExecutor` | graph_mcp 调度、结果映射、is_available | L2 + L3 |
| `graph_mcp.py` | Layer B 候选过滤、Layer C LLM Tool 选择、mcp_call、result_format | L1 + L3 |
| `QueryService.natural_query()` | UnifiedQueryResult → dict 兼容映射 | L2 |
| `dispatch_to_nl2sql` | Gateway 适配器 → Orchestrator 兼容 | L2 |
| 前端返回契约 | columns/rows/total/sql/insight/history_id/source/error | L4 |

---

## 3. 验收指标（量化）

| 指标 | 定义 | 目标 | 测量方式 |
|------|------|:---:|------|
| **MCP 命中率** | 15 个 MCP 目标场景中，实际走 MCP 的比例 | ≥ 80% | L3: 目标场景测试集 |
| **Tool 选择准确率** | LLM 选出的 Tool 与预期 Tool 一致的比例 | ≥ 85% | L3: 人工标注 golden tool |
| **参数提取成功率** | Tool 必填参数全部提取成功的比例 | ≥ 80% | L3: MCP 调用成功即参数正确 |
| **MCP 执行成功率** | MCP 调用后返回 success=true 的比例 | ≥ 90% | L3: MCP 健康时 |
| **端到端成功率** | 所有查询最终返回 success=true 的比例（含回退） | ≥ 95% | L3 |
| **回退率** | MCP 尝试后失败回退 Local 的比例 | < 10% | L3 |
| **黄金 Case 零退化** | Phase 1 12 条黄金 Case 行为不变 | 100% | L2 |
| **平均延迟（MCP 路径）** | Gateway 入口 → 返回的端到端时间 | < 5s | L3 |
| **CircuitBreaker 恢复** | OPEN → HALF_OPEN → CLOSED 状态流转正确 | 100% | L2 |

---

## 4. 测试分层

### L1: 单元测试补强（已在 Step 4.1 完成 → 104/104）
- 当前覆盖已充分，Step 5 不新增 L1 测试

### L2: Gateway 集成测试（mock MCP）
- 需要 MCP Server 不可用的模拟环境
- 验证回退链、eligibility、CircuitBreaker

### L3: Staging 环境真实 MCP 验证
- 需要: MCP Server 在 `:8922` 可访问
- 需要: MySQL 测试库可访问
- 需要: LLM (DeepSeek) 可用
- 核心验收层

### L4: 前端联调 / 手工冒烟
- QueryPage 和 OrchestratorPage 手工回归
- 确认 MCP 结果的 UI 展示正常

---

## 5. 验收用例矩阵

### A. 应该命中 MCP 的问题（P0 — 15 条）

| # | 问题 | 预期 Tool | 预期 source | 关键验证点 |
|---|------|----------|:---------:|-----------|
| A1 | "502620的库存情况" | `query_inventory_by_sku` | mcp | SKU 参数提取 |
| A2 | "06080816仓位有什么货" | `query_inventory_by_location` | mcp | 库位参数提取 |
| A3 | "批次2029084286671708161的库存" | `query_inventory_by_batch` | mcp | 19位批次号提取 |
| A4 | "商品502620的基本信息" | `query_product` | mcp | SKU 参数提取 |
| A5 | "502620的规格和条码" | `query_product_spec` | mcp | 规格查询 |
| A6 | "502620的仓库配置" | `query_product_warehouse_config` | mcp | 配置查询 |
| A7 | "最近的入库单" | `query_inbound_order` | mcp | 无必填参数 |
| A8 | "查询入库单号XXX的明细" | `query_inbound_detail` | mcp | 单号提取 |
| A9 | "最近的出库单" | `query_outbound_order` | mcp | 无必填参数 |
| A10 | "出库单号XXX的明细" | `query_outbound_detail` | mcp | 单号提取 |
| A11 | "各SKU库存总量" | `get_inventory_summary` | mcp | 聚合查询(无实体也 eligible) |
| A12 | "有没有快过期的商品" | `get_stock_warning` | mcp | 分析域(无实体也 eligible) |
| A13 | "哪些库存超过90天没动" | `get_slow_moving_inventory` | mcp | 分析域 |
| A14 | "502620的库存流水" | `query_stock_flow` | mcp | SKU+流水 |
| A15 | "收货验收记录" | `query_receiving_record` | mcp | 入库域 |

### B. 应该跳过 MCP、走 Local 的问题（P0 — 5 条）

| # | 问题 | 预期 source | 跳过原因 |
|---|------|:---------:|------|
| B1 | "库存情况"（无实体） | local | `missing_entity`（inventory domain 需实体） |
| B2 | "帮我看看最近的数据"（模糊） | local | `no_business_keyword` |
| B3 | "对比上月入库和出库的差异"（跨域） | local | LLM 可能选不出合适 Tool → 回退 |
| B4 | "502620 的利润是多少"（无此字段） | local | MCP Tool 不支持 → 回退 |
| B5 | "你好"（闲聊） | local | 不触发任何 domain |

### C. 应该报错 / 不应偷偷回退的问题（P0 — 4 条）

| # | 场景 | 预期行为 |
|---|------|---------|
| C1 | MCP 鉴权失败（API Key 错误） | 回退 Local（首次）+ ERROR 日志 |
| C2 | MCP 返回 SQL 安全违规 | **不回退**，直接返回错误 |
| C3 | `mcp_enabled=False` | 跳过 MCP，走 LocalExecutor |
| C4 | 缺必填参数（LLM 选 Tool 但缺参） | 回退 Local（error_code=tool_validation_failed）|

### D. 服务故障类问题（P0 — 5 条）

| # | 场景 | 预期行为 |
|---|------|---------|
| D1 | MCP Server 进程停止 | MCP 不可用 → 回退 Local（source=local）；CircuitBreaker 计数 |
| D2 | MCP Server 响应超时 | 回退 Local；CircuitBreaker 计数 |
| D3 | 连续 3 次 MCP 失败 | CircuitBreaker OPEN → 后续请求跳过 MCP |
| D4 | CircuitBreaker OPEN 60s 后 | HALF_OPEN → 试探 1 次 → 成功则 CLOSED |
| D5 | 所有 executor 都失败 | success=False, error_code=all_executors_failed |

### E. 回归验证（P0 — 12 条 Phase 1 黄金 Case）

| # | Phase 1 Case | 验证 |
|---|-------------|------|
| E1-E12 | 12 条黄金 Case | 行为与 Phase 1 完全一致（source 可能从 local 变为 mcp，但 success/columns/rows/total/insight 一致） |

---

## 6. 输出物

| 文档 | 内容 |
|------|------|
| `phase2-step5-acceptance-plan.md` | 本文档 — 验收计划 |
| `phase2-step5-acceptance-report.md` | 验收执行后的正式报告 |
| `phase2-step5-test-results.csv` | 每条 Case 的结果记录（case_id / question / expected_source / actual_source / success / latency_ms / notes） |
| `phase2-step5-issues.md` | 发现的缺陷清单（如有） |

---

## 7. Step 5 实施提示词（可直接复制使用）

```text
请以本项目的集成验收负责人 / QA Lead 角色，执行 Phase 2 / Step 5 集成验收。

## 背景
本项目已完成 DataQueryGateway + MCP + Local NL2SQL 回退链的全套接入。
当前代码基线: Phase 2 Step 4.1，单元测试 104/104 pass。
验收计划文档: docs/superpowers/plans/2026-06-25-phase2-step5-acceptance-plan.md

## 你的任务
1. 先阅读验收计划，复述验收目标和范围
2. 确认当前环境是否满足 L3 验收条件（MCP Server :8922、MySQL、LLM 可用）
3. 如环境不满足，请先说明哪些 Case 可以 mock 验证（L2）、哪些必须等环境就绪（L3）
4. 按验收用例矩阵执行验证（优先 P0 Case）
5. 记录每条 Case 的结果
6. 输出正式验收报告

## 验收分层执行顺序
- L2: 先执行 mock 环境可验证的 Case（回退链、CircuitBreaker、eligibility）
- L3: 在有真实 MCP Server 的环境执行 A 类 + D 类 Case
- L4: 前端手工冒烟（如果前端可访问）

## 重要约束
- 如果发现缺陷，不要直接修改生产代码。请将问题记录到 issues 清单
- 只做验收和问题记录，不扩展功能
- 如果 MCP Server 不可用导致无法执行 L3，不要跳过 — 请明确记录哪些 Case 因环境限制未验证
- 每条 Case 记录: case_id / question / expected_source / actual_source / success / latency_ms / 通过/失败 / 备注

## 输出要求
1. 环境检查结果
2. 每条 Case 的执行结果（表格）
3. 指标达成情况（命中率/成功率/回退率等）
4. 发现的缺陷清单
5. 是否建议 Phase 2 验收通过
```

---

> **文档版本**: v1.0
> **下一步**: 将上述提示词发给 Claude 执行 Step 5 集成验收
