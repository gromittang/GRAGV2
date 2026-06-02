"""
PM方案工作室服务层
支持知识库隔离检索、SSE流式对话、结构化输出生成
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


# 阶段提示词模板
STAGE_PROMPTS = {
    "problem": """你是PM方案分析师，当前处于"问题定义"阶段。
请帮助用户明确问题背景、目标、约束和利益相关者。

回答要点：
1. 分析问题背景和现状
2. 提炼核心目标（优先级排序）
3. 识别约束条件（技术、资源、时间等）
4. 列出利益相关者及其诉求

请基于知识库内容给出专业建议。""",

    "analysis": """你是PM方案分析师，当前处于"方案分析"阶段。
请帮助用户分析多个可行方案，对比优劣。

回答要点：
1. 提出至少2-3个可行方案
2. 分析各方案的技术路径
3. 对比优缺点和风险
4. 给出推荐建议（附带评分）

请基于知识库内容给出专业分析。""",

    "detail": """你是PM方案分析师，当前处于"方案细化"阶段。
请帮助用户细化选定方案的功能设计。

回答要点：
1. 列出功能模块清单
2. 编写用户故事
3. 明确技术实现要求
4. 定义验收标准

请基于知识库内容给出详细设计。""",

    "prd": """你是PM方案分析师，当前处于"PRD生成"阶段。
请帮助用户生成完整的产品需求文档。

回答要点：
1. 按标准PRD结构组织内容
2. 包含功能描述、用户故事、技术要求
3. 明确验收标准和里程碑
4. 语言简洁专业，便于团队理解

请基于之前阶段的讨论和知识库内容生成PRD。"""
}


class PMSolutionService:
    """PM方案服务"""

    def __init__(self, knowledge_id: str = None):
        self.knowledge_id = knowledge_id
        self.rag_service = get_rag_service(knowledge_id)

    def _retrieve_with_isolation(self, query: str, top_k: int = 5) -> List[Dict]:
        """知识库隔离检索"""
        retrieve_start = time.time()
        if not self.knowledge_id:
            log_timing("RETRIEVE", "未指定knowledge_id，返回空")
            return []

        session = get_session()
        try:
            # 严格按knowledge_id过滤
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
                # 向量库为空时的备用方案：直接从段落表检索
                sources = []
                for p in paragraphs[:top_k]:
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
                log_timing("RETRIEVE", f"从段落表返回 {len(sources)} 个来源", retrieve_start)
                session.close()
                return sources

            log_timing("RETRIEVE", "开始向量检索query...")
            query_start = time.time()
            results = collection.query(
                query_texts=[query],
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
        """SSE流式对话"""
        total_start = time.time()
        log_timing("CHAT", f"开始对话 session_id={session_id}, stage={stage_type}, input_len={len(user_input)}")

        # 1. 检索相关内容（知识库隔离）
        yield {"type": "status", "content": "正在搜索知识库..."}
        retrieve_start = time.time()
        sources = self._retrieve_with_isolation(user_input)
        log_timing("RETRIEVE", f"检索完成，返回{len(sources)}个来源", retrieve_start)

        # 构建上下文
        context = "\n\n".join([s["content"] for s in sources]) if sources else ""
        log_timing("CONTEXT", f"构建上下文完成，context_len={len(context)}")

        # 2. 获取对话历史
        history_start = time.time()
        history = self._get_chat_history(session_id, stage_type)
        log_timing("HISTORY", f"获取历史完成，history_count={len(history)}", history_start)

        # 3. 流式生成
        yield {"type": "status", "content": "正在生成回答..."}
        llm_start = time.time()
        log_timing("LLM", "开始调用LLM流式生成...")

        token_count = 0
        first_token_time = None

        for token in self._generate_llm_stream(stage_type, context, history, user_input):
            if first_token_time is None:
                first_token_time = time.time()
                log_timing("LLM", f"收到第一个token! LLM响应延迟={(first_token_time - llm_start)*1000:.0f}ms", llm_start)
            token_count += 1
            yield {"type": "token", "content": token}

        log_timing("LLM", f"流式生成完成，共{token_count}个token，总耗时={(time.time()-llm_start)*1000:.0f}ms", llm_start)

        # 4. 返回来源
        yield {"type": "done", "sources": sources}
        log_timing("CHAT", f"对话流程完成，总耗时={(time.time()-total_start)*1000:.0f}ms", total_start)

    def _get_chat_history(self, session_id: str, stage_type: str) -> List[Dict]:
        """获取对话历史"""
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

    def _generate_llm_stream(self, stage_type: str, context: str, history: List[Dict], user_input: str):
        """流式调用LLM"""
        llm_call_start = time.time()
        if not settings.deepseek_api_key:
            yield "[请配置DeepSeek API密钥]"
            return

        system_prompt = STAGE_PROMPTS.get(stage_type, STAGE_PROMPTS["problem"])

        messages = [{"role": "system", "content": system_prompt}]
        log_timing("LLM", f"system_prompt长度={len(system_prompt)}")

        # 添加历史对话
        for msg in history[-6:]:
            messages.append({"role": msg["role"], "content": msg["content"][:500]})
        log_timing("LLM", f"添加历史对话{len(history[-6:])}条")

        # 添加当前问题
        if context:
            current_msg = f"知识库参考：\n{context}\n\n用户问题：{user_input}"
        else:
            current_msg = user_input

        messages.append({"role": "user", "content": current_msg})
        log_timing("LLM", f"当前消息长度={len(current_msg)}, 总messages={len(messages)}")

        log_timing("LLM", f"开始发送HTTP请求到 {settings.deepseek_base_url}")

        try:
            http_start = time.time()
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
                log_timing("LLM", f"HTTP连接建立，状态码={response.status_code}", http_start)

                line_count = 0
                for line in response.iter_lines():
                    line_count += 1
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            log_timing("LLM", f"收到[DONE]信号，共处理{line_count}行")
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except Exception as e:
                            log_timing("LLM", f"解析chunk失败: {e}, data={data[:50]}")
                            continue

        except Exception as e:
            log_timing("LLM", f"生成中断: {str(e)}")
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
                # 尝试解析JSON
                try:
                    # 提取JSON部分（可能被markdown包裹）
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