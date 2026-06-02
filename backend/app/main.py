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
from app.api import chat, documents, knowledge, agent, pm_solution

settings = get_settings()

# 前端静态文件路径
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend", "vue-app", "dist")


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

    yield

    print("应用关闭")


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