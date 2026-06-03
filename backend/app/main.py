"""
知识库系统 FastAPI 入口
"""
import os

# 设置 HuggingFace 镜像（必须在其他导入之前）
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

from app.config import get_settings
from app.api import chat, documents, knowledge, agent, pm_solution, query, vector_admin

settings = get_settings()

# 前端静态文件路径（通过配置自动检测，支持Docker和本地环境）
FRONTEND_DIST = settings.resolved_frontend_dist_dir


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    print(f"启动 {settings.app_name} v{settings.app_version}")

    # 初始化数据目录
    os.makedirs(settings.resolved_chroma_persist_dir, exist_ok=True)
    os.makedirs(os.path.join(settings.data_dir, "uploads"), exist_ok=True)
    os.makedirs(os.path.join(settings.data_dir, "sessions"), exist_ok=True)
    os.makedirs(os.path.join(settings.data_dir, "images"), exist_ok=True)  # 图片目录

    # 初始化数据库
    from app.models.document import init_db
    init_db()

    print(f"行业配置: {settings.industry_type}")
    print(f"LLM Provider: {settings.llm_provider}")

    # 初始化数据查询模块
    from app.models.query_history import init_query_history
    init_query_history()
    print("查询历史数据库初始化完成")

    # 启动时检查向量索引健康状态
    await check_and_repair_vector_indices()

    yield

    print("应用关闭")


async def check_and_repair_vector_indices():
    """启动时检查向量索引健康状态，自动修复critical问题"""
    import sqlite3
    from sentence_transformers import SentenceTransformer
    from app.core.vector_store import get_vector_store_manager

    print("\n[启动检查] 检查向量索引健康状态...")

    try:
        # 连接数据库
        db_path = os.path.join(settings.data_dir, "kb.db")
        if not os.path.exists(db_path):
            print("[启动检查] 数据库文件不存在，跳过向量检查")
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

            print(f"[启动检查] {kb_name}: 段落={para_count}, 向量={vector_count}, 状态={status}")

        # 自动修复critical问题
        if need_rebuild:
            print(f"\n[启动修复] 发现 {len(need_rebuild)} 个需要重建索引的知识库")

            # 加载embedding模型
            print("[启动修复] 加载embedding模型...")
            model = SentenceTransformer('BAAI/bge-small-zh-v1.5')

            for kb_id, kb_name, para_count in need_rebuild:
                print(f"[启动修复] 正在重建: {kb_name} ({para_count} 段落)")

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

                    print(f"[启动修复] OK {kb_name}: 已重建 {len(paragraphs)} 个向量")

                except Exception as e:
                    print(f"[启动修复] FAIL {kb_name}: 重建失败 - {e}")

            print("\n[启动修复] 向量索引修复完成")

        else:
            print("[启动检查] OK 所有向量索引健康")

    except Exception as e:
        print(f"[启动检查] 检查失败: {e}")


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

# 注册路由 - 路径匹配前端API调用
app.include_router(chat.router, prefix="/api/v1/chat", tags=["对话"])
app.include_router(documents.router, prefix="/api/v1/docs", tags=["文档"])
app.include_router(knowledge.router, prefix="/api/v1", tags=["知识库"])
app.include_router(agent.router, prefix="/api/v1/agent", tags=["Agent"])
app.include_router(pm_solution.router, prefix="/api/v1/pm-solution", tags=["PM方案"])
app.include_router(query.router, prefix="/api/v1/query", tags=["数据查询"])
app.include_router(vector_admin.router, prefix="/api/v1/vector-admin", tags=["向量库管理"])

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