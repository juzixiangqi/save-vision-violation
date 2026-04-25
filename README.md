# 仓库违规检测系统

基于YOLO的仓库作业违规检测系统，支持人员搬运检测、区域管理和违规告警。

## 功能特性

- **实时跟踪与检测**：API调用远程模型服务，支持人员和箱子跟踪
- **智能追踪算法**：ByteTrack 纯运动跟踪，不依赖外观特征，俯视场景ID更稳定
- **状态机管理**：IDLE / CARRYING / OCCLUDED 三种状态管理，实时可视化
- **区域配置**：可视化Canvas区域绘制，支持多边形Zone定义
- **违规规则**：灵活配置区域间搬运限制（如 A→B 违规）
- **遮挡处理**：卡尔曼滤波跟踪，遮挡期间保持记忆
- **违规告警**：RabbitMQ推送违规事件（端口5673）
- **配置管理**：YAML配置文件，前端可视化配置向导
- **中文支持**：完整的界面中文显示

## 技术栈

**后端**
- Python 3.12
- [uv](https://docs.astral.sh/uv/) (包管理工具)
- FastAPI
- **模型推理：API 调用模式**（通过 HTTP 调用远程模型服务）
- ByteTrack (纯运动跟踪，不依赖外观特征)
- Redis (状态缓存)
- RabbitMQ (消息队列，端口5673)
- OpenCV + Pillow (中文绘制)

**前端**
- Vue 3
- Element Plus
- Vite
- Pinia (状态管理)

## 环境要求

- Python 3.12
- [uv](https://docs.astral.sh/uv/) - Python 包管理工具
- Node.js 18+ (前端开发)
- Docker (用于运行 Redis 和 RabbitMQ)
- **模型推理服务**（提供 `/predict` 接口，详见 DEPLOY.md）
- Windows中文字体（黑体/宋体/微软雅黑）或 Linux/macOS 中文字体

## 快速开始

### 前置条件

系统已从本地模型推理改为 **API 调用模式**，需要准备一个模型推理服务：
- 推理服务需提供 `POST /predict` 接口，接收图像并返回检测结果
- 详见 [DEPLOY.md](DEPLOY.md) 中的"模型推理服务说明"
- 开发测试时，修改 `backend/config.yml` 中的 `detection_params.model_api.url` 指向你的推理服务

### 1. 启动依赖服务

```bash
docker-compose up -d
```

这将启动 Redis (6379) 和 RabbitMQ (5673/15673)。

### 2. 安装后端依赖

项目使用 [uv](https://docs.astral.sh/uv/) 作为包管理工具，依赖配置在 `pyproject.toml` 中，使用清华镜像源。

```bash
# 安装依赖（自动创建虚拟环境）
uv sync

# 或使用指定的 Python 版本
uv python install 3.12
uv sync
```

### 3. 安装前端依赖

```bash
cd frontend
npm install
```

### 4. 配置模型API地址

编辑 `backend/config.yml`，设置模型推理服务地址：

```yaml
detection_params:
  model_api:
    url: http://your-model-api-server:31674/predict  # 改为实际地址
    timeout: 30
    imgsz: 640
    confidence: 0.2
  use_api: true
```

### 5. 启动后端服务

```bash
# 使用 uv 运行（推荐）
uv run python backend/run.py
```

后端服务将运行在 http://localhost:8000

### 6. 启动前端开发服务器

```bash
cd frontend
npm run dev
```

前端服务将运行在 http://localhost:5173

### 7. 访问系统

打开浏览器访问 http://localhost:5173，按照初始化向导完成配置。

## 可视化说明

### 人员状态颜色
- 🟢 **绿色边框** = IDLE（空闲，未搬运）
- 🟡 **黄色边框** = CARRYING（搬运中，已锁定箱子）
- 🔴 **红色边框** = OCCLUDED（遮挡/丢失箱子）

### 信息面板
- 右侧信息面板显示各状态人员统计
- 支持完整中文显示
- 实时显示违规详情

## 常用命令

```bash
# 添加新的 Python 依赖
uv add <package-name>

# 安装开发依赖
uv add --dev <package-name>

# 更新依赖
uv sync --upgrade

# 运行 Python 脚本
uv run python <script.py>

# 进入虚拟环境 shell
uv shell
```

## 配置流程

1. **摄像头配置**：添加摄像头（RTSP流或本地视频文件）
2. **区域绘制**：在Canvas上绘制Zone_A、Zone_B、Zone_C等区域
3. **违规规则**：定义哪些区域之间的搬运属于违规
4. **参数调优**：调整检测灵敏度和阈值
5. **启动监控**：确认配置并启动实时监控

## 项目结构

```
save-vision-violation/
├── backend/
│   ├── app/
│   │   ├── api/           # API路由
│   │   ├── config/        # 配置管理
│   │   ├── core/          # 核心逻辑（检测、追踪、违规检查）
│   │   ├── services/      # 服务（视频流、Redis、RabbitMQ）
│   │   └── utils/         # 工具函数
│   ├── config.yml         # 配置文件
│   └── run.py            # 启动脚本
├── frontend/
│   └── src/
│       ├── components/    # 组件
│       ├── views/         # 页面
│       ├── stores/        # Pinia状态管理
│       └── api/           # API接口
├── pyproject.toml        # Python 依赖配置 (uv)
├── .python-version       # Python 版本指定
├── CHANGELOG.md          # 变更日志
└── docker-compose.yml    # 依赖服务配置
```

## 核心算法说明

### 追踪算法
系统使用 ByteTrack 进行人员追踪：
- **纯运动跟踪**：基于 IoU 和距离，不依赖外观特征
- **卡尔曼滤波**：预测人员位置，遮挡后仍能恢复跟踪
- **两次匹配策略**：高分检测优先匹配，低分检测辅助匹配
- **俯视优化**：特别适合外观特征不明显的俯视场景

### 姿态检测
针对天花板45度俯视拍摄优化：
- 考虑透视导致的y轴压缩
- 放宽手部高度判断
- 强化水平距离判断

### 状态机
- **IDLE → CARRYING**: 检测搬起姿态 + 箱子在附近
- **CARRYING → OCCLUDED**: 人箱分离（IoU < 阈值）
- **CARRYING/OCCLUDED → IDLE**: 检测放下姿态或超时

## RabbitMQ 消息格式

违规事件将推送到 RabbitMQ 队列（端口5673）：

```json
{
  "event_type": "violation",
  "timestamp": "2026-03-16T10:30:00Z",
  "camera_id": "cam_001",
  "person_id": "person_123",
  "box_id": "box_456",
  "origin_zone": "zone_a",
  "drop_zone": "zone_b",
  "trajectory": [...],
  "confidence": 0.95
}
```

## 测试

运行测试脚本：

```bash
# 使用 uv 运行测试
uv run python backend/test_detection.py
```

## 离线部署

支持在无外网环境部署，详见 [DEPLOY.md](DEPLOY.md)。

## 性能说明

- **API调用模式**: 模型推理在独立服务中执行，后端专注于业务逻辑
- **ByteTrack**: 纯运动跟踪，比 DeepSort 更快（无需计算外观特征）
- **PIL中文绘制**: 增加约2-3ms每帧
- **总体性能**: 取决于模型推理服务的响应速度，建议部署在 GPU 服务器上

## 已知问题

- Windows系统需要安装中文字体（如黑体、宋体）才能正常显示中文
- 密集场景下（>10人）追踪准确率可能下降
- 人员快速移动（>5px/帧）可能导致ID切换

## 模型推理服务

系统采用 API 调用模式，需要独立的模型推理服务。推理服务需实现：

**POST /predict**
- 接收：multipart/form-data（file, imgsz, conf）
- 返回：JSON（status, predictions）

详见 [DEPLOY.md](DEPLOY.md) 中的"模型推理服务说明"章节。

## 更新日志

查看 [CHANGELOG.md](CHANGELOG.md) 了解详细更新记录。

## License

MIT
