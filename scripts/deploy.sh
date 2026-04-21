#!/bin/bash
# 离线环境部署脚本
# 在离线服务器上执行此脚本，启动仓库违规检测系统

set -e

echo "========================================"
echo "仓库违规检测系统 - 离线部署"
echo "========================================"

# 检查docker和docker-compose是否安装
if ! command -v docker &> /dev/null; then
    echo "错误: Docker未安装"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "错误: Docker Compose未安装"
    exit 1
fi

# 创建必要的目录
echo ""
echo "步骤1/3: 创建数据目录..."
echo "----------------------------------------"
mkdir -p config data/videos models logs
echo "✓ 创建目录结构"

# 检查是否存在配置文件
if [ ! -f "config/config.yml" ]; then
    echo ""
    echo "警告: 未找到 config/config.yml"
    echo "请从源码复制 backend/config.yml 到 config/config.yml 并根据服务器环境修改"
    echo "重要: 请将配置中的 host 地址修改为服务名:"
    echo "  redis.host → redis"
    echo "  rabbitmq.host → rabbitmq"
    echo ""
    read -p "是否继续? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 检查视频文件
if [ ! "$(ls -A data/videos 2>/dev/null)" ]; then
    echo ""
    echo "警告: data/videos 目录为空"
    echo "请将视频文件放入 data/videos/ 目录"
fi

# 检查模型文件
if [ ! "$(ls -A models 2>/dev/null)" ]; then
    echo ""
    echo "提示: models 目录为空，将使用镜像内置的默认模型"
    echo "如需自定义模型，请将 .pt 文件放入 models/ 目录"
fi

echo ""
echo "步骤2/3: 启动服务..."
echo "----------------------------------------"

# 使用docker-compose启动
if command -v docker-compose &> /dev/null; then
    docker-compose -f docker-compose.prod.yml up -d
else
    docker compose -f docker-compose.prod.yml up -d
fi

echo ""
echo "步骤3/3: 检查服务状态..."
echo "----------------------------------------"
sleep 5

echo ""
echo "服务状态:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep warehouse || true

echo ""
echo "========================================"
echo "部署完成！"
echo "========================================"
echo ""
echo "访问地址:"
echo "  前端界面: http://<服务器IP>"
echo "  后端API:  http://<服务器IP>:8000"
echo "  RabbitMQ管理: http://<服务器IP>:15672 (admin/admin)"
echo ""
echo "常用命令:"
echo "  查看日志: docker logs -f warehouse-backend"
echo "  停止服务: docker-compose -f docker-compose.prod.yml down"
echo "  重启服务: docker-compose -f docker-compose.prod.yml restart"
echo "========================================"
