"""
日志查看 API
从 data/logs/ 和 data/traces/ 的 JSON lines 文件读取最近条目
使用 seek-based 反向读取，避免全量加载大文件
"""
import os
import json
import glob
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter()
_settings = get_settings()

LOG_DIR = os.path.join(_settings.data_dir, "logs")
TRACE_DIR = os.path.join(_settings.data_dir, "traces")

MAX_LIMIT = 1000
MAX_MINUTES = 1440  # 24 hours
BLOCK_SIZE = 8192  # 8KB read-backward blocks


def _to_beijing_time(ts: str) -> str:
    """将 UTC ISO 时间戳转为北京时间字符串 (UTC+8)"""
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts)
        if dt.utcoffset() is not None:
            dt = dt.astimezone(timezone(timedelta(hours=8)))
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}"
    except (ValueError, TypeError):
        return ts[:23] if ts else ""


def _normalize_log_entry(data: dict) -> dict:
    """标准化日志条目：trace 扁平 JSON 直接透传，Loguru serialize 格式则提取字段"""
    # Trace span — already flat JSON, pass through as-is
    if "span_id" in data:
        ts = _to_beijing_time(data.get("start_time", ""))
        return {
            "trace_id": data.get("trace_id", ""),
            "span_id": data.get("span_id", ""),
            "parent_span_id": data.get("parent_span_id", ""),
            "timestamp": ts,
            "name": data.get("name", ""),
            "duration_ms": data.get("duration_ms", 0),
            "status": data.get("status", ""),
            "error": data.get("error"),
            "input": data.get("input", {}),
            "output": data.get("output", {}),
            "metadata": data.get("metadata", {}),
        }

    # Loguru serialize=True format: {"text": "...", "record": {"time": {...}, ...}}
    record = data.get("record", data)
    time = record.get("time", {})
    if isinstance(time, dict):
        ts = time.get("repr", "")
        # "2026-06-12 09:15:18.845845+08:00" -> "2026-06-12T09:15:18.845"
        ts = ts.replace(" ", "T")[:23] if ts else ""
    else:
        ts = str(time) if time else ""
    level = record.get("level", {})
    if isinstance(level, dict):
        level = level.get("name", "")
    extra = record.get("extra", {})
    return {
        "timestamp": ts,
        "level": level,
        "module": extra.get("module", ""),
        "trace_id": extra.get("trace_id", ""),
        "message": record.get("message", ""),
        "function": record.get("function", ""),
        "line": record.get("line", 0),
    }


def _parse_jsonl_line(line: str) -> Optional[dict]:
    """安全解析单行 JSON，失败返回 None"""
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
        return _normalize_log_entry(data)
    except json.JSONDecodeError:
        return None


def _read_file_backward(filepath: str, limit: int, cutoff: datetime) -> list:
    """从文件末尾反向读取 JSON lines，直到收集 limit 条或时间超过 cutoff

    Args:
        filepath: JSON lines 文件路径
        limit: 最多收集条数
        cutoff: 时间下限（早于此时间的条目被忽略）

    Returns:
        (entries, reached_start): entries 为正向排列的条目列表，reached_start 表示是否读到了文件头
    """
    entries = []
    try:
        with open(filepath, "rb") as f:
            f.seek(0, 2)
            file_size = f.tell()
            if file_size == 0:
                return entries, True

            pos = file_size
            leftover = b""

            while pos > 0 and len(entries) < limit:
                read_size = min(BLOCK_SIZE, pos)
                pos -= read_size
                f.seek(pos)
                chunk = f.read(read_size) + leftover

                # 按换行分割，第一条可能不完整
                lines = chunk.split(b"\n")

                # 最后一个元素是当前块的 leftover（不完整的第一行），留给下一轮
                leftover = lines[0]

                # 从后往前解析完整行
                for raw in reversed(lines[1:]):
                    if len(entries) >= limit:
                        break
                    entry = _parse_jsonl_line(raw.decode("utf-8", errors="replace"))
                    if entry is None:
                        continue
                    # 检查时间
                    ts_str = entry.get("timestamp", "")
                    try:
                        if ts_str:
                            ts = datetime.fromisoformat(ts_str)
                            # timestamp 没有时区信息，当作本地时间
                            if ts < cutoff:
                                return entries, False  # 超过 cutoff，停止
                    except (ValueError, TypeError):
                        pass
                    entries.append(entry)

            # 处理 leftover（文件的第一行）
            if leftover and len(entries) < limit:
                entry = _parse_jsonl_line(leftover.decode("utf-8", errors="replace"))
                if entry:
                    ts_str = entry.get("timestamp", "")
                    try:
                        if ts_str:
                            ts = datetime.fromisoformat(ts_str)
                            if ts >= cutoff:
                                entries.append(entry)
                    except (ValueError, TypeError):
                        entries.append(entry)

            entries.reverse()  # 恢复正向顺序
            return entries, (pos == 0)

    except FileNotFoundError:
        return entries, True
    except Exception:
        return entries, True


def _find_matching_files(directory: str, pattern: str) -> list:
    """查找匹配的文件，按日期倒序排列，跳过 .gz"""
    full_pattern = os.path.join(directory, pattern)
    files = glob.glob(full_pattern)
    files = [f for f in files if not f.endswith(".gz")]
    files.sort(reverse=True)  # 最新在前
    return files


def _read_recent_logs(limit: int, minutes: int) -> dict:
    """读取最近的 app 日志"""
    cutoff = datetime.now().replace(microsecond=0) - timedelta(minutes=minutes)
    files = _find_matching_files(LOG_DIR, "app.*.jsonl")
    entries = []

    for filepath in files:
        if len(entries) >= limit:
            break
        batch, _ = _read_file_backward(filepath, limit - len(entries), cutoff)
        entries.extend(batch)

    # 截断到 limit
    entries = entries[-limit:]
    return {"type": "logs", "entries": entries, "total": len(entries)}


def _read_recent_traces(limit: int, minutes: int) -> dict:
    """读取最近的 trace spans"""
    cutoff = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=minutes)
    files = _find_matching_files(TRACE_DIR, "trace.*.jsonl")
    entries = []

    for filepath in files:
        if len(entries) >= limit:
            break
        batch, _ = _read_file_backward(filepath, limit - len(entries), cutoff)
        entries.extend(batch)

    entries = entries[-limit:]
    return {"type": "traces", "entries": entries, "total": len(entries)}


async def _read_recent_queries(limit: int, minutes: int) -> dict:
    """从 SQLite query_history 读取最近的查询追踪记录"""
    import aiosqlite
    from app.models.query_history import HISTORY_DB_PATH

    cutoff = (datetime.now().replace(microsecond=0) - timedelta(minutes=minutes)).isoformat()

    entries = []
    try:
        async with aiosqlite.connect(HISTORY_DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT id, question, sql, result_count, trace_json, created_at
                FROM query_history
                WHERE created_at >= ?
                ORDER BY created_at DESC
                LIMIT ?
            """, [cutoff, limit])
            rows = await cursor.fetchall()
            for row in rows:
                trace = {}
                try:
                    trace = json.loads(row["trace_json"] or "{}")
                except (json.JSONDecodeError, TypeError):
                    pass
                entries.append({
                    "id": row["id"],
                    "question": row["question"],
                    "sql": row["sql"],
                    "result_count": row["result_count"],
                    "created_at": row["created_at"],
                    "trace": trace,
                })
    except Exception:
        pass  # 数据库不存在或尚未初始化时返回空列表

    return {"type": "queries", "entries": entries, "total": len(entries)}


class LogsResponse(BaseModel):
    type: str
    entries: list
    total: int


@router.get("/recent", response_model=LogsResponse)
async def get_recent_logs(
    type: str = Query("logs", description="日志类型: logs | traces | queries"),
    limit: int = Query(50, ge=1, le=MAX_LIMIT, description="返回条数上限"),
    minutes: int = Query(60, ge=1, le=MAX_MINUTES, description="时间范围（分钟）"),
):
    """获取最近的日志、追踪或查询记录

    - **type=logs**: 从 data/logs/app.*.jsonl 读取
    - **type=traces**: 从 data/traces/trace.*.jsonl 读取
    - **type=queries**: 从 SQLite query_history 读取
    """
    if type not in ("logs", "traces", "queries"):
        raise HTTPException(status_code=400, detail="type 必须为 logs、traces 或 queries")

    if type == "queries":
        return await _read_recent_queries(limit, minutes)

    loop = asyncio.get_running_loop()

    if type == "traces":
        result = await loop.run_in_executor(None, _read_recent_traces, limit, minutes)
    else:
        result = await loop.run_in_executor(None, _read_recent_logs, limit, minutes)

    return result
