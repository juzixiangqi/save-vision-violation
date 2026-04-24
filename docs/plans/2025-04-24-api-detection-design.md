# 模型API调用改造设计文档

> **日期**: 2025-04-24
> **目标**: 将本地YOLO模型推理改为通过HTTP API调用远程模型服务

## 背景

当前系统使用 `ultralytics.YOLO` 在本地加载 `.pt` 模型进行推理。现需要改为通过HTTP API调用远程模型服务（`10.190.28.23:31674/predict`），以便：
1. 模型部署在独立服务器上
2. 内网Linux服务器只运行检测业务逻辑（无GPU/模型文件）
3. 通过Docker镜像部署

## API接口规范

### 请求
- **URL**: `POST http://10.190.28.23:31674/predict`
- **Content-Type**: `multipart/form-data`
- **参数**:
  - `file`: 图像文件 (JPEG)
  - `imgsz`: 输入尺寸 (默认640)
  - `conf`: 置信度阈值 (默认0.2)

### 响应
```json
{
    "predictions": [
        {
            "bbox": [x1, y1, x2, y2],
            "class": "person_carry",
            "class_idx": 0,
            "confidence": 0.99
        }
    ],
    "status": "success"
}
```

## 架构变更

### 1. 检测器改造 (`app/core/detector.py`)

**当前**: `YOLODetector` 直接加载 `.pt` 模型，调用 `model(frame)`
**新设计**: 
- 保留 `Detection` 和 `Pose` 数据类
- `YOLODetector` 改为通过HTTP API调用
- 将 `np.ndarray` 编码为JPEG后通过 `requests` POST
- 解析JSON响应，转换为 `List[Detection]`
- 移除 `load_yolo_model()` 函数
- 移除 `ultralytics` 依赖

### 2. 配置模型更新 (`app/config/models.py`)

新增 `ModelAPIConfig`:
```python
class ModelAPIConfig(BaseModel):
    url: str = "http://10.190.28.23:31674/predict"
    timeout: int = 30
    imgsz: int = 640
    confidence: float = 0.2
```

更新 `DetectionParams`:
```python
class DetectionParams(BaseModel):
    use_api: bool = True  # 是否使用API模式
    model_api: ModelAPIConfig = ModelAPIConfig()
    person_carry: PersonCarryParams = PersonCarryParams()  # 保留兼容
    ...
```

### 3. API客户端模块 (`app/services/model_api_client.py`)

创建独立的API客户端:
```python
class ModelAPIClient:
    def __init__(self, config: ModelAPIConfig):
        self.url = config.url
        self.timeout = config.timeout
        
    def detect(self, frame: np.ndarray, imgsz: int = 640, conf: float = 0.2) -> List[Detection]:
        # 编码frame为JPEG
        # 发送multipart/form-data请求
        # 解析响应并返回Detection列表
```

### 4. 依赖调整 (`pyproject.toml`)

**移除**:
- `ultralytics>=8.3.0` (本地模型推理)
- `filterpy==1.4.5` (仅用于本地跟踪算法，检查是否必要)

**保留**:
- `opencv-python` (图像处理)
- `numpy` (数值计算)
- `requests` (新增，HTTP客户端)
- `fastapi`, `uvicorn` (Web服务)
- `redis`, `pika` (消息队列)
- `deep-sort-realtime` (跟踪)

### 5. 调用方适配

- `app/api/monitor.py`: `process_frame()` 无需修改（detector接口不变）
- `app/core/debug_visualizer.py`: `process_video_frame_debug()` 无需修改
- `backend/test_detection.py`: 需要适配或添加API模式测试

## 数据流

```
视频帧 → YOLODetector.detect(frame)
              ↓
        [API模式] 编码JPEG → POST /predict
              ↓
        解析JSON → List[Detection]
              ↓
        SimpleTracker.update()
              ↓
        StateMachine / ZoneManager
              ↓
        RabbitMQ告警
```

## 错误处理

1. **API不可达**: 记录错误，返回空检测列表，不中断视频流
2. **API返回错误**: 根据status字段判断，记录详细错误
3. **编码失败**: 捕获异常，返回空列表
4. **超时**: 可配置timeout，默认30秒

## Docker部署

### Dockerfile
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# 安装uv
RUN pip install uv

# 复制依赖文件
COPY pyproject.toml .
RUN uv sync

# 复制代码
COPY backend/app ./app
COPY backend/config.yml .
COPY backend/run.py .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uv", "run", "python", "run.py"]
```

### docker-compose.yml 更新
```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - MODEL_API_URL=http://10.190.28.23:31674/predict
    networks:
      - app-network
```

## 测试策略

1. **单元测试**: 模拟API响应测试 `ModelAPIClient`
2. **集成测试**: 使用真实API地址测试（需内网环境）
3. **回归测试**: 确保 `monitor.py` 流程不变

## 回滚方案

保留 `PersonCarryParams` 配置，通过 `use_api` 开关控制：
- `use_api=true`: 使用API模式
- `use_api=false`: 保留本地模型模式（需手动安装ultralytics）

## 实施步骤

1. 更新 `app/config/models.py` - 添加API配置
2. 创建 `app/services/model_api_client.py` - API客户端
3. 重构 `app/core/detector.py` - 支持API模式
4. 更新 `pyproject.toml` - 调整依赖
5. 适配调用方 - monitor.py, debug_visualizer.py
6. 更新测试 - test_detection.py
7. 创建 Dockerfile
8. 验证测试

## 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| API延迟高导致帧率下降 | 增加异步处理或降低检测频率（detection_interval） |
| API服务不可用 | 优雅降级，返回空检测，记录错误日志 |
| 网络不稳定 | 增加重试机制，配置合理超时 |
| 图像编码开销 | 使用JPEG质量参数平衡大小和速度 |

## 配置示例 (config.yml)

```yaml
detection_params:
  use_api: true
  model_api:
    url: "http://10.190.28.23:31674/predict"
    timeout: 30
    imgsz: 640
    confidence: 0.2
  person_carry:
    class_id: 0
    confidence: 0.5
    iou_threshold: 0.45
    model: "person_carry.pt"  # 保留兼容
```

## 环境变量支持

支持通过环境变量覆盖配置:
- `MODEL_API_URL`: API地址
- `MODEL_API_TIMEOUT`: 超时时间
- `MODEL_API_IMGSZ`: 输入尺寸
- `MODEL_API_CONFIDENCE`: 置信度阈值

---

**设计确认**: 待用户审批
