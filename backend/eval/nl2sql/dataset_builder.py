"""从 seed_queries.json 生成 golden_sql.json 标准用例。

v1: 仅做确定性 SQL 解析（sqlparse），不做 LLM 问法变体生成。
v2: 通过 --augment flag 启用 LLM 变体生成。
"""
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

try:
    import sqlparse
    from sqlparse.sql import IdentifierList, Identifier, Function
    from sqlparse.tokens import Keyword, DML, Name
except ImportError:
    print("Install sqlparse first: pip install sqlparse>=0.4.0")
    sys.exit(1)

_DATASETS_DIR = Path(__file__).resolve().parent / "datasets"
_SEED_FILE = _DATASETS_DIR / "seed_queries.json"
_GOLDEN_FILE = _DATASETS_DIR / "golden_sql.json"

_SQL_KEYWORDS = {
    "select", "from", "where", "group", "order", "limit", "having",
    "and", "or", "as", "on", "by", "asc", "desc", "distinct", "not",
    "null", "in", "is", "like", "between", "exists", "join", "inner",
    "left", "right", "outer", "cross", "full", "union", "all", "case",
    "when", "then", "else", "end", "cast", "coalesce", "ifnull", "nullif",
    "count", "sum", "avg", "max", "min", "date_sub", "now", "interval",
    "set", "into", "values", "create", "alter", "drop", "truncate",
    "primary", "key", "foreign", "index", "unique",
}

_JOIN_KW_SET = {"FROM", "JOIN", "INNER", "LEFT", "RIGHT", "OUTER", "CROSS", "FULL"}


def _is_join_keyword(value: str) -> bool:
    """sqlparse 会把 'LEFT JOIN' 合并为一个 token，需要按空格拆分匹配。"""
    return any(kw in value.upper().split() for kw in _JOIN_KW_SET)


def _extract_tables(sql: str) -> List[str]:
    """从 SQL 中提取涉及的表名（FROM / JOIN 后的表名）。"""
    tables = []
    parsed = sqlparse.parse(sql)
    if not parsed:
        return tables

    statement = parsed[0]

    def _find_table_after(tokens, start_idx):
        """从 start_idx+1 开始找真正的表名（跳过后续关键字和空白）。"""
        for j in range(start_idx + 1, len(tokens)):
            nxt = tokens[j]
            if nxt.is_whitespace:
                continue
            ttype = getattr(nxt, 'ttype', None)
            val = str(nxt.value) if hasattr(nxt, 'value') else ""
            # 跳过多词关键字的后续部分
            if ttype is Keyword:
                if _is_join_keyword(val):
                    continue
                break  # 遇到非 JOIN 关键字（如 ON/WHERE），停止
            # 找到表名
            if isinstance(nxt, Identifier):
                name = nxt.get_real_name()
                if name and name.lower() not in _SQL_KEYWORDS:
                    tables.append(name.lower())
            elif isinstance(nxt, (IdentifierList,)):
                for ident in nxt.get_identifiers():
                    if hasattr(ident, 'get_real_name'):
                        name = ident.get_real_name()
                        if name and name.lower() not in _SQL_KEYWORDS:
                            tables.append(name.lower())
            elif ttype is Name:
                name = str(nxt.value).strip().strip('`').strip('"').strip("'").lower()
                if name and name not in _SQL_KEYWORDS and len(name) > 1:
                    tables.append(name)
            break

    def _walk_tokens(tokens):
        for i, token in enumerate(tokens):
            ttype = getattr(token, 'ttype', None)
            value = str(token) if hasattr(token, 'value') else ""
            if ttype is Keyword and _is_join_keyword(value):
                _find_table_after(tokens, i)
            if hasattr(token, 'tokens'):
                _walk_tokens(token.tokens)

    _walk_tokens(statement.tokens)
    return list(dict.fromkeys(tables))


def _extract_columns(sql: str) -> List[str]:
    """从 SQL SELECT 子句中提取字段名。"""
    columns = []
    parsed = sqlparse.parse(sql)
    if not parsed:
        return columns

    statement = parsed[0]
    in_select = False

    def _walk_select(tokens):
        nonlocal in_select, columns
        for token in tokens:
            ttype = getattr(token, 'ttype', None)
            value = str(token).upper().strip() if hasattr(token, 'value') else ""

            if ttype is DML and value == "SELECT":
                in_select = True
                continue

            if not in_select:
                if hasattr(token, 'tokens'):
                    _walk_select(token.tokens)
                continue

            if ttype is Keyword and value == "FROM":
                in_select = False
                return

            if isinstance(token, Identifier):
                name = token.get_real_name()
                if name and name.lower() not in _SQL_KEYWORDS and name != "*":
                    columns.append(name.lower())
            elif isinstance(token, (IdentifierList,)):
                for ident in token.get_identifiers():
                    if hasattr(ident, 'get_real_name'):
                        name = ident.get_real_name()
                        if name and name.lower() not in _SQL_KEYWORDS and name != "*":
                            columns.append(name.lower())

            if hasattr(token, 'tokens'):
                _walk_select(token.tokens)

    _walk_select(statement.tokens)
    return list(dict.fromkeys(columns))


def _extract_keywords(sql: str) -> List[str]:
    """从 SQL 中提取关键标识符：表名、字段名、字面量值。"""
    keywords = []
    parsed = sqlparse.parse(sql)
    if not parsed:
        return keywords

    statement = parsed[0]

    for token in statement.flatten():
        if isinstance(token, Identifier):
            name = token.get_real_name()
            if name and name.lower() not in _SQL_KEYWORDS:
                keywords.append(name.lower())
        elif token.ttype is Name and not isinstance(token, (Function,)):
            name = str(token.value).strip().strip(",").strip("`").lower()
            if name and name not in _SQL_KEYWORDS:
                keywords.append(name)
        elif token.ttype is sqlparse.tokens.Number.Integer or token.ttype is sqlparse.tokens.Number.Float:
            keywords.append(token.value)
        elif token.ttype is sqlparse.tokens.Literal.String.Single:
            keywords.append(token.value.strip("'"))

    return list(dict.fromkeys(keywords))


def _load_hard_rules() -> Dict[str, List[str]]:
    """加载 _HARD_RULES。优先从 query_agent 导入，失败时使用本地副本。"""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from app.agents.query_agent import _HARD_RULES as rules
        return rules
    except Exception:
        # 本地副本，需与 query_agent.py._HARD_RULES 保持同步
        return {
            "库存": ["sto_stock_batch_yyyymm_org"],
            "stock": ["sto_stock_batch_yyyymm_org"],
            "inventory": ["sto_stock_batch_yyyymm_org"],
            "出库": ["sto_out_ware_head_yyyymm", "sto_out_ware_body_yyyymm"],
            "outbound": ["sto_out_ware_head_yyyymm", "sto_out_ware_body_yyyymm"],
            "配送": ["sto_send_pln_head_yyyymm", "sto_send_pln_collect_yyyymm"],
            "delivery": ["sto_send_pln_head_yyyymm", "sto_send_pln_collect_yyyymm"],
            "收货": ["sto_accept_head_yyyymm", "sto_accept_body_yyyymm"],
            "验收": ["sto_accept_head_yyyymm", "sto_accept_body_yyyymm"],
            "拣货": ["sto_pick_opr_head_yyyymm", "sto_pick_opr_body_yyyymm", "sto_plu_org_loc_set"],
            "商品信息": ["cob_plu", "cob_plu_packet"],
            "锁定": ["sto_lock_yyyymm_org"],
            "lock": ["sto_lock_yyyymm_org"],
        }


def _match_hard_rule(question: str, description: str) -> Optional[str]:
    """检查是否命中 _HARD_RULES 中的关键词。"""
    combined = f"{question} {description}".lower()
    for keyword in _load_hard_rules():
        if keyword.lower() in combined:
            return keyword
    return None


def build_dataset() -> List[Dict]:
    """读取 seed_queries.json，生成 golden_sql.json 条目。"""
    if not _SEED_FILE.exists():
        print(f"[ERROR] seed_queries.json not found at {_SEED_FILE}")
        sys.exit(1)

    with open(_SEED_FILE, "r", encoding="utf-8") as f:
        seeds = json.load(f)

    cases = []
    for i, seed in enumerate(seeds, 1):
        sql = seed.get("sql", "").strip()
        description = seed.get("description", "").strip()

        if not sql:
            print(f"[WARN] seed {i}: missing 'sql' field, skipped")
            continue
        if not description:
            print(f"[WARN] seed {i}: missing 'description' field, skipped")
            continue

        tables = _extract_tables(sql)
        columns = _extract_columns(sql)
        keywords = _extract_keywords(sql)
        hard_rule = _match_hard_rule(description, description)

        case = {
            "id": f"seed_{i:03d}",
            "question": description,
            "expected_tables": tables,
            "expected_columns": columns,
            "expected_sql": sql,
            "expected_keywords": keywords,
            "expected_insight_keywords": [],
            "hard_rule": hard_rule,
            "category": seed.get("category", "general"),
            "allow_equivalent": True,
            "_PENDING_REVIEW": True
        }
        cases.append(case)
        hw = f", hard_rule={hard_rule}" if hard_rule else ""
        print(f"  [OK] seed_{i:03d}: tables={tables}, columns={columns}{hw}")

    return cases


def main():
    """主入口。"""
    print("=" * 60)
    print("NL2SQL Dataset Builder (v1)")
    print("=" * 60)

    cases = build_dataset()

    if not cases:
        print("\n[ERROR] No cases generated. Check seed_queries.json.")
        sys.exit(1)

    _DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    with open(_GOLDEN_FILE, "w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)

    print(f"\nGenerated {len(cases)} cases -> {_GOLDEN_FILE}")
    print("Next: review golden_sql.json and remove _PENDING_REVIEW fields.")


if __name__ == "__main__":
    main()
