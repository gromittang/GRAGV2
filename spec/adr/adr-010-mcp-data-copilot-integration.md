# ADR-010: MCP Data Copilot 接入 — 数据查询主路径迁移

## 背景

现有 NL2SQL 模块通过 LLM 自由生成 SQL 执行数据查询，存在以下问题：

1. **SQL 准确率不稳定** — LLM 生成的 SQL 可能包含 JOIN 歧义、字段错误、语法问题
2. **prompt 维护成本高** — 需要持续在 prompt 中维护表结构、字段白名单、JOIN 规则、安全约束
3. **复杂查询不可控** — 聚合、预警、跨域查询的结果质量依赖 LLM 单次输出

WMS 系统已部署独立 MCP Data Copilot Server（端口 8922），提供 15 个只读预构建查询 Tool，覆盖库存/商品/入库/出库/分析五大领域。每个 Tool 封装了预编译 SQL、安全校验和参数验证。

## 决策

**引入 MCP Data Copilot 作为数据查询主路径，本地 NL2SQL 降级为回退路径。**

核心架构：

```
Gateway._check_mcp_eligibility (Layer A — 规则)
  ├── eligible=true → McpExecutor (priority=0)
  │   ├── tool_filter_node (Layer B — 规则: domain→候选Tool)
  │   ├── tool_select_node (Layer C — LLM: 选Tool+参数)
  │   ├── mcp_call_node (WmsMcpClient → MCP Server :8922)
  │   └── result_format_node
  │   成功 → 返回
  │   失败 → 回退 LocalExecutor
  └── eligible=false → LocalExecutor (priority=1) → QueryAgentExecutor (priority=2)
```

### 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| **传输协议** | MCP 2024-11-05 Streamable HTTP (SSE + Session) | MCP Server 实际使用的协议，非简化 JSON-RPC |
| **路由策略** | 规则优先 (Layer A/B) + LLM 辅助 (Layer C) | 规则快速、可测试、可解释；LLM 做精细判断 |
| **Tool 选择** | 单 Tool，一次 LLM 调用 | Phase 2 MVP 不做多 Tool 并行编排 |
| **回退策略** | MCP 失败 → Local → QueryAgent | 三级回退，每级有明确的准入和退出条件 |
| **熔断** | 全局 CircuitBreaker (3次失败→OPEN, 60s冷却) | 仅服务级故障计入，业务错误不计入 |
| **execute_sql_readonly** | Phase 2 不自动使用 | 预构建 Tool 优先，动态 SQL 仅作未来扩展点 |
| **结果格式** | MCP items → columns/rows/total 统一映射 | 兼容现有 QueryPage/OrchestratorPage |

## 理由

1. **准确率提升** — MCP Tool 的 SQL 是预编译的，不存在 LLM 生成 SQL 的质量波动
2. **安全增强** — MCP Server 内置安全校验（禁止 DML/DDL、自动 LIMIT、30s 超时），与本地 SQLValidateTool 形成纵深防御
3. **可维护性** — 新增查询类型只需在 MCP Server 注册 Tool，不需要修改 WMSRAGV2 的 prompt 或规则
4. **可回滚** — `mcp_enabled=False` 即可完全回退到 Phase 1 的本地 NL2SQL 路径
5. **可观测** — 每次查询记录 `source` 字段（mcp/local/queryagent），通过 LogsPage "查询追踪" Tab 可视化

## 影响

- **新增模块**: `mcp_client.py`, `graph_mcp.py`, `McpExecutor`, `CircuitBreaker`
- **Gateway 增强**: `_check_mcp_eligibility`, `_build_trace_json`, 三级回退链
- **配置新增**: `mcp_enabled`, `mcp_base_url`, `mcp_api_key`, `mcp_timeout`
- **查询历史扩展**: `query_history` 表新增 `trace_json` 列存储结构化追踪数据
- **前端**: LogsPage 新增 "查询追踪" Tab；QueryPage 响应新增 `source` 字段和 `X-Query-Source` 响应头
- **依赖新增**: `httpx` (MCP 客户端)
- **MCP Server 依赖**: 独立部署在 :8922，WMSRAGV2 通过网络调用

## 替代方案

| 方案 | 缺点 |
|------|------|
| 仅优化本地 NL2SQL prompt | prompt 优化有天花板，无法消除 LLM 生成 SQL 的不确定性 |
| 直接用 `execute_sql_readonly` | 需要 LLM 生成 SQL，与本地 NL2SQL 有相同问题 |
| MCP 替代全部本地 NL2SQL | MCP Server 不可用时完全不可用，无回退路径 |
| 多 Tool 并行编排 | Phase 2 MVP 复杂度太高，单 Tool 已覆盖 80% 高频场景 |

## 技术债务

1. `_build_candidate_descriptions` 使用静态 Tool Registry，未使用 MCP Server `list_tools()` 真实数据 — Phase 3 修复
2. `conftest.py` 的 `sys.modules` mock 脆弱，模块重命名后需同步更新 — Phase 3 Docker 化测试环境
3. Gateway 文件 ~770 行，需拆分 — Phase 3 提取 `circuit_breaker.py` 和 `eligibility_policy.py`

---

> **状态**: 已实施 (Phase 2 complete)
> **实施时间**: 2026-06-24 ~ 2026-06-25
> **测试基线**: 104/104 pass, MCP L3 验收 7/7 通过
> **关联文档**:
> - `docs/data-copilot-integration-guide.md` (MCP Server 接入说明 v1.1)
> - `docs/superpowers/plans/2026-06-25-phase2-retrospective.md`
> - `docs/superpowers/plans/2026-06-24-phase2-mcp-mvp-design.md`
