"""
知识库系统 FastAPI 入口
"""
import os

# 设置 HuggingFace 镜像（必须在其他导入之前）
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import uuid
import time

from app.config import get_settings
from app.core.logging import get_logger, set_trace_id
from app.core.tracing import (
    set_trace_context, start_trace_writer, stop_trace_writer,
    TraceContext, Span,
)
from app.api import chat, documents, knowledge, logs, orchestrator, pm_solution, query, vector_admin

settings = get_settings()
_log = get_logger("main")

# 前端静态文件路径（通过配置自动检测，支持Docker和本地环境）
FRONTEND_DIST = settings.resolved_frontend_dist_dir


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    _log.info("启动 {} v{}", settings.app_name, settings.app_version)

    # 初始化数据目录
    os.makedirs(settings.resolved_chroma_persist_dir, exist_ok=True)
    os.makedirs(os.path.join(settings.data_dir, "uploads"), exist_ok=True)
    os.makedirs(os.path.join(settings.data_dir, "sessions"), exist_ok=True)
    os.makedirs(os.path.join(settings.data_dir, "images"), exist_ok=True)
    os.makedirs(os.path.join(settings.data_dir, "traces"), exist_ok=True)
    os.makedirs(os.path.join(settings.data_dir, "logs"), exist_ok=True)

    # 启动本地 trace writer
    await start_trace_writer()

    # 初始化数据库
    from app.models.document import init_db
    init_db()

    _log.info("行业配置: {}", settings.industry_type)
    _log.info("LLM Provider: {}", settings.llm_provider)

    # 初始化数据查询模块
    from app.models.query_history import init_query_history
    from app.models.query_feedback import init_query_feedback
    init_query_history()
    init_query_feedback()
    _log.info("查询历史数据库初始化完成")

    # 初始化 Chat 和 PM 反馈表
    from app.models.chat_feedback import init_chat_feedback
    from app.models.pm_feedback import init_pm_feedback
    init_chat_feedback()
    init_pm_feedback()
    _log.info("Chat/PM 反馈数据库初始化完成")

    # 启动时检查向量索引健康状态
    await check_and_repair_vector_indices()

    yield

    await stop_trace_writer()
    _log.info("应用关闭")


async def check_and_repair_vector_indices():
    """启动时检查向量索引健康状态，自动修复critical问题"""
    import sqlite3
    from sentence_transformers import SentenceTransformer
    from app.core.vector_store import get_vector_store_manager

    _log.info("检查向量索引健康状态...")

    try:
        # 连接数据库
        db_path = os.path.join(settings.data_dir, "kb.db")
        if not os.path.exists(db_path):
            _log.info("数据库文件不存在，跳过向量检查")
            return

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 获取所有知识库和段落
        cursor.execute("SELECT id, name FROM knowledge")
        knowledges = cursor.fetchall()

        cursor.execute("SELECT knowledge_id, COUNT(*) FROM paragraph GROUP BY knowledge_id")
        para_counts = {row[0]: row[1] for row in cursor.fetchall()}

        conn.close()

        # 使用VectorStoreManager获取向量库客户端（避免实例冲突）
        vector_manager = get_vector_store_manager()
        chroma_client = vector_manager.get_client()
        collections = chroma_client.list_collections()

        # 检查每个知识库
        need_rebuild = []
        for kb_id, kb_name in knowledges:
            para_count = para_counts.get(kb_id, 0)

            # 找到对应的collection
            coll_name = f"kb_documents_{kb_id}"
            matching_colls = [c for c in collections if c.name == coll_name]
            vector_count = matching_colls[0].count() if matching_colls else 0

            status = "healthy"
            if para_count > 0 and vector_count == 0:
                status = "critical"
                need_rebuild.append((kb_id, kb_name, para_count))
            elif para_count > 0 and vector_count < para_count * 0.8:
                status = "warning"

            _log.info("{}: 段落={}, 向量={}, 状态={}", kb_name, para_count, vector_count, status)

        # 自动修复critical问题
        if need_rebuild:
            _log.warning("发现 {} 个需要重建索引的知识库", len(need_rebuild))

            # 加载embedding模型
            _log.info("加载embedding模型...")
            model = SentenceTransformer('BAAI/bge-small-zh-v1.5')

            for kb_id, kb_name, para_count in need_rebuild:
                _log.info("正在重建: {} ({} 段落)", kb_name, para_count)

                try:
                    # 获取段落数据
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT p.id, p.document_id, p.content, d.name
                        FROM paragraph p
                        LEFT JOIN document d ON p.document_id = d.id
                        WHERE p.knowledge_id = ?
                    """, (kb_id,))
                    paragraphs = cursor.fetchall()
                    conn.close()

                    if not paragraphs:
                        continue

                    # 删除旧collection
                    coll_name = f"kb_documents_{kb_id}"
                    try:
                        chroma_client.delete_collection(coll_name)
                    except:
                        pass

                    # 创建新collection
                    collection = chroma_client.create_collection(
                        name=coll_name,
                        metadata={"knowledge_name": kb_name, "hnsw:space": "cosine"}
                    )

                    # 生成embeddings
                    texts = [p[2] for p in paragraphs]
                    embeddings = model.encode(texts, show_progress_bar=False)

                    # 添加到向量库
                    ids = [p[0] for p in paragraphs]
                    metadatas = [{
                        "document_id": p[1],
                        "knowledge_id": kb_id,
                        "document_title": p[3] or "Unknown"
                    } for p in paragraphs]

                    collection.add(
                        ids=ids,
                        embeddings=embeddings.tolist(),
                        metadatas=metadatas,
                        documents=texts
                    )

                    _log.info("OK {}: 已重建 {} 个向量", kb_name, len(paragraphs))

                except Exception as e:
                    _log.error("FAIL {}: 重建失败 - {}", kb_name, e)

            _log.info("向量索引修复完成")

        else:
            _log.info("OK 所有向量索引健康")

    except Exception as e:
        _log.error("向量索引检查失败: {}", e)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    """为每个 HTTP 请求创建顶层 trace span"""
    trace_id = uuid.uuid4().hex[:16]
    set_trace_context(trace_id)
    set_trace_id(trace_id)

    with TraceContext("http_request",
                      method=request.method,
                      path=request.url.path,
                      query_params=dict(request.query_params)) as span:
        span.set_metadata(client_ip=request.client.host if request.client else "")
        start = time.time()
        response = await call_next(request)
        elapsed = (time.time() - start) * 1000
        span.set_output(status_code=response.status_code)

    response.headers["X-Trace-Id"] = trace_id
    return response

# 注册路由 - 路径匹配前端API调用
app.include_router(chat.router, prefix="/api/v1/chat", tags=["对话"])
app.include_router(documents.router, prefix="/api/v1/docs", tags=["文档"])
app.include_router(knowledge.router, prefix="/api/v1", tags=["知识库"])
app.include_router(pm_solution.router, prefix="/api/v1/pm-solution", tags=["PM方案"])
app.include_router(logs.router, prefix="/api/v1/logs", tags=["日志查看"])
app.include_router(query.router, prefix="/api/v1/query", tags=["数据查询"])
app.include_router(vector_admin.router, prefix="/api/v1/vector-admin", tags=["向量库管理"])
app.include_router(orchestrator.router, prefix="/api/v1/orchestrator", tags=["智能助手"])

# 图片静态文件服务（必须在catch-all路由之前）
IMAGES_DIR = os.path.join(settings.data_dir, "images")
if os.path.exists(IMAGES_DIR):
    app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")

# 挂载前端静态资源 (assets目录)
if os.path.exists(os.path.join(FRONTEND_DIST, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")


@app.get("/health")
async def health():
    return {"status": "healthy", "version": settings.app_version}


@app.get("/api")
async def api_info():
    """API信息"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "industry": settings.industry_type,
        "llm_provider": settings.llm_provider
    }


@app.get("/config")
async def get_config():
    """获取配置信息"""
    from app.core.settings import get_all_industries
    from app.core.llm_manager import get_llm_providers

    return {
        "industries": get_all_industries(),
        "llm_providers": get_llm_providers(),
        "current_industry": settings.industry_type,
        "current_llm": settings.llm_provider
    }


# 前端页面路由 - 所有非API路径返回index.html
@app.get("/{path:path}")
async def serve_frontend(path: str):
    """服务前端页面"""
    # 优先检查图片目录
    images_path = os.path.join(settings.data_dir, "images", path)
    if "images" in path or os.path.exists(images_path):
        # 如果是images路径请求
        parts = path.split("/")
        if parts[0] == "images" and len(parts) > 1:
            img_file = os.path.join(settings.data_dir, "images", parts[1])
            if os.path.exists(img_file) and os.path.isfile(img_file):
                return FileResponse(img_file)

    # 如果请求的是静态文件且存在，直接返回
    file_path = os.path.join(FRONTEND_DIST, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    # 否则返回index.html (Vue Router处理)
    index_path = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"error": "前端文件未找到，请先构建前端"}