"""
LangGraph PM Solution Studio Agent
4 阶段管线：problem → analysis → detail → prd
核心能力：interrupt() 人机协同、检查点回退、StreamWriter 流式输出

图结构 (修复: generate 与 interrupt 分离，避免节点重入导致双次生成):
  START → retrieve → generate → pause → [interrupt()]
    → (continue) → retrieve (loop)
    → (confirm)  → confirm → advance
      → (has next) → retrieve (next stage)
      → (completed) → END
"""
import asyncio
import json
import time
from typing import Any, Dict, List, Optional

from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import StreamWriter, interrupt

from app.config import get_settings
from app.core.agent_state import PMSolutionState
from app.core.logging import get_logger
from app.rag.context_utils import stream_llm, llm_complete

settings = get_settings()
_log = get_logger("pm.graph")


# ============================================================
# Stage Config
# ============================================================

STAGE_TEMPLATES = {
    "problem": {
        "name": "问题定义",
        "description": "明确问题背景、目标、约束",
        "order": 0,
        "output_schema": {
            "summary": "问题摘要",
            "background": "背景信息",
            "goals": ["目标列表"],
            "constraints": ["约束列表"],
            "stakeholders": ["利益相关者"]
        }
    },
    "analysis": {
        "name": "方案分析",
        "description": "分析多个可行方案",
        "order": 1,
        "output_schema": {
            "options": [{"name": "", "approach": "", "pros": "", "cons": "", "score": 0}],
            "recommendation": "推荐方案"
        }
    },
    "detail": {
        "name": "方案细化",
        "description": "细化选定方案的功能设计",
        "order": 2,
        "output_schema": {
            "features": [{"name": "", "description": "", "priority": ""}],
            "user_stories": ["用户故事"],
            "technical_requirements": ["技术需求"]
        }
    },
    "prd": {
        "name": "PRD生成",
        "description": "生成完整产品需求文档",
        "order": 3,
        "output_schema": {
            "prd_content": "完整PRD文档"
        }
    }
}

STAGE_PROMPTS = {
    "problem": """你是PM方案分析师，当前处于"问题定义"阶段（Phase1）。
请帮助用户明确问题背景、目标、约束和利益相关者。

【输出格式要求】请使用Markdown格式输出，不要使用JSON格式：
- 使用标题和列表组织内容
- 每个要点使用清晰的段落描述
- 示例格式：

## 问题摘要
简要描述核心问题

## 背景
分析问题背景和现状

## 目标
1. 核心目标A
2. 核心目标B

## 约束条件
- 技术约束：...
- 资源约束：...

## 利益相关者
- 角色A：诉求...
- 角色B：诉求...

请基于知识库内容给出专业建议。本阶段定义的主题将在后续阶段继承使用。""",

    "analysis": """你是PM方案分析师，当前处于"方案分析"阶段（Phase2）。

【重要】你必须基于Phase1（问题定义阶段）讨论的内容继续分析，不能偏离主题。
Phase1已经定义了问题和目标，现在你要针对这些问题提出解决方案。

【输出格式要求】请使用Markdown格式输出，不要使用JSON格式：

## 方案对比

### 方案1: 方案名称
**实现方式**: 描述实现思路
**优点**:
- 优点A
- 优点B
**缺点**:
- 缺点A
**评分**: X/10

### 方案2: 方案名称
...

## 推荐方案
说明推荐理由，附综合评分

必须围绕Phase1确定的主题展开，不要引入新话题。""",

    "detail": """你是PM方案分析师，当前处于"方案细化"阶段（Phase3）。

【重要】你必须继承Phase1和Phase2的内容继续细化。
- Phase1定义了问题和目标
- Phase2分析了多个方案并选择了推荐方案
现在你要细化Phase2推荐的方案。

【输出格式要求】请使用Markdown格式输出，不要使用JSON格式：

## 功能模块

### 模块1: 模块名称
**功能描述**: 详细描述
**优先级**: 高/中/低
**技术要点**: 实现要点

### 模块2: ...

## 用户故事
1. 作为角色X，我希望...，以便...
2. ...

## 技术要求
- 要求A
- 要求B

## 验收标准
- 标准A
- 标准B

必须围绕方案主题展开，不要偏离。""",

    "prd": """你是PM方案分析师，当前处于"PRD生成"阶段（Phase4）。

【重要】你必须整合Phase1-3的所有内容生成完整PRD。
- Phase1：问题定义和目标
- Phase2：方案分析和选择
- Phase3：方案细化

【输出格式要求】请使用Markdown格式输出标准的PRD文档结构：

# 产品需求文档：[产品名称]

## 1. 产品概述
### 1.1 背景
整合Phase1的问题背景

### 1.2 目标
整合Phase1的核心目标

## 2. 功能需求
### 2.1 功能列表
整合Phase3的功能模块，使用表格或列表形式

| 功能模块 | 描述 | 优先级 |
|---------|------|-------|
| 模块A | 描述 | 高 |

### 2.2 用户故事
整合Phase3的用户故事

## 3. 技术要求
整合Phase3的技术要求

## 4. 验收标准
整合Phase3的验收标准

## 5. 里程碑规划
- M1: 功能开发完成
- M2: 测试验收
- M3: 上线发布

语言简洁专业，便于团队理解。PRD必须完整反映前三个阶段的讨论成果。"""
}

STAGE_ORDER = ["problem", "analysis", "detail", "prd"]


# ============================================================
# Standalone Helper Functions (extracted from PMSolutionService)
# ============================================================

def _should_retrieve(user_input: str, stage_type: str) -> bool:
    """判断是否需要检索知识库"""
    if stage_type == "problem":
        return True

    new_topic_keywords = ["新功能", "另外", "不同的", "换个", "另一个问题", "新方案"]
    for kw in new_topic_keywords:
        if kw in user_input:
            return True

    if len(user_input) > 100:
        return True

    return False


def _retrieve_sync(query: str, knowledge_id: str = None, top_k: int = 5) -> List[Dict]:
    """同步知识库检索（支持 knowledge_id=None 时跨所有知识库检索）"""
    from app.models.document import get_session, Document, Paragraph
    from app.core.vector_store import get_vector_store_manager
    from app.core.embedding import get_default_embedding

    session = get_session()
    try:
        # 未指定 knowledge_id：检索所有知识库
        if not knowledge_id:
            vector_manager = get_vector_store_manager()
            all_collections = vector_manager.list_collections()
            active_collections = [
                c for c in all_collections
                if c.count() > 0 and c.name.startswith("kb_documents_")
            ]
            if not active_collections:
                session.close()
                return []

            embed_model = get_default_embedding()
            query_embedding = embed_model.get_text_embedding(query)
            similarity_threshold = 0.5

            all_sources = []
            for coll in active_collections:
                try:
                    results = coll.query(
                        query_embeddings=[query_embedding],
                        n_results=min(10, top_k),
                        include=['documents', 'metadatas', 'distances']
                    )
                    if results["ids"] and results["ids"][0]:
                        for i, _doc_id in enumerate(results["ids"][0]):
                            text = results["documents"][0][i] if results["documents"] else ""
                            metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                            distance = results["distances"][0][i] if results.get("distances") else 0.2
                            similarity = 1 - distance
                            if similarity < similarity_threshold:
                                continue

                            doc = session.query(Document).filter(
                                Document.id == metadata.get("document_id", "")
                            ).first()
                            doc_name = doc.name if doc else "未知文档"
                            all_sources.append({
                                "content": text[:200] + "..." if len(text) > 200 else text,
                                "score": similarity,
                                "metadata": {**metadata, "document_name": doc_name}
                            })
                except Exception:
                    continue

            all_sources.sort(key=lambda x: x["score"], reverse=True)
            session.close()
            return all_sources[:top_k]

        # 指定 knowledge_id：按原有逻辑检索
        paragraphs = session.query(Paragraph).filter(
            Paragraph.knowledge_id == knowledge_id
        ).all()

        if not paragraphs:
            session.close()
            return []

        vector_manager = get_vector_store_manager()
        collection = vector_manager.get_collection(knowledge_id)

        if collection.count() == 0:
            # 向量库为空时的备用方案：关键词匹配
            sources = []
            query_lower = query.lower()
            for p in paragraphs:
                if query_lower in p.content.lower() or any(
                    kw in p.content for kw in query.split()[:3]
                ):
                    doc = session.query(Document).filter(
                        Document.id == p.document_id
                    ).first()
                    doc_name = doc.name if doc else "未知文档"
                    sources.append({
                        "content": p.content[:200] + "..." if len(p.content) > 200 else p.content,
                        "score": 0.5,
                        "metadata": {
                            "document_id": p.document_id,
                            "document_name": doc_name,
                            "knowledge_id": knowledge_id
                        }
                    })
                    if len(sources) >= top_k:
                        break

            if not sources:
                for p in paragraphs[:top_k]:
                    doc = session.query(Document).filter(
                        Document.id == p.document_id
                    ).first()
                    doc_name = doc.name if doc else "未知文档"
                    sources.append({
                        "content": p.content[:200] + "..." if len(p.content) > 200 else p.content,
                        "score": 0.3,
                        "metadata": {
                            "document_id": p.document_id,
                            "document_name": doc_name,
                            "knowledge_id": knowledge_id
                        }
                    })
            session.close()
            return sources

        embed_model = get_default_embedding()
        query_embedding = embed_model.get_text_embedding(query)
        results = collection.query(
            query_embeddings=[query_embedding],
            where={"knowledge_id": knowledge_id},
            n_results=top_k
        )

        sources = []
        if results["ids"]:
            for i, _doc_id in enumerate(results["ids"][0]):
                text = results["documents"][0][i] if results["documents"] else ""
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                doc = session.query(Document).filter(
                    Document.id == metadata.get("document_id", "")
                ).first()
                doc_name = doc.name if doc else "未知文档"
                sources.append({
                    "content": text[:200] + "..." if len(text) > 200 else text,
                    "score": 0.8,
                    "metadata": {**metadata, "document_name": doc_name}
                })

        session.close()
        return sources[:top_k]

    except Exception as e:
        _log.error("PM retrieve failed: {}", e)
        session.close()
        return []


def _extract_summary(output_data: dict) -> str:
    """从结构化输出提取文本摘要"""
    if "summary" in output_data:
        return str(output_data["summary"])[:200]
    elif "recommendation" in output_data:
        return str(output_data["recommendation"])[:200]
    elif "prd_content" in output_data:
        return str(output_data["prd_content"])[:200]
    else:
        return json.dumps(output_data, ensure_ascii=False)[:200]


# ============================================================
# Graph Nodes
# ============================================================

async def retrieve_node(state: PMSolutionState) -> dict:
    """检索知识库（条件触发）"""
    user_input = state.get("user_input", "")
    stage_type = state["current_stage"]
    knowledge_id = state.get("knowledge_id")

    need_retrieve = _should_retrieve(user_input, stage_type)
    if not need_retrieve:
        _log.info("[PM-retrieve] skip retrieval, stage={}", stage_type)
        return {"context": "", "sources": [], "need_retrieve": False}

    _log.info("[PM-retrieve] retrieving, stage={}, knowledge_id={}", stage_type, knowledge_id)
    t0 = time.time()
    sources = await asyncio.to_thread(_retrieve_sync, user_input, knowledge_id)
    context = "\n\n".join([s["content"] for s in sources]) if sources else ""
    _log.info("[PM-retrieve] done, {} sources in {:.0f}ms", len(sources), (time.time() - t0) * 1000)

    return {"context": context, "sources": sources, "need_retrieve": True}


async def generate_node(state: PMSolutionState, writer: StreamWriter) -> dict:
    """纯流式生成（不调用 interrupt，避免节点重入时重复执行）

    关键设计：interrupt 放在独立的 pause_node 中，
    这样 LangGraph 恢复时不会从本节点开头重入，杜绝双次 LLM 调用。
    """
    stage_type = state["current_stage"]
    user_input = state.get("user_input", "")
    context = state.get("context", "")
    session_topic = state.get("session_topic", "")
    sources = state.get("sources", [])
    stage_chats = state.get("stage_chats", {})

    writer({"type": "status", "content": "正在生成回答..."})

    system_prompt = STAGE_PROMPTS.get(stage_type, STAGE_PROMPTS["problem"])

    # 本阶段近期对话历史
    current_chats = stage_chats.get(stage_type, [])

    # 如果当前阶段已有 assistant 回复，说明用户在提出修改意见
    # 将上一轮输出作为基准，要求 LLM 仅做局部修改
    existing_assistant_msgs = [m for m in current_chats if m.get("role") == "assistant"]
    if existing_assistant_msgs:
        last_response = existing_assistant_msgs[-1]["content"]
        system_prompt += f"""

【重要：局部修改模式】
以下是你在当前阶段上一轮的完整输出。用户希望你在其基础上进行局部修改。
请**仅**修改用户明确提到的内容，其他部分必须逐字保持不变，不得重写或扩写。

---上一轮输出开始---
{last_response}
---上一轮输出结束---

请严格根据用户意见修改上述内容，只改动被提及的部分，其余原样输出。"""

    # 构建上下文消息
    context_parts = []
    if session_topic:
        context_parts.append(f"【方案核心主题】\n{session_topic}\n")
    if context:
        context_parts.append(f"【知识库参考】\n{context}\n")

    # 前阶段摘要
    if stage_chats and stage_type != "problem":
        prev_summaries = []
        for st in STAGE_ORDER[:STAGE_ORDER.index(stage_type)]:
            st_chats = stage_chats.get(st, [])
            for msg in st_chats:
                if msg.get("role") == "assistant":
                    prev_summaries.append(f"[{st}] {msg['content'][:300]}...")
        if prev_summaries:
            context_parts.append("【前阶段讨论摘要】\n" + "\n".join(prev_summaries[-3:]) + "\n")

    if context_parts:
        current_msg = "\n".join(context_parts) + f"\n【当前用户输入】\n{user_input}"
    else:
        current_msg = user_input

    messages = [{"role": "system", "content": system_prompt}]

    for msg in current_chats[-4:]:
        messages.append({"role": msg["role"], "content": msg["content"][:500]})

    messages.append({"role": "user", "content": current_msg})

    # 提取 session_topic（首次生成时）
    if not session_topic and stage_type == "problem" and user_input:
        session_topic = user_input

    # 流式生成
    full_answer = ""
    async for token in stream_llm(messages, max_tokens=8000, temperature=0.7):
        if isinstance(token, dict) and token.get("type") == "usage":
            pass  # token usage record, not for streaming
        elif token is not None:
            full_answer += str(token)
            writer({"type": "token", "content": token})

    writer({"type": "done", "sources": sources, "stage": stage_type})

    # 更新聊天记录
    updated_stage_chats = dict(stage_chats)
    if stage_type not in updated_stage_chats:
        updated_stage_chats[stage_type] = []
    updated_stage_chats[stage_type].append({"role": "user", "content": user_input, "sources": []})
    updated_stage_chats[stage_type].append({"role": "assistant", "content": full_answer, "sources": sources})

    _log.info("[PM-generate] answer len={}, chats for stage {} = {}",
              len(full_answer), stage_type, len(updated_stage_chats.get(stage_type, [])))

    return {
        "answer": full_answer,
        "stage_chats": updated_stage_chats,
        "session_topic": session_topic,
    }


async def pause_node(state: PMSolutionState) -> dict:
    """人机协同暂停点：调用 interrupt() 等待用户决策。

    放在独立节点中，避免 generate_node 因 LangGraph 重入机制
    而被完整重执行（导致双次 LLM 调用）。
    """
    stage_type = state["current_stage"]
    sources = state.get("sources", [])
    answer = state.get("answer", "")

    resume_data = interrupt({
        "stage": stage_type,
        "answer_preview": answer[:200],
        "sources": sources
    })

    user_action = resume_data.get("action", "continue") if isinstance(resume_data, dict) else "continue"
    user_input_next = resume_data.get("input", "") if isinstance(resume_data, dict) else ""

    _log.info("[PM-pause] resumed, action={}, input_len={}", user_action, len(user_input_next))

    # 确认时如有用户输入，记录到当前阶段聊天历史（纳入确认的结构化输出和下一阶段上下文）
    result = {
        "user_input": user_input_next,
        "user_action": user_action,
    }
    if user_action == "confirm" and user_input_next:
        updated_stage_chats = dict(state.get("stage_chats", {}))
        if stage_type not in updated_stage_chats:
            updated_stage_chats[stage_type] = []
        updated_stage_chats[stage_type].append({
            "role": "user", "content": user_input_next, "sources": []
        })
        result["stage_chats"] = updated_stage_chats

    return result


async def confirm_node(state: PMSolutionState) -> dict:
    """生成阶段结构化 JSON 输出（非流式）"""
    stage_type = state["current_stage"]
    stage_chats = state.get("stage_chats", {})
    current_chats = stage_chats.get(stage_type, [])

    output_schema = STAGE_TEMPLATES[stage_type]["output_schema"]
    history_text = "\n".join([
        f"{msg['role']}: {msg['content'][:300]}"
        for msg in current_chats
    ])

    # 如果当前阶段已有 assistant 回复，将其作为基准，仅做局部修改
    existing_assistant_msgs = [m for m in current_chats if m.get("role") == "assistant"]
    base_instruction = ""
    if existing_assistant_msgs:
        last_response = existing_assistant_msgs[-1]["content"]
        base_instruction = f"""

【重要：局部修改模式】
以下是当前阶段已有的输出内容。请仅根据对话历史中用户的最新修改意见做局部调整，
其余字段和内容严格保持原样，不得重写或扩写无关部分。

---已有输出开始---
{last_response}
---已有输出结束---"""

    prompt = f"""根据以下对话历史，生成该阶段的结构化输出。
{base_instruction}
## 对话历史
{history_text}

## 输出格式要求
{json.dumps(output_schema, ensure_ascii=False, indent=2)}

请严格按照输出格式生成JSON内容，只返回JSON，不要其他解释。"""

    _log.info("[PM-confirm] generating structured output for stage={}, chats={}",
              stage_type, len(current_chats))

    answer, usage = await llm_complete(
        [{"role": "user", "content": prompt}],
        max_tokens=8000,
        temperature=0.3
    )

    # 解析 JSON
    content = answer or ""
    try:
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()
        else:
            json_str = content.strip()
        structured_output = json.loads(json_str)
    except (json.JSONDecodeError, IndexError):
        structured_output = {"raw_output": content}

    if usage:
        structured_output["_token_usage"] = usage

    _log.info("[PM-confirm] structured output keys={}", list(structured_output.keys()))

    return {"structured_output": structured_output}


async def advance_node(state: PMSolutionState) -> dict:
    """推进到下一阶段或完成"""
    stage_type = state["current_stage"]
    structured_output = state.get("structured_output", {})
    staged_outputs = dict(state.get("stage_outputs", {}))
    session_topic = state.get("session_topic", "")

    # 确认当前阶段输出
    staged_outputs[stage_type] = {
        "output_data": structured_output,
        "summary": _extract_summary(structured_output),
        "confirmed_at": time.time(),
    }

    current_idx = STAGE_ORDER.index(stage_type)

    if current_idx + 1 < len(STAGE_ORDER):
        next_stage = STAGE_ORDER[current_idx + 1]
        next_name = STAGE_TEMPLATES[next_stage]["name"]
        _log.info("[PM-advance] {} → {}", stage_type, next_stage)
        return {
            "current_stage": next_stage,
            "stage_outputs": staged_outputs,
            "user_action": "continue",
            "user_input": f"请开始{next_name}阶段的分析",
            "is_completed": False,
            "session_topic": session_topic,
        }
    else:
        _log.info("[PM-advance] all stages completed")
        return {
            "stage_outputs": staged_outputs,
            "is_completed": True,
            "session_topic": session_topic,
        }


# ============================================================
# Routing Functions
# ============================================================

def route_after_pause(state: PMSolutionState) -> str:
    if state.get("user_action") == "confirm":
        return "confirm"
    return "continue"


def route_after_advance(state: PMSolutionState) -> str:
    if state.get("is_completed"):
        return END
    return "next_stage"


# ============================================================
# Graph Builder
# ============================================================

def build_pm_graph() -> StateGraph:
    """构建 PM 方案工作室 StateGraph

    拓扑:
      START → retrieve → generate → pause → [interrupt 暂停]
        ↑        ↑                      │
        │        └─── continue ─────────┘
        │                               │ confirm
        └─── next_stage ────────────────┘
                        ↓
                 confirm → advance
                             │
                             ├── has next → retrieve (下一阶段)
                             └── completed → END
    """
    graph = StateGraph(PMSolutionState)

    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    graph.add_node("pause", pause_node)
    graph.add_node("confirm", confirm_node)
    graph.add_node("advance", advance_node)

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "pause")

    graph.add_conditional_edges("pause", route_after_pause, {
        "continue": "retrieve",
        "confirm": "confirm",
    })

    graph.add_edge("confirm", "advance")

    graph.add_conditional_edges("advance", route_after_advance, {
        "next_stage": "retrieve",
        END: END,
    })

    return graph


# ============================================================
# Compiled Graph Cache
# ============================================================

_pm_graph = None
_pm_checkpointer = None


def get_pm_graph() -> StateGraph:
    global _pm_graph, _pm_checkpointer
    if _pm_graph is None:
        _pm_checkpointer = MemorySaver()
        _pm_graph = build_pm_graph().compile(checkpointer=_pm_checkpointer)
        _log.info("[PM-graph] compiled with MemorySaver checkpointer")
    return _pm_graph


def get_pm_checkpointer() -> MemorySaver:
    global _pm_checkpointer
    if _pm_checkpointer is None:
        get_pm_graph()  # triggers compilation
    return _pm_checkpointer
