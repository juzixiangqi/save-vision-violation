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
mkdir -p config data/videos logs
echo "✓ 创建目录结构"

# 检查是否存在配置文件
if [ ! -f "config/config.yml" ]; then
    echo ""
    echo "警告: 未找到 config/config.yml"
    echo "请从源码复制 backend/config.yml 到 config/config.yml 并根据服务器环境修改"
    echo ""
    echo "重要配置项:"
    echo "  1. model_api.url → 模型推理服务地址（必须配置）"
    echo "  2. redis.host → redis（Docker服务名）"
    echo "  3. rabbitmq.host → rabbitmq（Docker服务名）"
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

echo ""
echo "提示: 系统使用 API 调用模式，不再需要在本地准备模型文件"
echo "      请确保 config/config.yml 中的 model_api.url 指向可用的推理服务"

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
echo "重要提醒:"
echo "  1. 请确认 config/config.yml 中的 model_api.url 配置正确"
echo "  2. 模型推理服务必须可访问，否则检测功能无法工作"
echo "  3. 可通过 docker logs warehouse-backend 查看模型API连接状态"
echo ""
echo "常用命令:"
echo "  查看日志: docker logs -f warehouse-backend"
echo "  停止服务: docker-compose -f docker-compose.prod.yml down"
echo "  重启服务: docker-compose -f docker-compose.prod.yml restart"
echo "========================================"
