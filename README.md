# 仓库违规检测系统

基于YOLO的仓库作业违规检测系统，支持人员搬运检测、区域管理和违规告警。

## 功能特性

- **实时跟踪与检测**：YOLOv8 + 姿态估计，支持人员和箱子跟踪
- **状态机管理**：IDLE / CARRYING / OCCLUDED 三种状态管理
- **区域配置**：可视化Canvas区域绘制，支持多边形Zone定义
- **违规规则**：灵活配置区域间搬运限制（如 A→B 违规）
- **遮挡处理**：卡尔曼滤波跟踪，遮挡期间保持记忆
- **违规告警**：RabbitMQ推送违规事件（端口5673）
- **配置管理**：YAML配置文件，前端可视化配置向导

## 技术栈

**后端**
- Python 3.10+
- FastAPI
- YOLOv8 (Ultralytics)
- Redis (状态缓存)
- RabbitMQ (消息队列，端口5673)
- OpenCV

**前端**
- Vue 3
- Element Plus
- Vite
- Pinia (状态管理)

## 快速开始

### 1. 启动依赖服务

```bash
docker-compose up -d
```

这将启动 Redis (6379) 和 RabbitMQ (5673/15673)。

### 2. 安装后端依赖

```bash
cd backend
pip install -r requirements.txt
```

### 3. 安装前端依赖

```bash
cd frontend
npm install
```

### 4. 启动后端服务

```bash
cd backend
python run.py
```

后端服务将运行在 http://localhost:8000

### 5. 启动前端开发服务器

```bash
cd frontend
npm run dev
```

前端服务将运行在 http://localhost:5173

### 6. 访问系统

打开浏览器访问 http://localhost:5173，按照初始化向导完成配置。

## 配置流程

1. **摄像头配置**：添加摄像头（RTSP流或本地视频文件）
2. **区域绘制**：在Canvas上绘制Zone_A、Zone_B、Zone_C等区域
3. **违规规则**：定义哪些区域之间的搬运属于违规
4. **参数调优**：调整检测灵敏度和阈值
5. **启动监控**：确认配置并启动实时监控

## 项目结构

```
warehouse-violation-detection/
├── backend/
│   ├── app/
│   │   ├── api/           # API路由
│   │   ├── config/        # 配置管理
│   │   ├── core/          # 核心逻辑
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
└── docker-compose.yml     # 依赖服务配置
```

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
cd backend
python test_detection.py
```

## License

MIT
