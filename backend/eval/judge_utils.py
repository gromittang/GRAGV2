"""共享 LLM Judge 工具函数。"""
import json
import re
import sys
from pathlib import Path
from typing import Dict, Optional

# 确保 backend/ 在 sys.path 上（eval/ 在 backend/ 下 1 层）
_backend_dir = str(Path(__file__).resolve().parents[1])
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)


def get_llm():
    """获取 LLM 实例，与项目使用一致的配置。"""
    from app.config import get_settings
    from app.core.llm_manager import get_llm as _get_llm

    settings = get_settings()
    return _get_llm(settings.llm_provider)


def parse_judge_response(content: str) -> Optional[Dict]:
    """从 LLM 响应中提取 JSON 评判结果。"""
    try:
        return json.loads(content.strip())
    except json.JSONDecodeError:
        pass

    match = re.search(r'\{[\s\S]*?\}', content.strip())
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None
