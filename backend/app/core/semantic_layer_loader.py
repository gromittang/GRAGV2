"""
语义层加载器
从 semantic-layer.md 提取的结构化数据，供领域分类、字段白名单、JOIN校验使用。
数据与 spec/nl2sql/semantic-layer.md 保持同步。
"""
from typing import Dict, List, Optional


# 域定义：名称 → {描述, 表列表, 关键词}
DOMAINS: Dict[str, dict] = {
    "库存": {
        "desc": "库存域涵盖仓库中商品的存储数量、批次、库位分布及库存状态。关注在库数量(stork_count)、库位(location_code)、批次(batch_no)、生产日期(mannu_date)、到期日期(due_date)。典型查询：当前库存量、按仓库统计库存分布、即将过期的批次库存、锁定库存。",
        "tables": ["sto_stock_batch_yyyymm_org", "sto_plu_org_loc_set"],
        "keywords": ["库存", "在库", "库存数量", "批次", "库位", "存量", "盘点", "过期", "临期"],
    },
    "出库": {
        "desc": "出库域涵盖商品从仓库发出的所有业务：出库单生成、出库建议、配送计划制定。关注出库数量(out_ware_count)、出库类型(out_ware_type)、时间(make_date)。典型查询：按时间统计出库量、按门店查配送量、出库单关联配送计划。配送相关查询常跨越出库单和配送计划两个维度。",
        "tables": [
            "sto_out_ware_head_yyyymm", "sto_out_ware_body_yyyymm",
            "sto_send_pln_head_yyyymm", "sto_send_pln_collect_yyyymm",
            "sto_send_pln_body_poll_yyyymm",
        ],
        "keywords": ["出库", "发货", "出仓", "外发", "调拨出", "出库单", "出库建议", "计划数量", "实发数量"],
    },
    "配送": {
        "desc": "配送域涵盖商品从仓库配送到门店/客户的全过程：配送计划制定、波次汇总、派车调度。关注配送数量(dst_count/send_count)、车牌(car_license)、门店(shop_code)、装车顺序(send_lin_num)。与出库域紧密关联——出库是配送的执行动作。",
        "tables": [
            "sto_send_pln_head_yyyymm", "sto_send_pln_collect_yyyymm",
            "sto_send_pln_body_poll_yyyymm",
        ],
        "keywords": ["配送", "派车", "波次", "装车", "发车", "路线", "汇总单", "车牌", "司机"],
    },
    "收货": {
        "desc": "收货域(含采购入库)涵盖供应商送货到仓库后的验收、入库流程。关注验收数量(accept_count)、实收数量(real_count)、供应商(sup_code)、验收状态(verify_status)。验收表本身就是采购收货记录表，不需要额外过滤busi_type。典型查询：按时间统计采购入库量、按供应商查收货明细。",
        "tables": ["sto_accept_head_yyyymm", "sto_accept_body_yyyymm"],
        "keywords": ["收货", "验收", "采购", "入库", "进货", "供应商", "采购订单", "实收", "验收单"],
    },
    "拣货": {
        "desc": "拣货域涵盖仓库作业人员从库位取出商品的全过程：摘果拣货、整箱拣货、散件拣货。关注摘果数量(move_count)、拣货包装(pick_pack)、作业类型(opr_type)、库位(location_code)。典型查询：按时间/库位统计拣货量、查询拣货任务状态。",
        "tables": [
            "sto_pick_opr_head_yyyymm", "sto_pick_opr_body_yyyymm",
            "sto_plu_org_loc_set",
        ],
        "keywords": ["拣货", "摘果", "拣货位", "拣货作业", "分拣", "播种", "RF拣货"],
    },
    "商品": {
        "desc": "商品域涵盖商品基础信息和包装规格。关注商品编码(plu_code)、名称(plu_name)、规格(spec_desc)、单位(plu_unit)、状态(is_active/biz_status)。商品查询需要JOIN包装表(cob_plu_packet)获取包装细数。注意cob_plu_packet没有is_active字段，商品有效性过滤只在cob_plu上做。",
        "tables": ["cob_plu", "cob_plu_packet"],
        "keywords": ["商品", "品名", "规格", "条码", "包装", "商品组", "品牌", "分类"],
    },
    "仓库设置": {
        "desc": "仓库设置域涵盖商品在特定仓库中的配置：批次处理策略(batch_type)、抽检标识(need_spot)、补货上下限(repl_low_count/repl_max_count)。典型查询：查看需要抽检的商品、查询补货库存低于警戒线的商品。",
        "tables": ["sto_plu_org_set", "sto_plu_org_loc_cpfr"],
        "keywords": ["仓库设置", "批次方式", "FIFO", "LIFO", "抽检", "补货", "警戒库存", "最高库存"],
    },
    "锁定": {
        "desc": "库存锁定域涵盖被冻结/锁定的库存记录：锁定数量(lock_count)、锁定状态(stock_status)、来源单据(ref_bill_type)。典型查询：查询当前被锁定的库存、按商品查锁定记录。",
        "tables": ["sto_lock_yyyymm_org"],
        "keywords": ["锁定", "冻结", "锁库", "占用"],
    },
    "仓位": {
        "desc": "仓位域涵盖仓库物理储位属性：库位编码(location_code)、职能(location_duty)、拣货频次(pick_frequency)、有效性(is_active)。典型查询：按物流区域查找可用库位、按拣货频次排序。",
        "tables": ["sto_location"],
        "keywords": ["库位", "仓位", "货架", "储位", "拣货位", "排位列", "层"],
    },
    "用户": {
        "desc": "用户域涵盖系统用户信息：用户编码(UserCode)、名称(UserName)、类型(UserType)、启用状态(IsEnable)。典型查询：查询有效用户列表、按组织筛选用户。",
        "tables": ["tFrsUser"],
        "keywords": ["用户", "账号", "管理员", "操作员", "员工"],
    },
}


# 表字段白名单：从 semantic-layer.md 的 "Key columns" 提取
TABLE_KEY_COLUMNS: Dict[str, List[str]] = {
    "sto_stock_batch_yyyymm_org": [
        "org_code", "store_code", "location_code", "plu_code", "bar_code",
        "batch_no", "stork_count", "store_status", "pur_date", "mannu_date",
        "due_date", "logistics_code",
    ],
    "sto_plu_org_loc_set": [
        "plu_code", "plu_ex_code", "org_code", "store_code", "log_area_code",
        "shelf_code", "location_code", "print_date", "print_times",
    ],
    "sto_out_ware_head_yyyymm": [
        "bill_no", "make_date", "shop_code", "out_ware_type", "out_ware_count",
        "ref_bill_no", "ref_bill_type", "org_code", "store_code", "busi_type",
        "remark", "package_count", "out_plu_count",
    ],
    "sto_out_ware_body_yyyymm": [
        "bill_no", "plu_code", "bar_code", "location_code", "pack_unit",
        "pack_qty", "pack_count", "sgl_count", "out_ware_count", "batch_no",
        "mannu_date", "log_area_code",
    ],
    "sto_send_pln_head_yyyymm": [
        "bill_no", "make_date", "org_code", "store_code", "shop_code",
        "send_count", "plan_count", "is_checked", "is_emerg_send",
        "is_allow_send", "ref_bill_no", "ref_bill_type", "dispatch_status",
        "wave_code", "collect_bill_no", "logist_code",
    ],
    "sto_send_pln_collect_yyyymm": [
        "collect_bill_no", "make_date", "org_code", "store_code", "shop_type",
        "shop_code", "car_license", "locations", "dst_count", "out_plu_count",
        "package_count", "plan_count", "send_lin_num",
    ],
    "sto_send_pln_body_poll_yyyymm": [
        "collect_bill_no", "ref_bill_no", "plu_code", "pack_unit", "pack_qty",
        "pack_count", "pick_count", "sgl_count", "out_ware_count", "send_count",
        "pur_price", "pur_cost",
    ],
    "sto_accept_head_yyyymm": [
        "bill_no", "make_date", "submit_date", "verify_date", "verify_status",
        "org_code", "sup_code", "cnt_code", "busi_type", "operate_mode",
        "stock_code", "status", "ref_bill_type", "ref_bill_no", "accept_count",
    ],
    "sto_accept_body_yyyymm": [
        "bill_no", "serial_no", "plu_code", "bar_code", "pack_unit",
        "pack_qty", "pack_count", "sgl_count", "accept_count", "real_count",
        "pur_price", "mannu_date", "due_date", "remark",
    ],
    "sto_pick_opr_head_yyyymm": [
        "bill_no", "make_date", "opr_type", "org_code", "owner_org_code",
        "shop_code", "send_bill_no", "ref_bill_type", "ref_bill_no",
        "wave_code", "move_count", "pick_pack", "opr_date", "opr_user",
        "locations",
    ],
    "sto_pick_opr_body_yyyymm": [
        "bill_no", "serial_no", "plu_code", "pack_unit", "pack_qty",
        "pack_count", "sgl_count", "move_count", "store_code", "log_area_code",
        "location_code", "to_store_code", "to_location_code", "batch_no",
        "mannu_date",
    ],
    "cob_plu": [
        "plu_code", "plu_name", "spec_desc", "plu_unit", "bar_code",
        "plu_kind", "biz_status", "is_active", "qa_days", "brand_code",
        "cls_code", "prod_area", "weight",
    ],
    "cob_plu_packet": [
        "plu_code", "pack_bar_code", "pack_unit", "pack_qty", "pack_spec",
        "is_base_ware", "is_pur_pack", "is_dist_pack", "pack_long",
        "pack_width", "pack_height", "pack_weight",
    ],
    "sto_plu_org_set": [
        "plu_code", "org_code", "store_code", "plu_kind", "batch_type",
        "need_spot", "plu_pick_policy", "min_picking_count", "fix_pick_type",
        "plu_cw_duty", "plu_abbr", "plu_store_type", "pick_frequency",
        "package_count_ctrl",
    ],
    "sto_plu_org_loc_cpfr": [
        "plu_code", "org_code", "store_code", "log_area_code", "shelf_code",
        "location_code", "repl_low_count", "repl_max_count", "put_more_count",
    ],
    "sto_lock_yyyymm_org": [
        "serial_no", "org_code", "store_code", "location_code", "plu_code",
        "bar_code", "batch_no", "lock_date", "lock_count", "stock_status",
        "ref_bill_type", "ref_bill_no", "shop_code", "mannu_date",
        "logistics_code",
    ],
    "sto_location": [
        "org_code", "store_code", "log_area_code", "shelf_code", "location_code",
        "location", "location_type", "location_duty", "location_pos", "status",
        "is_active", "pick_frequency", "pick_order", "pallets_count",
    ],
    "tFrsUser": [
        "UserID", "UserCode", "UserName", "UserType", "IsEnable", "BgnDate",
        "EndDate", "OrgCode", "EmpCode",
    ],
}


# JOIN 关系: (table_a, table_b) → [(col_a, col_b)]
JOIN_GRAPH: Dict[tuple, List[tuple]] = {
    ("sto_out_ware_head_yyyymm", "sto_out_ware_body_yyyymm"): [("bill_no", "bill_no")],
    ("sto_out_ware_head_yyyymm", "sto_send_pln_head_yyyymm"): [("ref_bill_no", "bill_no")],
    ("sto_send_pln_collect_yyyymm", "sto_send_pln_body_poll_yyyymm"): [("collect_bill_no", "collect_bill_no")],
    ("sto_stock_batch_yyyymm_org", "sto_plu_org_loc_set"): [("location_code", "location_code")],
    ("cob_plu", "cob_plu_packet"): [("plu_code", "plu_code")],
    ("sto_plu_org_set", "sto_plu_org_loc_cpfr"): [("plu_code", "plu_code")],
    ("sto_accept_head_yyyymm", "sto_accept_body_yyyymm"): [("bill_no", "bill_no")],
}


def get_domains() -> List[dict]:
    """获取所有域定义"""
    return [{"name": k, **v} for k, v in DOMAINS.items()]


def get_domain_tables(domain: str) -> List[str]:
    """获取域对应的表列表"""
    d = DOMAINS.get(domain, {})
    return d.get("tables", [])


def get_domain_desc(domain: str) -> str:
    """获取域描述文本（用于 embedding）"""
    d = DOMAINS.get(domain, {})
    return d.get("desc", "")


def get_essential_columns(table_name: str) -> List[str]:
    """获取表的关键字段列表"""
    return TABLE_KEY_COLUMNS.get(table_name, [])


def get_all_managed_tables() -> List[str]:
    """获取所有有 Key columns 定义的表"""
    return list(TABLE_KEY_COLUMNS.keys())


def get_join_keys(table_name: str) -> List[str]:
    """获取某表在所有 JOIN 关系中涉及的字段"""
    keys = set()
    for (a, b), cols in JOIN_GRAPH.items():
        if table_name == a:
            keys.update(c[0] for c in cols)
        elif table_name == b:
            keys.update(c[1] for c in cols)
    return list(keys)


def get_valid_joins(table_a: str, table_b: str) -> List[tuple]:
    """获取两表之间的合法 JOIN 条件"""
    key = (table_a, table_b)
    if key in JOIN_GRAPH:
        return JOIN_GRAPH[key]
    key_rev = (table_b, table_a)
    if key_rev in JOIN_GRAPH:
        return [(b, a) for a, b in JOIN_GRAPH[key_rev]]
    return []
