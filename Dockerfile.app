# 应用镜像：基于基础镜像，只复制代码（秒级构建）
# 构建命令: docker build -f Dockerfile.app -t aether-app:latest .
FROM aether-base:latest

WORKDIR /app

# 复制后端代码
COPY src/ ./src/
COPY alembic.ini ./
COPY alembic/ ./alembic/

# 构建前端（使用基础镜像中已安装的 node_modules）
COPY frontend/ /tmp/frontend/
RUN cd /tmp/frontend && npm run build && \
    cp -r dist/* /usr/share/nginx/html/ && \
    rm -rf /tmp/frontend
