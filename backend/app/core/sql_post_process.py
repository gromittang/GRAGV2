"""
SQL 后处理器
在 SQL 生成后、执行前对 SQL 做业务规则增强。
"""
import re


def inject_plu_name(sql: str) -> str:
    """如果 SQL 的 SELECT 中包含了 plu_code 但没有 plu_name，自动注入。

    规则：
    - 如果已 JOIN 的表中有 plu_name（如 cob_plu），直接追加该表的 plu_name
    - 否则添加 LEFT JOIN cob_plu 并追加 cob_plu.plu_name
    - 如果 cob_plu 已在 FROM/JOIN 中但 plu_name 未选，直接追加
    """
    if not sql or not sql.strip():
        return sql

    sql_lower = sql.lower()
    has_plu_code = bool(re.search(r'\bplu_code\b', sql_lower))
    has_plu_name = bool(re.search(r'\bplu_name\b', sql_lower))

    if not has_plu_code or has_plu_name:
        return sql

    # 判断 cob_plu 是否已在查询中
    has_cob_plu = 'cob_plu' in sql_lower

    if has_cob_plu:
        # cob_plu 已 JOIN，找到它的别名，追加 plu_name
        cob_alias = _find_alias(sql, 'cob_plu')
        plu_name_expr = f'{cob_alias}.plu_name' if cob_alias else 'cob_plu.plu_name'
        sql = _append_to_select(sql, plu_name_expr)
    else:
        # 需要新增 LEFT JOIN cob_plu
        plu_alias = _find_plu_code_alias(sql)
        join_on = f'{plu_alias}.plu_code = cob_plu.plu_code' if plu_alias else (
            # 尝试从第一个 FROM 表推断
            _first_from_alias(sql) + '.plu_code = cob_plu.plu_code'
        )
        sql = _append_to_select(sql, 'cob_plu.plu_name')
        sql = _inject_join(sql, f'LEFT JOIN cob_plu ON {join_on}')

    return sql


def _find_alias(sql: str, table_name: str) -> str:
    """查找某表在 SQL 中的别名。表名没有引号时直接匹配，加了引号时用反引号匹配。"""
    # 匹配: FROM/ JOIN table_name alias 或 FROM/ JOIN table_name AS alias
    pattern = rf'{table_name}\s+(?:AS\s+)?(\w+)'
    m = re.search(pattern, sql, re.IGNORECASE)
    if m:
        return m.group(1)
    # 如果没找到别名，可能表名本身作为别名（没有别名）
    # 检查是否使用了表名本身
    if re.search(rf'\b{table_name}\b', sql, re.IGNORECASE):
        return table_name
    return ""


def _find_plu_code_alias(sql: str) -> str:
    """找到 SELECT 中 plu_code 的表别名。"""
    m = re.search(r'(\w+)\.plu_code', sql, re.IGNORECASE)
    if m:
        return m.group(1)
    # 没有表前缀，尝试第一个 FROM 表的别名
    return _first_from_alias(sql)


def _first_from_alias(sql: str) -> str:
    """获取第一个 FROM 子句中的表别名。"""
    m = re.search(r'FROM\s+(\w+)\s+(?:AS\s+)?(\w+)', sql, re.IGNORECASE)
    if m:
        return m.group(2) if m.group(2) else m.group(1)
    return ""


def _append_to_select(sql: str, col_expr: str) -> str:
    """在 SELECT 与 FROM 之间追加一列。"""
    return re.sub(
        r'(\bFROM\b)',
        f', {col_expr} \\1',
        sql,
        count=1,
        flags=re.IGNORECASE,
    )


def _inject_join(sql: str, join_clause: str) -> str:
    """在 WHERE / LIMIT / ORDER / GROUP 之前注入 JOIN 子句。"""
    join_point = r'\b(WHERE|LIMIT|ORDER\s+BY|GROUP\s+BY)\b'
    if re.search(join_point, sql, re.IGNORECASE):
        return re.sub(
            join_point,
            f'{join_clause} \\1',
            sql,
            count=1,
            flags=re.IGNORECASE,
        )
    # 如果都没找到，追加到末尾
    return sql.rstrip().rstrip(';').rstrip() + f' {join_clause}'
