# WMS MCP Server — Data Copilot 接入说明

> **版本**: 1.1.0 (2026-06-25 修订)
> **目标读者**: Knowledge Base / Data Copilot 项目开发者
> **前置要求**: Python 3.11+, `httpx`, 可访问 WMS MCP Server 的网络环境
>
> **v1.1 修订内容**:
> - 第 1 节: 补充 MCP 2024-11-05 session 生命周期、SSE 响应格式、structuredContent 说明
> - 第 4 节: 重写 Python Client 为实际异步实现 (async/await + session 握手 + SSE 解析)
> - 第 7 节: 新增 session/SSE 相关错误排查

---

## 目录

1. [MCP Server 信息](#1-mcp-server-信息)
2. [MCP Tool 清单（附参数和返回格式）](#2-mcp-tool-清单)
3. [HTTP 调用示例](#3-http-调用示例)
4. [Python MCP Client 封装](#4-python-mcp-client-封装)
5. [LangChain / LlamaIndex 接入](#5-langchain--llamaindex-接入)
6. [Agent 调用流程示意](#6-agent-调用流程示意)
7. [常见错误与排查](#7-常见错误与排查)

---

## 1. MCP Server 信息

### 1.1 基本信息

| 项目 | 值 |
|------|-----|
| **Server 名称** | `wms-mcp-server` |
| **Server 说明** | Enterprise WMS MCP Server — read-only query tools for Data Copilot |
| **版本** | `1.0.0-alpha` |
| **传输协议** | MCP 2024-11-05 Streamable HTTP（[规范](https://spec.modelcontextprotocol.io/)） |
| **响应格式** | SSE (Server-Sent Events): `event: message\ndata: {json}\n\n` |
| **数据格式** | JSON-RPC 2.0 |
| **认证方式** | `X-API-Key` 请求头（每请求必带） |

### 1.2 URL

| 环境 | MCP 端点 |
|------|---------|
| 开发 | `http://localhost:8922/mcp` |
| 生产 | `http://<wms-server-host>:8922/mcp` |

> **注意**: 所有 MCP 请求都是 **POST** 到这个单一 URL。不同的操作（list tools、call tool）通过 JSON-RPC 的 `method` 字段区分。

### 1.3 Session 生命周期

MCP 2024-11-05 要求每个客户端在调用 Tool 前完成三步握手：

```
1. initialize → Server 返回 Mcp-Session-Id header + 能力声明（SSE 格式）
2. notifications/initialized → 客户端确认 session 就绪
3. 后续所有请求携带 Mcp-Session-Id header → 调用 tools/call 等
```

**请求头要求**:
- `Content-Type: application/json`
- `Accept: application/json, text/event-stream`（必须同时接受两种格式）
- `X-API-Key: <your-api-key>`（认证，每请求必带）
- `Mcp-Session-Id: <session-id>`（initialize 之后的所有请求必须携带）

### 1.4 响应格式

Tool 调用成功时的两种响应格式：

**新格式（MCP 2024-11-05）** — 通过 `structuredContent` 返回:
```json
{
  "content": [{"type": "text", "text": "..."}],
  "structuredContent": {"total": 23, "items": [...]},
  "isError": false
}
```

**旧格式（直接返回）** — 部分 Tool 直接返回数据:
```json
{"total": 23, "limit": 100, "items": [...]}
```

**错误格式**:
```json
{"content": [{"type": "text", "text": "Error calling tool..."}], "isError": true}
```

客户端应同时兼容新旧两种格式：优先提取 `structuredContent`，否则使用原始 result。

### 1.5 认证

每个 HTTP 请求必须在请求头中携带 API Key：

```
X-API-Key: <your-api-key>
```

**错误码**：

| HTTP 状态码 | 含义 |
|:----------:|------|
| 401 | 缺少 `X-API-Key` 请求头 |
| 403 | API Key 存在但无效 |

> 如果服务没有配置任何 API Key（仅限开发环境），则跳过认证。但生产环境强制要求。

### 1.6 健康检查

可以通过 MCP Tool 检测服务是否可用：

- **`ping`**: 轻量检查，返回 `{"status": "ok"}` — 只要服务进程在运行就成功
- **`health`**: 深度检查，验证数据库连通性，返回 `{"status": "healthy", "db": "connected", "version": "1.0.0-alpha"}`

---

## 2. MCP Tool 清单

> 所有 Tool 均为**只读**（`readOnlyHint=True`），不会修改数据库。

### 通用返回格式

所有分页类 Tool 返回统一的 JSON 结构：

```json
{
  "total": 23,
  "limit": 100,
  "offset": 0,
  "items": [ /* 数据行数组 */ ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `total` | `int` | 本次返回的行数（非全局总数） |
| `limit` | `int` | 请求时的 limit 值 |
| `offset` | `int` | 请求时的 offset 值 |
| `items` | `array<object>` | 数据行列表，每行是一个 dict |

`limit` 会被 clamp 到 `[1, 5000]` 范围，`offset` 最小为 `0`。

### 2.1 库存查询 (Inventory)

#### `query_inventory_by_sku` — 按 SKU 查库存

查询某商品的库存分布情况，包括在各仓位/批次的数量。默认附带拣货位信息。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:--:|--------|------|
| `sku_code` | `string` | ✅ | — | 商品编码 |
| `org_code` | `string` | — | `null` | 物流组织 |
| `store_code` | `string` | — | `null` | 仓库 (`01`=良品, `02`=不良品) |
| `location_code` | `string` | — | `null` | 库位编码 |
| `log_area_code` | `string` | — | `null` | 物理大区（需 `include_pick_location=True`） |
| `batch_no` | `string` | — | `null` | 批次号（19位Snowflake ID） |
| `include_pick_location` | `boolean` | — | `true` | 是否 JOIN 拣货位表 |
| `include_zero_stock` | `boolean` | — | `false` | 是否包含零库存行 |
| `limit` | `integer` | — | `100` | 返回行数上限 |
| `offset` | `integer` | — | `0` | 分页偏移 |

**返回行字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `store_code` | `string` | 仓库 |
| `plu_code` | `string` | 商品编码 |
| `plu_ex_code` | `string` | 商品扩展码（`*`=主码） |
| `location_code` | `string` | 库位 |
| `batch_no` | `string` | 批次号 |
| `mannu_date` | `string` | 生产日期 (YYYY-MM-DD) |
| `due_date` | `string` | 到期日期 (YYYY-MM-DD) |
| `pur_date` | `string` | 进货日期 (YYYY-MM-DD) |
| `stork_count` | `float` | 库存数量 |
| `store_status` | `string` | 库存状态 (`0`=正常) |
| `owner_org_code` | `string` | 货主组织 |
| `bar_code` | `string` | 条码 |
| `logistics_code` | `string` | 物流码 |
| `log_area_code` | `string` | 物理大区（仅 `include_pick_location=True`） |
| `shelf_code` | `string` | 货架号（仅 `include_pick_location=True`） |

<details>
<summary>返回示例</summary>

```json
{
  "total": 1,
  "limit": 100,
  "offset": 0,
  "items": [
    {
      "store_code": "01",
      "plu_code": "502620",
      "plu_ex_code": "*",
      "location_code": "06080816",
      "batch_no": "2029084286671708161",
      "mannu_date": "2024-06-01",
      "due_date": "2025-12-31",
      "pur_date": "2024-07-15",
      "stork_count": 1452.0,
      "store_status": "0",
      "owner_org_code": "WL01",
      "bar_code": "6901234567890",
      "logistics_code": "L20240601",
      "log_area_code": "901",
      "shelf_code": "A-03-05"
    }
  ]
}
```
</details>

---

#### `query_inventory_by_location` — 按仓位查库存

查看指定仓位下所有商品的库存情况。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:--:|--------|------|
| `location_code` | `string` | ✅ | — | 库位编码 |
| `org_code` | `string` | — | `null` | 物流组织 |
| `store_code` | `string` | — | `null` | 仓库 |
| `log_area_code` | `string` | — | `null` | 物理大区 |
| `include_pick_location` | `boolean` | — | `true` | 是否 JOIN 拣货位表 |
| `include_zero_stock` | `boolean` | — | `false` | 是否包含零库存行 |
| `limit` | `integer` | — | `100` | 返回行数上限 |
| `offset` | `integer` | — | `0` | 分页偏移 |

**返回行字段**: 与 `query_inventory_by_sku` 相同。

---

#### `query_inventory_by_batch` — 按批次号查库存

查询指定批次的所有商品库存。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:--:|--------|------|
| `batch_no` | `string` | ✅ | — | 批次号（19位Snowflake ID） |
| `sku_code` | `string` | — | `null` | 可选：限定商品 |
| `org_code` | `string` | — | `null` | 物流组织 |
| `store_code` | `string` | — | `null` | 仓库 |
| `include_pick_location` | `boolean` | — | `true` | 是否 JOIN 拣货位表 |
| `include_zero_stock` | `boolean` | — | `false` | 是否包含零库存行 |
| `limit` | `integer` | — | `100` | 返回行数上限 |
| `offset` | `integer` | — | `0` | 分页偏移 |

**返回行字段**: 与 `query_inventory_by_sku` 相同。

---

### 2.2 商品查询 (Product)

#### `query_product` — 商品主数据

查询商品基本信息，含品牌名和品类名（已 JOIN）。至少提供一个查询条件，否则返回所有有效商品。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:--:|--------|------|
| `sku_code` | `string` | — | `null` | 商品编码（精确匹配） |
| `sku_name` | `string` | — | `null` | 商品名称（LIKE 模糊，如 `"牛奶"`） |
| `bar_code` | `string` | — | `null` | 条码 |
| `brand_code` | `string` | — | `null` | 品牌编码 |
| `cls_code` | `string` | — | `null` | 品类编码 |
| `status` | `string` | — | `"1"` | 状态 (`1`=正常, `0`=未启用, `2`=预淘汰, `3`=淘汰) |
| `limit` | `integer` | — | `100` | 返回行数上限 |
| `offset` | `integer` | — | `0` | 分页偏移 |

**返回行字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `plu_code` | `string` | 商品编码 |
| `plu_name` | `string` | 商品名称 |
| `plu_unit` | `string` | 单位 |
| `spec_desc` | `string` | 规格描述 |
| `qa_days` | `integer` | 保质期天数 |
| `weight` | `float` | 重量 |
| `bar_code` | `string` | 主条码 |
| `biz_status` | `string` | 业务状态 |
| `brand_name` | `string` | 品牌名（来自 `cob_brand`） |
| `cls_name` | `string` | 品类名（来自 `cob_cls`） |

---

#### `query_product_spec` — 商品规格详情

查询商品的包装层级和条码列表。一个 SKU 可能有多条包装记录和多个条码。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:--:|--------|------|
| `sku_code` | `string` | ✅ | — | 商品编码 |
| `limit` | `integer` | — | `100` | 返回行数上限 |
| `offset` | `integer` | — | `0` | 分页偏移 |

**返回行字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `plu_code` | `string` | 商品编码 |
| `plu_name` | `string` | 商品名称 |
| `plu_unit` | `string` | 基本单位 |
| `spec_desc` | `string` | 规格描述 |
| `qa_days` | `integer` | 保质期天数 |
| `weight` | `float` | 重量 |
| `bar_code` | `string` | 主条码 |
| `biz_status` | `string` | 状态 |
| `pack_unit` | `string` | 包装单位 |
| `pack_qty` | `float` | 包装数量 |
| `pack_spec` | `string` | 包装规格 |
| `pack_bar_code` | `string` | 包装条码 |
| `is_base_ware` | `string` | 是否基本包装 (`1`=是) |
| `is_dist_pack` | `string` | 是否配送包装 |
| `is_pur_pack` | `string` | 是否采购包装 |
| `alt_bar_code` | `string` | 替代条码（来自 `cob_plu_bars`） |
| `bar_type` | `string` | 条码类型 |

> **注意**: 返回行数 = 包装记录数 × 条码记录数。如果一个 SKU 有 3 条包装 + 2 个条码，会返回最多 6 行（LEFT JOIN 笛卡尔积），所以给定了 `limit` 和 `offset`。

---

#### `query_product_warehouse_config` — 商品仓库配置

查询商品在仓库中的设置（批次处理方式、抽检要求）和补货策略（拣货位、补货警戒数）。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:--:|--------|------|
| `sku_code` | `string` | ✅ | — | 商品编码 |
| `org_code` | `string` | — | `null` | 物流组织 |
| `log_area_code` | `string` | — | `null` | 物理大区 |

**返回行字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `plu_code` | `string` | 商品编码 |
| `plu_name` | `string` | 商品名称 |
| `batch_type` | `string` | 批次处理方式 (`1`=按批次管理, `0`=不管理) |
| `need_spot` | `string` | 是否抽检 (`0`=需要, `1`=免检) |
| `location_code` | `string` | 拣货位 |
| `log_area_code` | `string` | 物理大区 |
| `repl_low_count` | `float` | 补货最低数量 |
| `repl_max_count` | `float` | 补货最高数量 |
| `put_more_count` | `float` | 最大存放量 |

---

### 2.3 入库查询 (Inbound)

#### `query_inbound_order` — 入库单头

查询入库单主信息。所有日期字段自动从 UTC 转换为 UTC+8。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:--:|--------|------|
| `bill_no` | `string` | — | `null` | 入库单号（精确匹配） |
| `org_code` | `string` | — | `null` | 物流组织 |
| `store_code` | `string` | — | `null` | 仓库 |
| `supplier_code` | `string` | — | `null` | 供应商编码 |
| `date_from` | `string` | — | `null` | 开始日期 `YYYY-MM-DD` |
| `date_to` | `string` | — | `null` | 结束日期 `YYYY-MM-DD` |
| `bill_type` | `string` | — | `null` | 业务类型（如 `PURCHASE`） |
| `status` | `string` | — | `null` | 审核状态 (`0`=未审核, `1`=已审核, `2`=已拒绝) |
| `limit` | `integer` | — | `100` | 返回行数上限 |
| `offset` | `integer` | — | `0` | 分页偏移 |

**返回行字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `bill_no` | `string` | 入库单号 |
| `make_date` | `datetime` | 制单时间（已转 UTC+8） |
| `org_code` | `string` | 组织 |
| `store_code` | `string` | 仓库 |
| `owner_org_code` | `string` | 货主 |
| `busi_type` | `string` | 业务类型 |
| `in_ware_type` | `string` | 入库类型 |
| `pur_voucher` | `string` | 采购凭证号 |
| `remark` | `string` | 备注 |

---

#### `query_inbound_detail` — 入库单明细

按入库单号查询明细行。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:--:|--------|------|
| `bill_no` | `string` | ✅ | — | 入库单号 |
| `limit` | `integer` | — | `200` | 返回行数上限（明细通常较多，默认 200） |
| `offset` | `integer` | — | `0` | 分页偏移 |

**返回行字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `bill_no` | `string` | 入库单号 |
| `serial_no` | `integer` | 行号 |
| `plu_code` | `string` | 商品编码 |
| `plu_ex_code` | `string` | 扩展码 |
| `in_ware_count` | `float` | 入库数量 |
| `location_code` | `string` | 目标库位 |
| `batch_no` | `string` | 批次号 |

---

#### `query_receiving_record` — 收货验收记录

查询收货验收单（预约单→验收单的对应关系）。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:--:|--------|------|
| `org_code` | `string` | — | `null` | 物流组织 |
| `store_code` | `string` | — | `null` | 仓库（映射到 `stock_code` 列） |
| `supplier_code` | `string` | — | `null` | 供应商编码 |
| `date_from` | `string` | — | `null` | 开始日期 `YYYY-MM-DD` |
| `date_to` | `string` | — | `null` | 结束日期 `YYYY-MM-DD` |
| `status` | `string` | — | `null` | 执行状态 (`0`=未执行, `1`=执行中, `2`=已完成) |
| `limit` | `integer` | — | `100` | 返回行数上限 |
| `offset` | `integer` | — | `0` | 分页偏移 |

**返回行字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `bill_no` | `string` | 验收单号 |
| `org_code` | `string` | 组织 |
| `stock_code` | `string` | 仓库编码（列名是 `stock_code`） |
| `sup_code` | `string` | 供应商编码 |
| `make_date_local` | `datetime` | 制单时间（已转 UTC+8） |
| `status` | `string` | 执行状态 |
| `remark` | `string` | 备注 |
| `serial_no` | `integer` | 行号 |
| `plu_code` | `string` | 商品编码 |
| `plu_ex_code` | `string` | 扩展码 |
| `real_count` | `float` | 实收数量 |
| `accept_count` | `float` | 合格数量 |
| `pur_price` | `float` | 采购单价 |

---

### 2.4 出库查询 (Outbound)

#### `query_outbound_order` — 出库单头

查询出库单主信息，左关联配送计划表获取 ERP 单据号。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:--:|--------|------|
| `bill_no` | `string` | — | `null` | 出库单号（精确匹配） |
| `org_code` | `string` | — | `null` | 物流组织 |
| `store_code` | `string` | — | `null` | 仓库 |
| `shop_code` | `string` | — | `null` | 收货单位编码 |
| `date_from` | `string` | — | `null` | 开始日期 `YYYY-MM-DD` |
| `date_to` | `string` | — | `null` | 结束日期 `YYYY-MM-DD` |
| `wave_code` | `string` | — | `null` | 波次号 |
| `out_ware_type` | `string` | — | `null` | 出库类型 (`0`=拣货建议) |
| `limit` | `integer` | — | `100` | 返回行数上限 |
| `offset` | `integer` | — | `0` | 分页偏移 |

**返回行字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `bill_no` | `string` | 出库单号 |
| `make_date` | `datetime` | 制单时间 |
| `org_code` | `string` | 组织 |
| `store_code` | `string` | 仓库 |
| `shop_code` | `string` | 收货单位 |
| `out_ware_type` | `string` | 出库类型 |
| `ref_bill_no` | `string` | ERP 配送单号（来自 `sto_send_pln_head_yyyymm`） |

---

#### `query_outbound_detail` — 出库单明细

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:--:|--------|------|
| `bill_no` | `string` | ✅ | — | 出库单号 |
| `limit` | `integer` | — | `200` | 返回行数上限 |
| `offset` | `integer` | — | `0` | 分页偏移 |

**返回行字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `bill_no` | `string` | 出库单号 |
| `plu_code` | `string` | 商品编码 |
| `plu_ex_code` | `string` | 扩展码 |
| `location_code` | `string` | 来源库位 |
| `log_area_code` | `string` | 物理大区 |
| `out_ware_count` | `float` | 实发数量 |
| `plan_count` | `float` | 计划数量 |
| `pack_qty` | `float` | 包装数量 |
| `pack_count` | `float` | 包装件数 |
| `sgl_count` | `float` | 散件数量 |
| `batch_no` | `string` | 批次号 |

---

### 2.5 分析查询 (Analytics)

> 分析类查询涉及 GROUP BY、跨表 JOIN、聚合函数。`org_code` 由系统自动注入为 `'WL01'`，客户端无需传递。

#### `get_inventory_summary` — 库存汇总

按 SKU 聚合库存：总量、批次数、库位数。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:--:|--------|------|
| `store_code` | `string` | — | `null` | 仓库过滤 |
| `log_area_code` | `string` | — | `null` | 物理大区过滤（通过子查询） |
| `limit` | `integer` | — | `100` | 返回行数上限 |
| `offset` | `integer` | — | `0` | 分页偏移 |

**返回行字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `plu_code` | `string` | 商品编码 |
| `plu_name` | `string` | 商品名称 |
| `total_qty` | `float` | 总库存量 (`SUM(stork_count)`) |
| `batch_count` | `integer` | 批次数 (`COUNT(DISTINCT batch_no)`) |
| `location_count` | `integer` | 库位数 (`COUNT(DISTINCT location_code)`) |

---

#### `get_stock_warning` — 库存预警

按预警类型返回低库存或临期商品。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:--:|--------|------|
| `warning_type` | `string` | — | `"all"` | 预警类型: `low_stock` / `near_expiry` / `all` |
| `low_stock_threshold` | `integer` | — | `10` | 低库存阈值（库存 < 此值触发） |
| `near_expiry_days` | `integer` | — | `30` | 临期天数（到期日 ≤ 此天数触发） |
| `limit` | `integer` | — | `100` | 返回行数上限 |

**返回行字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `plu_code` | `string` | 商品编码 |
| `plu_name` | `string` | 商品名称 |
| `location_code` | `string` | 库位 |
| `batch_no` | `string` | 批次号 |
| `stork_count` | `float` | 库存量 |
| `due_date` | `string` | 到期日期 |
| `warning_type` | `string` | 预警类型 (`low_stock` 或 `near_expiry`) |

---

#### `get_slow_moving_inventory` — 慢周转库存

找出长期未出库的库存（跨库存 + 出库域 JOIN）。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:--:|--------|------|
| `dormant_days` | `integer` | — | `90` | 静默天数（最近一次出库距今 > N 天） |
| `limit` | `integer` | — | `100` | 返回行数上限 |
| `offset` | `integer` | — | `0` | 分页偏移 |

**返回行字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `plu_code` | `string` | 商品编码 |
| `plu_name` | `string` | 商品名称 |
| `location_code` | `string` | 库位 |
| `stork_count` | `float` | 库存量 |
| `last_outbound_date` | `string` | 最后出库日期（`null` = 从未出库） |

---

#### `query_stock_flow` — 库存流水

查询批次库存流水台账（出入库记录）。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:--:|--------|------|
| `sku_code` | `string` | — | `null` | 商品编码 |
| `store_code` | `string` | — | `null` | 仓库 |
| `date_from` | `string` | — | `null` | 开始日期 `YYYY-MM-DD` |
| `date_to` | `string` | — | `null` | 结束日期 `YYYY-MM-DD` |
| `limit` | `integer` | — | `100` | 返回行数上限 |
| `offset` | `integer` | — | `0` | 分页偏移 |

**返回行字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `serial_no` | `integer` | 序号 |
| `plu_code` | `string` | 商品编码 |
| `plu_ex_code` | `string` | 扩展码 |
| `location_code` | `string` | 库位 |
| `batch_no` | `string` | 批次号 |
| `generate_date` | `string` | 生成日期 (YYYY-MM-DD) |
| `generate_time` | `string` | 生成时间 |
| `generate_count` | `float` | 发生数量（正=入库, 负=出库） |
| `stock_type` | `string` | 库存类型 |
| `store_code` | `string` | 仓库 |
| `org_code` | `string` | 组织 |
| `ref_bill_no` | `string` | 相关单据号 |
| `ref_bill_type` | `string` | 相关单据类型 |
| `shop_code` | `string` | 往来单位 |
| `shop_type` | `string` | 往来单位类型 |
| `store_status` | `string` | 状态 |
| `stork_count` | `float` | 发生后库存量 |

---

### 2.6 动态 SQL 执行

#### `execute_sql_readonly` — 受控只读 SQL

允许执行自定义 SELECT/WITH 语句，带有多层安全控制：
- 仅允许 `SELECT` / `WITH` (CTE)
- 禁止 DML/DDL/DCL/多语句/危险函数
- **自动注入 `saas_id` 过滤条件**
- **自动注入 LIMIT**（上限 5000）
- **30 秒硬超时**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:--:|--------|------|
| `sql` | `string` | ✅ | — | SQL SELECT/WITH 语句 |
| `params` | `object` | — | `null` | 绑定参数，如 `{"sku_code": "502620"}` |
| `limit` | `integer` | — | `1000` | 返回行数上限（最大 5000） |

**返回格式**:

```json
{
  "columns": ["plu_code", "plu_name", "stork_count"],
  "rows": [
    ["502620", "测试商品A", 1452.0],
    ["502621", "测试商品B", 320.0]
  ],
  "row_count": 2,
  "injected_limit": 1000
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `columns` | `array<string>` | 列名列表（按 SELECT 顺序） |
| `rows` | `array<array>` | 数据行（二维数组，无列名） |
| `row_count` | `integer` | 实际返回行数 |
| `injected_limit` | `integer` | 系统注入的 LIMIT 值 |

> **注意**: `execute_sql_readonly` 的返回格式与其他 Tool 不同 — 它是 `columns + rows`（二维数组）而非 `items`（对象数组）。这是为了支持任意 SQL 的列名，避免列名硬编码。

---

## 3. HTTP 调用示例

> **注意**: MCP 2024-11-05 要求先 `initialize` 建立 session，后续请求携带 `Mcp-Session-Id`。
> 以下示例展示完整流程。

### 3.1 建立 Session（initialize）

```bash
# Step 1: initialize — 获取 session ID
curl -s -X POST http://localhost:8922/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "jsonrpc": "2.0",
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {},
      "clientInfo": {"name": "test", "version": "1.0"}
    },
    "id": 1
  }' -D - 2>&1 | grep -i mcp-session-id

# 输出示例: mcp-session-id: 9a4f9e516acb4346a0be34cd98fc15ca
# 记下这个 session ID，后续所有请求都需要携带

# Step 2: 发送 initialized 通知
curl -s -X POST http://localhost:8922/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-API-Key: your-api-key" \
  -H "Mcp-Session-Id: 9a4f9e516acb4346a0be34cd98fc15ca" \
  -d '{"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}'
```

### 3.2 列出所有 Tool（需先完成 3.1）

```bash
curl -s -X POST http://localhost:8922/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-API-Key: your-api-key" \
  -H "Mcp-Session-Id: 9a4f9e516acb4346a0be34cd98fc15ca" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 2}'
```

### 3.3 调用具体 Tool（需先完成 3.1）

```bash
# 按 SKU 查库存
curl -X POST http://localhost:8922/mcp \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "query_inventory_by_sku",
      "arguments": {
        "sku_code": "502620",
        "include_zero_stock": false,
        "limit": 20
      }
    },
    "id": 2
  }'

# 库存预警（临期30天）
curl -X POST http://localhost:8922/mcp \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "get_stock_warning",
      "arguments": {
        "warning_type": "near_expiry",
        "near_expiry_days": 30,
        "limit": 50
      }
    },
    "id": 3
  }'

# 动态查询（带参数绑定）
curl -X POST http://localhost:8922/mcp \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "execute_sql_readonly",
      "arguments": {
        "sql": "SELECT plu_code, plu_name, stork_count FROM sto_stock_batch_yyyymm_org WHERE plu_code = :sku AND stork_count > :min_qty",
        "params": {"sku": "502620", "min_qty": 100},
        "limit": 200
      }
    },
    "id": 4
  }'
```

### 3.3 认证失败

```bash
# 缺少 API Key → 401
curl -X POST http://localhost:8922/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"ping","arguments":{}},"id":1}'

# 响应: HTTP 401 {"error_code":"AUTH_ERROR","message":"Missing API Key","detail":null}

# 错误 API Key → 403
curl -X POST http://localhost:8922/mcp \
  -H "Content-Type: application/json" \
  -H "X-API-Key: wrong-key" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"ping","arguments":{}},"id":1}'

# 响应: HTTP 403 {"error_code":"AUTH_ERROR","message":"Invalid API Key","detail":null}
```

---

## 4. Python MCP Client 封装

> **实际实现**: `backend/app/core/mcp_client.py`
> 以下代码与项目中的实际实现一致——异步、支持 MCP 2024-11-05 session 生命周期。

### 4.1 架构概览

```
McpClientManager  ← 连接管理、健康检查缓存、Tool 缓存
    └── WmsMcpClient  ← HTTP 层、session 握手、SSE 解析、JSON-RPC
            └── httpx.AsyncClient
```

### 4.2 基础 Client 类

```python
"""
WMS MCP Client — 异步 Python 客户端, 支持 MCP 2024-11-05 Streamable HTTP.
"""
import json, re, logging
from typing import Any, Optional
import httpx

_log = logging.getLogger("mcp_client")


class McpErrorCode:
    """统一错误码"""
    MCP_UNAVAILABLE = "mcp_unavailable"
    MCP_AUTH_ERROR = "mcp_auth_error"
    MCP_TIMEOUT = "mcp_timeout"
    TOOL_SELECTION_FAILED = "tool_selection_failed"
    TOOL_VALIDATION_FAILED = "tool_validation_failed"
    TOOL_EXECUTION_ERROR = "mcp_tool_error"
    SQL_SECURITY_VIOLATION = "sql_security_violation"
    INTERNAL_ERROR = "internal_error"


class WmsMcpError(Exception):
    """携带统一错误码的异常"""
    def __init__(self, code: str, message: str,
                 detail: str = None, http_status: int = None):
        self.code = code
        self.message = message
        self.detail = detail
        self.http_status = http_status
        super().__init__(f"[{code}] {message}")


class WmsMcpClient:
    """WMS MCP Server 异步客户端 — MCP 2024-11-05 Streamable HTTP 协议。

    管理 session 生命周期: initialize → session → call_tool → close。
    响应解析: 支持 SSE (text/event-stream) 和纯 JSON 两种格式。
    结果解包: 自动提取 structuredContent（新格式）或透传原始 result（旧格式）。
    """

    def __init__(self, base_url: str, api_key: str = "",
                 timeout: float = 60.0):
        self._url = base_url.rstrip("/") + "/mcp"
        self._api_key = api_key
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._request_id = 0
        self._session_id: Optional[str] = None
        self._session_initialized = False

    # -- Session 生命周期 --

    async def _ensure_session(self):
        """三步握手: initialize → 获取 session ID → initialized 通知"""
        if self._session_initialized:
            return
        client = await self._ensure_client()
        # Step 1: initialize
        resp = await client.post(self._url, json={
            "jsonrpc": "2.0", "method": "initialize",
            "params": {"protocolVersion": "2024-11-05",
                       "capabilities": {},
                       "clientInfo": {"name": "wmsrag-client", "version": "1.0"}},
            "id": self._next_id(),
        })
        self._session_id = resp.headers.get("Mcp-Session-Id")
        if not self._session_id:
            _log.warning("MCP initialize 未返回 session ID")
            return
        # Step 2: initialized notification
        await client.post(self._url, json={
            "jsonrpc": "2.0", "method": "notifications/initialized",
            "params": {},
        }, headers={"Mcp-Session-Id": self._session_id})
        self._session_initialized = True

    # -- SSE 解析 --

    @staticmethod
    def _parse_sse_body(text: str) -> dict:
        """解析 SSE 格式: event: message\\ndata: {json}\\n\\n"""
        for line in text.strip().split("\n"):
            if line.strip().startswith("data:"):
                return json.loads(line.strip()[5:].strip())
        return json.loads(text)  # fallback: 纯 JSON

    # -- 核心方法 --

    async def call_tool(self, name: str,
                        arguments: dict = None) -> dict:
        """调用 MCP Tool。自动管理 session, 解析 SSE, 解包 structuredContent。"""
        await self._ensure_session()
        client = await self._ensure_client()
        headers = {}
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        payload = {"jsonrpc": "2.0", "method": "tools/call",
                   "params": {"name": name, "arguments": arguments or {}},
                   "id": self._next_id()}

        try:
            resp = await client.post(self._url, json=payload, headers=headers)
        except httpx.TimeoutException:
            raise WmsMcpError(code=McpErrorCode.MCP_TIMEOUT,
                              message=f"MCP 调用超时: {name}")
        except httpx.ConnectError as e:
            raise WmsMcpError(code=McpErrorCode.MCP_UNAVAILABLE,
                              message=f"无法连接 MCP Server", detail=str(e))

        # HTTP 层错误
        if resp.status_code in (401, 403):
            body = resp.json() if resp.text else {}
            raise WmsMcpError(code=McpErrorCode.MCP_AUTH_ERROR,
                              message=body.get("message", f"HTTP {resp.status_code}"),
                              http_status=resp.status_code)

        # 解析响应: SSE 或 JSON
        text = resp.text
        if text.startswith("event:") or "text/event-stream" in \
                resp.headers.get("content-type", ""):
            body = self._parse_sse_body(text)
        else:
            body = json.loads(text)

        # JSON-RPC 层错误
        if "error" in body:
            err = body["error"]
            raise WmsMcpError(code=McpErrorCode.INTERNAL_ERROR,
                              message=err.get("message", ""))

        result = body.get("result", body)

        # 解包 structuredContent（新格式）
        if isinstance(result, dict) and "structuredContent" in result:
            return result["structuredContent"]

        # 检测 Tool 级错误
        if isinstance(result, dict) and result.get("isError"):
            error_text = ""
            for item in result.get("content", []):
                if isinstance(item, dict) and item.get("type") == "text":
                    error_text += item.get("text", "")
            raise WmsMcpError(code=McpErrorCode.TOOL_EXECUTION_ERROR,
                              message=error_text or "MCP Tool 执行失败")

        return result

    async def ping(self) -> bool:
        try:
            r = await self.call_tool("ping", {})
            return r.get("status") == "ok"
        except Exception:
            return False

    async def list_tools(self) -> list[dict]:
        try:
            await self._ensure_session()
            client = await self._ensure_client()
            headers = {"Mcp-Session-Id": self._session_id} \
                if self._session_id else {}
            resp = await client.post(self._url, json={
                "jsonrpc": "2.0", "method": "tools/list",
                "params": {}, "id": self._next_id(),
            }, headers=headers)
            body = json.loads(resp.text)
            return body.get("result", {}).get("tools", [])
        except Exception:
            return []

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
        self._session_initialized = False

    async def __aenter__(self): return self
    async def __aexit__(self, *args): await self.close()
```

### 4.3 McpClientManager — 连接管理器

```python
class McpClientManager:
    """管理 WmsMcpClient 生命周期, 提供健康检查缓存和 Tool 描述格式化。

    关键参数:
      - base_url: MCP Server 地址, 如 "http://localhost:8922"
      - api_key:  API Key, 如为空则在开发环境跳过认证
      - timeout:  请求超时 (秒), 默认 60
    """

    def __init__(self, base_url: str, api_key: str = "",
                 timeout: float = 60.0):
        ...

    async def is_available(self) -> bool:
        """MCP Server 是否可用 (30s 缓存)"""

    async def call_tool(self, name: str,
                        arguments: dict = None) -> dict:
        """调用 MCP Tool (公共接口)"""

    async def get_tools(self) -> list[ToolDef]:
        """获取 Tool 列表 (5min 缓存)"""

    def get_tool_descriptions(self,
                              tools: list = None) -> str:
        """生成 LLM Tool 选择用的格式化描述文本"""

    async def refresh_tools_cache(self):
        """强制刷新 Tool 缓存"""

    async def close(self):
        """关闭连接"""
```

### 4.4 使用示例

```python
import asyncio
from app.core.mcp_client import WmsMcpClient, McpClientManager

# --- 方式 A: 直接使用 WmsMcpClient ---
async def direct_usage():
    async with WmsMcpClient("http://localhost:8922",
                            api_key="gk-xxx", timeout=60) as c:
        print("Ping:", await c.ping())

        tools = await c.list_tools()
        for t in tools:
            print(f"  {t['name']}")

        r = await c.call_tool("query_inventory_by_sku",
                              {"sku_code": "001525", "limit": 5})
        print(f"找到 {r['total']} 条库存记录")

asyncio.run(direct_usage())

# --- 方式 B: 使用 McpClientManager (推荐, 带缓存) ---
async def managed_usage():
    mgr = McpClientManager("http://localhost:8922",
                           api_key="gk-xxx")
    if await mgr.is_available():
        # LLM Tool 选择用的描述
        desc = mgr.get_tool_descriptions()
        print(desc)

        # 直接调用
        r = await mgr.call_tool("get_stock_warning",
                                {"warning_type": "near_expiry"})
        print(f"预警: {r['total']} 项")
    await mgr.close()

asyncio.run(managed_usage())
```

---

## 5. LangGraph / LangChain / LlamaIndex 接入

> **LangGraph 与 LangChain 的 Tool 机制完全通用。** LangGraph 底层使用 LangChain 的 `BaseTool` 和 `@tool` 装饰器 — 这意味着下面所有的 Tool 定义方式（MCP 自动导入、手动 `@tool` 封装）在 LangGraph 和 LangChain 中 **100% 互换**。
>
> 区别仅在于编排层：LangChain 用 Chain/Agent，LangGraph 用 StateGraph/Node。Tool 本身无感知。

### 5.1 通用前提：Tool 的三种获取方式

无论用 LangGraph 还是 LangChain，获取 WMS Tool 的方式相同：

| 方式 | 适用场景 | 说明 |
|------|---------|------|
| **A. MCP 自动导入** | 快速原型 | `langchain-mcp` 自动发现所有 18 个 Tool |
| **B. 手动 `@tool` 封装** | 生产环境 | 选择性暴露、自定义 Tool 描述、结果格式化 |
| **C. 直接调用 Client** | Graph Node 内 | 在 LangGraph 的 node 函数里直接用 `WmsMcpClient` |

---

### 5.2 方式 A：MCP 自动导入（零封装）

```python
"""
MCP 自动导入 — LangGraph 和 LangChain 通用
需要: pip install langchain-mcp langchain-openai
"""
from langchain_mcp import MCPToolkit

# 1. 连接 WMS MCP Server，自动发现所有 18 个 Tool
toolkit = MCPToolkit(
    server_url="http://wms-server:8922/mcp",
    headers={"X-API-Key": "your-api-key"},
)
tools = toolkit.get_tools()  # list[BaseTool] — LangGraph/LangChain 通用

# 2. 直接绑定到 LLM（LangGraph 或 LangChain 都可以用同一个 tools 列表）
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4o").bind_tools(tools)
```

---

### 5.3 方式 B：手动 `@tool` 封装（推荐生产使用）

手动封装可以：选择性暴露 Tool、自定义描述（帮助 LLM 更好地选择）、格式化返回结果。

```python
"""
手动封装 WMS Tool — 适用于 LangGraph / LangChain
"""
from langchain_core.tools import tool
from wms_client import WmsMcpClient  # 第 4 节的 Client 封装

_client = WmsMcpClient("http://wms-server:8922", api_key="your-api-key")


@tool
def query_inventory(sku_code: str, limit: int = 100) -> str:
    """查询 WMS 中某商品的库存分布（含库位、批次、数量）。

    适用场景：
    - 用户问"XX商品库存多少""XX货在哪个仓位"
    - 需要知道批次号、生产日期、到期日期时

    Args:
        sku_code: 商品编码，如 "502620"
        limit: 返回行数上限
    """
    result = _client.call_tool("query_inventory_by_sku", {
        "sku_code": sku_code,
        "include_zero_stock": False,
        "limit": limit,
    })
    if result["total"] == 0:
        return f"未找到 SKU {sku_code} 的库存。"
    items = result["items"]
    lines = [f"SKU {sku_code} 共有 {len(items)} 条库存记录:"]
    for item in items:
        lines.append(
            f"  - 库位={item['location_code']} "
            f"批次={item['batch_no']} "
            f"数量={item['stork_count']} "
            f"到期={item.get('due_date', '?')}"
        )
    return "\n".join(lines)


@tool
def query_stock_warnings(
    warning_type: str = "all", limit: int = 100
) -> str:
    """查询库存预警（低库存或临期商品）。

    适用场景：
    - 用户问"有没有快过期的""哪些货库存不够了"
    - warning_type: low_stock=低库存, near_expiry=临期, all=全部

    Args:
        warning_type: 预警类型，可选 low_stock / near_expiry / all
        limit: 返回行数上限
    """
    result = _client.call_tool("get_stock_warning", {
        "warning_type": warning_type,
        "limit": limit,
    })
    if result["total"] == 0:
        return "当前无库存预警。"
    items = result["items"]
    lines = [f"库存预警（{warning_type}）共 {len(items)} 项:"]
    for item in items:
        lines.append(
            f"  - [{item['warning_type']}] {item['plu_name']} "
            f"库位={item['location_code']} 库存={item['stork_count']}"
        )
    return "\n".join(lines)


# 导出 Tool 列表 — LangGraph / LangChain 通用
wms_tools = [query_inventory, query_stock_warnings]
```

---

### 5.4 LangGraph 示例

> **项目实际实现**: `backend/app/agents/graph_mcp.py` — 完整的 LangGraph 图（tool_filter → tool_select → mcp_call → result_format）。
> 以下展示核心 `mcp_call_node` 如何与 `McpClientManager` 集成。

LangGraph 的 Tool 调用在 `ToolNode` 或手写的 node 函数中完成。项目实际采用**自定义 Node 模式**——在节点函数中直接调用 `McpClientManager.call_tool()`，灵活控制 Tool 选择、参数填充、结果格式化。

#### 模式 1：使用 ToolNode（简洁）

```python
"""
LangGraph + WMS MCP — 使用预构建 ToolNode
"""
from langgraph.graph import StateGraph, MessagesState, START
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o").bind_tools(wms_tools)  # wms_tools 来自 5.3

def chatbot(state: MessagesState):
    """LLM 决策节点：决定调用哪个 Tool 还是直接回答"""
    return {"messages": [llm.invoke(state["messages"])]}

# 构建 Graph
graph = StateGraph(MessagesState)
graph.add_node("chatbot", chatbot)
graph.add_node("tools", ToolNode(wms_tools))  # 直接复用 wms_tools
graph.add_edge(START, "chatbot")
graph.add_conditional_edges("chatbot", _route)  # 有 tool_call → tools, 无 → END
graph.add_edge("tools", "chatbot")              # Tool 结果返回 chatbot 继续思考
app = graph.compile()

# 调用
response = app.invoke({
    "messages": [{"role": "user", "content": "502620的库存情况，有没有临期的？"}]
})
```

#### 模式 2：在 Node 中直接调用 Client（灵活）

```python
"""
LangGraph + WMS MCP — 在自定义 Node 中直接调用 Client
适合需要多 Tool 编排、结果转换的场景
"""
from langgraph.graph import StateGraph, MessagesState, START, END
from typing import TypedDict
from wms_client import WmsMcpClient

_client = WmsMcpClient("http://wms-server:8922", api_key="your-api-key")

class WmsState(TypedDict):
    messages: list
    inventory_data: list | None   # 库存查询结果
    warnings: list | None         # 预警结果

def fetch_inventory_node(state: WmsState) -> WmsState:
    """从最后一条消息中提取 SKU，调用 WMS 查库存"""
    last_msg = state["messages"][-1].content
    sku = _extract_sku(last_msg)  # 自定义的 SKU 提取逻辑
    if sku:
        result = _client.call_tool("query_inventory_by_sku", {"sku_code": sku})
        return {"inventory_data": result["items"]}
    return {"inventory_data": []}

def check_warnings_node(state: WmsState) -> WmsState:
    """查询库存预警"""
    result = _client.call_tool("get_stock_warning", {"warning_type": "all"})
    return {"warnings": result["items"]}

# 构建 Graph
graph = StateGraph(WmsState)
graph.add_node("fetch_inventory", fetch_inventory_node)
graph.add_node("check_warnings", check_warnings_node)
graph.add_node("respond", respond_node)  # 汇总结果生成回答
graph.add_edge(START, "fetch_inventory")
graph.add_edge("fetch_inventory", "check_warnings")
graph.add_edge("check_warnings", "respond")
graph.add_edge("respond", END)
app = graph.compile()
```

> **核心要点**: LangGraph 的 Tool 和 LangChain 的 Tool 是**同一个东西**。你在 LangChain 中怎么定义 `@tool`，在 LangGraph 中就怎么用。唯一的区别是 LangGraph 的图结构让你可以精确控制 Tool 调用的时机和顺序。

---

### 5.5 LlamaIndex 集成

```python
"""
LlamaIndex FunctionTool 集成示例
"""
from llama_index.core.tools import FunctionTool
from wms_client import WmsMcpClient

_client = WmsMcpClient("http://wms-server:8922", api_key="your-api-key")

def query_inventory_fn(sku_code: str) -> dict:
    """按 SKU 查库存"""
    return _client.call_tool("query_inventory_by_sku", {"sku_code": sku_code})

def search_product_fn(keyword: str) -> dict:
    """按名称模糊搜商品"""
    return _client.call_tool("query_product", {"sku_name": keyword, "limit": 10})

def get_slow_moving_fn(days: int = 90) -> dict:
    """查慢周转库存"""
    return _client.call_tool("get_slow_moving_inventory", {"dormant_days": days})

inventory_tool = FunctionTool.from_defaults(
    fn=query_inventory_fn,
    name="wms_query_inventory",
    description="查询 WMS 中某 SKU 的库存分布（库位+批次+数量）",
)

product_tool = FunctionTool.from_defaults(
    fn=search_product_fn,
    name="wms_search_product",
    description="按名称模糊搜索 WMS 商品主数据",
)

slow_moving_tool = FunctionTool.from_defaults(
    fn=get_slow_moving_fn,
    name="wms_slow_moving",
    description="查询超过N天未出库的慢周转库存",
)
```

---

## 6. Agent 调用流程示意

### 6.1 典型 Agent 交互流程

```
┌─────────────────────────────────────────────────────────────┐
│  Data Copilot Agent                                         │
│                                                              │
│  用户: "502620 这个货库存够不够发？有没有临期的？"            │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 1. LLM 理解意图 → 拆解为 Tool Calls                    │   │
│  │                                                       │   │
│  │    Tool Call 1: query_inventory_by_sku                │   │
│  │      sku_code="502620"                                │   │
│  │      include_zero_stock=false                         │   │
│  │    → 返回: 3 条库存记录（不同库位/批次）                │   │
│  │                                                       │   │
│  │    Tool Call 2: get_stock_warning                     │   │
│  │      warning_type="near_expiry"                       │   │
│  │      near_expiry_days=30                              │   │
│  │    → 返回: 1 条临期预警（批次 20241201001 30天后到期）  │   │
│  │                                                       │   │
│  │ 2. LLM 整合结果 → 生成回答                              │   │
│  │                                                       │   │
│  │    "SKU 502620 当前库存 850 件，分布在 3 个库位。      │   │
│  │     良品仓 A-01-01 有 500 件（批次 20250101001），     │   │
│  │     良品仓 A-01-01 有 300 件（批次 20250301001），     │   │
│  │     不良品仓 A-02-01 有 50 件（批次 20250101002）。    │   │
│  │     ⚠️ 批次 20241201001 库存为 0，已全部出库。         │   │
│  │     ⚠️ 无 30 天内临期批次。"                           │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 推荐的多 Tool 组合模式

| 用户问题类型 | 推荐调用的 Tool（按顺序） |
|-------------|------------------------|
| "XX商品的库存情况" | `query_inventory_by_sku` → 如有关注批次则加 `query_inventory_by_batch` |
| "有哪些商品快过期了" | `get_stock_warning(type="near_expiry")` |
| "哪些库存太久没动" | `get_slow_moving_inventory` → 如有需要查明细 `query_outbound_order` |
| "最近入库了什么" | `query_inbound_order(date_from="...", date_to="...")` → `query_inbound_detail(bill_no="...")` |
| "XX商品基本信息" | `query_product` → `query_product_spec` → `query_product_warehouse_config` |
| "统计各SKU库存总量" | `get_inventory_summary`（按 total_qty DESC 排序） |
| "某批次去哪了" | `query_stock_flow(sku_code="...")` → 追踪流水 |
| 复杂自定义查询 | `execute_sql_readonly`（最后手段） |

### 6.3 分页处理

Agent 应遵循分页模式获取大数据集：

```python
def fetch_all_inventory(client, sku_code: str) -> list[dict]:
    """分页获取某 SKU 的全部库存（假设 < 5000 行）。"""
    all_items = []
    offset = 0
    page_size = 100
    while True:
        result = client.call_tool("query_inventory_by_sku", {
            "sku_code": sku_code,
            "limit": page_size,
            "offset": offset,
        })
        items = result["items"]
        all_items.extend(items)
        if len(items) < page_size:  # 最后一页
            break
        offset += page_size
    return all_items
```

---

## 7. 常见错误与排查

### 7.1 认证错误

| 错误 | HTTP | 原因 | 解决 |
|------|:----:|------|------|
| `Missing API Key` | 401 | 请求头缺 `X-API-Key` | 添加 `X-API-Key` 请求头 |
| `Invalid API Key` | 403 | API Key 不在配置的密钥列表中 | 确认 Key 正确，检查逗号分隔的多个 Key |
| — | — | Key 前后有空格 | `.env` 中 `API_KEY=key1,key2` 不要加引号 |

### 7.2 SQL 执行错误

| 错误码 | 说明 | 解决 |
|--------|------|------|
| `VALIDATION_ERROR: SQL rejected: DML not allowed` | 传入了 UPDATE/DELETE/INSERT 等 | 只允许 SELECT / WITH |
| `VALIDATION_ERROR: SQL rejected: Disallowed keyword: DROP` | 包含被禁关键字 | 移除 DDL/DCL 语句 |
| `VALIDATION_ERROR: SQL rejected: Multiple statements are not allowed` | SQL 中包含分号 | 只发一条 SQL |
| `DATABASE_ERROR: SQL execution failed` | MySQL 执行出错（语法、权限等） | 检查 SQL 语法和表名 |
| （超时） | 查询超 30 秒 | 优化 SQL 或缩小 `limit` |

### 7.3 参数错误

| 错误 | 原因 | 解决 |
|------|------|------|
| 返回 `total: 0`，items 为空 | 查询条件不匹配数据 | 检查 `sku_code`/`org_code` 是否存在 |
| `batch_no` 过滤无效 | 传入了非字符串类型 | `batch_no` 必须是字符串：`"2029084286671708161"` |
| `log_area_code` 过滤无效 | 未设 `include_pick_location=True` | `log_area_code` 需要拣货位 JOIN 才能生效 |
| `execute_sql_readonly` 结果被截断 | 超过 LIMIT | 增加 `limit` 参数（最大 5000） |

### 7.4 网络/连接错误

| 错误 | 排查 |
|------|------|
| `httpx.ConnectError` | 确认 Server 已启动；检查 host/port |
| `httpx.ReadTimeout` | 查询超时，减小 `limit` 或优化查询条件 |
| 404 Not Found | 确认 URL 以 `/mcp` 结尾 |

### 7.5 Session / SSE 相关错误

| 错误 | 排查 |
|------|------|
| `MCP initialize 未返回 session ID` | Server 未返回 `Mcp-Session-Id` header。检查 `Accept` header 是否包含 `text/event-stream` |
| `Session not found` (JSON-RPC -32600) | Session 已过期或从未建立。重新 `initialize` |
| `Not Acceptable` (HTTP 406) | `Accept` header 缺少 `text/event-stream` |
| `Missing API Key` (HTTP 401) | 请求未携带 `X-API-Key` header，或 Server 配置了 API Key 但客户端未提供 |
| 响应解析失败 | Server 可能返回了纯 JSON 而非 SSE 格式。检查 `Content-Type` header |
| `structuredContent` 为空 | 部分 Tool 使用旧格式（直接返回 data）。客户端已兼容两种格式 |
| `isError: true` | Tool 执行失败（非协议错误）。检查 `content[0].text` 获取具体错误信息 |

### 7.6 调试技巧

```python
# 1. 先用 ping 确认连通
client = WmsMcpClient("http://localhost:8922", api_key="xxx")
assert client.ping(), "无法连接 WMS MCP Server"

# 2. 列 Tool 确认哪些可用
tools = client.list_tools()
for t in tools:
    print(f"  {t['name']} — {t['description']}")

# 3. 用最小参数调用
result = client.call_tool("query_inventory_by_sku", {
    "sku_code": "502620",
    "limit": 1,
})
print(f"示例数据: {result['items'][0] if result['items'] else '无数据'}")

# 4. execute_sql_readonly 验证数据是否存在
result = client.call_tool("execute_sql_readonly", {
    "sql": "SELECT COUNT(*) AS cnt FROM sto_stock_batch_yyyymm_org",
    "limit": 1,
})
print(f"库存表总行数: {result['rows'][0][0]}")
```
