# WMS Semantic Layer

## 业务概念 → 主表映射 (Business Concept Mapping)

### 库存 (Inventory / Stock)

库存域涵盖仓库中商品的存储数量、批次、库位分布及库存状态查询。典型查询包括：查询某商品的当前库存量、按仓库/库位统计库存分布、查询即将过期的批次库存、锁定库存查询。核心特征是关注"在库数量（stork_count）"和"库位（location_code）"。

MUST USE:
- `sto_stock_batch_yyyymm_org` AS PRIMARY TABLE — 批次库存表，核心库存查询
- `sto_plu_org_loc_set` — 商品拣货位设置表

**Key columns — sto_stock_batch_yyyymm_org (16 columns):**
`org_code`, `store_code` ('01'=良品仓/'02'=不良品仓), `location_code` (库位), `plu_code`, `bar_code`, `batch_no` (批号), `stork_count` (库存数量), `store_status` (0=在库/1=在途), `pur_date` (进货日期), `mannu_date` (生产日期), `due_date` (到期日期), `logistics_code` (物流商)

JOIN: `sto_stock_batch_yyyymm_org.location_code = sto_plu_org_loc_set.location_code`

### 出库 (Outbound)

出库域涵盖商品从仓库发出的所有业务，包括：出库单生成、出库建议、配送计划制定与汇总。典型查询包括：按时间统计出库总量、按门店查配送量、按商品查出库明细、出库单与配送计划的关联查询。关键词："出库""发货""配送计划""出仓"。注意："配送"相关查询虽然表面上属于配送，但底层数据源通常跨越出库单和配送计划两个维度。

MUST USE:
- `sto_out_ware_head_yyyymm` — 出库单头表（含时间、状态）
- `sto_out_ware_body_yyyymm` — 出库单明细表（含商品行项）
- `sto_send_pln_head_yyyymm` — 配送计划头表
- `sto_send_pln_collect_yyyymm` — 配送汇总表
- `sto_send_pln_body_poll_yyyymm` — 配送计划轮询明细表

**Key columns — sto_out_ware_head_yyyymm (42 columns total, no real_count or shop_type):**
`bill_no`, `make_date`, `shop_code`, `out_ware_type` (0=建议/1=出库单), `out_ware_count` (出库数量), `ref_bill_no`, `ref_bill_type`, `org_code`, `store_code`, `busi_type`, `remark`, `package_count`, `out_plu_count`

**Key columns — sto_out_ware_body_yyyymm (30 columns):**
`bill_no`, `plu_code`, `bar_code`, `location_code`, `pack_unit`, `pack_qty`, `pack_count`, `sgl_count`, `out_ware_count`, `batch_no`, `mannu_date`, `log_area_code`

**Key columns — sto_send_pln_head_yyyymm (52 columns, no shop_type):**
`bill_no`, `make_date`, `org_code`, `store_code`, `shop_code` (收货单位编码), `send_count` (发货数量), `plan_count` (计划数量), `is_checked` (0=未复核/1=已复核), `is_emerg_send` (0=否/1=紧急), `is_allow_send` (0=否/1=允许发货), `ref_bill_no`, `ref_bill_type`, `dispatch_status` (派车状态), `wave_code` (波次编码), `collect_bill_no` (汇总单号), `logist_code` (物流商)

**Key columns — sto_send_pln_collect_yyyymm (46 columns):**
`collect_bill_no` (汇总单号), `make_date`, `org_code`, `store_code`, `shop_type` (0=门店/1=供应商/2=客户/3=外部物流), `shop_code`, `car_license` (车牌号), `locations` (发车位数), `dst_count` (配送数量), `out_plu_count` (商品品种数), `package_count` (包装件数), `plan_count` (计划数量), `send_lin_num` (装车顺序)

**Key columns — sto_send_pln_body_poll_yyyymm (29 columns):**
`collect_bill_no`, `ref_bill_no`, `plu_code`, `pack_unit` (配送包装单位), `pack_qty` (包装细数), `pack_count` (包装数量), `pick_count` (拣货包装数), `sgl_count` (散件数量), `out_ware_count` (计划数量), `send_count` (实发数量), `pur_price` (配送价), `pur_cost` (配送金额)

When time filtering needed:
- Use `sto_out_ware_head_yyyymm.make_date` (创建时间)
- Use `sto_send_pln_head_yyyymm.make_date` (配送计划创建时间)
- JOIN pattern: `sto_out_ware_head_yyyymm.bill_no = sto_out_ware_body_yyyymm.bill_no`
- JOIN to delivery: `sto_out_ware_head_yyyymm.ref_bill_no = sto_send_pln_head_yyyymm.bill_no`
- JOIN delivery collect: `sto_send_pln_collect_yyyymm.collect_bill_no = sto_send_pln_body_poll_yyyymm.collect_bill_no`

### 拣货 (Picking)

拣货域涵盖仓库作业人员根据订单从库位取出商品的全过程，包括摘果拣货、整箱拣货、散件拣货。典型查询包括：按时间/库位/作业员统计拣货量、查询拣货任务状态、按商品统计拣货频次。核心数据在拣货作业头+明细表，库位信息在拣货位设置表。关键词："拣货""摘果""拣货位""拣货作业"。

MUST USE:
- `sto_pick_opr_head_yyyymm` — 拣货作业头表
- `sto_pick_opr_body_yyyymm` — 拣货作业明细表
- `sto_plu_org_loc_set` — 商品拣货位设置表

**Key columns — sto_pick_opr_head_yyyymm (27 columns, no shop_type):**
`bill_no`, `make_date`, `opr_type` (作业类型), `org_code`, `owner_org_code`, `shop_code` (收货单位), `send_bill_no` (配送单号), `ref_bill_type`, `ref_bill_no`, `wave_code` (波次编码), `move_count` (摘果数量), `pick_pack` (拣货包装: 0=散件+整箱/1=仅整箱/2=仅整件/3=仅散件/4=按件包装), `opr_date` (作业完成日期), `opr_user` (RF作业人), `locations` (发车位数)

**Key columns — sto_pick_opr_body_yyyymm (26 columns):**
`bill_no`, `serial_no`, `plu_code`, `pack_unit`, `pack_qty` (包装细数), `pack_count` (包装数量), `sgl_count` (散件数量), `move_count` (摘果数量), `store_code` (取货仓库), `log_area_code` (取货物流区域), `location_code` (取货库位), `to_store_code` (目标仓库), `to_location_code` (目标库位), `batch_no`, `mannu_date` (生产日期)

**Key columns — sto_plu_org_loc_set (10 columns, no is_active field):**
`plu_code`, `plu_ex_code`, `org_code`, `store_code`, `log_area_code`, `shelf_code`, `location_code`, `print_date`, `print_times`

When querying picking locations:
- `sto_plu_org_loc_set` is the primary table for location assignments
- Filter by `log_area_code` for specific warehouse zones
- JOIN: `sto_pick_opr_head_yyyymm.bill_no = sto_pick_opr_body_yyyymm.bill_no`

### 配送 (Delivery / Dispatch)

配送域涵盖商品从仓库配送到门店/客户的全过程，包括配送计划制定、波次汇总、派车调度。与出库域紧密关联——出库是配送的执行动作，配送是出库的上游计划。典型查询：按车牌/路线/门店统计配送量、查询配送汇总单明细。关键词："配送""发货""派车""波次""装车"。

MUST USE:
- `sto_send_pln_head_yyyymm` AS PRIMARY TABLE — 配送计划头表（单号、波次、状态）
- `sto_send_pln_collect_yyyymm` — 配送汇总表（含 shop_code, car_license 等头信息）
- `sto_send_pln_body_poll_yyyymm` — 配送明细表（含商品级别的计划和实发数量）

Key columns 已在出库域中列出。JOIN: `sto_send_pln_collect_yyyymm.collect_bill_no = sto_send_pln_body_poll_yyyymm.collect_bill_no`

### 收货 / 验收 / 采购入库 (Receiving / Acceptance / Procurement)

MUST USE:
- `sto_accept_head_yyyymm` — 收货验收头表（含时间、状态、供应商）
- `sto_accept_body_yyyymm` — 收货验收明细表（含商品行项、数量、价格）
- JOIN: `sto_accept_head_yyyymm.bill_no = sto_accept_body_yyyymm.bill_no`

**Key columns — sto_accept_head_yyyymm (40 columns):**
`bill_no`, `make_date`, `submit_date`, `verify_date`, `verify_status` (0=未验收/1=审核通过/2=审核不通过/3=已生成验收单), `org_code`, `sup_code` (供应商), `cnt_code` (合同), `busi_type`, `operate_mode` (0=经销/1=代销/2=联营), `stock_code`, `status` (0=未执行/1=执行完/2=终止), `ref_bill_type` (来源单据类型：'采购'=采购订单收货), `ref_bill_no`, `accept_count` (验收总数量)

**Key columns — sto_accept_body_yyyymm (29 columns, no rec_count, no shop_type):**
`bill_no`, `serial_no`, `plu_code`, `bar_code`, `pack_unit`, `pack_qty` (包装细数), `pack_count` (包装数量), `sgl_count` (散件数量), `accept_count` (验收数量), `real_count` (实收数量), `pur_price` (含税进价), `mannu_date` (生产日期), `due_date` (到期日期), `remark`

**采购商品数量**: 使用 `sto_accept_body_yyyymm.accept_count`（验收数量）或 `sto_accept_body_yyyymm.real_count`（实收数量）。默认使用 `accept_count`。

**重要**: 验收表本身就是采购收货入库的记录表。"采购商品"的查询直接使用验收表即可，**不需要**额外添加 `busi_type` 过滤条件。`busi_type` 是业务类型编码字段，不存在字符串值'采购'。如果确实需要按来源单据类型过滤，使用 `ref_bill_type`。

### 商品信息 (Product Info)

MUST USE:
- `cob_plu` — 商品基础表（商品编码、名称、规格、单位、状态等）
- `cob_plu_packet` — 商品包装表（包装细数、包装单位、长宽高等）

JOIN: `cob_plu.plu_code = cob_plu_packet.plu_code`

**Key columns — cob_plu (25 columns):**
`plu_code`, `plu_name` (商品名称), `spec_desc` (规格描述, NOT spec), `plu_unit` (单位, NOT unit), `bar_code`, `plu_kind` (0=商品/1=商品组), `biz_status` (0=未审核/1=审核/2=预淘汰/3=淘汰), `is_active` (0=无效/1=有效), `qa_days`, `brand_code`, `cls_code`, `prod_area`, `weight`

**Key columns — cob_plu_packet (20 columns, DOES NOT HAVE is_active):**
`plu_code`, `pack_bar_code`, `pack_unit` (包装单位), `pack_qty` (包装细数), `pack_spec` (包装规格), `is_base_ware` (1=库存基础包装), `is_pur_pack` (1=采购包装), `is_dist_pack` (1=配送包装), `pack_long`, `pack_width`, `pack_height`, `pack_weight`

**IMPORTANT**: cob_plu_packet is a detail/child table and has NO is_active or biz_status field. To filter active products, JOIN with cob_plu: `cob_plu.is_active = 1 AND cob_plu.biz_status = 1`.

### 商品仓库设置 (Warehouse Product Settings)

商品仓库设置域涵盖商品在特定仓库中的配置参数，包括批次处理策略、抽检标识、补货上下限。典型查询：查询某商品的批次处理方式、查看需要抽检的商品列表、查询补货库存低于警戒线的商品。

MUST USE:
- `sto_plu_org_set` — 商品仓库设置表（批次方式、抽检标识等）
- `sto_plu_org_loc_cpfr` — 商品仓库补货设置表（补货警戒、最高库存等）

**Key columns — sto_plu_org_set (17 columns):**
`plu_code`, `org_code`, `store_code`, `plu_kind` (0=普通商品/1=称重商品), `batch_type` (0=FIFO/1=LIFO/2=指定批次FIFO/3=指定批次LIFO), `need_spot` (0=否/1=需抽检), `plu_pick_policy` (0=摘果/1=播种), `min_picking_count` (最小拣货起始数), `fix_pick_type` (商品分货原则: 0=只走不出/1=只出不走/2=实际分货标识), `plu_cw_duty` (商品职能), `plu_abbr` (商品简称), `plu_store_type` (商品存储原则), `pick_frequency` (拣货频次: ABCD), `package_count_ctrl` (包装标签数)

**Key columns — sto_plu_org_loc_cpfr (11 columns):**
`plu_code`, `org_code`, `store_code`, `log_area_code`, `shelf_code`, `location_code`, `repl_low_count` (补货警戒数量), `repl_max_count` (最高库存), `put_more_count` (存放次数)

JOIN: `sto_plu_org_set.plu_code = sto_plu_org_loc_cpfr.plu_code`

### 库存锁定 (Stock Lock)

库存锁定域涵盖库存被冻结/锁定的记录，用于防止特定批次的库存被出库或移动。典型查询：查询当前被锁定的库存、按商品查锁定记录、按锁定来源单据追溯。关键词："锁定""冻结""锁库"。

MUST USE:
- `sto_lock_yyyymm_org` — 库存锁定表

**Key columns — sto_lock_yyyymm_org (20 columns):**
`serial_no`, `org_code`, `store_code`, `location_code`, `plu_code`, `bar_code`, `batch_no`, `lock_date` (锁定日期), `lock_count` (锁定数量), `stock_status` (0=释放/1=锁定), `ref_bill_type` (来源单据类型), `ref_bill_no` (来源单据号), `shop_code` (门店编码), `mannu_date` (生产日期), `logistics_code` (物流商)

### 仓位 (Location)

仓位域涵盖仓库内物理储位的属性信息，包括库位编码、职能分类（食品/非食/日配）、拣货频次。典型查询：按物流区域/货架查找可用库位、按拣货频次排序。关键词："库位""仓位""货架""储位"。

MUST USE:
- `sto_location` AS PRIMARY TABLE

**Key columns — sto_location (25 columns):**
`org_code`, `store_code`, `log_area_code` (物流区域), `shelf_code` (货架编码), `location_code` (库位编码), `location` (库位位置: 排-列-层), `location_type` (库位类型), `location_duty` (库位职能), `location_pos` (库位位置: 0=库位/1=上架/2=上柜/3=货位), `status` (库位状态), `is_active` (0=无效/1=有效), `pick_frequency` (拣货频次: ABCD), `pick_order` (拣货顺序), `pallets_count` (托盘数量)

### 用户 (User)

用户域涵盖系统用户的基本信息，包括用户编码、名称、类型、启用状态。典型查询：查询某组织的有效用户列表、按用户类型筛选。

MUST USE:
- `tFrsUser` AS PRIMARY TABLE

**Key columns — tFrsUser (26 columns):**
`UserID`, `UserCode` (用户编码), `UserName` (用户名称), `UserType` (0=集团管理员/1=组织管理员/2=普通用户), `IsEnable` (0=无效/1=有效), `BgnDate` (有效开始日期), `EndDate` (失效日期), `OrgCode` (关联组织编码), `EmpCode` (员工编码)

---

## 跨表通用枚举约定 (Cross-Table Enum Conventions)

### 是否类布尔字段 (Boolean-like: 0=否/1=是)

The following fields use 0=No/1=Yes pattern across ALL tables:
- `is_active` — 是否有效
- `is_allow_send` — 是否允许发货
- `is_checked` — 是否已复核
- `is_emerg_send` — 是否紧急发货
- `need_spot` — 是否需要抽检

When user asks "有效的"/"启用的"/"已审核的", use `= 1`.
When user asks "无效的"/"停用的"/"未审核的", use `= 0`.

### shop_type (收货单位类型)

Appears in ALL outbound/delivery head tables. Same enum everywhere:
- `0` = 门店
- `1` = 供应商
- `2` = 客户
- `3` = 外部物流

### store_code (仓库编码)

Appears in stock/location/container tables:
- `'01'` = 良品仓
- `'02'` = 不良品仓
- 不填/不条件 = 全部仓库

Default to 良品仓 (`store_code = '01'`) unless user specifies otherwise.

### out_ware_type (出库类型)

In `sto_out_ware_head_yyyymm`:
- `0` = 出库建议（系统生成的出库建议，非正式出库单）
- `1` = 出库单（正式出库单据）

### batch_type (批次处理方式)

In `sto_plu_org_set`:
- `0` = 先进先出（FIFO）
- `1` = 后进先出（LIFO）
- `2` = 指定批次，未指定的先进先出
- `3` = 指定批次，未指定的后进先出

### stock_status (库存锁定状态)

In `sto_lock_yyyymm_org`:
- `0` = 释放（未锁定）
- `1` = 锁定

### store_status (库存状态)

In `sto_stock_batch_yyyymm_org`:
- `0` = 在库
- `1` = 在途

### verify_status (验收状态)

In `sto_accept_head_yyyymm`:
- `0` = 未验收
- `1` = 审核通过
- `2` = 审核不通过
- `3` = 已生成验收单

### plu_kind (商品类型)

In `cob_plu`:
- `0` = 商品
- `1` = 商品组

In `sto_plu_org_set`:
- `0` = 普通商品
- `1` = 称重商品

### biz_status (商品业务状态)

In `cob_plu`:
- `0` = 未审核
- `1` = 审核
- `2` = 预淘汰
- `3` = 淘汰

### operate_mode (经营方式)

In `sto_accept_head_yyyymm`:
- `0` = 经销
- `1` = 代销
- `2` = 联营

### is_pur_pack (采购包装)

In `cob_plu_packet`:
- `1` = 默认采购包装

### is_base_ware (库存基础包装)

In `cob_plu_packet`:
- `1` = 库存基础包装

### is_dist_pack (配送包装)

In `cob_plu_packet`:
- `1` = 默认配送包装

---

## 时间处理规则 (Time Handling)

### 重要：表名中的 _yyyymm 是字面量

**`_yyyymm` 是表名的一部分，不是占位符。不要将其替换为数字。** 正确表名: `sto_out_ware_head_yyyymm`，错误: `sto_out_ware_head_202606`。

### 默认年份

**用户未指定年份时，默认使用当前年份 2026 年**。例如：
- "3月份" → 2026年3月（`>= '2026-03-01' AND < '2026-04-01'`）
- "查询今年的出库量" → 2026年全年
- "上个月" → 2026年5月

### 时区转换

**所有时间字段存储为 UTC 时间**，查询北京时间时统一使用：
```sql
DATE_ADD(table.make_date, INTERVAL 8 HOUR)
```

涉及的时间字段：
- `make_date` — 制单/创建时间（几乎所有头表都有此字段）
- 所有 WHERE 条件中的时间比较都必须加此转换

### 头表 vs 明细表的时间字段

- **头表** (以 `_head_yyyymm` 结尾): 包含时间字段 (`make_date`, `submit_date` 等)
- **明细表** (以 `_body_yyyymm` 结尾): 仅含行项目数据，**不含时间字段**

When user asks about dates/time periods:
- MUST use head tables for time filtering
- JOIN body tables to get line-item details

---

## 常用 JOIN 模式 (Common JOIN Patterns)

### 出库流水查询
```
sto_out_ware_head_yyyymm (头表: 时间+单据信息)
  └─ sto_out_ware_body_yyyymm (明细: 商品+数量)
    ON bill_no
```

### 出库关联配送
```
sto_out_ware_head_yyyymm.ref_bill_no = sto_send_pln_head_yyyymm.bill_no
```

### 配送汇总+明细
```
sto_send_pln_collect_yyyymm (汇总: 客户+车牌)
  └─ sto_send_pln_body_poll_yyyymm (明细: 商品+实发数量)
    ON collect_bill_no
```

### 库存+拣货位
```
sto_stock_batch_yyyymm_org (库存数量)
  └─ sto_plu_org_loc_set (拣货位)
    ON location_code
```

### 商品+包装
```
cob_plu (商品基础信息)
  └─ cob_plu_packet (包装信息)
    ON plu_code
```

### 商品仓库+补货
```
sto_plu_org_set (仓库设置)
  └─ sto_plu_org_loc_cpfr (补货设置)
    ON plu_code
```

### 收货头+明细
```
sto_accept_head_yyyymm (收货头)
  └─ sto_accept_body_yyyymm (收货明细)
    ON bill_no
```

---

## WHERE 条件约定 (Common WHERE Conventions)

1. **默认使用良品仓**: 库存类查询默认加 `store_code = '01'`，除非用户明确提到"不良品"
2. **默认只查有效数据**: 商品查询默认加 `is_active = 1`、`biz_status = 1`
3. **出库时间过滤必须加时区转换**: `DATE_ADD(make_date, INTERVAL 8 HOUR)`
4. **出库建议 vs 出库单**: 日常查询通常用 `out_ware_type = 0`（出库建议），正式记录用 `1`
5. **库存锁定查询**: `stock_status = 1` 为锁定中

---

## 列反模式 (Column Anti-Patterns — DO NOT USE)

以下列名常被误用在不包含它们的表上。**如果某列不在该表的【Key columns】清单中，切勿使用。**

| Table | 没有该列 | 替代方案 |
|-------|---------|---------|
| `sto_out_ware_head_yyyymm` | `real_count` | 使用 `out_ware_count` |
| `sto_out_ware_head_yyyymm` | `shop_type` | 该列仅在配送汇总表(stop_send_pln_collect_yyyymm等)中存在 |
| `sto_plu_org_loc_set` | `is_active` | 该表无可用的"是否有效"字段，不需要加 is_active 过滤 |
| `cob_plu_packet` | `is_active` | 该表是包装明细表，没有独立的状态字段；商品有效性查询请用 cob_plu.is_active |
| `sto_out_ware_body_yyyymm` | `shop_type` | 该表仅含行项目数据，不含 shop_type |
| `sto_accept_body_yyyymm` | `rec_count` | 使用 `accept_count`（验收数量）或 `real_count`（实收数量） |
| `sto_accept_head_yyyymm` | `rec_count` | 使用 `accept_count`（验收总数量） |
| `sto_accept_head_yyyymm` | `busi_type = '采购'` | busi_type 是业务类型编码字段，不存在值'采购'。验收表本身就是采购收货表，不需额外过滤。如需按来源单据类型过滤，使用 ref_bill_type |

**通用规则**: `is_active` 字段不是所有表都有的。只有当表的关键列清单中明确列出 `is_active` 时才使用。`cob_plu` 有该字段，`cob_plu_packet`/`sto_plu_org_loc_set` 没有。
**通用规则**: `rec_count` 不是任何表的有效列名。验收/收货场景的数量字段统一使用 `accept_count` 或 `real_count`。
