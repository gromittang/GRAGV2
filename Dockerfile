# Stage 1: 前端构建
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
RUN npm config set registry https://registry.npmmirror.com
COPY frontend/vue-app/package*.json ./
RUN npm install --legacy-peer-deps
COPY frontend/vue-app/ ./
RUN npm run build

# Stage 2: Python 镜像
FROM python:3.11-slim

# Debian 镜像源
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python 依赖（精简版）
COPY backend/requirements-docker.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 后端代码
COPY backend/app ./app

# 前端构建产物
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# 数据目录
RUN mkdir -p /app/data/chroma /app/data/uploads /app/data/sessions /app/data/images

ENV DATA_DIR=/app/data \
    APP_ENV=production \
    SERVER_PORT=8811

EXPOSE 8811

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s \
    CMD curl -f http://localhost:8811/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8811"]