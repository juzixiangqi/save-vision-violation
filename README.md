# 仓库违规检测系统 - 启动指南

## 项目概述

基于YOLO的仓库作业违规检测系统，支持人员搬运检测、区域管理和违规告警。

**当前架构：**
- **模型推理**：远程API调用模式（HTTP调用外部模型服务）
- **视频源**：支持本地视频文件 + 海康威视RTSP流（通过API获取）
- **消息推送**：RabbitMQ（端口5672/5673）
- **状态缓存**：Redis（端口6379）

---

## 环境要求

### 必需
- Python 3.12
- [uv](https://docs.astral.sh/uv/) - Python包管理工具
- Node.js 18+ (前端开发)

### 可选（根据使用场景）
- Docker (运行Redis和RabbitMQ本地实例)
- 模型推理服务访问权限（生产环境需要）
- 海康威视RTSP流访问权限（生产环境需要）

---

## 快速启动（本地开发测试模式）

> **说明**：此模式用于本地开发测试，无需模型API和RTSP流权限。
> 系统会跳过实际检测，但前端界面、配置管理、区域绘制等功能均可正常使用。

### 1. 克隆/进入项目

```bash
cd save-vision-violation
```

### 2. 安装后端依赖

```bash
# 使用uv安装Python依赖（自动创建虚拟环境）
uv sync

# 如果未安装Python 3.12
uv python install 3.12
uv sync
```

### 3. 安装前端依赖

```bash
cd frontend
npm install
cd ..
```

### 4. 启动后端服务

```bash
# 在项目根目录执行
uv run python backend/run.py
```

后端服务将运行在 http://localhost:8000

### 5. 启动前端开发服务器

```bash
# 新开一个终端窗口
cd frontend
npm run dev
```

前端服务将运行在 http://localhost:5173

### 6. 访问系统

打开浏览器访问 http://localhost:5173

---

## 生产环境启动（完整功能）

### 前置条件

1. **模型推理服务**：需要提供 `/predict` 接口的模型服务
2. **海康威视平台**：需要摄像头监控点indexCode以获取RTSP流
3. **RabbitMQ消息队列**：用于违规告警推送
4. **Redis缓存**：用于运行时状态存储

### 配置步骤

#### 1. 配置模型API地址

编辑 `backend/config.yml`：

```yaml
detection_params:
  model_api:
    url: http://your-model-api-server:31674/predict  # 改为实际地址
    timeout: 30
    imgsz: 640
    confidence: 0.2
  use_api: true
```

或通过环境变量覆盖：
```bash
export MODEL_API_URL=http://your-model-api-server:31674/predict
```

#### 2. 配置RabbitMQ

编辑 `backend/config.yml`：

```yaml
rabbitmq:
  host: 10.190.196.147      # RabbitMQ服务器地址
  port: 5672                # 端口（默认5672，Docker映射可能为5673）
  username: admin
  password: admin
  virtual_host: biz-prod    # 虚拟主机
  exchange: ai_video        # 交换机名称
  exchange_type: fanout
  queue: ai_video           # 队列名称
```

#### 3. 配置Redis

编辑 `backend/config.yml`：

```yaml
redis:
  host: localhost           # Redis服务器地址
  port: 6379
  db: 0
  password: null            # 无密码则设为null
```

#### 4. 配置摄像头

通过前端界面配置：
1. 访问 http://localhost:5173
2. 进入"设置" → "摄像头配置"
3. 添加摄像头：
   - **本地视频模式**：source填写本地视频路径（如 `E:\\videos\\test.mp4`）
   - **RTSP流模式**：填写海康监控点indexCode，系统通过API自动获取RTSP地址

#### 5. 配置区域和规则

通过前端界面：
1. 在摄像头画面上绘制监控区域（Zone_A, Zone_B等）
2. 配置违规规则（如 A→B 违规）

### 启动服务

```bash
# 1. 启动Redis和RabbitMQ（如使用Docker）
docker-compose up -d

# 2. 启动后端
uv run python backend/run.py

# 3. 启动前端（新终端）
cd frontend && npm run dev
```

---

## Docker部署

### 构建镜像

```bash
# 构建后端镜像
docker build -f docker/Dockerfile.backend -t warehouse-backend:latest .

# 构建前端镜像
docker build -f docker/Dockerfile.frontend -t warehouse-frontend:latest .
```

### 启动服务

```bash
# 开发环境（仅Redis + RabbitMQ）
docker-compose up -d

# 生产环境（完整服务栈）
docker-compose -f docker-compose.prod.yml up -d
```

### 数据持久化

| 宿主机路径 | 容器内路径 | 说明 |
|-----------|-----------|------|
| `./config/config.yml` | `/app/config.yml` | 配置文件 |
| `./data` | `/app/data` | 数据目录 |
| `./logs` | `/app/logs` | 日志目录 |

---

## 功能模块说明

### 1. 监控面板 (Dashboard)
- 显示系统运行状态
- Redis/RabbitMQ连接状态
- 实时跟踪人员数量

### 2. 调试测试 (DebugTest)
- 上传本地视频进行单帧调试
- 查看检测结果和标注
- 支持跳帧和倍速播放

### 3. 配置向导 (SetupWizard)
- 分步骤配置系统
- 服务配置（Redis/RabbitMQ）
- 摄像头配置
- 区域绘制（Canvas可视化）
- 违规规则设置

### 4. 设置页面 (Settings)
- 修改系统配置
- 管理摄像头、区域、规则
- 调整检测参数

---

## 常用命令

```bash
# 添加Python依赖
uv add <package-name>

# 安装开发依赖
uv add --dev <package-name>

# 更新依赖
uv sync --upgrade

# 运行测试
uv run python backend/test_detection.py

# 进入虚拟环境shell
uv shell

# 前端构建
cd frontend && npm run build

# 前端预览生产构建
cd frontend && npm run preview
```

---

## 测试说明

### 本地测试（无需外部服务）

```bash
# 运行基础功能测试
uv run python backend/test_detection.py
```

测试内容：
- 区域管理器（ZoneManager）
- 状态机（StateMachine）
- API客户端初始化（不调用实际API）

### 完整功能测试（需要外部服务）

```bash
# 测试API检测（需要模型服务可用）
# 修改 test_detection.py 取消注释 test_api_detector() 调用

# 测试视频流处理（需要本地视频文件）
uv run python backend/test_detection.py
```

---

## 常见问题

### Q: 启动后端时报错 "ModuleNotFoundError"
**A**: 确保已运行 `uv sync` 安装依赖，并使用 `uv run` 前缀运行命令。

### Q: 前端无法连接后端API
**A**: 检查：
1. 后端是否已启动（http://localhost:8000/health 应返回健康状态）
2. 前端vite.config.js中的proxy配置是否正确
3. 是否有其他服务占用8000或5173端口

### Q: 模型API连接失败
**A**: 
- 检查 `config.yml` 中的 `model_api.url` 是否正确
- 确认网络可以访问模型服务地址
- 查看后端日志中的具体错误信息

### Q: RTSP流无法获取
**A**:
- 检查海康平台API配置（appKey, appSecret, host）
- 确认摄像头indexCode正确
- 检查网络是否可以访问海康平台

### Q: RabbitMQ连接失败
**A**:
- 检查 `config.yml` 中的RabbitMQ配置
- 确认RabbitMQ服务已启动
- 检查端口是否正确（默认5672，Docker映射可能为5673）

### Q: Redis连接失败
**A**:
- 检查 `config.yml` 中的Redis配置
- 确认Redis服务已启动
- 检查密码是否正确（无密码设为null）

---

## 项目结构

```
save-vision-violation/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI路由
│   │   │   ├── config.py     # 配置管理API
│   │   │   ├── zones.py      # 区域管理API
│   │   │   ├── rules.py      # 规则管理API
│   │   │   ├── monitor.py    # 监控控制API
│   │   │   └── debug_stream.py  # 调试流API
│   │   ├── config/           # 配置管理
│   │   │   ├── models.py     # Pydantic模型
│   │   │   └── manager.py    # 配置管理器
│   │   ├── core/             # 核心逻辑
│   │   │   ├── detector.py   # 检测器（API/本地模式）
│   │   │   ├── tracker.py    # 跟踪器
│   │   │   ├── state_machine.py  # 状态机
│   │   │   ├── zone_manager.py   # 区域管理
│   │   │   └── debug_visualizer.py  # 可视化
│   │   ├── services/         # 外部服务
│   │   │   ├── model_api_client.py  # 模型API客户端
│   │   │   ├── rtsp_client.py       # 海康RTSP客户端
│   │   │   ├── video_stream.py      # 视频流处理
│   │   │   ├── redis_client.py      # Redis客户端
│   │   │   └── rabbitmq_client.py   # RabbitMQ客户端
│   │   └── main.py           # FastAPI应用入口
│   ├── config.yml            # 运行时配置
│   ├── config.template.yml   # 配置模板
│   ├── run.py                # 启动脚本
│   └── test_detection.py     # 测试脚本
├── frontend/
│   ├── src/
│   │   ├── api/              # API接口
│   │   ├── components/       # Vue组件
│   │   ├── views/            # 页面视图
│   │   ├── router/           # 路由配置
│   │   └── stores/           # Pinia状态管理
│   ├── package.json
│   └── vite.config.js
├── docker/
│   ├── Dockerfile.backend    # 后端Dockerfile
│   ├── Dockerfile.frontend   # 前端Dockerfile
│   ├── nginx.conf            # Nginx配置
│   └── DEPLOY.md             # 部署文档
├── docker-compose.yml        # 开发环境Docker Compose
├── docker-compose.prod.yml   # 生产环境Docker Compose
├── pyproject.toml            # Python依赖配置
└── README.md                 # 本文件
```

---

## 核心算法

### 跟踪算法
- **ByteTrack** 纯运动跟踪，不依赖外观特征
- **卡尔曼滤波** 预测人员位置
- **匈牙利算法** 最优匹配

### 状态机
- **TRACKING** → 追踪中
- 区域间移动检测违规

### 空白区域保持
- 人员跨区域移动时保持区域记忆
- 避免中间空白区域导致违规检测失效

---

## API接口文档

启动后端后访问：http://localhost:8000/docs

主要接口：
- `GET /api/config` - 获取配置
- `PUT /api/config` - 更新配置
- `POST /api/monitor/start` - 启动监控
- `POST /api/monitor/stop` - 停止监控
- `GET /api/monitor/status` - 获取状态
- `POST /api/monitor/debug-stream` - 启动调试流（SSE）
- `POST /api/monitor/debug-frame` - 处理单帧图片

---

## 更新日志

查看 [CHANGELOG.md](CHANGELOG.md) 了解详细更新记录。

## License

MIT
