# 模型API调用改造实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将本地YOLO模型推理改为通过HTTP API调用远程模型服务，并打包为Docker镜像用于内网Linux部署

**Architecture:** 保留现有检测流水线架构，仅替换detector实现。新增ModelAPIClient处理HTTP请求，通过环境变量配置API地址。移除ultralytics等本地模型依赖。

**Tech Stack:** Python 3.12, FastAPI, requests, OpenCV, Docker

---

### Task 1: 更新配置模型支持API配置

**Files:**
- Modify: `backend/app/config/models.py`

**Step 1: 添加ModelAPIConfig类**

在 `PersonCarryParams` 类之前添加:

```python
class ModelAPIConfig(BaseModel):
    """模型API配置"""
    url: str = "http://10.190.28.23:31674/predict"
    timeout: int = 30
    imgsz: int = 640
    confidence: float = 0.2
```

**Step 2: 更新DetectionParams类**

修改 `DetectionParams` 类，添加 `use_api` 和 `model_api` 字段:

```python
class DetectionParams(BaseModel):
    use_api: bool = True  # 是否使用API模式
    model_api: ModelAPIConfig = ModelAPIConfig()  # API配置
    person_carry: PersonCarryParams = PersonCarryParams()  # 本地模型配置（兼容）
    tracking: TrackingParams = TrackingParams()
    # 兼容性保留以下字段（旧代码依赖）
    pose: PoseParams = PoseParams()
    box: BoxDetectionParams = BoxDetectionParams()
    lift_detection: LiftDetectionParams = LiftDetectionParams()
    drop_detection: DropDetectionParams = DropDetectionParams()
```

**Step 3: 验证**

运行: `cd backend && uv run python -c "from app.config.models import DetectionParams; print(DetectionParams())"`

Expected: 正常输出默认配置，包含use_api=True

**Step 4: Commit**

```bash
git add backend/app/config/models.py
git commit -m "feat: add ModelAPIConfig for remote model API"
```

---

### Task 2: 创建模型API客户端模块

**Files:**
- Create: `backend/app/services/model_api_client.py`

**Step 1: 创建API客户端**

```python
import io
import os
from typing import List, Optional

import cv2
import numpy as np
import requests

from app.config.models import ModelAPIConfig
from app.core.detector import Detection


class ModelAPIClient:
    """模型API客户端 - 通过HTTP调用远程模型服务"""

    def __init__(self, config: Optional[ModelAPIConfig] = None):
        if config is None:
            # 从环境变量读取配置
            config = ModelAPIConfig(
                url=os.getenv("MODEL_API_URL", "http://10.190.28.23:31674/predict"),
                timeout=int(os.getenv("MODEL_API_TIMEOUT", "30")),
                imgsz=int(os.getenv("MODEL_API_IMGSZ", "640")),
                confidence=float(os.getenv("MODEL_API_CONFIDENCE", "0.2")),
            )
        self.config = config
        self.session = requests.Session()

    def detect(self, frame: np.ndarray, imgsz: Optional[int] = None, conf: Optional[float] = None) -> List[Detection]:
        """
        通过API检测图像

        Args:
            frame: OpenCV图像 (BGR格式)
            imgsz: 输入尺寸（覆盖配置）
            conf: 置信度阈值（覆盖配置）

        Returns:
            Detection对象列表
        """
        imgsz = imgsz or self.config.imgsz
        conf = conf or self.config.confidence

        try:
            # 编码图像为JPEG
            _, img_encoded = cv2.imencode(".jpg", frame)
            if not _:
                print("[ModelAPIClient] 图像编码失败")
                return []

            # 准备multipart数据
            files = {
                "file": ("image.jpg", io.BytesIO(img_encoded.tobytes()), "image/jpeg")
            }
            data = {
                "imgsz": str(imgsz),
                "conf": str(conf),
            }

            # 发送请求
            response = self.session.post(
                self.config.url,
                files=files,
                data=data,
                timeout=self.config.timeout,
            )
            response.raise_for_status()

            # 解析响应
            result = response.json()
            if result.get("status") != "success":
                print(f"[ModelAPIClient] API返回错误: {result}")
                return []

            # 转换为Detection对象
            detections = []
            for i, pred in enumerate(result.get("predictions", [])):
                bbox = pred["bbox"]
                x1, y1, x2, y2 = bbox
                center = ((x1 + x2) / 2, (y1 + y2) / 2)
                bottom_center = ((x1 + x2) / 2, y2)

                detections.append(
                    Detection(
                        id=f"person_carry_{i+1}",
                        bbox=[float(x) for x in bbox],
                        confidence=float(pred["confidence"]),
                        center=center,
                        bottom_center=bottom_center,
                        class_id=int(pred.get("class_idx", 0)),
                        class_name=str(pred.get("class", "person_carry")),
                    )
                )

            return detections

        except requests.exceptions.ConnectionError as e:
            print(f"[ModelAPIClient] 连接错误: {e}")
            return []
        except requests.exceptions.Timeout as e:
            print(f"[ModelAPIClient] 请求超时: {e}")
            return []
        except Exception as e:
            print(f"[ModelAPIClient] 检测错误: {e}")
            return []

    def health_check(self) -> bool:
        """检查API服务是否可用"""
        try:
            # 尝试发送一个简单请求（OPTIONS或GET）
            response = self.session.get(
                self.config.url.replace("/predict", "/health"),
                timeout=5,
            )
            return response.status_code == 200
        except:
            return False
```

**Step 2: 验证**

运行: `cd backend && uv run python -c "from app.services.model_api_client import ModelAPIClient; print('OK')"`

Expected: 正常输出OK（无导入错误）

**Step 3: Commit**

```bash
git add backend/app/services/model_api_client.py
git commit -m "feat: add ModelAPIClient for remote model inference"
```

---

### Task 3: 重构检测器支持API模式

**Files:**
- Modify: `backend/app/core/detector.py`

**Step 1: 重构YOLODetector类**

替换整个文件内容:

```python
import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import os

from app.config.manager import config_manager


@dataclass
class Detection:
    id: str  # track_id
    bbox: List[float]  # [x1, y1, x2, y2]
    confidence: float
    center: Tuple[float, float]
    bottom_center: Tuple[float, float]
    class_id: int = 0  # 兼容旧代码
    class_name: str = "person_carry"

    def __post_init__(self):
        """确保bbox字段存在（兼容旧代码）"""
        pass


@dataclass
class Pose:
    """姿态数据类（兼容性保留，新的检测逻辑不再使用）"""

    id: str
    keypoints: np.ndarray  # [17, 3] - x, y, confidence
    bbox: List[float]
    confidence: float


class YOLODetector:
    def __init__(self):
        config = config_manager.get_config()
        self.detection_params = config.detection_params
        self.use_api = self.detection_params.use_api

        if self.use_api:
            # API模式
            from app.services.model_api_client import ModelAPIClient
            self.api_client = ModelAPIClient(self.detection_params.model_api)
            print(f"[Detector] 使用API模式: {self.detection_params.model_api.url}")
        else:
            # 本地模型模式（兼容）
            self._init_local_model()

        self.id_counter = 0

    def _init_local_model(self):
        """初始化本地模型（兼容模式）"""
        import os
        import tempfile
        import shutil
        from ultralytics import YOLO

        model_path = self.detection_params.person_carry.model

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"模型文件不存在: {model_path}")

        file_ext = os.path.splitext(model_path)[1].lower()

        if file_ext == ".pt":
            self.model = YOLO(model_path)
        elif file_ext == ".pth":
            temp_pt_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as tmp:
                    temp_pt_path = tmp.name
                shutil.copy2(model_path, temp_pt_path)
                print(f"[Detector] 已将 {model_path} 复制到临时文件 {temp_pt_path} 进行加载")
                self.model = YOLO(temp_pt_path)
                try:
                    os.unlink(temp_pt_path)
                except:
                    pass
            except Exception as e:
                if temp_pt_path and os.path.exists(temp_pt_path):
                    try:
                        os.unlink(temp_pt_path)
                    except:
                        pass
                raise e
        else:
            raise ValueError(f"不支持的模型格式: {file_ext}，只支持 .pt 或 .pth")

        print(f"[Detector] 已加载本地模型: {model_path}")

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """检测搬箱子的人"""
        if self.use_api:
            return self._detect_api(frame)
        else:
            return self._detect_local(frame)

    def _detect_api(self, frame: np.ndarray) -> List[Detection]:
        """通过API检测"""
        return self.api_client.detect(
            frame,
            imgsz=self.detection_params.model_api.imgsz,
            conf=self.detection_params.model_api.confidence,
        )

    def _detect_local(self, frame: np.ndarray) -> List[Detection]:
        """本地模型检测（兼容模式）"""
        detections = []

        results = self.model(
            frame,
            conf=self.detection_params.person_carry.confidence,
            iou=self.detection_params.person_carry.iou_threshold,
        )

        for result in results:
            if result.boxes is None:
                continue

            for i, box in enumerate(result.boxes):
                cls = int(box.cls[0])
                conf = float(box.conf[0])

                # 只检测person_carry类别
                if cls != self.detection_params.person_carry.class_id:
                    continue

                bbox = box.xyxy[0].cpu().numpy().tolist()
                x1, y1, x2, y2 = bbox
                center = ((x1 + x2) / 2, (y1 + y2) / 2)
                bottom_center = ((x1 + x2) / 2, y2)

                self.id_counter += 1
                detections.append(
                    Detection(
                        id=f"person_carry_{self.id_counter}",
                        bbox=[float(x) for x in bbox],
                        confidence=conf,
                        center=center,
                        bottom_center=bottom_center,
                    )
                )

        return detections
```

**Step 2: 验证**

运行: `cd backend && uv run python -c "from app.core.detector import YOLODetector; print('OK')"`

Expected: 正常输出OK（无导入错误）

**Step 3: Commit**

```bash
git add backend/app/core/detector.py
git commit -m "feat: refactor YOLODetector to support API mode"
```

---

### Task 4: 更新依赖配置

**Files:**
- Modify: `pyproject.toml`

**Step 1: 添加requests，移除ultralytics**

修改dependencies:
```toml
dependencies = [
    "fastapi==0.109.0",
    "uvicorn[standard]==0.27.0",
    "pydantic==2.5.3",
    "pydantic-settings==2.1.0",
    "pyyaml==6.0.1",
    "opencv-python>=4.9.0",
    "requests>=2.31.0",  # 新增：HTTP客户端
    # "ultralytics>=8.3.0",  # 移除：本地模型推理（API模式不需要）
    "redis==5.0.1",
    "pika==1.3.2",
    "numpy==1.26.3",
    "filterpy==1.4.5",
    "python-multipart==0.0.6",
    "websockets==12.0",
    "deep-sort-realtime>=1.3.0",
    "pillow>=10.0.0",
    "setuptools<70",
]
```

**Step 2: 更新依赖**

运行: `uv sync`

Expected: 成功安装requests，ultralytics不再安装

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add requests, remove ultralytics for API mode"
```

---

### Task 5: 更新测试脚本

**Files:**
- Modify: `backend/test_detection.py`

**Step 1: 添加API模式测试**

在文件末尾添加:

```python
def test_api_detector():
    """测试API模式检测器（需要API服务可用）"""
    print("\n" + "=" * 50)
    print("测试API模式检测器")
    print("=" * 50)

    try:
        import os
        os.environ["MODEL_API_URL"] = "http://10.190.28.23:31674/predict"

        from app.core.detector import YOLODetector
        from app.config.manager import config_manager
        from app.config.models import DetectionParams, ModelAPIConfig

        # 临时设置API模式
        config = config_manager.get_config()
        original_use_api = config.detection_params.use_api
        config.detection_params.use_api = True
        config.detection_params.model_api = ModelAPIConfig()

        detector = YOLODetector()

        # 创建测试图像
        test_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

        # 检测
        detections = detector.detect(test_frame)
        print(f"✓ API检测完成，检测到 {len(detections)} 个目标")

        # 恢复配置
        config.detection_params.use_api = original_use_api

        return True
    except Exception as e:
        print(f"✗ API检测器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_api_client():
    """测试API客户端"""
    print("\n" + "=" * 50)
    print("测试API客户端")
    print("=" * 50)

    try:
        from app.services.model_api_client import ModelAPIClient
        from app.config.models import ModelAPIConfig

        client = ModelAPIClient(ModelAPIConfig())
        print(f"✓ API客户端创建成功")
        print(f"  URL: {client.config.url}")
        print(f"  Timeout: {client.config.timeout}")

        return True
    except Exception as e:
        print(f"✗ API客户端测试失败: {e}")
        return False
```

**Step 2: 更新main函数**

修改 `main()` 函数:
```python
def main():
    """运行所有测试"""
    print("\n")
    print("╔" + "=" * 48 + "╗")
    print("║" + " " * 10 + "仓库违规检测系统测试" + " " * 16 + "║")
    print("╚" + "=" * 48 + "╝")
    print("\n")

    results = []
    results.append(("区域管理器", test_zone_manager()))
    results.append(("状态机", test_state_machine()))
    results.append(("API客户端", test_api_client()))
    # results.append(("API检测器", test_api_detector()))  # 需要真实API服务

    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{name:20s} {status}")

    print("-" * 50)
    print(f"总计: {passed}/{total} 通过")

    return passed == total
```

**Step 3: 运行测试**

运行: `cd backend && uv run python test_detection.py`

Expected: 区域管理器、状态机、API客户端测试通过

**Step 4: Commit**

```bash
git add backend/test_detection.py
git commit -m "test: add API mode tests"
```

---

### Task 6: 创建Dockerfile

**Files:**
- Create: `Dockerfile`

**Step 1: 创建Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 安装uv
RUN pip install --no-cache-dir uv

# 复制依赖文件
COPY pyproject.toml .
COPY README.md .

# 创建虚拟环境并安装依赖
RUN uv venv && uv sync

# 复制应用代码
COPY backend/app ./app
COPY backend/config.yml .
COPY backend/run.py .

# 暴露端口
EXPOSE 8000

# 设置环境变量
ENV PYTHONPATH=/app
ENV MODEL_API_URL=http://10.190.28.23:31674/predict
ENV MODEL_API_TIMEOUT=30
ENV MODEL_API_IMGSZ=640
ENV MODEL_API_CONFIDENCE=0.2

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# 启动命令
CMD ["uv", "run", "python", "run.py"]
```

**Step 2: 创建.dockerignore**

```
__pycache__
*.pyc
*.pyo
*.pyd
.Python
*.so
*.egg
*.egg-info
dist
build
.git
.gitignore
.env
.venv
venv
ENV
node_modules
frontend
*.pt
*.pth
*.onnx
```

**Step 3: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "feat: add Dockerfile for internal network deployment"
```

---

### Task 7: 更新docker-compose.yml

**Files:**
- Modify: `docker-compose.yml`

**Step 1: 添加app服务**

```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - MODEL_API_URL=http://10.190.28.23:31674/predict
      - MODEL_API_TIMEOUT=30
      - MODEL_API_IMGSZ=640
      - MODEL_API_CONFIDENCE=0.2
      - REDIS_HOST=redis
      - RABBITMQ_HOST=rabbitmq
    depends_on:
      - redis
      - rabbitmq
    networks:
      - app-network
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    networks:
      - app-network

  rabbitmq:
    image: rabbitmq:3-management-alpine
    ports:
      - "5672:5672"
      - "15672:15672"
    environment:
      - RABBITMQ_DEFAULT_USER=admin
      - RABBITMQ_DEFAULT_PASS=admin
    networks:
      - app-network

networks:
  app-network:
    driver: bridge
```

**Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: update docker-compose with app service"
```

---

### Task 8: 添加健康检查端点

**Files:**
- Modify: `backend/app/main.py`

**Step 1: 添加健康检查**

在现有路由中添加:

```python
@app.get("/api/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "api_mode": True,
        "model_api_url": os.getenv("MODEL_API_URL", "http://10.190.28.23:31674/predict"),
    }
```

**Step 2: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: add health check endpoint"
```

---

### Task 9: 最终验证

**Step 1: 运行所有测试**

```bash
cd backend
uv run python test_detection.py
```

Expected: 所有测试通过

**Step 2: 检查导入**

```bash
uv run python -c "
from app.core.detector import YOLODetector
from app.services.model_api_client import ModelAPIClient
from app.config.models import ModelAPIConfig
print('All imports OK')
"
```

Expected: All imports OK

**Step 3: 检查Docker构建**

```bash
docker build -t save-vision-violation:test .
```

Expected: 构建成功

**Step 4: Commit**

```bash
git add -A
git commit -m "feat: complete API mode migration"
```

---

## 变更清单

### 修改的文件
1. `backend/app/config/models.py` - 添加ModelAPIConfig
2. `backend/app/core/detector.py` - 重构支持API模式
3. `backend/test_detection.py` - 添加API测试
4. `pyproject.toml` - 更新依赖
5. `backend/app/main.py` - 添加健康检查
6. `docker-compose.yml` - 添加app服务

### 新增的文件
1. `backend/app/services/model_api_client.py` - API客户端
2. `Dockerfile` - Docker镜像
3. `.dockerignore` - Docker忽略文件
4. `docs/plans/2025-04-24-api-detection-design.md` - 设计文档

### 移除的依赖
- `ultralytics` (本地YOLO推理，API模式不需要)

### 新增的依赖
- `requests` (HTTP客户端)

## 部署说明

### 构建镜像
```bash
docker build -t save-vision-violation:latest .
```

### 运行容器
```bash
docker run -d \
  -p 8000:8000 \
  -e MODEL_API_URL=http://10.190.28.23:31674/predict \
  -e MODEL_API_TIMEOUT=30 \
  save-vision-violation:latest
```

### 使用docker-compose
```bash
docker-compose up -d
```

## 注意事项

1. **内网部署**: 确保内网Linux服务器能访问 `10.190.28.23:31674`
2. **RTSP流**: 只有内网有权限连接RTSP，确保容器网络配置正确
3. **API可用性**: 如果API服务不可用，检测器会返回空列表，不会中断视频流
4. **性能**: API调用会增加延迟，可通过调整 `detection_interval` 降低检测频率
