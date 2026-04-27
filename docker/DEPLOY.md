# 仓库违规检测系统 - Docker 部署指南

## 概述

本系统包含两个服务：
- **后端服务** (`warehouse-backend`): FastAPI 应用，端口 8000
- **前端服务** (`warehouse-frontend`): Vue3 + Nginx，端口 80

Redis 和 RabbitMQ 通过 **IP:端口** 远程调用，不通过 Docker Compose 管理。

---

## 目录结构

```
save-vision-violation/
├── docker/
│   ├── Dockerfile.backend    # 后端镜像构建文件
│   ├── Dockerfile.frontend   # 前端镜像构建文件
│   └── nginx.conf            # Nginx 代理配置
├── docker-compose.yml        # 服务编排
├── backend/                  # 后端源码
├── frontend/                 # 前端源码
├── config/                   # 运行时配置（挂载卷）
├── data/                     # 数据目录（挂载卷）
└── logs/                     # 日志目录（挂载卷）
```

---

## 环境变量配置

创建 `.env` 文件（或直接在 docker-compose.yml 中配置）：

```bash
# 模型推理服务（必填）
MODEL_API_URL=http://10.190.28.23:31674/predict
MODEL_API_TIMEOUT=30
MODEL_API_IMGSZ=640
MODEL_API_CONFIDENCE=0.2

# Redis 远程连接（可选，通过IP端口调用）
REDIS_HOST=10.x.x.x
REDIS_PORT=6379

# RabbitMQ 远程连接（可选，通过IP端口调用）
RABBITMQ_HOST=10.x.x.x
RABBITMQ_PORT=5672
RABBITMQ_USER=admin
RABBITMQ_PASS=admin
```

---

## 构建与启动

### 1. 准备目录

```bash
mkdir -p config data logs
```

### 2. 复制配置文件

将 `backend/config.yml` 复制到 `config/config.yml`，并根据环境修改：

```bash
cp backend/config.yml config/config.yml
```

关键配置项：
- `model_api.url` → 模型推理服务地址
- `redis.host` → Redis 远程 IP
- `rabbitmq.host` → RabbitMQ 远程 IP

### 3. 构建并启动

```bash
# 构建镜像并启动
docker-compose up -d --build

# 仅启动（已构建过镜像）
docker-compose up -d
```

### 4. 查看状态

```bash
docker-compose ps
docker-compose logs -f backend
docker-compose logs -f frontend
```

---

## 常用命令

```bash
# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 重新构建并启动
docker-compose up -d --build

# 查看后端日志
docker logs -f warehouse-backend

# 查看前端日志
docker logs -f warehouse-frontend
```

---

## 访问地址

| 服务 | 地址 |
|------|------|
| 前端界面 | http://<服务器IP> |
| 后端 API | http://<服务器IP>:8000 |
| 健康检查 | http://<服务器IP>:8000/health |

---

## 注意事项

1. **模型推理服务**：必须确保 `MODEL_API_URL` 指向的服务可访问，否则检测功能无法工作
2. **远程中间件**：Redis 和 RabbitMQ 通过 IP:端口 远程调用，不占用本地容器资源
3. **配置文件**：`config/config.yml` 通过卷挂载，修改后重启容器生效
4. **数据持久化**：`data/` 和 `logs/` 目录通过卷挂载到容器内

---

## 镜像说明

### 后端镜像
- 基础镜像：`ubuntu:22.04`
- Python 版本：3.10
- 构建方式：多阶段构建（builder + runtime）
- 依赖安装：使用内网 PyPI 源
- 启动命令：`uvicorn app.main:app --host 0.0.0.0 --port 8000`

### 前端镜像
- 构建镜像：`node:20-alpine`
- 运行镜像：`nginx:alpine`
- 构建方式：多阶段构建（构建 Vue → Nginx 服务）
- 依赖安装：使用内网 npm 仓库
- API 代理：Nginx 将 `/api/` 转发到后端服务
