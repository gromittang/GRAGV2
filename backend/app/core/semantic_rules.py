"""
语义规则共享模块
从 query_agent.py 提取，供新旧 Agent 共同使用，避免代码重复。
"""
import os


HARD_RULES: dict[str, list[str]] = {
    "库存": ["sto_stock_batch_yyyymm_org"],
    "stock": ["sto_stock_batch_yyyymm_org"],
    "inventory": ["sto_stock_batch_yyyymm_org"],
    "出库": ["sto_out_ware_head_yyyymm", "sto_out_ware_body_yyyymm"],
    "outbound": ["sto_out_ware_head_yyyymm", "sto_out_ware_body_yyyymm"],
    "配送": ["sto_send_pln_head_yyyymm", "sto_send_pln_collect_yyyymm"],
    "delivery": ["sto_send_pln_head_yyyymm", "sto_send_pln_collect_yyyymm"],
    "收货": ["sto_accept_head_yyyymm", "sto_accept_body_yyyymm"],
    "验收": ["sto_accept_head_yyyymm", "sto_accept_body_yyyymm"],
    "采购": ["sto_accept_head_yyyymm", "sto_accept_body_yyyymm"],
    "入库": ["sto_accept_head_yyyymm", "sto_accept_body_yyyymm"],
    "拣货": ["sto_pick_opr_head_yyyymm", "sto_pick_opr_body_yyyymm", "sto_plu_org_loc_set"],
    "摘果": ["sto_pick_opr_head_yyyymm", "sto_pick_opr_body_yyyymm"],
    "商品信息": ["cob_plu", "cob_plu_packet"],
    "商品基础": ["cob_plu", "cob_plu_packet"],
    "锁定": ["sto_lock_yyyymm_org"],
    "lock": ["sto_lock_yyyymm_org"],
}

_SPEC_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "spec")
)


def load_spec_context() -> str:
    parts = []
    for rel_path in ["nl2sql/semantic-layer.md", "business-rules/sql-rules.md"]:
        path = os.path.join(_SPEC_DIR, rel_path)
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    parts.append(content)
            except Exception:
                pass
    if not parts:
        return ""
    return "【业务规则 - 优先级高于表结构】\n\n" + "\n\n".join(parts) + "\n\n"


def match_semantic_rules(question: str) -> list[str]:
    forced_tables: list[str] = []
    question_lower = question.lower()
    for keyword, tables in HARD_RULES.items():
        if keyword.lower() in question_lower:
            forced_tables.extend(tables)
    return list(dict.fromkeys(forced_tables))


def parse_insight(content: str) -> dict:
    lines = content.split("\n")
    insights = []
    follow_ups = []

    for line in lines:
        line = line.strip()
        if line.startswith("- ") and "结论" in content[:200]:
            insights.append(line[2:])
        elif "追问" in line or "还想了解" in line:
            if ":" in line:
                follow_part = line.split(":")[-1]
                follow_ups = [q.strip() for q in follow_part.replace("?", "").split(",") if q.strip()][:3]

    summary = insights[0] if insights else "查询成功"

    return {
        "summary": summary,
        "insights": insights[:3],
        "follow_ups": follow_ups[:3],
        "raw": content,
    }
