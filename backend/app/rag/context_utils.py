"""
上下文处理工具函数
图片提取、预处理、消息构建、LLM 流式调用
"""
import re
import json
from typing import List, Dict, Optional

import httpx

from app.config import get_settings

settings = get_settings()


def extract_images_from_text(text: str) -> List[Dict]:
    """
    从文本中提取图片信息
    格式: [IMG]{url}|图片{n}[/IMG]
    返回: [{"url": url, "label": label}, ...]
    """
    pattern = r'\[IMG\]([^|]+)\|([^[]+)\[/IMG\]'
    matches = re.findall(pattern, text)
    return [{"url": match[0], "label": match[1]} for match in matches]


def preprocess_context(context: str):
    """预处理知识库上下文：提取图片引用、去重、清理标记

    Returns:
        (cleaned_context, img_refs)
        img_refs: {idx: {"url": str, "label": str}}，无图片时为空dict
    """
    images = extract_images_from_text(context)
    if not images:
        return context, {}

    # 按URL去重
    seen_urls = set()
    unique_images = []
    for img in images:
        if img["url"] not in seen_urls:
            seen_urls.add(img["url"])
            unique_images.append(img)

    # 替换原始 [IMG] 标记为更可读的占位符
    cleaned = context
    img_refs = {}
    for idx, img in enumerate(unique_images, 1):
        original = f"[IMG]{img['url']}|{img['label']}[/IMG]"
        placeholder = f"【图片{idx}: {img['label']}】"
        img_refs[idx] = img
        cleaned = cleaned.replace(original, placeholder)

    return cleaned, img_refs


def build_chat_messages(question: str, context: str, history: List[Dict] = None,
                        img_refs: Dict = None) -> List[Dict]:
    """构建 LLM 消息"""
    history_context = ""
    if history:
        parts = []
        for msg in history[-6:]:
            role = "用户" if msg["role"] == "user" else "系统"
            content = msg["content"][:150] if len(msg["content"]) > 150 else msg["content"]
            parts.append(f"{role}: {content}")
        history_context = "\n【对话历史】\n" + "\n".join(parts) + "\n"

    # 构建图片引用表（有图片时）
    img_section = ""
    if img_refs:
        lines = ["\n【可用图片引用】"]
        for idx, img in img_refs.items():
            lines.append(f"- 图片{idx}: ![{img['label']}]({img['url']})")
        img_section = "\n".join(lines)

    # System prompt（单独拆分，提高指令遵循度）
    system_prompt = "你是知识库问答助手。请根据提供的知识库内容回答问题。如果知识库内容不足以回答，请告知用户你无法回答该问题。"
    if img_refs:
        system_prompt += (
            "\n注意：知识库中的【图片N: xxx】表示该位置有一张图片。"
            "如果回答内容涉及该图片，请直接使用\"可用图片引用\"中提供的 "
            "Markdown 图片语法 ![描述](URL) 将其插入到回答的合适位置。"
        )

    user_prompt = f"""{history_context}
【知识库内容】
{context}
{img_section}
【当前问题】
{question}

请根据知识库内容简洁准确回答，标注来源。"""

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"][:200]})
    messages.append({"role": "user", "content": user_prompt})
    return messages


def apply_img_safety_net(text: str, img_refs: Dict) -> str:
    """后处理安全网：将 LLM 未转换的【图片N】替换为 Markdown 图片语法"""
    if not img_refs:
        return text
    for idx, img in img_refs.items():
        markdown_img = f"![{img['label']}]({img['url']})"
        text = text.replace(f"【图片{idx}: {img['label']}】", markdown_img)
        text = text.replace(f"【图片{idx}】", markdown_img)
    return text


async def stream_llm(messages: List[Dict], max_tokens: int = 1000, temperature: float = 0.7):
    """异步流式 LLM 调用（httpx.AsyncClient），逐个 yield token 字符串

    最后一个 yield 为 dict: {"type": "usage", "prompt_tokens": N, "completion_tokens": N, "total_tokens": N}
    若未捕获到 usage 则为 None。
    """
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{settings.deepseek_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.deepseek_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": settings.deepseek_model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": True,
                    "stream_options": {"include_usage": True}
                }
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                            if "usage" in chunk and chunk["usage"]:
                                yield {"type": "usage", **chunk["usage"]}
                        except Exception:
                            continue

    except Exception as e:
        yield f"\n[生成中断: {str(e)}]"
    finally:
        yield None  # sentinel: 无 usage 数据


async def llm_complete(messages: List[Dict], max_tokens: int = 1000, temperature: float = 0.7):
    """异步非流式 LLM 调用，返回完整回答和 token 用量

    Returns:
        (answer_text, usage_dict_or_None)
        其中 usage_dict = {"prompt_tokens": N, "completion_tokens": N, "total_tokens": N}
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.deepseek_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.deepseek_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": settings.deepseek_model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }
            )
            if response.status_code == 200:
                result = response.json()
                answer = result["choices"][0]["message"]["content"]
                usage = result.get("usage")
                return answer, usage
            return f"API失败: {response.status_code}", None
    except Exception as e:
        return f"生成失败: {str(e)}", None


def get_document_info(document_id: str) -> Dict:
    """从数据库获取文档信息"""
    if not document_id:
        return {"name": "", "id": ""}
    try:
        from app.models.document import get_session, Document
        session = get_session()
        doc = session.query(Document).filter(Document.id == document_id).first()
        if doc:
            result = {"name": doc.name, "id": doc.id}
        else:
            result = {"name": "未知文档", "id": document_id}
        session.close()
        return result
    except Exception:
        return {"name": "未知文档", "id": document_id}


def get_kb_context_for_rejection(limit: int = 10) -> str:
    """获取知识库概览文本（知识库名 + 文档标题样本），供拒答提示词使用

    Returns:
        格式化字符串，每行 "- 知识库名 / 文档标题"
        无结果返回 "（知识库暂无文档）"
        异常返回 "（无法获取知识库信息）"
    """
    try:
        from app.models.document import get_session, Document, Knowledge

        session = get_session()
        try:
            rows = (
                session.query(Knowledge.name, Document.name)
                .join(Document, Document.knowledge_id == Knowledge.id)
                .filter(Document.is_active == True)
                .order_by(Document.created_at.desc())
                .limit(limit)
                .all()
            )
            if rows:
                lines = [f"- {kb_name} / {doc_name}" for kb_name, doc_name in rows]
                return "\n".join(lines)
            return "（知识库暂无文档）"
        finally:
            session.close()
    except Exception:
        return "（无法获取知识库信息）"


def build_sources(nodes: List) -> List[Dict]:
    """构建来源信息，包含文档名称和图片"""
    sources = []
    seen_doc_ids = set()

    for n in nodes:
        doc_id = n.metadata.get("document_id", "")
        doc_info = get_document_info(doc_id)
        images = extract_images_from_text(n.text)

        source = {
            "content": n.text[:200] + "..." if len(n.text) > 200 else n.text,
            "score": getattr(n, "score", 0),
            "images": images,
            "metadata": {
                **n.metadata,
                "document_name": doc_info["name"],
                "document_id": doc_info["id"],
            }
        }

        if doc_id and doc_id in seen_doc_ids:
            continue
        if doc_id:
            seen_doc_ids.add(doc_id)

        sources.append(source)

    return sources[:5]