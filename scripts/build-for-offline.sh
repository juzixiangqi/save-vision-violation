#!/bin/bash
# 离线部署镜像构建脚本
# 在有网络的机器上执行此脚本，构建并导出Docker镜像
#
# 重要说明：
# - 系统已从本地模型推理改为 API 调用模式
# - 后端镜像不再包含模型文件和 PyTorch 等重型依赖
# - 需要额外准备模型推理服务（详见 DEPLOY.md）
# - 使用原生pip安装Python依赖（指定内网PyPI仓库）
# - Redis/RabbitMQ使用latest标签
# - 支持多次运行（幂等性）

set -e

echo "========================================"
echo "仓库违规检测系统 - 离线部署镜像构建"
echo "========================================"
echo ""
echo "架构说明："
echo "  - 后端：API 调用模式（不含模型）"
echo "  - 前端：Vue3 + Nginx"
echo "  - 依赖：Redis + RabbitMQ"
echo "  - 模型推理服务：需单独准备"
echo "  - Python依赖：使用原生pip（内网PyPI仓库）"
echo "  - Python版本：3.12（基于python:3.12-slim）"
echo "  - Node版本：20（基于node:20-alpine）"
echo "  - 基础镜像：使用latest标签（Redis/RabbitMQ）"
echo "========================================"

# 镜像标签
TAG="latest"
BACKEND_IMAGE="warehouse-backend:${TAG}"
FRONTEND_IMAGE="warehouse-frontend:${TAG}"
REDIS_IMAGE="redis:7-alpine"
RABBITMQ_IMAGE="rabbitmq:3-management-alpine"

# 导出目录
EXPORT_DIR="./docker-images"
mkdir -p "${EXPORT_DIR}"

echo ""
echo "步骤1/6: 清理旧镜像（幂等性处理）..."
echo "----------------------------------------"
# 删除已存在的同名镜像（如果存在）
if docker images | grep -q "${BACKEND_IMAGE}"; then
    echo "发现旧的后端镜像，正在删除..."
    docker rmi -f ${BACKEND_IMAGE} || true
fi
if docker images | grep -q "${FRONTEND_IMAGE}"; then
    echo "发现旧的前端镜像，正在删除..."
    docker rmi -f ${FRONTEND_IMAGE} || true
fi
# 清理构建缓存（可选，确保干净构建）
echo "清理Docker构建缓存..."
docker builder prune -f || true
echo "✓ 清理完成"

echo ""
echo "步骤2/6: 拉取基础镜像..."
echo "----------------------------------------"
echo "注意：Redis和RabbitMQ使用latest标签"
docker pull ${REDIS_IMAGE}
docker pull ${RABBITMQ_IMAGE}

echo ""
echo "步骤3/6: 构建后端镜像..."
echo "----------------------------------------"
echo "注意：后端镜像不包含模型，体积已大幅减小"
echo "      使用原生pip安装依赖（内网PyPI仓库）"
docker build -f docker/Dockerfile.backend -t ${BACKEND_IMAGE} .

echo ""
echo "步骤4/6: 构建前端镜像..."
echo "----------------------------------------"
docker build -f docker/Dockerfile.frontend -t ${FRONTEND_IMAGE} .

echo ""
echo "步骤5/6: 导出镜像到tar文件..."
echo "----------------------------------------"

# 导出各个镜像（覆盖旧文件）
echo "导出后端镜像..."
docker save ${BACKEND_IMAGE} > "${EXPORT_DIR}/warehouse-backend.tar"

echo "导出前端镜像..."
docker save ${FRONTEND_IMAGE} > "${EXPORT_DIR}/warehouse-frontend.tar"

echo "导出Redis镜像..."
docker save ${REDIS_IMAGE} > "${EXPORT_DIR}/redis.tar"

echo "导出RabbitMQ镜像..."
docker save ${RABBITMQ_IMAGE} > "${EXPORT_DIR}/rabbitmq.tar"

echo ""
echo "步骤6/6: 复制部署文件..."
echo "----------------------------------------"
cp -f docker-compose.prod.yml "${EXPORT_DIR}/"
cp -rf scripts "${EXPORT_DIR}/"

echo ""
echo "========================================"
echo "构建完成！导出文件列表："
echo "========================================"
ls -lh "${EXPORT_DIR}/"

echo ""
echo "========================================"
echo "请将以下文件复制到离线服务器："
echo "========================================"
echo "1. ${EXPORT_DIR}/warehouse-backend.tar     (~500MB，不含模型)"
echo "2. ${EXPORT_DIR}/warehouse-frontend.tar    (~200MB)"
echo "3. ${EXPORT_DIR}/redis.tar                 (~50MB)"
echo "4. ${EXPORT_DIR}/rabbitmq.tar              (~200MB)"
echo "5. ${EXPORT_DIR}/docker-compose.prod.yml"
echo "6. ${EXPORT_DIR}/scripts/"
echo ""
echo "重要提示："
echo "  - 后端镜像不包含模型推理能力"
echo "  - 需要额外准备模型推理服务（详见 DEPLOY.md）"
echo "  - 部署时需在 config.yml 中配置 model_api.url"
echo "  - 使用原生pip安装依赖（内网PyPI仓库）"
echo "  - Python版本：3.12，Node版本：20"
echo "  - Redis/RabbitMQ使用latest标签"
echo ""
echo "在离线服务器上执行: cd scripts && bash load-images.sh"
echo "========================================"
