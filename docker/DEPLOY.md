# 仓库违规检测系统 - 部署指南

## 概述

本系统包含两个服务：
- **后端服务** (`warehouse-backend`): FastAPI 应用，端口 8000
- **前端服务** (`warehouse-frontend`): Vue3 + Nginx，端口 80

Redis 和 RabbitMQ 通过 **IP:端口** 远程调用，不通过 Docker Compose 管理。

---

## 部署模式

### 模式一：本地开发测试（推荐无权限环境使用）

适用于：
- 本地开发调试
- 无模型API权限
- 无RTSP流权限
- 测试前端界面和配置功能

**特点：**
- 后端正常启动，但检测功能会跳过（API不可用时返回空结果）
- 前端所有界面功能可用
- 可以配置区域、规则、摄像头
- 可以测试视频流调试功能（需本地视频文件）

**启动步骤：**

1. 安装依赖
```bash
# Python后端依赖
uv sync

# 前端依赖
cd frontend
npm install
cd ..
```

2. 启动后端
```bash
uv run python backend/run.py
```

3. 启动前端（新终端）
```bash
cd frontend
npm run dev
```

4. 访问 http://localhost:5173

---

### 模式二：生产环境部署（需要完整权限）

适用于：
- 生产服务器部署
- 有模型API访问权限
- 有RTSP流访问权限
- 有RabbitMQ和Redis服务

**前置条件：**
1. 模型推理服务可访问
2. 海康威视平台可访问
3. RabbitMQ服务可访问
4. Redis服务可访问

**配置步骤：**

1. 编辑 `backend/config.yml`：
```yaml
# 模型API配置
detection_params:
  model_api:
    url: http://your-model-api:31674/predict
    timeout: 30
    imgsz: 640
    confidence: 0.2
  use_api: true

# RabbitMQ配置
rabbitmq:
  host: 10.190.196.147
  port: 5672
  username: admin
  password: admin
  virtual_host: biz-prod
  exchange: ai_video
  exchange_type: fanout
  queue: ai_video

# Redis配置
redis:
  host: localhost
  port: 6379
  db: 0
  password: null
```

2. 构建Docker镜像
```bash
# 后端
docker build -f docker/Dockerfile.backend -t warehouse-backend:latest .

# 前端
docker build -f docker/Dockerfile.frontend -t warehouse-frontend:latest .
```

3. 启动服务
```bash
# 使用docker-compose.prod.yml（包含Redis + RabbitMQ + Backend + Frontend）
docker-compose -f docker-compose.prod.yml up -d
```

---

## 目录结构

```
save-vision-violation/
├── docker/
│   ├── Dockerfile.backend    # 后端镜像构建文件
│   ├── Dockerfile.frontend   # 前端镜像构建文件
│   └── nginx.conf            # Nginx 代理配置
├── docker-compose.yml        # 开发环境配置（仅Redis+RabbitMQ）
├── docker-compose.prod.yml   # 生产环境配置（完整服务栈）
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
| API文档 | http://<服务器IP>:8000/docs |

---

## 无权限环境测试指南

### 场景：本地无模型API和RTSP权限

**问题：**
- 无法调用模型API进行人员检测
- 无法获取海康RTSP视频流

**解决方案：**

1. **后端正常启动**
   - 修改 `config.yml` 中的API地址为无效地址（或保持默认）
   - 后端会正常启动，但检测时API调用会失败并返回空结果
   - 不影响其他功能（配置管理、区域管理、规则管理等）

2. **使用本地视频测试**
   - 在前端配置摄像头时，选择"本地视频"模式
   - 填写本地视频文件路径
   - 可以测试视频流播放和调试功能

3. **测试功能清单**
   - [x] 前端界面正常显示
   - [x] 配置管理（增删改查）
   - [x] 区域绘制（Canvas）
   - [x] 规则配置
   - [x] 本地视频播放
   - [x] 单帧图片调试
   - [x] 服务连接测试
   - [ ] 实时人员检测（需要模型API）
   - [ ] RTSP流获取（需要海康权限）
   - [ ] 违规告警推送（需要RabbitMQ）

### 测试步骤

1. 启动后端和前端（见"模式一"）
2. 访问 http://localhost:5173
3. 进入"设置"页面
4. 配置摄像头（使用本地视频路径）
5. 绘制监控区域
6. 配置违规规则
7. 进入"调试测试"页面
8. 选择视频并播放，查看界面是否正常

---

## 注意事项

1. **模型推理服务**：必须确保 `MODEL_API_URL` 指向的服务可访问，否则检测功能无法工作
2. **远程中间件**：Redis 和 RabbitMQ 通过 IP:端口 远程调用，不占用本地容器资源
3. **配置文件**：`config/config.yml` 通过卷挂载，修改后重启容器生效
4. **数据持久化**：`data/` 和 `logs/` 目录通过卷挂载到容器内
5. **本地测试**：无权限时后端仍可启动，只是检测功能不可用

---

## 镜像说明

### 后端镜像
- 基础镜像：`ubuntu:24.04`
- Python 版本：3.12
- 构建方式：多阶段构建（builder + runtime）
- 依赖安装：使用内网 PyPI 源
- 启动命令：`uvicorn app.main:app --host 0.0.0.0 --port 8000`

### 前端镜像
- 构建镜像：`node:20-alpine`
- 运行镜像：`nginx:alpine`
- 构建方式：多阶段构建（构建 Vue → Nginx 服务）
- 依赖安装：使用内网 npm 仓库
- API 代理：Nginx 将 `/api/` 转发到后端服务

---

## 故障排查

### 后端无法启动

**检查日志：**
```bash
docker logs warehouse-backend
```

**常见问题：**
1. 配置文件格式错误 → 检查 `config.yml` YAML语法
2. 端口被占用 → 检查8000端口是否被其他程序占用
3. 依赖缺失 → 重新构建镜像 `docker-compose up -d --build`

### 前端无法访问

**检查：**
```bash
docker logs warehouse-frontend
```

**常见问题：**
1. 后端未启动 → 先启动后端服务
2. Nginx配置错误 → 检查 `docker/nginx.conf`

### 模型API连接失败

**现象：** 检测功能不可用，日志显示连接错误

**解决：**
1. 检查网络是否可以访问模型服务地址
2. 检查 `MODEL_API_URL` 配置是否正确
3. 联系管理员获取API访问权限

### RTSP流获取失败

**现象：** 摄像头无法获取视频流

**解决：**
1. 检查海康平台配置（appKey, appSecret, host）
2. 检查摄像头indexCode是否正确
3. 检查网络是否可以访问海康平台
4. 使用本地视频文件替代进行测试

---

## 更新部署

### 更新代码后重新部署

```bash
# 1. 拉取最新代码
git pull

# 2. 重新构建镜像
docker-compose up -d --build

# 3. 查看状态
docker-compose ps
```

### 仅更新配置

```bash
# 修改 config/config.yml 后，重启容器
docker-compose restart backend
```

---

## 安全建议

1. **修改默认密码**：RabbitMQ默认密码为admin，生产环境请修改
2. **配置防火墙**：仅开放必要的端口（80, 8000）
3. **使用HTTPS**：生产环境建议配置SSL证书
4. **限制API访问**：配置CORS允许的来源

---

## 联系支持

如有问题，请查看：
- [README.md](../README.md) - 项目概述和快速启动
- [CHANGELOG.md](../CHANGELOG.md) - 更新日志
- API文档：启动后访问 http://localhost:8000/docs
