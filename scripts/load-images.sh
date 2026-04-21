#!/bin/bash
# 离线环境镜像加载脚本
# 在离线服务器上执行此脚本，加载Docker镜像

set -e

echo "========================================"
echo "仓库违规检测系统 - 离线镜像加载"
echo "========================================"

# 镜像文件目录（默认与脚本同级目录）
IMAGE_DIR="${1:-.}"

echo ""
echo "步骤1/4: 检查镜像文件..."
echo "----------------------------------------"

required_files=(
    "${IMAGE_DIR}/warehouse-backend.tar"
    "${IMAGE_DIR}/warehouse-frontend.tar"
    "${IMAGE_DIR}/redis.tar"
    "${IMAGE_DIR}/rabbitmq.tar"
)

for file in "${required_files[@]}"; do
    if [ ! -f "$file" ]; then
        echo "错误: 找不到镜像文件 $file"
        echo "请确保所有.tar镜像文件在当前目录中"
        exit 1
    fi
    echo "✓ 找到: $(basename "$file")"
done

echo ""
echo "步骤2/4: 加载后端镜像..."
echo "----------------------------------------"
docker load < "${IMAGE_DIR}/warehouse-backend.tar"

echo ""
echo "步骤3/4: 加载前端镜像..."
echo "----------------------------------------"
docker load < "${IMAGE_DIR}/warehouse-frontend.tar"

echo ""
echo "步骤4/4: 加载依赖服务镜像..."
echo "----------------------------------------"
docker load < "${IMAGE_DIR}/redis.tar"
docker load < "${IMAGE_DIR}/rabbitmq.tar"

echo ""
echo "========================================"
echo "镜像加载完成！"
echo "========================================"
docker images | grep -E "(warehouse|redis|rabbitmq)"

echo ""
echo "========================================"
echo "接下来请执行: bash deploy.sh"
echo "========================================"
