#!/bin/bash
# 本地开发启动脚本
clear

# 加载 .env 文件
set -a
source .env
set +a

# 构建 DATABASE_URL
export DATABASE_URL="postgresql://postgres:${DB_PASSWORD}@localhost:5432/aether"

# 启动 uvicorn（热重载模式）
echo "🚀 启动本地开发服务器..."
echo "📍 后端地址: http://localhost:8084"
echo "📊 数据库: ${DATABASE_URL}"
echo ""

uv run uvicorn src.main:app --reload --port 8084
