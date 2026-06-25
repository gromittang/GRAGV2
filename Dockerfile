# Stage 1: 前端构建
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
RUN npm config set registry https://registry.npmmirror.com
COPY frontend/vue-app/package*.json ./
RUN npm install --legacy-peer-deps
COPY frontend/vue-app/ ./
RUN npm run build

# Stage 2: Python 镜像（使用稳定版 bookworm）
FROM python:3.11-slim-bookworm

# 使用阿里云镜像源（解决网络问题）
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先安装 PyTorch CPU-only（必须单独安装，避免 CUDA 包）
# 升级 pip 以避免下载问题
RUN pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple

# 先安装 PyTorch CPU-only（使用本地预下载的 wheel 文件，保持原文件名）
COPY torch-2.4.0+cpu-cp311-cp311-linux_x86_64.whl /tmp/
RUN pip install --no-cache-dir /tmp/torch-2.4.0+cpu-cp311-cp311-linux_x86_64.whl \
    && rm /tmp/torch-2.4.0+cpu-cp311-cp311-linux_x86_64.whl

# 再安装其他依赖（torch 已存在，不会拉取 CUDA 版本）
COPY backend/requirements-docker.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 后端代码
COPY backend/app ./app

# 前端构建产物（复制到后端期望的路径）
RUN mkdir -p ./frontend/vue-app
COPY --from=frontend-build /app/frontend/dist ./frontend/vue-app/dist

# 数据目录
RUN mkdir -p /app/data/chroma /app/data/uploads /app/data/sessions /app/data/images

ENV DATA_DIR=/app/data \
    APP_ENV=production \
    SERVER_PORT=8812 \
    FRONTEND_DIST_DIR=/app/frontend/vue-app/dist

EXPOSE 8812

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s \
    CMD curl -f http://localhost:8812/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8812"]