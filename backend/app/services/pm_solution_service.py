"""
PM方案工作室服务层
支持知识库隔离检索、SSE流式对话、结构化输出生成
支持跨阶段上下文继承
"""
from typing import List, Dict, Any, Optional
import json
import httpx
import time
from datetime import datetime

from app.config import get_settings
from app.services.rag_service import get_rag_service
from app.models.document import get_session, Document, Paragraph

settings = get_settings()

# 日志辅助函数
def log_timing(stage: str, message: str, start_time: float = None):
    """记录时间日志"""
    elapsed = (time.time() - start_time) * 1000 if start_time else 0
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    if start_time:
        print(f"[{timestamp}] [PM-{stage}] {message} (耗时: {elapsed:.0f}ms)")
    else:
        print(f"[{timestamp}] [PM-{stage}] {message}")


# 阶段提示词模板 - 强调继承前阶段内容，明确输出格式
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


class PMSolutionService:
    """PM方案服务"""

    def __init__(self, knowledge_id: str = None):
        self.knowledge_id = knowledge_id
        self.rag_service = get_rag_service(knowledge_id)

    def _get_session_topic(self, session_id: str) -> str:
        """获取session的核心主题（从Phase1用户输入提取）"""
        session = get_session()
        try:
            from app.models.pm_solution import PMChat, PMStage

            # 获取Phase1的第一条用户消息作为主题
            problem_stage = session.query(PMStage).filter(
                PMStage.session_id == session_id,
                PMStage.stage_type == "problem"
            ).first()

            if not problem_stage:
                session.close()
                return ""

            first_chat = session.query(PMChat).filter(
                PMChat.stage_id == problem_stage.id,
                PMChat.role == "user"
            ).order_by(PMChat.created_at).first()

            topic = first_chat.content if first_chat else ""
            session.close()
            return topic

        except Exception as e:
            log_timing("TOPIC", f"获取主题失败: {e}")
            session.close()
            return ""

    def _get_all_session_history(self, session_id: str, current_stage: str) -> List[Dict]:
        """获取整个session的对话历史（跨阶段继承）"""
        session = get_session()
        try:
            from app.models.pm_solution import PMChat, PMStage

            # 定义阶段顺序
            stage_order = ["problem", "analysis", "detail", "prd"]
            current_idx = stage_order.index(current_stage) if current_stage in stage_order else 0

            # 获取当前及之前所有阶段的对话（继承历史）
            history = []
            for stage_type in stage_order[:current_idx + 1]:
                stage = session.query(PMStage).filter(
                    PMStage.session_id == session_id,
                    PMStage.stage_type == stage_type
                ).first()

                if stage:
                    chats = session.query(PMChat).filter(
                        PMChat.stage_id == stage.id
                    ).order_by(PMChat.created_at).all()

                    for c in chats:
                        history.append({
                            "role": c.role,
                            "content": c.content,
                            "stage": stage_type
                        })

            session.close()
            return history

        except Exception as e:
            log_timing("HISTORY", f"获取全历史失败: {e}")
            session.close()
            return []

    def _should_retrieve(self, user_input: str, session_id: str, stage_type: str) -> bool:
        """判断是否需要重新检索知识库"""
        # Phase1总是需要检索
        if stage_type == "problem":
            return True

        # 检查用户输入是否包含新话题关键词
        new_topic_keywords = ["新功能", "另外", "不同的", "换个", "另一个问题", "新方案"]
        for kw in new_topic_keywords:
            if kw in user_input:
                return True

        # 检查用户输入是否足够长（可能是新内容）
        if len(user_input) > 100:
            return True

        # 其他情况不检索，使用已有上下文
        return False

    def _retrieve_with_isolation(self, query: str, top_k: int = 5) -> List[Dict]:
        """知识库隔离检索（支持不限定知识库时检索全部）"""
        retrieve_start = time.time()

        session = get_session()
        try:
            # 如果未指定knowledge_id，检索所有知识库
            if not self.knowledge_id:
                log_timing("RETRIEVE", "未指定knowledge_id，检索所有知识库")

                # 获取所有有数据的向量库collection
                from app.core.vector_store import get_vector_store_manager
                vector_manager = get_vector_store_manager()
                all_collections = vector_manager.list_collections()

                # 找到有数据的collection
                active_collections = [c for c in all_collections if c.count() > 0 and c.name.startswith("kb_documents_")]

                if not active_collections:
                    log_timing("RETRIEVE", "所有向量库为空，返回空")
                    session.close()
                    return []

                log_timing("RETRIEVE", f"找到 {len(active_collections)} 个有数据的向量库")

                # 生成查询向量
                from app.core.embedding import get_default_embedding
                embed_model = get_default_embedding()
                query_embedding = embed_model.get_text_embedding(query)

                # 相似度阈值：低于此值的结果不返回
                similarity_threshold = 0.5

                # 从每个collection检索，合并结果
                all_sources = []
                for coll in active_collections:
                    try:
                        # 每个collection取足够数量，最后合并排序
                        results = coll.query(
                            query_embeddings=[query_embedding],
                            n_results=min(10, top_k),  # 每个collection取足够数量
                            include=['documents', 'metadatas', 'distances']  # 包含距离信息
                        )

                        if results["ids"] and results["ids"][0]:
                            for i, doc_id in enumerate(results["ids"][0]):
                                text = results["documents"][0][i] if results["documents"] else ""
                                metadata = results["metadatas"][0][i] if results["metadatas"] else {}

                                # ChromaDB distance转相似度: similarity = 1 - distance (cosine空间)
                                distance = results["distances"][0][i] if results.get("distances") else 0.2
                                similarity = 1 - distance

                                # 阈值过滤：只返回相似度>=阈值的结果
                                if similarity < similarity_threshold:
                                    continue

                                doc = session.query(Document).filter(
                                    Document.id == metadata.get("document_id", "")
                                ).first()
                                doc_name = doc.name if doc else "未知文档"

                                all_sources.append({
                                    "content": text[:200] + "..." if len(text) > 200 else text,
                                    "score": similarity,  # 使用真实相似度
                                    "metadata": {
                                        **metadata,
                                        "document_name": doc_name
                                    }
                                })
                    except Exception as e:
                        log_timing("RETRIEVE", f"Collection {coll.name} 检索失败: {e}")
                        continue

                # 按相似度排序（高到低），取top_k
                all_sources.sort(key=lambda x: x["score"], reverse=True)
                session.close()
                log_timing("RETRIEVE", f"从所有知识库返回 {len(all_sources[:top_k])} 个来源（阈值={similarity_threshold}）", retrieve_start)
                return all_sources[:top_k]

            # 指定了knowledge_id，按原来的逻辑检索
            log_timing("RETRIEVE", "开始查询段落表...")
            paragraphs = session.query(Paragraph).filter(
                Paragraph.knowledge_id == self.knowledge_id
            ).all()

            log_timing("RETRIEVE", f"知识库 {self.knowledge_id} 有 {len(paragraphs)} 个段落", retrieve_start)

            if not paragraphs:
                log_timing("RETRIEVE", "段落表无数据，返回空")
                session.close()
                return []

            # 使用向量检索（带metadata过滤）
            log_timing("RETRIEVE", "开始获取向量库collection...")
            from app.core.vector_store import get_vector_store_manager
            vector_manager = get_vector_store_manager()
            collection = vector_manager.get_collection(self.knowledge_id)

            log_timing("RETRIEVE", f"向量库collection count: {collection.count()}")

            if collection.count() == 0:
                log_timing("RETRIEVE", "向量库为空，尝试从段落表检索...")
                # 向量库为空时的备用方案：关键词匹配而非顺序取
                sources = []
                query_lower = query.lower()
                for p in paragraphs:
                    # 简单关键词匹配
                    if query_lower in p.content.lower() or any(kw in p.content for kw in query.split()[:3]):
                        doc = session.query(Document).filter(Document.id == p.document_id).first()
                        doc_name = doc.name if doc else "未知文档"
                        sources.append({
                            "content": p.content[:200] + "..." if len(p.content) > 200 else p.content,
                            "score": 0.5,
                            "metadata": {
                                "document_id": p.document_id,
                                "document_name": doc_name,
                                "knowledge_id": self.knowledge_id
                            }
                        })
                        if len(sources) >= top_k:
                            break

                if not sources:
                    # 如果关键词匹配无结果，取前几个
                    for p in paragraphs[:top_k]:
                        doc = session.query(Document).filter(Document.id == p.document_id).first()
                        doc_name = doc.name if doc else "未知文档"
                        sources.append({
                            "content": p.content[:200] + "..." if len(p.content) > 200 else p.content,
                            "score": 0.3,
                            "metadata": {
                                "document_id": p.document_id,
                                "document_name": doc_name,
                                "knowledge_id": self.knowledge_id
                            }
                        })

                log_timing("RETRIEVE", f"从段落表返回 {len(sources)} 个来源", retrieve_start)
                session.close()
                return sources

            log_timing("RETRIEVE", "开始向量检索query...")
            query_start = time.time()

            # 使用embedding模型生成查询向量
            from app.core.embedding import get_default_embedding
            embed_model = get_default_embedding()
            query_embedding = embed_model.get_text_embedding(query)

            results = collection.query(
                query_embeddings=[query_embedding],
                where={"knowledge_id": self.knowledge_id},
                n_results=top_k
            )
            log_timing("RETRIEVE", f"向量检索完成 ids={len(results['ids'][0])}", query_start)

            sources = []
            if results["ids"]:
                for i, doc_id in enumerate(results["ids"][0]):
                    text = results["documents"][0][i] if results["documents"] else ""
                    metadata = results["metadatas"][0][i] if results["metadatas"] else {}

                    # 获取文档名称
                    doc = session.query(Document).filter(
                        Document.id == metadata.get("document_id", "")
                    ).first()
                    doc_name = doc.name if doc else "未知文档"

                    sources.append({
                        "content": text[:200] + "..." if len(text) > 200 else text,
                        "score": 0.8,
                        "metadata": {
                            **metadata,
                            "document_name": doc_name
                        }
                    })

            session.close()
            log_timing("RETRIEVE", f"最终返回 {len(sources)} 个来源", retrieve_start)
            return sources[:top_k]

        except Exception as e:
            log_timing("RETRIEVE", f"检索失败: {e}")
            session.close()
            return []

    def chat_stream(self, session_id: str, stage_type: str, user_input: str):
        """SSE流式对话 - 支持跨阶段上下文继承"""
        total_start = time.time()
        log_timing("CHAT", f"开始对话 session_id={session_id}, stage={stage_type}")

        # 1. 获取方案核心主题（从Phase1）
        session_topic = self._get_session_topic(session_id)
        log_timing("CHAT", f"方案主题: {session_topic[:50] if session_topic else '无'}...")

        # 2. 判断是否需要检索知识库
        need_retrieve = self._should_retrieve(user_input, session_id, stage_type)

        # 3. 构建检索查询
        if need_retrieve:
            yield {"type": "status", "content": "正在搜索知识库..."}
            retrieve_start = time.time()

            # 检索查询策略：优先使用用户输入，必要时补充方案主题
            # 用户输入通常更准确反映当前需求
            if len(user_input) >= 10:
                # 用户输入足够长，直接使用
                retrieve_query = user_input
            elif session_topic and len(session_topic) > 20:
                # 用户输入较短，但方案主题有内容，合并使用
                retrieve_query = f"{user_input} {session_topic[:100]}"
            else:
                # 都不够长，使用用户输入
                retrieve_query = user_input

            log_timing("RETRIEVE", f"检索查询: {retrieve_query[:50]}...")
            sources = self._retrieve_with_isolation(retrieve_query)
            log_timing("RETRIEVE", f"检索完成，返回{len(sources)}个来源（相似度>=0.5）", retrieve_start)

            # 构建上下文
            context = "\n\n".join([s["content"] for s in sources]) if sources else ""
        else:
            log_timing("RETRIEVE", "跳过检索，使用已有上下文")
            sources = []
            context = ""

        # 4. 获取完整对话历史（跨阶段）
        history_start = time.time()
        all_history = self._get_all_session_history(session_id, stage_type)
        log_timing("HISTORY", f"获取全历史完成，history_count={len(all_history)}", history_start)

        # 5. 流式生成
        yield {"type": "status", "content": "正在生成回答..."}
        llm_start = time.time()

        token_count = 0
        for token in self._generate_llm_stream(stage_type, context, all_history, user_input, session_topic):
            token_count += 1
            yield {"type": "token", "content": token}

        log_timing("LLM", f"流式生成完成，共{token_count}个token", llm_start)

        # 6. 返回来源
        yield {"type": "done", "sources": sources}
        log_timing("CHAT", f"对话流程完成，总耗时={(time.time()-total_start)*1000:.0f}ms", total_start)

    def _get_chat_history(self, session_id: str, stage_type: str) -> List[Dict]:
        """获取当前阶段的对话历史（用于存储）"""
        session = get_session()
        try:
            from app.models.pm_solution import PMChat, PMStage

            stage = session.query(PMStage).filter(
                PMStage.session_id == session_id,
                PMStage.stage_type == stage_type
            ).first()

            if not stage:
                session.close()
                return []

            chats = session.query(PMChat).filter(
                PMChat.stage_id == stage.id
            ).order_by(PMChat.created_at).all()

            history = [{"role": c.role, "content": c.content} for c in chats]
            session.close()
            return history

        except Exception as e:
            print(f"[PM] 获取历史失败: {e}")
            session.close()
            return []

    def _generate_llm_stream(self, stage_type: str, context: str, history: List[Dict], user_input: str, session_topic: str = ""):
        """流式调用LLM - 包含跨阶段上下文"""
        if not settings.deepseek_api_key:
            yield "[请配置DeepSeek API密钥]"
            return

        system_prompt = STAGE_PROMPTS.get(stage_type, STAGE_PROMPTS["problem"])

        # 构建增强的上下文消息
        context_parts = []

        # 1. 如果有方案主题，添加到上下文
        if session_topic:
            context_parts.append(f"【方案核心主题】\n{session_topic}\n")

        # 2. 添加知识库检索结果
        if context:
            context_parts.append(f"【知识库参考】\n{context}\n")

        # 3. 添加之前的对话历史摘要（如果有且不是Phase1）
        if history and stage_type != "problem":
            # 提取之前阶段的assistant回复作为摘要
            prev_summaries = []
            for msg in history:
                if msg["role"] == "assistant" and msg["stage"] != stage_type:
                    prev_summaries.append(f"[{msg['stage']}] {msg['content'][:300]}...")
            if prev_summaries:
                context_parts.append(f"【前阶段讨论摘要】\n" + "\n".join(prev_summaries[-3:]) + "\n")

        # 构建当前消息
        if context_parts:
            current_msg = "\n".join(context_parts) + f"\n【当前用户输入】\n{user_input}"
        else:
            current_msg = user_input

        messages = [{"role": "system", "content": system_prompt}]
        log_timing("LLM", f"system_prompt长度={len(system_prompt)}")

        # 添加当前阶段的对话历史（最近几条）
        current_stage_history = [msg for msg in history if msg.get("stage") == stage_type]
        for msg in current_stage_history[-4:]:
            messages.append({"role": msg["role"], "content": msg["content"][:500]})

        messages.append({"role": "user", "content": current_msg})
        log_timing("LLM", f"当前消息长度={len(current_msg)}, 总messages={len(messages)}")

        try:
            with httpx.stream(
                "POST",
                f"{settings.deepseek_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.deepseek_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": settings.deepseek_model,
                    "messages": messages,
                    "max_tokens": 8000,
                    "temperature": 0.7,
                    "stream": True
                },
                timeout=60.0
            ) as response:
                for line in response.iter_lines():
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
                        except Exception:
                            continue

        except Exception as e:
            yield f"\n[生成中断: {str(e)}]"

    def generate_structured_output(self, stage_type: str, chat_history: List[Dict], output_schema: Dict) -> Dict:
        """基于对话历史生成结构化输出"""
        if not settings.deepseek_api_key:
            return {"error": "请配置DeepSeek API密钥"}

        # 格式化对话历史
        history_text = "\n".join([
            f"{msg['role']}: {msg['content'][:300]}"
            for msg in chat_history
        ])

        prompt = f"""根据以下对话历史，生成该阶段的结构化输出。

## 对话历史
{history_text}

## 输出格式要求
{json.dumps(output_schema, ensure_ascii=False, indent=2)}

请严格按照输出格式生成JSON内容，只返回JSON，不要其他解释。"""

        try:
            response = httpx.post(
                f"{settings.deepseek_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.deepseek_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": settings.deepseek_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 8000,
                    "temperature": 0.3
                },
                timeout=30.0
            )

            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                try:
                    if "```json" in content:
                        json_str = content.split("```json")[1].split("```")[0].strip()
                    elif "```" in content:
                        json_str = content.split("```")[1].split("```")[0].strip()
                    else:
                        json_str = content.strip()

                    return json.loads(json_str)
                except:
                    return {"raw_output": content}

            return {"error": f"API失败: {response.status_code}"}

        except Exception as e:
            return {"error": f"生成失败: {str(e)}"}