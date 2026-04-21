# 仓库违规检测系统 - 离线部署指南

## 方案概述

本方案支持在无外网环境的Linux服务器上部署仓库违规检测系统。

**基本原理：**
1. 在有网络的机器上构建Docker镜像
2. 将镜像导出为tar文件
3. 将tar文件传输到离线服务器
4. 在离线服务器上加载镜像并运行

**架构：**
- `warehouse-backend`: Python FastAPI后端服务（端口8000）
- `warehouse-frontend`: Vue3前端 + Nginx（端口80）
- `redis`: Redis缓存服务（端口6379）
- `rabbitmq`: RabbitMQ消息队列（端口5672/15672）

---

## 环境要求

### 构建环境（有网络）
- Docker >= 20.10
- Docker Compose >= 2.0
- Bash环境（Linux/macOS/WSL）
- 磁盘空间：>= 10GB（镜像体积较大，含YOLO模型和依赖）

### 部署环境（无网络）
- Docker >= 20.10
- Docker Compose >= 2.0
- Linux x86_64系统
- 磁盘空间：>= 5GB
- 内存：>= 4GB（建议8GB以上，YOLO检测需要较多内存）

---

## 第一步：构建镜像（有网络环境）

### 1.1 准备源码

确保项目源码完整，包含：
```
save-vision-violation/
├── backend/           # 后端代码
├── frontend/          # 前端代码
├── docker/            # Docker配置文件
├── scripts/           # 构建和部署脚本
├── pyproject.toml     # Python依赖
└── *.pt               # YOLO模型文件（如有）
```

### 1.2 执行构建脚本

```bash
cd save-vision-violation

# 赋予脚本执行权限
chmod +x scripts/build-for-offline.sh

# 执行构建
bash scripts/build-for-offline.sh
```

**构建过程说明：**
1. 拉取基础镜像（python:3.12-slim, node:20-alpine, redis, rabbitmq）
2. 构建后端镜像（安装Python依赖和模型）
3. 构建前端镜像（编译Vue应用并配置Nginx）
4. 导出所有镜像到 `docker-images/` 目录
5. 复制部署文件

**构建时间：** 约10-30分钟（取决于网络速度和机器性能）

### 1.3 获取输出文件

构建完成后，`docker-images/` 目录包含：
```
docker-images/
├── warehouse-backend.tar      # 后端镜像（~2-3GB）
├── warehouse-frontend.tar     # 前端镜像（~200MB）
├── redis.tar                  # Redis镜像（~50MB）
├── rabbitmq.tar               # RabbitMQ镜像（~200MB）
├── docker-compose.prod.yml    # 生产环境编排文件
└── scripts/
    ├── load-images.sh         # 镜像加载脚本
    └── deploy.sh              # 部署脚本
```

---

## 第二步：传输到离线服务器

### 2.1 打包部署包

```bash
cd save-vision-violation
tar czvf warehouse-deploy.tar.gz docker-images/
```

### 2.2 传输文件

使用U盘、移动硬盘或内网传输工具将 `warehouse-deploy.tar.gz` 复制到离线服务器。

**文件大小预估：** 3-5GB

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
warehouse-backend    latest    xxx    xxx    xGB
warehouse-frontend   latest    xxx    xxx    xxxMB
```

### 3.3 准备配置文件和数据

**创建目录结构：**
```bash
mkdir -p config data/videos models logs
```

**复制配置文件：**
```bash
# 从源码复制配置文件
cp /path/to/source/backend/config.yml config/
```

**修改配置文件：**

编辑 `config/config.yml`，将服务地址改为Docker服务名：

```yaml
redis:
  host: redis        # 改为服务名
  port: 6379
  password: null
  db: 0

rabbitmq:
  host: rabbitmq     # 改为服务名
  port: 5672
  username: admin
  password: admin
  virtual_host: /
  exchange: ''
  exchange_type: fanout
  queue: ai_video
  routing_key: ''
```

**重要：** 
- `redis.host` 必须改为 `redis`
- `rabbitmq.host` 必须改为 `rabbitmq`
- RabbitMQ认证信息应与 `docker-compose.prod.yml` 中一致（默认admin/admin）

**准备视频文件：**
```bash
# 将视频文件放入挂载目录
cp /path/to/your/videos/*.mp4 data/videos/
```

**准备自定义模型（可选）：**
```bash
# 如果有自定义训练模型，放入models目录
cp /path/to/custom/model.pt models/
# 然后在config.yml中修改对应model路径
```

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

## 第四步：访问系统

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
docker-compose -f docker-compose.prod.yml restart
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

### Q1: 镜像构建失败，提示空间不足

**解决：** 清理Docker缓存或扩容磁盘
```bash
docker system prune -a    # 清理未使用镜像
docker builder prune      # 清理构建缓存
```

### Q2: 服务启动后无法访问

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

### Q3: 视频检测时提示找不到文件

**解决：** 确认视频文件已放入 `data/videos/` 目录，并在前端配置正确路径。

### Q4: RabbitMQ连接失败

**排查：**
1. 检查RabbitMQ是否启动：`docker ps | grep rabbitmq`
2. 检查配置文件中的host是否为 `rabbitmq`
3. 检查认证信息是否匹配

### Q5: 模型加载失败

**排查：**
1. 检查模型文件是否在镜像中或挂载目录中
2. 检查config.yml中的model路径是否正确
3. 查看后端日志确认模型加载错误信息

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
├── models/                    # 自定义模型目录（可选）
└── logs/                      # 日志目录
```

---

## 性能优化建议

1. **CPU优化：** YOLO检测较耗CPU，建议分配至少4核
2. **内存优化：** 建议8GB以上内存，可通过docker-compose限制内存使用
3. **GPU支持：** 如需GPU加速，需安装NVIDIA Docker Runtime并修改Dockerfile使用CUDA基础镜像
4. **存储优化：** 视频文件建议放在高速磁盘（SSD）上

---

## 安全建议

1. **修改默认密码：** 部署后请修改RabbitMQ默认密码
2. **限制端口访问：** 生产环境只开放80端口，关闭8000/15672等管理端口的外网访问
3. **配置HTTPS：** 使用Nginx配置SSL证书
4. **定期备份：** 定期备份config.yml和日志数据

---

## 技术支持

如有问题，请检查：
1. Docker和Docker Compose版本是否符合要求
2. 服务器资源是否充足（CPU/内存/磁盘）
3. 日志输出中的错误信息
4. 配置文件中的服务地址是否正确
