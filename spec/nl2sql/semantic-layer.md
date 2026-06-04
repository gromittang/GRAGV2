# Inventory Semantic Layer

When user asks "库存 / stock / inventory":

MUST USE:

- sto_stock_batch_yyyymm_org AS PRIMARY TABLE


When user asks "仓位 / location":

MUST USE:

- sto_location AS PRIMARY TABLE

When user asks "用户 / user":

MUST USE:

- tFrsUser AS PRIMARY TABLE


######

Business Concept: 出库（Outbound）

Candidate Tables:

Primary:

- sto_out_note_body_yyyymm
- sto_out_note_head_yyyymm
- sto_out_ware_body_yyyymm
- sto_out_ware_box_body_yyyymm
- sto_out_ware_box_calc_yyyymm
- sto_out_ware_collect_yyyymm
- sto_out_ware_head_yyyymm
- sto_out_ware_pack_calc_yyyymm
- sto_out_ware_split_plu_yyyymm
- sto_pick_opr_body_yyyymm
- sto_pick_opr_head_yyyymm

- sto_send_pln_body_collect_yyyymm
- sto_send_pln_body_poll_yyyymm
- sto_send_pln_body_yyyymm
- sto_send_pln_collect_yyyymm
- sto_send_pln_diff_yyyymm
- sto_send_pln_dst_collect
- sto_send_pln_head_yyyymm
- 


Secondary:

- sto_pick_split_opr_body_yyyymm
- sto_pick_split_opr_head_yyyymm

Context Rule:

IF question contains:

- 明细

Prefer:

- sto_out_note_body_yyyymm
- sto_out_ware_body_yyyymm
- sto_out_ware_box_body_yyyymm
- sto_out_ware_collect_yyyymm
- sto_out_ware_pack_calc_yyyymm
- sto_out_ware_split_plu_yyyymm
- sto_pick_opr_body_yyyymm
- sto_send_pln_body_collect_yyyymm
- sto_send_pln_body_poll_yyyymm
- sto_send_pln_body_yyyymm
- sto_send_pln_collect_yyyymm
- sto_send_pln_diff_yyyymm
- sto_send_pln_dst_collect

IF question contains:

- 时间
- 日期
- 月份
- 某天
- 最近

Prefer tables with "_head" suffix (header tables).

Reason: Head tables contain time fields (创建时间, 审核时间, 出库时间 etc.).
Body tables (with "_body" suffix) only contain line items without time info.

When time filtering is needed:
  - Prefer joining the corresponding _head table to get time fields
  - Use head table's time fields for WHERE / GROUP BY date conditions

IF question contains:

- 配送
- 调拨
- 运输

Expand scope to include:

sto_dispatch_calc

Reason: 配送/调拨/运输场景的数据存储在 sto_dispatch_calc 表中，
该表不与出库主表直接关联，需要显式扩展检索范围。

IF question ambiguous:

TopK candidate tables = 5