#!/bin/bash
# 离线部署镜像构建脚本
# 在有网络的机器上执行此脚本，构建并导出Docker镜像
#
# 重要说明：
# - 系统已从本地模型推理改为 API 调用模式
# - 后端镜像不再包含模型文件和 PyTorch 等重型依赖
# - 需要额外准备模型推理服务（详见 DEPLOY.md）

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
echo "步骤1/5: 拉取基础镜像..."
echo "----------------------------------------"
docker pull ${REDIS_IMAGE}
docker pull ${RABBITMQ_IMAGE}

echo ""
echo "步骤2/5: 构建后端镜像..."
echo "----------------------------------------"
echo "注意：后端镜像不包含模型，体积已大幅减小"
docker build -f docker/Dockerfile.backend -t ${BACKEND_IMAGE} .

echo ""
echo "步骤3/5: 构建前端镜像..."
echo "----------------------------------------"
docker build -f docker/Dockerfile.frontend -t ${FRONTEND_IMAGE} .

echo ""
echo "步骤4/5: 导出镜像到tar文件..."
echo "----------------------------------------"

# 导出各个镜像
echo "导出后端镜像..."
docker save ${BACKEND_IMAGE} > "${EXPORT_DIR}/warehouse-backend.tar"

echo "导出前端镜像..."
docker save ${FRONTEND_IMAGE} > "${EXPORT_DIR}/warehouse-frontend.tar"

echo "导出Redis镜像..."
docker save ${REDIS_IMAGE} > "${EXPORT_DIR}/redis.tar"

echo "导出RabbitMQ镜像..."
docker save ${RABBITMQ_IMAGE} > "${EXPORT_DIR}/rabbitmq.tar"

echo ""
echo "步骤5/5: 复制部署文件..."
echo "----------------------------------------"
cp docker-compose.prod.yml "${EXPORT_DIR}/"
cp -r scripts "${EXPORT_DIR}/"

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
echo ""
echo "在离线服务器上执行: cd scripts && bash load-images.sh"
echo "========================================"
