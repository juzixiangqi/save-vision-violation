# 仓库违规检测系统 - 离线部署指南

## 方案概述

本方案支持在无外网环境的Linux服务器上部署仓库违规检测系统。

**架构变更说明：**
> **v2.0 重要更新**：系统已从本地模型推理改为 **API 调用模式**。后端服务不再内置 YOLO 模型，而是通过 HTTP API 调用独立的模型推理服务。这带来了以下变化：
> - 后端镜像体积大幅减小（无需包含模型文件和 PyTorch 等重型依赖）
> - 需要额外部署或接入一个模型推理服务（提供 `/predict` 接口）
> - 模型推理服务可以部署在同一台机器上，也可以部署在内网其他机器上

**基本原理：**
1. 在有网络的机器上构建Docker镜像
2. 将镜像导出为tar文件
3. 将tar文件传输到离线服务器
4. 在离线服务器上加载镜像并运行

**架构：**
- `warehouse-backend`: Python FastAPI后端服务（端口8000）
  - 通过 API 调用模型推理服务（需单独部署）
- `warehouse-frontend`: Vue3前端 + Nginx（端口80）
- `redis`: Redis缓存服务（端口6379）
- `rabbitmq`: RabbitMQ消息队列（端口5672/15672）
- `model-api` (外部): 模型推理服务（需单独准备）

---

## 环境要求

### 构建环境（有网络）
- Docker >= 20.10
- Docker Compose >= 2.0
- Bash环境（Linux/macOS/WSL）
- 内网PyPI仓库访问权限（用于安装Python依赖）
- 磁盘空间：>= 5GB（后端镜像不再包含模型，体积已大幅减小）

### 部署环境（无网络）
- Docker >= 20.10
- Docker Compose >= 2.0
- Linux x86_64系统
- 磁盘空间：>= 3GB
- 内存：>= 4GB（建议8GB以上）
- **模型推理服务**：需要在内网中有一台可访问的模型推理服务（详见下方说明）

---

## 模型推理服务说明

### 什么是模型推理服务？

模型推理服务是一个独立的 HTTP 服务，提供图像检测接口。后端服务通过调用该服务来完成人员/箱子检测，而不是在本地加载模型进行推理。

### 推理服务接口规范

推理服务必须提供以下接口：

**POST /predict**
- Content-Type: `multipart/form-data`
- 请求参数：
  - `file`: 图像文件（JPEG格式）
  - `imgsz`: 输入尺寸（如 640）
  - `conf`: 置信度阈值（如 0.2）
- 响应格式：
  ```json
  {
    "status": "success",
    "predictions": [
      {
        "bbox": [x1, y1, x2, y2],
        "confidence": 0.95,
        "class_idx": 0,
        "class": "person_carry"
      }
    ]
  }
  ```

### 推理服务部署方式

#### 方式一：使用项目提供的推理服务镜像（推荐）

如果项目提供了独立的模型推理服务 Docker 镜像，可以一并构建和部署：

```bash
# 构建推理服务镜像（如有提供）
docker build -f docker/Dockerfile.model-api -t warehouse-model-api:latest .

# 导出镜像
docker save warehouse-model-api:latest > docker-images/warehouse-model-api.tar
```

#### 方式二：自行部署推理服务

可以使用任何支持 YOLO 模型的推理框架部署，例如：
- [Triton Inference Server](https://github.com/triton-inference-server/server)
- [TorchServe](https://github.com/pytorch/serve)
- 自定义 FastAPI/Flask 服务

**最低要求：**
- 必须支持上述 `/predict` 接口规范
- 必须能够处理 multipart/form-data 请求
- 建议部署在 GPU 服务器上以获得更好性能

#### 方式三：使用已有的内网推理服务

如果内网已有符合接口规范的推理服务，只需在配置中指定其地址即可。

---

## 第一步：构建镜像（有网络环境）

### 1.1 准备源码

确保项目源码完整，包含：
```
save-vision-violation/
├── backend/           # 后端代码
├── frontend/          # 前端代码
├── docker/            # Docker配置文件
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── nginx.conf
├── scripts/           # 构建和部署脚本
├── pyproject.toml     # Python依赖
└── docker-compose.prod.yml  # 生产环境编排文件
```

> **注意**：
> - 不再需要在源码中包含 `.pt` 模型文件，模型已移至推理服务。
> - Python版本：3.12（基于python:3.12-slim），Node版本：20（基于node:20-alpine）
> - Redis/RabbitMQ基础镜像使用 `latest` 标签（内网环境，不指定具体版本）
> - Python依赖使用原生 `pip` 安装，指定内网PyPI仓库
> - 支持多次运行构建脚本（自动清理旧镜像）

### 1.2 执行构建脚本

```bash
cd save-vision-violation

# 赋予脚本执行权限
chmod +x scripts/build-for-offline.sh

# 执行构建
bash scripts/build-for-offline.sh
```

**构建过程说明：**
1. 清理旧镜像（确保幂等性，多次运行不会出错）
2. 拉取基础镜像（python:3.12-slim, node:20-alpine, redis:7-alpine, rabbitmq:3-management-alpine）
3. 构建后端镜像（使用原生pip安装依赖，指定内网PyPI仓库，**不含模型**）
4. 构建前端镜像（编译Vue应用并配置Nginx）
5. 导出所有镜像到 `docker-images/` 目录
6. 复制部署文件

**构建时间：** 约5-15分钟（后端镜像构建更快，无需下载模型依赖）

**多次运行说明：**
脚本支持多次运行，会自动清理旧镜像并重新构建。每次运行都会生成最新的镜像文件。

### 1.3 获取输出文件

构建完成后，`docker-images/` 目录包含：
```
docker-images/
├── warehouse-backend.tar      # 后端镜像（~500MB，不含模型）
├── warehouse-frontend.tar     # 前端镜像（~200MB）
├── redis.tar                  # Redis镜像（~50MB）
├── rabbitmq.tar               # RabbitMQ镜像（~200MB）
├── docker-compose.prod.yml    # 生产环境编排文件
└── scripts/
    ├── load-images.sh         # 镜像加载脚本
    └── deploy.sh              # 部署脚本
```

> 如果使用了独立的模型推理服务镜像，还会有：
> - `warehouse-model-api.tar` # 推理服务镜像（大小取决于模型）

---

## 第二步：传输到离线服务器

### 2.1 打包部署包

```bash
cd save-vision-violation
tar czvf warehouse-deploy.tar.gz docker-images/
```

### 2.2 传输文件

使用U盘、移动硬盘或内网传输工具将 `warehouse-deploy.tar.gz` 复制到离线服务器。

**文件大小预估：** 1-2GB（后端镜像大幅减小）

---

## 第三步：离线部署（无网络环境）

### 3.1 解压部署包

```bash
# 在离线服务器上
tar xzvf warehouse-deploy.tar.gz
cd docker-images
```

### 3.2 加载Docker镜像

```bash
# 赋予脚本执行权限
chmod +x scripts/*.sh

# 加载所有镜像
bash scripts/load-images.sh
```

**验证镜像加载：**
```bash
docker images | grep warehouse
```

应显示：
```
warehouse-backend    latest    xxx    xxx    500MB
warehouse-frontend   latest    xxx    xxx    200MB
```

### 3.3 准备配置文件

**创建目录结构：**
```bash
mkdir -p config data/videos logs
```

**复制配置文件：**
```bash
# 从源码复制配置文件
cp /path/to/source/backend/config.yml config/
```

**修改配置文件：**

编辑 `config/config.yml`，配置以下关键项：

```yaml
# 1. 模型API配置（最重要）
detection_params:
  model_api:
    url: http://模型推理服务IP:端口/predict  # 改为实际推理服务地址
    timeout: 30
    imgsz: 640
    confidence: 0.2
  use_api: true  # 必须设置为 true

# 2. Redis配置
redis:
  host: redis        # Docker服务名，不要改
  port: 6379
  password: null
  db: 0

# 3. RabbitMQ配置
rabbitmq:
  host: rabbitmq     # Docker服务名，不要改
  port: 5672
  username: admin
  password: admin
  virtual_host: /
  exchange: ''
  exchange_type: fanout
  queue: ai_video
  routing_key: ''
```

**重要配置说明：**
- `model_api.url`: **必须**修改为实际可访问的模型推理服务地址
  - 如果推理服务部署在同一台服务器的Docker中，使用服务名（如 `http://model-api:8000/predict`）
  - 如果推理服务部署在其他机器上，使用IP地址（如 `http://192.168.1.100:31674/predict`）
- `use_api`: 必须设置为 `true`，启用API模式
- `redis.host` 必须改为 `redis`
- `rabbitmq.host` 必须改为 `rabbitmq`
- RabbitMQ认证信息应与 `docker-compose.prod.yml` 中一致（默认admin/admin）

**准备视频文件：**
```bash
# 将视频文件放入挂载目录
cp /path/to/your/videos/*.mp4 data/videos/
```

> **注意**：不再需要准备模型文件（`.pt`），模型已在推理服务中。

### 3.4 启动服务

```bash
bash scripts/deploy.sh
```

脚本将自动：
1. 检查Docker环境
2. 创建必要目录
3. 启动所有服务
4. 显示访问地址

---

## 第四步：验证部署

### 4.1 检查服务状态

```bash
docker ps
```

应显示以下容器运行中：
- `warehouse-backend`
- `warehouse-frontend`
- `warehouse-redis`
- `warehouse-rabbitmq`

### 4.2 验证模型API连接

```bash
# 进入后端容器
docker exec -it warehouse-backend bash

# 测试模型API连通性
curl -X POST http://<模型推理服务地址>/predict \
  -F "file=@/app/data/videos/test.jpg" \
  -F "imgsz=640" \
  -F "conf=0.2"
```

### 4.3 访问系统

服务启动后，通过浏览器访问：

- **前端界面：** http://<服务器IP>
- **后端API：** http://<服务器IP>:8000
- **健康检查：** http://<服务器IP>:8000/health
- **RabbitMQ管理：** http://<服务器IP>:15672 （admin/admin）

---

## 日常运维

### 查看日志

```bash
# 后端日志
docker logs -f warehouse-backend

# 前端日志
docker logs -f warehouse-frontend

# Redis日志
docker logs -f warehouse-redis

# RabbitMQ日志
docker logs -f warehouse-rabbitmq
```

### 停止服务

```bash
docker-compose -f docker-compose.prod.yml down
```

### 重启服务

```bash
# 重启所有服务
docker-compose -f docker-compose.prod.yml restart

# 只重启后端
docker-compose -f docker-compose.prod.yml restart backend
```

### 更新配置

修改 `config/config.yml` 后，重启后端服务：
```bash
docker-compose -f docker-compose.prod.yml restart backend
```

### 备份数据

```bash
# 备份配置和日志
tar czvf backup-$(date +%Y%m%d).tar.gz config/ logs/ data/
```

---

## 常见问题

### Q1: 后端启动后提示模型API连接失败

**排查步骤：**
1. 检查 `config/config.yml` 中的 `model_api.url` 是否正确
2. 从后端容器内测试连通性：`docker exec warehouse-backend curl <模型API地址>`
3. 检查模型推理服务是否正常运行
4. 检查防火墙是否放行了模型API端口

**解决：**
```bash
# 检查后端日志中的模型API错误
docker logs warehouse-backend | grep -i "model\|api\|error"

# 测试模型API连通性
docker exec warehouse-backend curl -v http://<模型API地址>/health
```

### Q2: 多次运行构建脚本是否有影响？

**解答：** 没有影响，脚本已做幂等性处理：
- 自动检测并删除旧镜像
- 自动清理构建缓存
- 导出的tar文件会覆盖旧文件
- 可以直接多次运行 `bash scripts/build-for-offline.sh`

### Q3: 镜像构建失败，提示空间不足

**解决：** 清理Docker缓存或扩容磁盘
```bash
docker system prune -a    # 清理未使用镜像
docker builder prune      # 清理构建缓存
```

### Q3: 服务启动后无法访问

**排查步骤：**
1. 检查服务状态：`docker ps`
2. 查看后端日志：`docker logs warehouse-backend`
3. 检查端口占用：`netstat -tlnp | grep 80`
4. 确认防火墙放行：
   ```bash
   # CentOS/RHEL
   firewall-cmd --add-port=80/tcp --permanent
   firewall-cmd --reload
   
   # Ubuntu/Debian
   ufw allow 80/tcp
   ```

### Q4: 视频检测时提示找不到文件

**解决：** 确认视频文件已放入 `data/videos/` 目录，并在前端配置正确路径。

### Q5: RabbitMQ连接失败

**排查：**
1. 检查RabbitMQ是否启动：`docker ps | grep rabbitmq`
2. 检查配置文件中的host是否为 `rabbitmq`
3. 检查认证信息是否匹配

### Q6: 模型推理延迟高

**排查：**
1. 检查模型推理服务的资源使用情况（CPU/GPU/内存）
2. 调整后端配置中的 `model_api.timeout`（默认30秒）
3. 考虑将推理服务部署在GPU服务器上
4. 检查网络延迟：`ping <模型推理服务IP>`

### Q7: 如何切换回本地模型模式（不推荐）

虽然系统已改为API模式，但仍保留了本地模型的兼容代码。如需切换：

1. 准备模型文件（`.pt`）放入 `models/` 目录
2. 修改 `config/config.yml`：
   ```yaml
   detection_params:
     use_api: false
     person_carry:
       model: models/person_carry.pt
   ```
3. 确保后端镜像包含 ultralytics 等模型依赖（当前镜像已移除这些依赖，需要重新构建）

> **警告**：本地模型模式需要重新构建包含 PyTorch 的后端镜像，会大幅增加镜像体积。

---

## 目录结构说明

部署后的目录结构：
```
docker-images/
├── docker-compose.prod.yml    # 编排文件
├── scripts/
│   ├── load-images.sh         # 镜像加载
│   └── deploy.sh              # 部署脚本
├── config/
│   └── config.yml             # 系统配置文件（需手动准备）
├── data/
│   └── videos/                # 视频文件目录
└── logs/                      # 日志目录
```

> **注意**：不再包含 `models/` 目录，模型已移至推理服务。

---

## 性能优化建议

1. **模型推理服务优化：**
   - 建议部署在 GPU 服务器上，推理速度提升 5-10 倍
   - 使用 TensorRT 或 ONNX Runtime 加速
   - 开启推理服务的 batch 推理支持

2. **网络优化：**
   - 后端与模型推理服务建议部署在同一局域网内
   - 确保网络带宽充足（每帧图像约 100-500KB）

3. **后端优化：**
   - 建议分配至少4核CPU
   - 建议8GB以上内存
   - 视频文件建议放在高速磁盘（SSD）上

---

## 安全建议

1. **修改默认密码：** 部署后请修改RabbitMQ默认密码
2. **限制端口访问：** 生产环境只开放80端口，关闭8000/15672等管理端口的外网访问
3. **模型API安全：** 如果模型推理服务暴露在内网，建议添加访问控制或API密钥
4. **配置HTTPS：** 使用Nginx配置SSL证书
5. **定期备份：** 定期备份config.yml和日志数据

---

## 技术支持

如有问题，请检查：
1. Docker和Docker Compose版本是否符合要求
2. 服务器资源是否充足（CPU/内存/磁盘）
3. 模型推理服务是否正常运行且接口可访问
4. 日志输出中的错误信息
5. 配置文件中的服务地址是否正确，特别是 `model_api.url`
