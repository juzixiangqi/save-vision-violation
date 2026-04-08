# 仓库违规检测系统实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 构建一个基于YOLO的仓库违规检测系统，支持区域配置、违规规则配置、状态机管理和RabbitMQ告警推送

**Architecture:** 
- 后端：Python + FastAPI + YOLOv8 + Redis + RabbitMQ
- 前端：Vue3 + ElementPlus + Vite + Canvas区域绘制
- 配置：YAML文件持久化 + Redis运行时状态缓存

**Tech Stack:** Python 3.12, [uv](https://docs.astral.sh/uv/) (包管理工具), FastAPI, YOLOv8, Redis, RabbitMQ, Vue3, ElementPlus, Vite, OpenCV

---

## 阶段一：项目基础架构

### Task 1: 创建项目目录结构

**Files:**
- Create: `pyproject.toml` (Python 依赖配置，使用 uv 管理)
- Create: `.python-version` (Python 版本指定)
- Create: `backend/config.yml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/config/__init__.py`
- Create: `backend/app/config/models.py`
- Create: `backend/app/config/manager.py`
- Create: `frontend/package.json`
- Create: `frontend/vite.config.js`

**Step 1: 创建 pyproject.toml**

```toml
[project]
name = "save-vision-violation"
version = "0.1.0"
description = "基于YOLO的仓库作业违规检测系统"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "fastapi==0.109.0",
    "uvicorn[standard]==0.27.0",
    "pydantic==2.5.3",
    "pydantic-settings==2.1.0",
    "pyyaml==6.0.1",
    "opencv-python>=4.9.0",
    "ultralytics==8.1.0",
    "redis==5.0.1",
    "pika==1.3.2",
    "numpy==1.26.3",
    "filterpy==1.4.5",
    "python-multipart==0.0.6",
    "websockets==12.0",
]

[[tool.uv.index]]
name = "tsinghua"
url = "https://pypi.tuna.tsinghua.edu.cn/simple"
default = true
```

**Step 1b: 创建 .python-version**

```
3.12
```

**Step 2: 创建基础配置文件 config.yml**

```yaml
system:
  name: "仓库违规检测系统"
  version: "1.0.0"

cameras: []

zones: []

violation_rules: []

detection_params:
  yolo:
    model: "yolov8n.pt"
    confidence: 0.5
    iou_threshold: 0.45
  pose:
    model: "yolov8n-pose.pt"
  tracking:
    max_age: 30
    min_hits: 3
  lift_detection:
    hands_below_hip_threshold: 0
    hands_distance_threshold: 150
    consecutive_frames: 5
    speed_variance_threshold: 10
  drop_detection:
    hands_rise_threshold: 30
    iou_drop_threshold: 0.1
    occlusion_timeout: 5

rabbitmq:
  host: "localhost"
  port: 5672
  username: "guest"
  password: "guest"
  queue: "violations"

redis:
  host: "localhost"
  port: 6379
  db: 0
```

**Step 3: 创建配置模型 models.py**

```python
from pydantic import BaseModel, Field
from typing import List, Optional, Tuple
from enum import Enum

class Zone(BaseModel):
    id: str
    name: str
    color: str = "#FF6B6B"
    points: List[List[int]]  # [[x1,y1], [x2,y2], ...]

class ViolationRule(BaseModel):
    id: str
    name: str
    from_zone: str
    to_zone: str
    enabled: bool = True

class Camera(BaseModel):
    id: str
    name: str
    source: str  # RTSP地址或本地视频路径
    enabled: bool = True
    fps: int = 25

class YoloParams(BaseModel):
    model: str = "yolov8n.pt"
    confidence: float = 0.5
    iou_threshold: float = 0.45

class PoseParams(BaseModel):
    model: str = "yolov8n-pose.pt"

class TrackingParams(BaseModel):
    max_age: int = 30
    min_hits: int = 3

class LiftDetectionParams(BaseModel):
    hands_below_hip_threshold: int = 0
    hands_distance_threshold: int = 150
    consecutive_frames: int = 5
    speed_variance_threshold: int = 10

class DropDetectionParams(BaseModel):
    hands_rise_threshold: int = 30
    iou_drop_threshold: float = 0.1
    occlusion_timeout: int = 5

class DetectionParams(BaseModel):
    yolo: YoloParams = YoloParams()
    pose: PoseParams = PoseParams()
    tracking: TrackingParams = TrackingParams()
    lift_detection: LiftDetectionParams = LiftDetectionParams()
    drop_detection: DropDetectionParams = DropDetectionParams()

class RabbitMQConfig(BaseModel):
    host: str = "localhost"
    port: int = 5672
    username: str = "guest"
    password: str = "guest"
    queue: str = "violations"

class RedisConfig(BaseModel):
    host: str = "localhost"
    port: int = 6379
    db: int = 0

class SystemConfig(BaseModel):
    name: str = "仓库违规检测系统"
    version: str = "1.0.0"

class Config(BaseModel):
    system: SystemConfig = SystemConfig()
    cameras: List[Camera] = []
    zones: List[Zone] = []
    violation_rules: List[ViolationRule] = []
    detection_params: DetectionParams = DetectionParams()
    rabbitmq: RabbitMQConfig = RabbitMQConfig()
    redis: RedisConfig = RedisConfig()
```

**Step 4: 创建配置管理器 manager.py**

```python
import yaml
import os
from pathlib import Path
from .models import Config

class ConfigManager:
    def __init__(self, config_path: str = "config.yml"):
        self.config_path = Path(config_path)
        self._config = None
        self._load_config()
    
    def _load_config(self):
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                self._config = Config(**data)
        else:
            self._config = Config()
            self._save_config()
    
    def _save_config(self):
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(self._config.model_dump(), f, allow_unicode=True, default_flow_style=False)
    
    def get_config(self) -> Config:
        return self._config
    
    def update_config(self, config: Config):
        self._config = config
        self._save_config()
    
    def update_cameras(self, cameras: list):
        self._config.cameras = cameras
        self._save_config()
    
    def update_zones(self, zones: list):
        self._config.zones = zones
        self._save_config()
    
    def update_rules(self, rules: list):
        self._config.violation_rules = rules
        self._save_config()
    
    def update_detection_params(self, params: dict):
        self._config.detection_params = params
        self._save_config()

config_manager = ConfigManager()
```

**Step 5: 创建前端 package.json**

```json
{
  "name": "warehouse-violation-frontend",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "vue": "^3.4.15",
    "vue-router": "^4.2.5",
    "pinia": "^2.1.7",
    "element-plus": "^2.5.3",
    "@element-plus/icons-vue": "^2.3.1",
    "axios": "^1.6.7"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.3",
    "vite": "^5.0.12"
  }
}
```

**Step 6: 创建前端 vite.config.js**

```javascript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
```

**Step 7: Commit**

```bash
git add pyproject.toml .python-version backend/ frontend/
git commit -m "chore: setup project structure and config management"
```

---

## 阶段二：后端API开发

### Task 2: 实现配置相关API

**Files:**
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/config.py`
- Create: `backend/app/api/zones.py`
- Create: `backend/app/api/rules.py`
- Modify: `backend/app/main.py`

**Step 1: 创建配置API config.py**

```python
from fastapi import APIRouter, HTTPException
from app.config.manager import config_manager
from app.config.models import Config, Camera, Zone, ViolationRule, DetectionParams

router = APIRouter(prefix="/api/config", tags=["config"])

@router.get("", response_model=Config)
async def get_config():
    return config_manager.get_config()

@router.put("", response_model=Config)
async def update_config(config: Config):
    config_manager.update_config(config)
    return config

@router.get("/cameras")
async def get_cameras():
    return config_manager.get_config().cameras

@router.put("/cameras")
async def update_cameras(cameras: list[Camera]):
    config_manager.update_cameras(cameras)
    return cameras

@router.get("/zones")
async def get_zones():
    return config_manager.get_config().zones

@router.put("/zones")
async def update_zones(zones: list[Zone]):
    config_manager.update_zones(zones)
    return zones

@router.get("/rules")
async def get_rules():
    return config_manager.get_config().violation_rules

@router.put("/rules")
async def update_rules(rules: list[ViolationRule]):
    config_manager.update_rules(rules)
    return rules

@router.get("/detection-params")
async def get_detection_params():
    return config_manager.get_config().detection_params

@router.put("/detection-params")
async def update_detection_params(params: DetectionParams):
    config_manager.update_detection_params(params)
    return params
```

**Step 2: 创建区域API zones.py**

```python
from fastapi import APIRouter
from app.config.manager import config_manager
from app.config.models import Zone
from typing import List

router = APIRouter(prefix="/api/zones", tags=["zones"])

@router.get("", response_model=List[Zone])
async def list_zones():
    return config_manager.get_config().zones

@router.post("", response_model=Zone)
async def create_zone(zone: Zone):
    zones = config_manager.get_config().zones
    zones.append(zone)
    config_manager.update_zones(zones)
    return zone

@router.put("/{zone_id}", response_model=Zone)
async def update_zone(zone_id: str, zone: Zone):
    zones = config_manager.get_config().zones
    for i, z in enumerate(zones):
        if z.id == zone_id:
            zones[i] = zone
            config_manager.update_zones(zones)
            return zone
    raise HTTPException(status_code=404, detail="Zone not found")

@router.delete("/{zone_id}")
async def delete_zone(zone_id: str):
    zones = config_manager.get_config().zones
    zones = [z for z in zones if z.id != zone_id]
    config_manager.update_zones(zones)
    return {"message": "Zone deleted"}
```

**Step 3: 创建规则API rules.py**

```python
from fastapi import APIRouter, HTTPException
from app.config.manager import config_manager
from app.config.models import ViolationRule
from typing import List

router = APIRouter(prefix="/api/rules", tags=["rules"])

@router.get("", response_model=List[ViolationRule])
async def list_rules():
    return config_manager.get_config().violation_rules

@router.post("", response_model=ViolationRule)
async def create_rule(rule: ViolationRule):
    rules = config_manager.get_config().violation_rules
    rules.append(rule)
    config_manager.update_rules(rules)
    return rule

@router.put("/{rule_id}", response_model=ViolationRule)
async def update_rule(rule_id: str, rule: ViolationRule):
    rules = config_manager.get_config().violation_rules
    for i, r in enumerate(rules):
        if r.id == rule_id:
            rules[i] = rule
            config_manager.update_rules(rules)
            return rule
    raise HTTPException(status_code=404, detail="Rule not found")

@router.delete("/{rule_id}")
async def delete_rule(rule_id: str):
    rules = config_manager.get_config().violation_rules
    rules = [r for r in rules if r.id != rule_id]
    config_manager.update_rules(rules)
    return {"message": "Rule deleted"}
```

**Step 4: 更新主入口 main.py**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import config, zones, rules

app = FastAPI(title="仓库违规检测系统", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(config.router)
app.include_router(zones.router)
app.include_router(rules.router)

@app.get("/")
async def root():
    return {"message": "仓库违规检测系统API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**Step 5: 测试API**

安装依赖并启动服务:
```bash
# 安装 Python 3.12 (如果尚未安装)
uv python install 3.12

# 安装项目依赖
uv sync

# 启动开发服务器
uv run uvicorn backend.app.main:app --reload
```

测试: `curl http://localhost:8000/api/config`
Expected: 返回默认配置JSON

**Step 6: Commit**

```bash
git add backend/
git commit -m "feat: add config, zones, rules APIs"
```

---

## 阶段三：核心检测逻辑

### Task 3: 实现YOLO检测器和姿态估计

**Files:**
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/detector.py`

**Step 1: 创建检测器 detector.py**

```python
import cv2
import numpy as np
from ultralytics import YOLO
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from app.config.manager import config_manager

@dataclass
class Detection:
    id: str
    bbox: List[float]  # [x1, y1, x2, y2]
    confidence: float
    class_id: int
    class_name: str
    center: Tuple[float, float]

@dataclass
class Pose:
    id: str
    keypoints: np.ndarray  # [17, 3] - x, y, confidence
    bbox: List[float]
    confidence: float

class YOLODetector:
    def __init__(self):
        config = config_manager.get_config()
        self.detection_params = config.detection_params
        
        # 加载检测模型
        self.detector = YOLO(self.detection_params.yolo.model)
        
        # 加载姿态模型
        self.pose_estimator = YOLO(self.detection_params.pose.model)
        
        self.person_id_counter = 0
        self.box_id_counter = 0
    
    def detect(self, frame: np.ndarray) -> Tuple[List[Detection], List[Pose]]:
        """检测人员和箱子"""
        persons = []
        boxes = []
        poses = []
        
        # 目标检测
        results = self.detector(frame, conf=self.detection_params.yolo.confidence, 
                               iou=self.detection_params.yolo.iou_threshold)
        
        for result in results:
            boxes_data = result.boxes
            for i, box in enumerate(boxes_data):
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                bbox = box.xyxy[0].cpu().numpy().tolist()
                x1, y1, x2, y2 = bbox
                center = ((x1 + x2) / 2, (y1 + y2) / 2)
                
                # COCO类别: 0=person, 需要训练或使用自定义模型检测box
                # 暂时使用person检测，box需要额外处理或使用自定义权重
                if cls == 0:  # person
                    self.person_id_counter += 1
                    persons.append(Detection(
                        id=f"person_{self.person_id_counter}",
                        bbox=bbox,
                        confidence=conf,
                        class_id=cls,
                        class_name="person",
                        center=center
                    ))
        
        # 姿态估计
        pose_results = self.pose_estimator(frame, conf=0.5)
        for result in pose_results:
            if result.keypoints is not None:
                for i, kpts in enumerate(result.keypoints):
                    self.person_id_counter += 1
                    keypoints = kpts.xy.cpu().numpy()  # [17, 2]
                    conf = kpts.conf.cpu().numpy() if hasattr(kpts, 'conf') else np.ones(17)
                    keypoints_3d = np.concatenate([keypoints, conf.reshape(-1, 1)], axis=1)
                    
                    # 获取bbox
                    if result.boxes:
                        bbox = result.boxes[i].xyxy[0].cpu().numpy().tolist()
                    else:
                        bbox = [0, 0, 0, 0]
                    
                    poses.append(Pose(
                        id=f"person_{self.person_id_counter}",
                        keypoints=keypoints_3d,
                        bbox=bbox,
                        confidence=float(result.boxes[i].conf[0]) if result.boxes else 0.5
                    ))
        
        return persons, poses
    
    def detect_boxes(self, frame: np.ndarray) -> List[Detection]:
        """
        检测箱子 - 需要自定义训练或使用特定模型
        临时方案：使用颜色/形状检测或人工标注初始化
        """
        # TODO: 实现箱子检测逻辑
        # 方案1: 使用预训练的box检测模型
        # 方案2: 使用背景减除 + 轮廓检测
        # 方案3: 用户手动标注初始位置
        return []

# 17个关键点索引 (COCO格式)
POSE_KEYPOINTS = {
    'nose': 0,
    'left_eye': 1,
    'right_eye': 2,
    'left_ear': 3,
    'right_ear': 4,
    'left_shoulder': 5,
    'right_shoulder': 6,
    'left_elbow': 7,
    'right_elbow': 8,
    'left_wrist': 9,
    'right_wrist': 10,
    'left_hip': 11,
    'right_hip': 12,
    'left_knee': 13,
    'right_knee': 14,
    'left_ankle': 15,
    'right_ankle': 16
}
```

**Step 2: Commit**

```bash
git add backend/app/core/detector.py
git commit -m "feat: add YOLO detector and pose estimator"
```

### Task 4: 实现区域管理和工具函数

**Files:**
- Create: `backend/app/core/zone_manager.py`
- Create: `backend/app/utils/__init__.py`
- Create: `backend/app/utils/helpers.py`

**Step 1: 创建区域管理器 zone_manager.py**

```python
from typing import List, Dict, Tuple
from app.config.manager import config_manager
from app.config.models import Zone

class ZoneManager:
    def __init__(self):
        self.zones = []
        self._load_zones()
    
    def _load_zones(self):
        self.zones = config_manager.get_config().zones
    
    def reload(self):
        self._load_zones()
    
    def get_zone_at_point(self, point: Tuple[float, float]) -> Optional[Zone]:
        """判断点是否在哪个区域内"""
        for zone in self.zones:
            if self._point_in_polygon(point, zone.points):
                return zone
        return None
    
    def _point_in_polygon(self, point: Tuple[float, float], polygon: List[List[int]]) -> bool:
        """射线法判断点是否在多边形内"""
        x, y = point
        n = len(polygon)
        inside = False
        
        p1x, p1y = polygon[0]
        for i in range(n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        
        return inside
    
    def get_all_zones(self) -> List[Zone]:
        return self.zones

zone_manager = ZoneManager()
```

**Step 2: 创建工具函数 helpers.py**

```python
import numpy as np
from typing import List, Tuple

def calculate_iou(box1: List[float], box2: List[float]) -> float:
    """计算两个边界框的IoU"""
    x1_1, y1_1, x2_1, y2_1 = box1
    x1_2, y1_2, x2_2, y2_2 = box2
    
    # 计算交集
    x1_i = max(x1_1, x1_2)
    y1_i = max(y1_1, y1_2)
    x2_i = min(x2_1, x2_2)
    y2_i = min(y2_1, y2_2)
    
    if x2_i <= x1_i or y2_i <= y1_i:
        return 0.0
    
    intersection = (x2_i - x1_i) * (y2_i - y1_i)
    
    # 计算并集
    area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
    area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
    union = area1 + area2 - intersection
    
    return intersection / union if union > 0 else 0.0

def calculate_distance(point1: Tuple[float, float], point2: Tuple[float, float]) -> float:
    """计算两点之间的欧氏距离"""
    return np.sqrt((point1[0] - point2[0])**2 + (point1[1] - point2[1])**2)

def calculate_center(bbox: List[float]) -> Tuple[float, float]:
    """计算边界框中心点"""
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2, (y1 + y2) / 2)

def calculate_velocity(positions: List[Tuple[float, float]], dt: float = 1.0) -> Tuple[float, float]:
    """计算速度 (使用最近2帧)"""
    if len(positions) < 2:
        return (0.0, 0.0)
    
    p1 = positions[-2]
    p2 = positions[-1]
    vx = (p2[0] - p1[0]) / dt
    vy = (p2[1] - p1[1]) / dt
    return (vx, vy)

def calculate_variance(values: List[float]) -> float:
    """计算方差"""
    if len(values) < 2:
        return 0.0
    return np.var(values)

def is_hands_below_hips(keypoints: np.ndarray) -> bool:
    """判断双手是否在臀部下方"""
    # 关键点索引
    LEFT_WRIST = 9
    RIGHT_WRIST = 10
    LEFT_HIP = 11
    RIGHT_HIP = 12
    
    left_wrist_y = keypoints[LEFT_WRIST, 1]
    right_wrist_y = keypoints[RIGHT_WRIST, 1]
    left_hip_y = keypoints[LEFT_HIP, 1]
    right_hip_y = keypoints[RIGHT_HIP, 1]
    
    avg_wrist_y = (left_wrist_y + right_wrist_y) / 2
    avg_hip_y = (left_hip_y + right_hip_y) / 2
    
    return avg_wrist_y > avg_hip_y

def calculate_hands_distance(keypoints: np.ndarray) -> float:
    """计算双手之间的距离"""
    LEFT_WRIST = 9
    RIGHT_WRIST = 10
    
    left_wrist = keypoints[LEFT_WRIST, :2]
    right_wrist = keypoints[RIGHT_WRIST, :2]
    
    return calculate_distance(tuple(left_wrist), tuple(right_wrist))

def is_carrying_pose(keypoints: np.ndarray, params: dict) -> bool:
    """判断是否为搬运姿态"""
    # 检查手是否在臀部下方
    hands_below = is_hands_below_hips(keypoints)
    
    # 检查双手距离是否小于阈值（环抱）
    hands_dist = calculate_hands_distance(keypoints)
    hands_close = hands_dist < params.get('hands_distance_threshold', 150)
    
    return hands_below and hands_close
```

**Step 3: Commit**

```bash
git add backend/app/core/zone_manager.py backend/app/utils/
git commit -m "feat: add zone manager and helper functions"
```

### Task 5: 实现卡尔曼滤波和状态机

**Files:**
- Create: `backend/app/core/kalman.py`
- Create: `backend/app/core/state_machine.py`

**Step 1: 创建卡尔曼滤波器 kalman.py**

```python
import numpy as np
from filterpy.kalman import KalmanFilter

class BoxKalmanFilter:
    """用于箱子跟踪的卡尔曼滤波器"""
    
    def __init__(self):
        # 状态: [x, y, vx, vy]
        # 观测: [x, y]
        self.kf = KalmanFilter(dim_x=4, dim_z=2)
        
        # 状态转移矩阵
        self.kf.F = np.array([
            [1, 0, 1, 0],
            [0, 1, 0, 1],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ])
        
        # 观测矩阵
        self.kf.H = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0]
        ])
        
        # 观测噪声
        self.kf.R *= 10
        
        # 初始协方差
        self.kf.P *= 100
        
        # 过程噪声
        self.kf.Q *= 0.1
        
        self.initialized = False
    
    def init(self, x: float, y: float):
        """初始化滤波器"""
        self.kf.x = np.array([x, y, 0, 0])
        self.initialized = True
    
    def predict(self) -> Tuple[float, float]:
        """预测下一状态"""
        if not self.initialized:
            return (0, 0)
        self.kf.predict()
        return (self.kf.x[0], self.kf.x[1])
    
    def update(self, x: float, y: float):
        """更新状态"""
        if not self.initialized:
            self.init(x, y)
        else:
            self.kf.update(np.array([x, y]))
    
    def get_position(self) -> Tuple[float, float]:
        """获取当前位置"""
        return (self.kf.x[0], self.kf.x[1])
    
    def get_velocity(self) -> Tuple[float, float]:
        """获取当前速度"""
        return (self.kf.x[2], self.kf.x[3])
```

**Step 2: 创建状态机 state_machine.py**

```python
from enum import Enum
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime
import json

class PersonState(Enum):
    IDLE = "idle"
    CARRYING = "carrying"
    OCCLUDED = "occluded"

@dataclass
class PersonStateData:
    person_id: str
    state: PersonState
    origin_zone: Optional[str] = None
    locked_box_id: Optional[str] = None
    last_update: datetime = field(default_factory=datetime.now)
    occlusion_start: Optional[datetime] = None
    position_history: List[Dict] = field(default_factory=list)
    frame_count: int = 0  # 用于防抖计数

class StateMachine:
    """人员搬运状态机"""
    
    def __init__(self):
        self.persons: Dict[str, PersonStateData] = {}
    
    def get_person_state(self, person_id: str) -> Optional[PersonStateData]:
        """获取人员状态"""
        return self.persons.get(person_id)
    
    def transition_to_carrying(self, person_id: str, origin_zone: str, 
                                locked_box_id: str) -> bool:
        """状态转换: IDLE -> CARRYING"""
        if person_id not in self.persons:
            self.persons[person_id] = PersonStateData(
                person_id=person_id,
                state=PersonState.IDLE
            )
        
        person = self.persons[person_id]
        
        if person.state == PersonState.IDLE:
            person.state = PersonState.CARRYING
            person.origin_zone = origin_zone
            person.locked_box_id = locked_box_id
            person.last_update = datetime.now()
            return True
        
        return False
    
    def transition_to_occluded(self, person_id: str) -> bool:
        """状态转换: CARRYING -> OCCLUDED"""
        person = self.persons.get(person_id)
        if person and person.state == PersonState.CARRYING:
            person.state = PersonState.OCCLUDED
            person.occlusion_start = datetime.now()
            person.last_update = datetime.now()
            return True
        return False
    
    def transition_from_occluded(self, person_id: str) -> bool:
        """状态转换: OCCLUDED -> CARRYING"""
        person = self.persons.get(person_id)
        if person and person.state == PersonState.OCCLUDED:
            person.state = PersonState.CARRYING
            person.occlusion_start = None
            person.last_update = datetime.now()
            return True
        return False
    
    def transition_to_idle(self, person_id: str, drop_zone: str) -> Optional[Dict]:
        """状态转换: CARRYING/OCCLUDED -> IDLE，返回违规事件数据"""
        person = self.persons.get(person_id)
        if not person:
            return None
        
        if person.state in [PersonState.CARRYING, PersonState.OCCLUDED]:
            # 记录可能的违规
            violation_data = None
            if person.origin_zone and person.origin_zone != drop_zone:
                violation_data = {
                    "person_id": person_id,
                    "origin_zone": person.origin_zone,
                    "drop_zone": drop_zone,
                    "box_id": person.locked_box_id,
                    "trajectory": person.position_history.copy()
                }
            
            # 重置状态
            person.state = PersonState.IDLE
            person.origin_zone = None
            person.locked_box_id = None
            person.occlusion_start = None
            person.position_history = []
            person.frame_count = 0
            person.last_update = datetime.now()
            
            return violation_data
        
        return None
    
    def update_position(self, person_id: str, position: tuple, zone: Optional[str]):
        """更新人员位置历史"""
        if person_id not in self.persons:
            self.persons[person_id] = PersonStateData(
                person_id=person_id,
                state=PersonState.IDLE
            )
        
        person = self.persons[person_id]
        person.position_history.append({
            "position": position,
            "zone": zone,
            "timestamp": datetime.now().isoformat()
        })
        
        # 保持最近100个位置记录
        if len(person.position_history) > 100:
            person.position_history = person.position_history[-100:]
    
    def check_occlusion_timeout(self, person_id: str, timeout_seconds: int = 5) -> bool:
        """检查遮挡是否超时"""
        person = self.persons.get(person_id)
        if not person or person.state != PersonState.OCCLUDED:
            return False
        
        if person.occlusion_start:
            elapsed = (datetime.now() - person.occlusion_start).total_seconds()
            return elapsed > timeout_seconds
        
        return False
    
    def increment_frame_count(self, person_id: str) -> int:
        """增加帧计数"""
        if person_id not in self.persons:
            self.persons[person_id] = PersonStateData(
                person_id=person_id,
                state=PersonState.IDLE
            )
        self.persons[person_id].frame_count += 1
        return self.persons[person_id].frame_count
    
    def reset_frame_count(self, person_id: str):
        """重置帧计数"""
        if person_id in self.persons:
            self.persons[person_id].frame_count = 0
```

**Step 3: Commit**

```bash
git add backend/app/core/kalman.py backend/app/core/state_machine.py
git commit -m "feat: add Kalman filter and state machine"
```

---

## 阶段四：Redis和RabbitMQ服务

### Task 6: 实现Redis客户端

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/redis_client.py`

**Step 1: 创建Redis客户端 redis_client.py**

```python
import redis
import json
from typing import Optional, Dict
from datetime import datetime
from app.config.manager import config_manager

class RedisClient:
    """Redis客户端 - 用于运行时状态缓存"""
    
    def __init__(self):
        config = config_manager.get_config().redis
        self.client = redis.Redis(
            host=config.host,
            port=config.port,
            db=config.db,
            decode_responses=True
        )
    
    def save_person_state(self, person_id: str, state_data: Dict):
        """保存人员状态到Redis"""
        key = f"person:{person_id}"
        state_data['last_update'] = datetime.now().isoformat()
        self.client.setex(key, 3600, json.dumps(state_data))  # 1小时过期
    
    def get_person_state(self, person_id: str) -> Optional[Dict]:
        """从Redis获取人员状态"""
        key = f"person:{person_id}"
        data = self.client.get(key)
        if data:
            return json.loads(data)
        return None
    
    def delete_person_state(self, person_id: str):
        """删除人员状态"""
        key = f"person:{person_id}"
        self.client.delete(key)
    
    def save_box_state(self, box_id: str, state_data: Dict):
        """保存箱子状态到Redis"""
        key = f"box:{box_id}"
        state_data['last_update'] = datetime.now().isoformat()
        self.client.setex(key, 3600, json.dumps(state_data))
    
    def get_box_state(self, box_id: str) -> Optional[Dict]:
        """从Redis获取箱子状态"""
        key = f"box:{box_id}"
        data = self.client.get(key)
        if data:
            return json.loads(data)
        return None
    
    def save_frame_cache(self, camera_id: str, frame_data: bytes, timestamp: float):
        """保存帧缓存用于提取片段"""
        key = f"frame:{camera_id}:{int(timestamp * 1000)}"
        self.client.setex(key, 10, frame_data)  # 10秒过期
    
    def get_system_status(self) -> Dict:
        """获取系统状态"""
        return {
            "connected": self.client.ping(),
            "persons_tracked": len(self.client.keys("person:*")),
            "boxes_tracked": len(self.client.keys("box:*"))
        }

redis_client = RedisClient()
```

**Step 2: Commit**

```bash
git add backend/app/services/redis_client.py
git commit -m "feat: add Redis client for state caching"
```

### Task 7: 实现RabbitMQ客户端

**Files:**
- Create: `backend/app/services/rabbitmq_client.py`

**Step 1: 创建RabbitMQ客户端 rabbitmq_client.py**

```python
import pika
import json
from datetime import datetime
from typing import Dict
from app.config.manager import config_manager

class RabbitMQClient:
    """RabbitMQ客户端 - 用于违规告警推送"""
    
    def __init__(self):
        config = config_manager.get_config().rabbitmq
        self.config = config
        self.connection = None
        self.channel = None
        self._connect()
    
    def _connect(self):
        """建立连接"""
        try:
            credentials = pika.PlainCredentials(
                self.config.username,
                self.config.password
            )
            parameters = pika.ConnectionParameters(
                host=self.config.host,
                port=self.config.port,
                credentials=credentials
            )
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            self.channel.queue_declare(queue=self.config.queue, durable=True)
            print(f"[RabbitMQ] Connected to {self.config.host}:{self.config.port}")
        except Exception as e:
            print(f"[RabbitMQ] Connection failed: {e}")
            self.connection = None
    
    def publish_violation(self, violation_data: Dict):
        """发布违规告警"""
        if not self.connection or self.connection.is_closed:
            self._connect()
        
        if not self.connection:
            print("[RabbitMQ] Cannot publish, not connected")
            return False
        
        message = {
            "event_type": "violation",
            "timestamp": datetime.now().isoformat(),
            "camera_id": violation_data.get("camera_id", "unknown"),
            "person_id": violation_data.get("person_id"),
            "box_id": violation_data.get("box_id"),
            "origin_zone": violation_data.get("origin_zone"),
            "drop_zone": violation_data.get("drop_zone"),
            "trajectory": violation_data.get("trajectory", []),
            "confidence": violation_data.get("confidence", 1.0)
        }
        
        try:
            self.channel.basic_publish(
                exchange='',
                routing_key=self.config.queue,
                body=json.dumps(message, ensure_ascii=False),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # 持久化
                    content_type='application/json'
                )
            )
            print(f"[RabbitMQ] Published violation: {message['person_id']}")
            return True
        except Exception as e:
            print(f"[RabbitMQ] Publish failed: {e}")
            return False
    
    def close(self):
        """关闭连接"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()

rabbitmq_client = RabbitMQClient()
```

**Step 2: Commit**

```bash
git add backend/app/services/rabbitmq_client.py
git commit -m "feat: add RabbitMQ client for violation alerts"
```

---

## 阶段五：违规检测引擎

### Task 8: 实现违规检测器

**Files:**
- Create: `backend/app/core/violation_checker.py`

**Step 1: 创建违规检测器 violation_checker.py**

```python
import numpy as np
from typing import List, Tuple, Optional, Dict
from datetime import datetime
from dataclasses import dataclass

from app.core.detector import Detection, Pose
from app.core.state_machine import StateMachine, PersonState
from app.core.zone_manager import zone_manager
from app.core.kalman import BoxKalmanFilter
from app.utils.helpers import (
    calculate_iou, calculate_distance, is_carrying_pose,
    calculate_velocity, calculate_variance, calculate_center
)
from app.config.manager import config_manager

@dataclass
class LiftEvent:
    person_id: str
    box_id: str
    origin_zone: str
    timestamp: datetime

@dataclass
class DropEvent:
    person_id: str
    drop_zone: str
    timestamp: datetime
    is_violation: bool = False
    origin_zone: Optional[str] = None

class ViolationChecker:
    """违规检测器 - 核心逻辑"""
    
    def __init__(self):
        self.state_machine = StateMachine()
        self.box_trackers: Dict[str, BoxKalmanFilter] = {}
        self.box_positions: Dict[str, List[Tuple[float, float]]] = {}
        self.last_frame_data = {}
        self.config = config_manager.get_config()
        self.frame_buffer = {}  # person_id -> consecutive_frames_count
    
    def process_frame(self, persons: List[Detection], poses: List[Pose], 
                     boxes: List[Detection], camera_id: str = "default") -> List[Dict]:
        """
        处理一帧数据，检测违规
        返回违规事件列表
        """
        violations = []
        current_time = datetime.now()
        
        # 更新箱子跟踪
        self._update_box_tracking(boxes)
        
        # 处理每个人
        for person in persons:
            person_id = person.id
            person_center = person.center
            
            # 查找对应姿态
            pose = self._find_pose_for_person(person, poses)
            
            # 获取当前区域
            current_zone = zone_manager.get_zone_at_point(person_center)
            current_zone_id = current_zone.id if current_zone else None
            
            # 更新位置历史
            self.state_machine.update_position(person_id, person_center, current_zone_id)
            
            # 获取人员状态
            person_state = self.state_machine.get_person_state(person_id)
            
            if person_state is None or person_state.state == PersonState.IDLE:
                # 尝试检测搬起事件
                lift_event = self._detect_lift_event(person, pose, boxes, current_zone_id)
                if lift_event:
                    self.state_machine.transition_to_carrying(
                        person_id, 
                        lift_event.origin_zone,
                        lift_event.box_id
                    )
                    print(f"[LIFT] Person {person_id} lifted box {lift_event.box_id} from {lift_event.origin_zone}")
            
            elif person_state.state == PersonState.CARRYING:
                # 检查是否遮挡
                if self._is_occluded(person, boxes, person_state.locked_box_id):
                    self.state_machine.transition_to_occluded(person_id)
                    print(f"[OCCLUSION] Person {person_id} occluded")
                else:
                    # 检查是否放下
                    drop_event = self._detect_drop_event(person, pose, boxes, person_state)
                    if drop_event:
                        violation_data = self.state_machine.transition_to_idle(person_id, drop_event.drop_zone)
                        if violation_data:
                            violation_data['camera_id'] = camera_id
                            violation_data['confidence'] = 0.9
                            violations.append(violation_data)
                            print(f"[VIOLATION] Person {person_id}: {violation_data['origin_zone']} -> {drop_event.drop_zone}")
            
            elif person_state.state == PersonState.OCCLUDED:
                # 检查遮挡超时
                if self.state_machine.check_occlusion_timeout(person_id, 
                    self.config.detection_params.drop_detection.occlusion_timeout):
                    # 超时强制放下
                    violation_data = self.state_machine.transition_to_idle(person_id, current_zone_id)
                    if violation_data:
                        violation_data['camera_id'] = camera_id
                        violations.append(violation_data)
                        print(f"[VIOLATION-TIMEOUT] Person {person_id}: {violation_data['origin_zone']} -> {current_zone_id}")
                else:
                    # 尝试重识别箱子
                    if self._reidentify_box(person, boxes, person_state.locked_box_id):
                        self.state_machine.transition_from_occluded(person_id)
                        print(f"[REIDENTIFY] Person {person_id} box reidentified")
                    else:
                        # 检查是否放下（通过姿态）
                        drop_event = self._detect_drop_by_pose_only(person, pose, current_zone_id)
                        if drop_event:
                            violation_data = self.state_machine.transition_to_idle(person_id, drop_event.drop_zone)
                            if violation_data:
                                violation_data['camera_id'] = camera_id
                                violations.append(violation_data)
        
        self.last_frame_data = {
            'persons': persons,
            'poses': poses,
            'boxes': boxes
        }
        
        return violations
    
    def _find_pose_for_person(self, person: Detection, poses: List[Pose]) -> Optional[Pose]:
        """为人员找到对应的姿态"""
        person_center = calculate_center(person.bbox)
        best_pose = None
        min_distance = float('inf')
        
        for pose in poses:
            pose_center = calculate_center(pose.bbox)
            dist = calculate_distance(person_center, pose_center)
            if dist < min_distance and dist < 100:  # 100像素阈值
                min_distance = dist
                best_pose = pose
        
        return best_pose
    
    def _update_box_tracking(self, boxes: List[Detection]):
        """更新箱子跟踪"""
        # 为每个箱子更新卡尔曼滤波器
        for box in boxes:
            if box.id not in self.box_trackers:
                self.box_trackers[box.id] = BoxKalmanFilter()
                self.box_trackers[box.id].init(box.center[0], box.center[1])
                self.box_positions[box.id] = []
            else:
                self.box_trackers[box.id].update(box.center[0], box.center[1])
            
            self.box_positions[box.id].append(box.center)
            if len(self.box_positions[box.id]) > 10:
                self.box_positions[box.id] = self.box_positions[box.id][-10:]
    
    def _detect_lift_event(self, person: Detection, pose: Optional[Pose], 
                          boxes: List[Detection], current_zone: Optional[str]) -> Optional[LiftEvent]:
        """检测搬起事件"""
        if not pose or not current_zone:
            return None
        
        params = self.config.detection_params.lift_detection
        
        # 检查姿态
        if not is_carrying_pose(pose.keypoints, params.model_dump()):
            return None
        
        # 查找人员下方的箱子
        person_box = self._find_box_below_person(person, boxes)
        if not person_box:
            return None
        
        # 检查箱子是否在运动
        if not self._is_box_moving(person_box.id):
            return None
        
        # 防抖：需要连续多帧满足条件
        person_id = person.id
        if person_id not in self.frame_buffer:
            self.frame_buffer[person_id] = 0
        
        self.frame_buffer[person_id] += 1
        
        if self.frame_buffer[person_id] >= params.consecutive_frames:
            self.frame_buffer[person_id] = 0
            return LiftEvent(
                person_id=person_id,
                box_id=person_box.id,
                origin_zone=current_zone,
                timestamp=datetime.now()
            )
        
        return None
    
    def _detect_drop_event(self, person: Detection, pose: Optional[Pose],
                          boxes: List[Detection], person_state) -> Optional[DropEvent]:
        """检测放下事件"""
        if not pose:
            return None
        
        params = self.config.detection_params.drop_detection
        current_zone = zone_manager.get_zone_at_point(person.center)
        current_zone_id = current_zone.id if current_zone else None
        
        # 方法1: 通过姿态检测（手快速上升且张开）
        if self._detect_drop_by_pose(pose, params):
            return DropEvent(
                person_id=person.id,
                drop_zone=current_zone_id,
                timestamp=datetime.now()
            )
        
        # 方法2: 通过IoU检测（人箱分离）
        locked_box = self._find_box_by_id(boxes, person_state.locked_box_id)
        if locked_box:
            iou = calculate_iou(person.bbox, locked_box.bbox)
            if iou < params.iou_drop_threshold:
                return DropEvent(
                    person_id=person.id,
                    drop_zone=current_zone_id,
                    timestamp=datetime.now()
                )
        
        return None
    
    def _detect_drop_by_pose_only(self, person: Detection, pose: Optional[Pose],
                                   current_zone_id: Optional[str]) -> Optional[DropEvent]:
        """仅通过姿态检测放下（用于遮挡期间）"""
        if not pose:
            return None
        
        params = self.config.detection_params.drop_detection
        
        if self._detect_drop_by_pose(pose, params):
            return DropEvent(
                person_id=person.id,
                drop_zone=current_zone_id,
                timestamp=datetime.now()
            )
        
        return None
    
    def _detect_drop_by_pose(self, pose: Pose, params) -> bool:
        """通过姿态判断是否为放下动作"""
        # 获取手腕位置
        left_wrist = pose.keypoints[9, :2]
        right_wrist = pose.keypoints[10, :2]
        
        # 检查双手是否快速上升
        # 这里需要历史数据，简化处理：检查手是否在臀部上方且距离较大
        left_hip = pose.keypoints[11, :2]
        right_hip = pose.keypoints[12, :2]
        avg_hip_y = (left_hip[1] + right_hip[1]) / 2
        
        avg_wrist_y = (left_wrist[1] + right_wrist[1]) / 2
        hands_distance = calculate_distance(tuple(left_wrist), tuple(right_wrist))
        
        # 手在臀部上方且距离大于阈值（张开）
        hands_up = avg_wrist_y < avg_hip_y - params.hands_rise_threshold
        hands_open = hands_distance > 200  # 双手张开的阈值
        
        return hands_up and hands_open
    
    def _find_box_below_person(self, person: Detection, boxes: List[Detection]) -> Optional[Detection]:
        """查找人员下方的箱子"""
        person_center = person.center
        best_box = None
        min_distance = float('inf')
        
        for box in boxes:
            # 检查箱子是否在人员下方（y坐标更大）
            if box.center[1] > person_center[1]:
                dist = calculate_distance(person_center, box.center)
                if dist < min_distance and dist < 150:  # 150像素阈值
                    min_distance = dist
                    best_box = box
        
        return best_box
    
    def _find_box_by_id(self, boxes: List[Detection], box_id: str) -> Optional[Detection]:
        """通过ID查找箱子"""
        for box in boxes:
            if box.id == box_id:
                return box
        return None
    
    def _is_box_moving(self, box_id: str) -> bool:
        """判断箱子是否在运动"""
        if box_id not in self.box_positions:
            return False
        
        positions = self.box_positions[box_id]
        if len(positions) < 2:
            return False
        
        # 计算速度方差
        velocities = []
        for i in range(1, len(positions)):
            vx = positions[i][0] - positions[i-1][0]
            vy = positions[i][1] - positions[i-1][1]
            velocities.append(np.sqrt(vx**2 + vy**2))
        
        variance = calculate_variance(velocities)
        threshold = self.config.detection_params.lift_detection.speed_variance_threshold
        
        return variance > threshold
    
    def _is_occluded(self, person: Detection, boxes: List[Detection], 
                    locked_box_id: str) -> bool:
        """检查箱子是否被遮挡"""
        # 检查锁定的箱子是否还在检测列表中
        for box in boxes:
            if box.id == locked_box_id:
                # 箱子还在，检查IoU是否显著降低
                iou = calculate_iou(person.bbox, box.bbox)
                return iou < 0.1  # IoU很低说明被遮挡
        
        # 箱子完全丢失
        return True
    
    def _reidentify_box(self, person: Detection, boxes: List[Detection],
                       locked_box_id: str) -> bool:
        """重识别箱子"""
        if locked_box_id not in self.box_trackers:
            return False
        
        # 预测箱子位置
        predicted_pos = self.box_trackers[locked_box_id].predict()
        
        # 查找最接近预测的箱子
        for box in boxes:
            dist = calculate_distance(predicted_pos, box.center)
            if dist < 100:  # 100像素匹配阈值
                # 更新箱子ID为锁定ID
                box.id = locked_box_id
                self.box_trackers[locked_box_id].update(box.center[0], box.center[1])
                return True
        
        return False
```

**Step 2: Commit**

```bash
git add backend/app/core/violation_checker.py
git commit -m "feat: add violation checker with lift/drop detection"
```

---

## 阶段六：视频流处理和主程序

### Task 9: 实现视频流处理器

**Files:**
- Create: `backend/app/services/video_stream.py`

**Step 1: 创建视频流处理器 video_stream.py**

```python
import cv2
import numpy as np
import threading
import time
from typing import Callable, Optional
from datetime import datetime

class VideoStream:
    """视频流处理器"""
    
    def __init__(self, source: str, camera_id: str, frame_callback: Optional[Callable] = None):
        self.source = source
        self.camera_id = camera_id
        self.frame_callback = frame_callback
        self.cap = None
        self.running = False
        self.thread = None
        self.fps = 0
        self.frame_count = 0
        self.last_fps_time = time.time()
    
    def start(self):
        """启动视频流"""
        self.cap = cv2.VideoCapture(self.source)
        if not self.cap.isOpened():
            raise Exception(f"Cannot open video source: {self.source}")
        
        self.running = True
        self.thread = threading.Thread(target=self._process_frames)
        self.thread.start()
        print(f"[VideoStream] Started camera {self.camera_id}")
    
    def _process_frames(self):
        """处理视频帧"""
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                # 视频结束或读取失败，循环播放（本地视频）或重连（RTSP）
                if isinstance(self.source, str) and self.source.endswith(('.mp4', '.avi', '.mkv')):
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # 循环播放
                    continue
                else:
                    time.sleep(0.1)
                    continue
            
            self.frame_count += 1
            
            # 计算FPS
            current_time = time.time()
            if current_time - self.last_fps_time >= 1.0:
                self.fps = self.frame_count
                self.frame_count = 0
                self.last_fps_time = current_time
            
            # 回调处理
            if self.frame_callback:
                try:
                    self.frame_callback(frame, self.camera_id)
                except Exception as e:
                    print(f"[VideoStream] Frame callback error: {e}")
            
            # 控制帧率
            time.sleep(0.033)  # ~30fps
    
    def stop(self):
        """停止视频流"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.cap:
            self.cap.release()
        print(f"[VideoStream] Stopped camera {self.camera_id}")
    
    def get_fps(self) -> int:
        """获取当前FPS"""
        return self.fps

class StreamManager:
    """视频流管理器"""
    
    def __init__(self):
        self.streams: dict[str, VideoStream] = {}
    
    def add_stream(self, camera_id: str, source: str, frame_callback: Callable):
        """添加视频流"""
        if camera_id in self.streams:
            self.streams[camera_id].stop()
        
        stream = VideoStream(source, camera_id, frame_callback)
        self.streams[camera_id] = stream
        return stream
    
    def start_stream(self, camera_id: str):
        """启动指定视频流"""
        if camera_id in self.streams:
            self.streams[camera_id].start()
    
    def stop_stream(self, camera_id: str):
        """停止指定视频流"""
        if camera_id in self.streams:
            self.streams[camera_id].stop()
    
    def stop_all(self):
        """停止所有视频流"""
        for stream in self.streams.values():
            stream.stop()
        self.streams.clear()
    
    def get_status(self) -> dict:
        """获取所有流状态"""
        return {
            camera_id: {
                "running": stream.running,
                "fps": stream.fps
            }
            for camera_id, stream in self.streams.items()
        }

stream_manager = StreamManager()
```

**Step 2: Commit**

```bash
git add backend/app/services/video_stream.py
git commit -m "feat: add video stream processor"
```

### Task 10: 实现监控API和主程序集成

**Files:**
- Create: `backend/app/api/monitor.py`
- Modify: `backend/app/main.py`
- Create: `backend/run.py`

**Step 1: 创建监控API monitor.py**

```python
from fastapi import APIRouter, HTTPException
from typing import Dict, List
from app.services.video_stream import stream_manager
from app.services.redis_client import redis_client
from app.services.rabbitmq_client import rabbitmq_client
from app.config.manager import config_manager
from app.core.detector import YOLODetector
from app.core.violation_checker import ViolationChecker
from app.core.zone_manager import zone_manager
import cv2
import numpy as np

router = APIRouter(prefix="/api/monitor", tags=["monitor"])

# 全局检测器和违规检查器
detector: YOLODetector = None
violation_checker: ViolationChecker = None

def init_detector():
    """初始化检测器"""
    global detector, violation_checker
    if detector is None:
        detector = YOLODetector()
        violation_checker = ViolationChecker()

@router.post("/start")
async def start_monitoring():
    """启动监控"""
    global detector, violation_checker
    
    init_detector()
    zone_manager.reload()
    
    config = config_manager.get_config()
    
    # 为每个启用的摄像头启动流
    for camera in config.cameras:
        if camera.enabled:
            def frame_callback(frame, camera_id=camera.id):
                process_frame(frame, camera_id)
            
            stream = stream_manager.add_stream(camera.id, camera.source, frame_callback)
            stream.start()
    
    return {"message": "Monitoring started", "cameras": len(config.cameras)}

@router.post("/stop")
async def stop_monitoring():
    """停止监控"""
    stream_manager.stop_all()
    return {"message": "Monitoring stopped"}

@router.get("/status")
async def get_status():
    """获取监控状态"""
    return {
        "streams": stream_manager.get_status(),
        "redis": redis_client.get_system_status()
    }

def process_frame(frame: np.ndarray, camera_id: str):
    """处理单帧"""
    global detector, violation_checker
    
    if detector is None or violation_checker is None:
        return
    
    try:
        # 检测人员和姿态
        persons, poses = detector.detect(frame)
        
        # 检测箱子（暂时为空，需要自定义实现）
        boxes = []
        
        # 检查违规
        violations = violation_checker.process_frame(persons, poses, boxes, camera_id)
        
        # 发送违规告警
        for violation in violations:
            rabbitmq_client.publish_violation(violation)
    
    except Exception as e:
        print(f"[ProcessFrame] Error: {e}")

@router.get("/test-frame")
async def test_frame(camera_id: str = "test"):
    """测试单帧处理"""
    init_detector()
    
    # 创建测试帧
    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    
    # 处理
    persons, poses = detector.detect(frame)
    
    return {
        "persons_detected": len(persons),
        "poses_detected": len(poses),
        "camera_id": camera_id
    }
```

**Step 2: 更新 main.py**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import config, zones, rules, monitor
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    print("[Main] Starting up...")
    yield
    # 关闭时
    print("[Main] Shutting down...")
    from app.services.video_stream import stream_manager
    from app.services.rabbitmq_client import rabbitmq_client
    stream_manager.stop_all()
    rabbitmq_client.close()

app = FastAPI(
    title="仓库违规检测系统",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(config.router)
app.include_router(zones.router)
app.include_router(rules.router)
app.include_router(monitor.router)

@app.get("/")
async def root():
    return {"message": "仓库违规检测系统API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

**Step 3: 创建启动脚本 run.py**

```python
#!/usr/bin/env python3
"""
仓库违规检测系统启动脚本
"""

import uvicorn
import os
import sys

def main():
    """主函数"""
    # 确保工作目录正确
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # 启动FastAPI服务
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

if __name__ == "__main__":
    main()
```

**Step 4: Commit**

```bash
git add backend/
git commit -m "feat: add monitoring API and integrate all components"
```

---

## 阶段七：前端开发

### Task 11: 创建前端基础结构

**Files:**
- Create: `frontend/src/main.js`
- Create: `frontend/src/App.vue`
- Create: `frontend/src/router/index.js`
- Create: `frontend/src/stores/config.js`
- Create: `frontend/index.html`

**Step 1: 创建 index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>仓库违规检测系统</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
```

**Step 2: 创建 main.js**

```javascript
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'

const app = createApp(App)

// 注册所有图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus)

app.mount('#app')
```

**Step 3: 创建路由 router/index.js**

```javascript
import { createRouter, createWebHistory } from 'vue-router'
import SetupWizard from '../views/SetupWizard.vue'
import Dashboard from '../views/Dashboard.vue'
import Settings from '../views/Settings.vue'

const routes = [
  {
    path: '/',
    name: 'Setup',
    component: SetupWizard
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: Dashboard
  },
  {
    path: '/settings',
    name: 'Settings',
    component: Settings
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
```

**Step 4: 创建状态管理 stores/config.js**

```javascript
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api'

export const useConfigStore = defineStore('config', () => {
  // State
  const config = ref(null)
  const zones = ref([])
  const rules = ref([])
  const cameras = ref([])
  const detectionParams = ref(null)
  const loading = ref(false)

  // Getters
  const isConfigured = computed(() => {
    return zones.value.length > 0 && rules.value.length > 0 && cameras.value.length > 0
  })

  // Actions
  async function loadConfig() {
    loading.value = true
    try {
      const response = await api.getConfig()
      config.value = response.data
      zones.value = response.data.zones || []
      rules.value = response.data.violation_rules || []
      cameras.value = response.data.cameras || []
      detectionParams.value = response.data.detection_params
    } catch (error) {
      console.error('Failed to load config:', error)
    } finally {
      loading.value = false
    }
  }

  async function saveZones(newZones) {
    try {
      await api.updateZones(newZones)
      zones.value = newZones
    } catch (error) {
      console.error('Failed to save zones:', error)
      throw error
    }
  }

  async function saveRules(newRules) {
    try {
      await api.updateRules(newRules)
      rules.value = newRules
    } catch (error) {
      console.error('Failed to save rules:', error)
      throw error
    }
  }

  async function saveCameras(newCameras) {
    try {
      await api.updateCameras(newCameras)
      cameras.value = newCameras
    } catch (error) {
      console.error('Failed to save cameras:', error)
      throw error
    }
  }

  async function saveDetectionParams(params) {
    try {
      await api.updateDetectionParams(params)
      detectionParams.value = params
    } catch (error) {
      console.error('Failed to save detection params:', error)
      throw error
    }
  }

  return {
    config,
    zones,
    rules,
    cameras,
    detectionParams,
    loading,
    isConfigured,
    loadConfig,
    saveZones,
    saveRules,
    saveCameras,
    saveDetectionParams
  }
})
```

**Step 5: 创建 API 接口 api/index.js**

```javascript
import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
})

export default {
  // Config
  getConfig: () => api.get('/config'),
  updateConfig: (config) => api.put('/config', config),
  
  // Cameras
  getCameras: () => api.get('/config/cameras'),
  updateCameras: (cameras) => api.put('/config/cameras', cameras),
  
  // Zones
  getZones: () => api.get('/config/zones'),
  updateZones: (zones) => api.put('/config/zones', zones),
  createZone: (zone) => api.post('/zones', zone),
  updateZone: (id, zone) => api.put(`/zones/${id}`, zone),
  deleteZone: (id) => api.delete(`/zones/${id}`),
  
  // Rules
  getRules: () => api.get('/config/rules'),
  updateRules: (rules) => api.put('/config/rules', rules),
  createRule: (rule) => api.post('/rules', rule),
  updateRule: (id, rule) => api.put(`/rules/${id}`, rule),
  deleteRule: (id) => api.delete(`/rules/${id}`),
  
  // Detection Params
  getDetectionParams: () => api.get('/config/detection-params'),
  updateDetectionParams: (params) => api.put('/config/detection-params', params),
  
  // Monitor
  startMonitoring: () => api.post('/monitor/start'),
  stopMonitoring: () => api.post('/monitor/stop'),
  getStatus: () => api.get('/monitor/status'),
  testFrame: (cameraId) => api.get('/monitor/test-frame', { params: { camera_id: cameraId } })
}
```

**Step 6: Commit**

```bash
git add frontend/src/
git commit -m "feat: add frontend base structure, router and state management"
```

### Task 12: 创建配置向导页面

**Files:**
- Create: `frontend/src/views/SetupWizard.vue`
- Create: `frontend/src/components/CameraConfig.vue`
- Create: `frontend/src/components/ZoneEditor.vue`

**Step 1: 创建摄像头配置组件 CameraConfig.vue**

```vue
<template>
  <div class="camera-config">
    <el-form :model="form" label-width="120px">
      <el-form-item label="摄像头名称">
        <el-input v-model="form.name" placeholder="例如：入口摄像头" />
      </el-form-item>
      
      <el-form-item label="视频源">
        <el-radio-group v-model="sourceType">
          <el-radio label="file">本地文件</el-radio>
          <el-radio label="rtsp">RTSP流</el-radio>
        </el-radio-group>
      </el-form-item>
      
      <el-form-item label="文件路径" v-if="sourceType === 'file'">
        <el-input v-model="form.source" placeholder="例如：./test_video.mp4" />
      </el-form-item>
      
      <el-form-item label="RTSP地址" v-else>
        <el-input v-model="form.source" placeholder="例如：rtsp://192.168.1.100:554/stream" />
      </el-form-item>
      
      <el-form-item label="帧率">
        <el-input-number v-model="form.fps" :min="1" :max="60" />
      </el-form-item>
      
      <el-form-item>
        <el-button type="primary" @click="addCamera">添加摄像头</el-button>
        <el-button @click="testConnection">测试连接</el-button>
      </el-form-item>
    </el-form>
    
    <el-divider />
    
    <h4>已配置摄像头</h4>
    <el-table :data="cameras" style="width: 100%">
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="source" label="视频源" show-overflow-tooltip />
      <el-table-column prop="fps" label="帧率" width="80" />
      <el-table-column label="操作" width="120">
        <template #default="{ $index }">
          <el-button type="danger" size="small" @click="removeCamera($index)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:modelValue'])

const cameras = ref([...props.modelValue])
const sourceType = ref('file')

const form = reactive({
  name: '',
  source: '',
  fps: 25,
  enabled: true
})

watch(cameras, (newVal) => {
  emit('update:modelValue', newVal)
}, { deep: true })

const addCamera = () => {
  if (!form.name || !form.source) {
    ElMessage.warning('请填写完整信息')
    return
  }
  
  cameras.value.push({
    id: `cam_${Date.now()}`,
    name: form.name,
    source: form.source,
    fps: form.fps,
    enabled: true
  })
  
  form.name = ''
  form.source = ''
  ElMessage.success('摄像头添加成功')
}

const removeCamera = (index) => {
  cameras.value.splice(index, 1)
}

const testConnection = () => {
  // 实际项目中应该调用后端API测试
  ElMessage.info('测试功能待实现')
}
</script>

<style scoped>
.camera-config {
  padding: 20px;
}
</style>
```

**Step 2: 创建区域编辑器组件 ZoneEditor.vue**

```vue
<template>
  <div class="zone-editor">
    <div class="toolbar">
      <el-button type="primary" @click="startDrawing" :disabled="isDrawing">
        <el-icon><Plus /></el-icon> 绘制区域
      </el-button>
      <el-button @click="clearDrawing" :disabled="!isDrawing">
        取消绘制
      </el-button>
      <el-button type="danger" @click="clearAll" v-if="zones.length > 0">
        清除所有
      </el-button>
      <span class="tip" v-if="isDrawing">点击画布添加顶点，双击完成绘制</span>
    </div>
    
    <div class="canvas-container" ref="containerRef">
      <canvas
        ref="canvasRef"
        @click="handleCanvasClick"
        @dblclick="handleCanvasDblClick"
        @mousemove="handleMouseMove"
      />
    </div>
    
    <div class="zone-list" v-if="zones.length > 0">
      <h4>已定义区域</h4>
      <el-table :data="zones" style="width: 100%">
        <el-table-column prop="name" label="名称">
          <template #default="{ row, $index }">
            <el-input v-model="row.name" size="small" @change="updateZones" />
          </template>
        </el-table-column>
        <el-table-column label="颜色" width="100">
          <template #default="{ row }">
            <el-color-picker v-model="row.color" size="small" @change="draw" />
          </template>
        </el-table-column>
        <el-table-column label="顶点数" width="100">
          <template #default="{ row }">
            {{ row.points.length }} 个
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ $index }">
            <el-button type="danger" size="small" @click="deleteZone($index)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => []
  },
  backgroundImage: {
    type: String,
    default: null
  }
})

const emit = defineEmits(['update:modelValue'])

const canvasRef = ref(null)
const containerRef = ref(null)
const ctx = ref(null)
const isDrawing = ref(false)
const currentPoints = ref([])
const zones = ref([...props.modelValue])
const mousePos = ref({ x: 0, y: 0 })

// 预定义颜色
const colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8', '#F7DC6F']

onMounted(() => {
  initCanvas()
  draw()
})

watch(() => props.modelValue, (newVal) => {
  zones.value = [...newVal]
  draw()
}, { deep: true })

const initCanvas = () => {
  const canvas = canvasRef.value
  const container = containerRef.value
  
  // 设置画布大小
  canvas.width = container.clientWidth
  canvas.height = 400
  
  ctx.value = canvas.getContext('2d')
}

const draw = () => {
  if (!ctx.value) return
  
  const canvas = canvasRef.value
  const context = ctx.value
  
  // 清空画布
  context.clearRect(0, 0, canvas.width, canvas.height)
  
  // 绘制背景
  context.fillStyle = '#f5f5f5'
  context.fillRect(0, 0, canvas.width, canvas.height)
  
  // 绘制网格
  drawGrid(context, canvas.width, canvas.height)
  
  // 绘制已保存的区域
  zones.value.forEach((zone, index) => {
    drawZone(context, zone.points, zone.color, zone.name, index === hoveredZoneIndex.value)
  })
  
  // 绘制正在绘制的区域
  if (isDrawing.value && currentPoints.value.length > 0) {
    drawZone(context, currentPoints.value, '#999999', '绘制中...', true)
    
    // 绘制从最后一个点到鼠标的线
    if (currentPoints.value.length > 0) {
      const lastPoint = currentPoints.value[currentPoints.value.length - 1]
      context.beginPath()
      context.moveTo(lastPoint[0], lastPoint[1])
      context.lineTo(mousePos.value.x, mousePos.value.y)
      context.strokeStyle = '#999999'
      context.setLineDash([5, 5])
      context.stroke()
      context.setLineDash([])
    }
  }
}

const drawGrid = (context, width, height) => {
  context.strokeStyle = '#e0e0e0'
  context.lineWidth = 1
  
  const gridSize = 50
  
  for (let x = 0; x <= width; x += gridSize) {
    context.beginPath()
    context.moveTo(x, 0)
    context.lineTo(x, height)
    context.stroke()
  }
  
  for (let y = 0; y <= height; y += gridSize) {
    context.beginPath()
    context.moveTo(0, y)
    context.lineTo(width, y)
    context.stroke()
  }
}

const drawZone = (context, points, color, name, isHovered) => {
  if (points.length < 3) return
  
  context.beginPath()
  context.moveTo(points[0][0], points[0][1])
  
  for (let i = 1; i < points.length; i++) {
    context.lineTo(points[i][0], points[i][1])
  }
  
  context.closePath()
  
  // 填充
  context.fillStyle = color + (isHovered ? '66' : '33')
  context.fill()
  
  // 描边
  context.strokeStyle = color
  context.lineWidth = isHovered ? 3 : 2
  context.stroke()
  
  // 绘制顶点
  points.forEach(point => {
    context.beginPath()
    context.arc(point[0], point[1], 4, 0, Math.PI * 2)
    context.fillStyle = color
    context.fill()
  })
  
  // 绘制区域名称
  if (name) {
    const center = calculateCenter(points)
    context.fillStyle = color
    context.font = 'bold 14px Arial'
    context.textAlign = 'center'
    context.fillText(name, center[0], center[1])
  }
}

const calculateCenter = (points) => {
  let sumX = 0, sumY = 0
  points.forEach(p => {
    sumX += p[0]
    sumY += p[1]
  })
  return [sumX / points.length, sumY / points.length]
}

const startDrawing = () => {
  isDrawing.value = true
  currentPoints.value = []
  ElMessage.info('点击画布添加顶点，双击完成绘制')
}

const clearDrawing = () => {
  isDrawing.value = false
  currentPoints.value = []
  draw()
}

const clearAll = () => {
  zones.value = []
  updateZones()
  draw()
}

const handleCanvasClick = (e) => {
  if (!isDrawing.value) return
  
  const rect = canvasRef.value.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top
  
  currentPoints.value.push([x, y])
  draw()
}

const handleCanvasDblClick = (e) => {
  if (!isDrawing.value || currentPoints.value.length < 3) {
    if (currentPoints.value.length < 3) {
      ElMessage.warning('至少需要3个顶点')
    }
    return
  }
  
  // 完成绘制
  const color = colors[zones.value.length % colors.length]
  zones.value.push({
    id: `zone_${Date.now()}`,
    name: `Zone_${String.fromCharCode(65 + zones.value.length)}`,
    color: color,
    points: [...currentPoints.value]
  })
  
  updateZones()
  clearDrawing()
  ElMessage.success('区域添加成功')
}

const handleMouseMove = (e) => {
  const rect = canvasRef.value.getBoundingClientRect()
  mousePos.value = {
    x: e.clientX - rect.left,
    y: e.clientY - rect.top
  }
  
  if (isDrawing.value) {
    draw()
  }
}

const deleteZone = (index) => {
  zones.value.splice(index, 1)
  updateZones()
  draw()
}

const updateZones = () => {
  emit('update:modelValue', [...zones.value])
}

const hoveredZoneIndex = ref(-1)
</script>

<style scoped>
.zone-editor {
  padding: 20px;
}

.toolbar {
  margin-bottom: 15px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.tip {
  color: #666;
  font-size: 14px;
  margin-left: 10px;
}

.canvas-container {
  border: 2px solid #dcdfe6;
  border-radius: 4px;
  overflow: hidden;
}

.zone-list {
  margin-top: 20px;
}
</style>
```

**Step 3: 创建配置向导页面 SetupWizard.vue**

```vue
<template>
  <div class="setup-wizard">
    <el-page-header @back="goBack" title="仓库违规检测系统" />
    
    <div class="wizard-content">
      <el-steps :active="activeStep" finish-status="success" simple>
        <el-step title="摄像头配置" />
        <el-step title="区域绘制" />
        <el-step title="违规规则" />
        <el-step title="参数调优" />
        <el-step title="确认启动" />
      </el-steps>
      
      <div class="step-content">
        <!-- Step 1: 摄像头配置 -->
        <div v-if="activeStep === 0">
          <h3>步骤 1: 配置摄像头</h3>
          <p class="description">添加需要监控的摄像头或视频源</p>
          <CameraConfig v-model="cameras" />
        </div>
        
        <!-- Step 2: 区域绘制 -->
        <div v-if="activeStep === 1">
          <h3>步骤 2: 绘制监控区域</h3>
          <p class="description">在画布上绘制Zone_A、Zone_B、Zone_C等区域</p>
          <ZoneEditor v-model="zones" />
        </div>
        
        <!-- Step 3: 违规规则 -->
        <div v-if="activeStep === 2">
          <h3>步骤 3: 配置违规规则</h3>
          <p class="description">定义哪些区域之间的搬运属于违规</p>
          <RuleConfig v-model="rules" :zones="zones" />
        </div>
        
        <!-- Step 4: 参数调优 -->
        <div v-if="activeStep === 3">
          <h3>步骤 4: 检测参数调优</h3>
          <p class="description">调整检测灵敏度和阈值</p>
          <ParamSettings v-model="detectionParams" />
        </div>
        
        <!-- Step 5: 确认启动 -->
        <div v-if="activeStep === 4">
          <h3>步骤 5: 确认配置</h3>
          <el-card class="summary-card">
            <template #header>
              <span>配置摘要</span>
            </template>
            
            <div class="summary-section">
              <h4>摄像头 ({{ cameras.length }})</h4>
              <el-tag v-for="cam in cameras" :key="cam.id" class="summary-tag">
                {{ cam.name }}
              </el-tag>
            </div>
            
            <div class="summary-section">
              <h4>区域 ({{ zones.length }})</h4>
              <el-tag v-for="zone in zones" :key="zone.id" 
                     class="summary-tag" :style="{ backgroundColor: zone.color }">
                {{ zone.name }}
              </el-tag>
            </div>
            
            <div class="summary-section">
              <h4>违规规则 ({{ rules.length }})</h4>
              <div v-for="rule in rules" :key="rule.id" class="rule-item">
                {{ rule.name }}: {{ getZoneName(rule.from_zone) }} → {{ getZoneName(rule.to_zone) }}
              </div>
            </div>
          </el-card>
          
          <div class="action-buttons">
            <el-button type="success" size="large" @click="startMonitoring" :loading="starting">
              <el-icon><VideoPlay /></el-icon>
              启动监控
            </el-button>
          </div>
        </div>
      </div>
      
      <div class="step-actions">
        <el-button v-if="activeStep > 0" @click="prevStep">上一步</el-button>
        <el-button v-if="activeStep < 4" type="primary" @click="nextStep" :disabled="!canProceed">
          下一步
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useConfigStore } from '../stores/config'
import api from '../api'
import CameraConfig from '../components/CameraConfig.vue'
import ZoneEditor from '../components/ZoneEditor.vue'
import RuleConfig from '../components/RuleConfig.vue'
import ParamSettings from '../components/ParamSettings.vue'

const router = useRouter()
const configStore = useConfigStore()

const activeStep = ref(0)
const starting = ref(false)

// 本地状态
const cameras = ref([])
const zones = ref([])
const rules = ref([])
const detectionParams = ref({})

onMounted(async () => {
  await configStore.loadConfig()
  cameras.value = [...configStore.cameras]
  zones.value = [...configStore.zones]
  rules.value = [...configStore.rules]
  detectionParams.value = configStore.detectionParams || {}
})

const canProceed = computed(() => {
  switch (activeStep.value) {
    case 0:
      return cameras.value.length > 0
    case 1:
      return zones.value.length >= 2
    case 2:
      return rules.value.length > 0
    case 3:
      return true
    default:
      return true
  }
})

const nextStep = async () => {
  // 保存当前步骤数据
  await saveCurrentStep()
  
  if (activeStep.value < 4) {
    activeStep.value++
  }
}

const prevStep = () => {
  if (activeStep.value > 0) {
    activeStep.value--
  }
}

const saveCurrentStep = async () => {
  try {
    switch (activeStep.value) {
      case 0:
        await configStore.saveCameras(cameras.value)
        break
      case 1:
        await configStore.saveZones(zones.value)
        break
      case 2:
        await configStore.saveRules(rules.value)
        break
      case 3:
        await configStore.saveDetectionParams(detectionParams.value)
        break
    }
  } catch (error) {
    ElMessage.error('保存失败: ' + error.message)
  }
}

const startMonitoring = async () => {
  starting.value = true
  try {
    await api.startMonitoring()
    ElMessage.success('监控已启动')
    router.push('/dashboard')
  } catch (error) {
    ElMessage.error('启动失败: ' + error.message)
  } finally {
    starting.value = false
  }
}

const getZoneName = (zoneId) => {
  const zone = zones.value.find(z => z.id === zoneId)
  return zone ? zone.name : zoneId
}

const goBack = () => {
  router.push('/')
}
</script>

<style scoped>
.setup-wizard {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.wizard-content {
  margin-top: 30px;
}

.step-content {
  margin: 30px 0;
  min-height: 400px;
}

.description {
  color: #666;
  margin-bottom: 20px;
}

.step-actions {
  display: flex;
  justify-content: center;
  gap: 20px;
  margin-top: 30px;
}

.summary-card {
  margin: 20px 0;
}

.summary-section {
  margin-bottom: 20px;
}

.summary-section h4 {
  margin-bottom: 10px;
  color: #333;
}

.summary-tag {
  margin-right: 10px;
  margin-bottom: 5px;
}

.rule-item {
  padding: 5px 0;
  border-bottom: 1px solid #eee;
}

.action-buttons {
  text-align: center;
  margin-top: 30px;
}
</style>
```

**Step 4: Commit**

```bash
git add frontend/src/components/CameraConfig.vue frontend/src/components/ZoneEditor.vue frontend/src/views/SetupWizard.vue
git commit -m "feat: add setup wizard with camera config and zone editor"
```

### Task 13: 创建规则配置和参数设置组件

**Files:**
- Create: `frontend/src/components/RuleConfig.vue`
- Create: `frontend/src/components/ParamSettings.vue`

**Step 1: 创建规则配置组件 RuleConfig.vue**

```vue
<template>
  <div class="rule-config">
    <el-form :model="form" label-width="120px">
      <el-form-item label="规则名称">
        <el-input v-model="form.name" placeholder="例如：A区到B区违规" />
      </el-form-item>
      
      <el-form-item label="起始区域">
        <el-select v-model="form.from_zone" placeholder="选择起始区域">
          <el-option
            v-for="zone in zones"
            :key="zone.id"
            :label="zone.name"
            :value="zone.id"
          />
        </el-select>
      </el-form-item>
      
      <el-form-item label="目标区域">
        <el-select v-model="form.to_zone" placeholder="选择目标区域">
          <el-option
            v-for="zone in zones"
            :key="zone.id"
            :label="zone.name"
            :value="zone.id"
          />
        </el-select>
      </el-form-item>
      
      <el-form-item>
        <el-button type="primary" @click="addRule" :disabled="!isValid">
          添加规则
        </el-button>
      </el-form-item>
    </el-form>
    
    <el-divider />
    
    <h4>已配置规则</h4>
    <el-table :data="rules" style="width: 100%">
      <el-table-column prop="name" label="规则名称" />
      <el-table-column label="违规路径">
        <template #default="{ row }">
          {{ getZoneName(row.from_zone) }} 
          <el-icon><Right /></el-icon>
          {{ getZoneName(row.to_zone) }}
        </template>
      </el-table-column>
      <el-table-column prop="enabled" label="状态" width="100">
        <template #default="{ row }">
          <el-switch v-model="row.enabled" @change="updateRules" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ $index }">
          <el-button type="danger" size="small" @click="removeRule($index)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => []
  },
  zones: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:modelValue'])

const rules = ref([...props.modelValue])

const form = reactive({
  name: '',
  from_zone: '',
  to_zone: '',
  enabled: true
})

const isValid = computed(() => {
  return form.name && form.from_zone && form.to_zone && form.from_zone !== form.to_zone
})

watch(rules, (newVal) => {
  emit('update:modelValue', [...newVal])
}, { deep: true })

const addRule = () => {
  if (form.from_zone === form.to_zone) {
    ElMessage.warning('起始区域和目标区域不能相同')
    return
  }
  
  rules.value.push({
    id: `rule_${Date.now()}`,
    name: form.name,
    from_zone: form.from_zone,
    to_zone: form.to_zone,
    enabled: true
  })
  
  form.name = ''
  form.from_zone = ''
  form.to_zone = ''
  ElMessage.success('规则添加成功')
}

const removeRule = (index) => {
  rules.value.splice(index, 1)
}

const updateRules = () => {
  emit('update:modelValue', [...rules.value])
}

const getZoneName = (zoneId) => {
  const zone = props.zones.find(z => z.id === zoneId)
  return zone ? zone.name : zoneId
}
</script>

<style scoped>
.rule-config {
  padding: 20px;
}
</style>
```

**Step 2: 创建参数设置组件 ParamSettings.vue**

```vue
<template>
  <div class="param-settings">
    <el-tabs type="border-card">
      <el-tab-pane label="YOLO检测">
        <el-form :model="params.yolo" label-width="150px">
          <el-form-item label="模型">
            <el-select v-model="params.yolo.model">
              <el-option label="YOLOv8 Nano" value="yolov8n.pt" />
              <el-option label="YOLOv8 Small" value="yolov8s.pt" />
              <el-option label="YOLOv8 Medium" value="yolov8m.pt" />
            </el-select>
          </el-form-item>
          
          <el-form-item label="置信度阈值">
            <el-slider v-model="params.yolo.confidence" :min="0.1" :max="1" :step="0.05" show-input />
          </el-form-item>
          
          <el-form-item label="IoU阈值">
            <el-slider v-model="params.yolo.iou_threshold" :min="0.1" :max="1" :step="0.05" show-input />
          </el-form-item>
        </el-form>
      </el-tab-pane>
      
      <el-tab-pane label="搬起检测">
        <el-form :model="params.lift_detection" label-width="180px">
          <el-form-item label="双手距离阈值 (像素)">
            <el-input-number v-model="params.lift_detection.hands_distance_threshold" :min="50" :max="300" />
          </el-form-item>
          
          <el-form-item label="连续帧数 (防抖)">
            <el-input-number v-model="params.lift_detection.consecutive_frames" :min="3" :max="15" />
            <span class="hint">需要连续多少帧满足条件才触发搬起</span>
          </el-form-item>
          
          <el-form-item label="速度方差阈值">
            <el-input-number v-model="params.lift_detection.speed_variance_threshold" :min="1" :max="50" />
          </el-form-item>
        </el-form>
      </el-tab-pane>
      
      <el-tab-pane label="放下检测">
        <el-form :model="params.drop_detection" label-width="180px">
          <el-form-item label="手上升阈值 (像素)">
            <el-input-number v-model="params.drop_detection.hands_rise_threshold" :min="10" :max="100" />
          </el-form-item>
          
          <el-form-item label="IoU下降阈值">
            <el-slider v-model="params.drop_detection.iou_drop_threshold" :min="0" :max="0.5" :step="0.01" show-input />
          </el-form-item>
          
          <el-form-item label="遮挡超时 (秒)">
            <el-input-number v-model="params.drop_detection.occlusion_timeout" :min="3" :max="10" />
            <span class="hint">遮挡超过此时间强制视为放下</span>
          </el-form-item>
        </el-form>
      </el-tab-pane>
      
      <el-tab-pane label="跟踪参数">
        <el-form :model="params.tracking" label-width="150px">
          <el-form-item label="最大丢失帧数">
            <el-input-number v-model="params.tracking.max_age" :min="10" :max="100" />
          </el-form-item>
          
          <el-form-item label="最小确认帧数">
            <el-input-number v-model="params.tracking.min_hits" :min="1" :max="10" />
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { reactive, watch } from 'vue'

const props = defineProps({
  modelValue: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['update:modelValue'])

const defaultParams = {
  yolo: {
    model: 'yolov8n.pt',
    confidence: 0.5,
    iou_threshold: 0.45
  },
  pose: {
    model: 'yolov8n-pose.pt'
  },
  tracking: {
    max_age: 30,
    min_hits: 3
  },
  lift_detection: {
    hands_below_hip_threshold: 0,
    hands_distance_threshold: 150,
    consecutive_frames: 5,
    speed_variance_threshold: 10
  },
  drop_detection: {
    hands_rise_threshold: 30,
    iou_drop_threshold: 0.1,
    occlusion_timeout: 5
  }
}

const params = reactive({
  ...defaultParams,
  ...props.modelValue
})

watch(params, (newVal) => {
  emit('update:modelValue', { ...newVal })
}, { deep: true })
</script>

<style scoped>
.param-settings {
  padding: 20px;
}

.hint {
  margin-left: 10px;
  color: #909399;
  font-size: 12px;
}
</style>
```

**Step 3: Commit**

```bash
git add frontend/src/components/RuleConfig.vue frontend/src/components/ParamSettings.vue
git commit -m "feat: add rule config and parameter settings components"
```

### Task 14: 创建监控面板和主应用

**Files:**
- Create: `frontend/src/views/Dashboard.vue`
- Create: `frontend/src/components/ViolationList.vue`
- Create: `frontend/src/App.vue`

**Step 1: 创建监控面板 Dashboard.vue**

```vue
<template>
  <div class="dashboard">
    <el-page-header @back="goBack" title="监控面板">
      <template #extra>
        <el-button type="danger" @click="stopMonitoring" v-if="isRunning">
          <el-icon><VideoPause /></el-icon> 停止监控
        </el-button>
        <el-button type="primary" @click="startMonitoring" v-else>
          <el-icon><VideoPlay /></el-icon> 启动监控
        </el-button>
        <el-button @click="goToSettings">
          <el-icon><Setting /></el-icon> 设置
        </el-button>
      </template>
    </el-page-header>
    
    <div class="dashboard-content">
      <el-row :gutter="20">
        <el-col :span="16">
          <el-card class="status-card">
            <template #header>
              <span>系统状态</span>
            </template>
            <div class="status-grid">
              <div class="status-item">
                <div class="status-label">监控状态</div>
                <div class="status-value">
                  <el-tag :type="isRunning ? 'success' : 'info'">
                    {{ isRunning ? '运行中' : '已停止' }}
                  </el-tag>
                </div>
              </div>
              <div class="status-item">
                <div class="status-label">Redis连接</div>
                <div class="status-value">
                  <el-tag :type="redisStatus ? 'success' : 'danger'">
                    {{ redisStatus ? '正常' : '断开' }}
                  </el-tag>
                </div>
              </div>
              <div class="status-item">
                <div class="status-label">跟踪人员</div>
                <div class="status-value">{{ trackedPersons }}</div>
              </div>
              <div class="status-item">
                <div class="status-label">跟踪箱子</div>
                <div class="status-value">{{ trackedBoxes }}</div>
              </div>
            </div>
          </el-card>
          
          <el-card class="stream-card" v-if="isRunning">
            <template #header>
              <span>视频流</span>
            </template>
            <div class="stream-placeholder">
              <el-icon size="48"><VideoCamera /></el-icon>
              <p>视频流处理中...</p>
              <p class="hint">实时画面在后台处理，违规事件将显示在右侧</p>
            </div>
          </el-card>
        </el-col>
        
        <el-col :span="8">
          <ViolationList />
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api'
import ViolationList from '../components/ViolationList.vue'

const router = useRouter()

const isRunning = ref(false)
const redisStatus = ref(false)
const trackedPersons = ref(0)
const trackedBoxes = ref(0)
let statusInterval = null

onMounted(() => {
  checkStatus()
  statusInterval = setInterval(checkStatus, 2000)
})

onUnmounted(() => {
  if (statusInterval) {
    clearInterval(statusInterval)
  }
})

const checkStatus = async () => {
  try {
    const response = await api.getStatus()
    const status = response.data
    
    isRunning.value = Object.values(status.streams).some(s => s.running)
    redisStatus.value = status.redis.connected
    trackedPersons.value = status.redis.persons_tracked
    trackedBoxes.value = status.redis.boxes_tracked
  } catch (error) {
    console.error('Failed to get status:', error)
  }
}

const startMonitoring = async () => {
  try {
    await api.startMonitoring()
    ElMessage.success('监控已启动')
    isRunning.value = true
  } catch (error) {
    ElMessage.error('启动失败: ' + error.message)
  }
}

const stopMonitoring = async () => {
  try {
    await api.stopMonitoring()
    ElMessage.success('监控已停止')
    isRunning.value = false
  } catch (error) {
    ElMessage.error('停止失败: ' + error.message)
  }
}

const goToSettings = () => {
  router.push('/settings')
}

const goBack = () => {
  router.push('/')
}
</script>

<style scoped>
.dashboard {
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px;
}

.dashboard-content {
  margin-top: 20px;
}

.status-card, .stream-card {
  margin-bottom: 20px;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
}

.status-item {
  text-align: center;
  padding: 15px;
  background: #f5f7fa;
  border-radius: 8px;
}

.status-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}

.status-value {
  font-size: 18px;
  font-weight: bold;
}

.stream-placeholder {
  height: 300px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
  border-radius: 8px;
  color: #909399;
}

.stream-placeholder .hint {
  font-size: 12px;
  margin-top: 10px;
}
</style>
```

**Step 2: 创建违规列表组件 ViolationList.vue**

```vue
<template>
  <el-card class="violation-list">
    <template #header>
      <div class="card-header">
        <span>违规事件</span>
        <el-button size="small" @click="clearAll">清空</el-button>
      </div>
    </template>
    
    <div class="violation-items" v-if="violations.length > 0">
      <el-timeline>
        <el-timeline-item
          v-for="(violation, index) in violations"
          :key="index"
          :type="violation.type"
          :timestamp="violation.time"
          placement="top"
        >
          <el-card :class="['violation-card', violation.type]">
            <div class="violation-header">
              <el-tag :type="violation.type" size="small">
                {{ violation.type === 'danger' ? '违规' : '事件' }}
              </el-tag>
              <span class="violation-time">{{ violation.time }}</span>
            </div>
            <div class="violation-body">
              <p><strong>人员ID:</strong> {{ violation.person_id }}</p>
              <p><strong>箱子ID:</strong> {{ violation.box_id }}</p>
              <p>
                <strong>路径:</strong>
                <el-tag size="small" type="info">{{ violation.origin_zone }}</el-tag>
                <el-icon><Right /></el-icon>
                <el-tag size="small" type="danger">{{ violation.drop_zone }}</el-tag>
              </p>
            </div>
          </el-card>
        </el-timeline-item>
      </el-timeline>
    </div>
    
    <el-empty v-else description="暂无违规事件" />
  </el-card>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const violations = ref([])

// 模拟违规事件（实际应从RabbitMQ或WebSocket获取）
const addMockViolation = () => {
  const mockViolations = [
    {
      type: 'danger',
      time: new Date().toLocaleTimeString(),
      person_id: 'person_001',
      box_id: 'box_015',
      origin_zone: 'Zone_A',
      drop_zone: 'Zone_B'
    }
  ]
  violations.value = mockViolations
}

const clearAll = () => {
  violations.value = []
}

onMounted(() => {
  // 实际项目中应该连接WebSocket或定期从后端获取
  // addMockViolation()
})
</script>

<style scoped>
.violation-list {
  height: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.violation-items {
  max-height: 600px;
  overflow-y: auto;
}

.violation-card {
  margin-bottom: 10px;
}

.violation-card.danger {
  border-left: 4px solid #f56c6c;
}

.violation-card.warning {
  border-left: 4px solid #e6a23c;
}

.violation-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.violation-time {
  font-size: 12px;
  color: #909399;
}

.violation-body p {
  margin: 5px 0;
  font-size: 13px;
}
</style>
```

**Step 3: 创建设置页面 Settings.vue**

```vue
<template>
  <div class="settings">
    <el-page-header @back="goBack" title="系统设置" />
    
    <div class="settings-content">
      <el-tabs type="border-card">
        <el-tab-pane label="摄像头">
          <CameraConfig v-model="cameras" />
        </el-tab-pane>
        
        <el-tab-pane label="区域">
          <ZoneEditor v-model="zones" />
        </el-tab-pane>
        
        <el-tab-pane label="规则">
          <RuleConfig v-model="rules" :zones="zones" />
        </el-tab-pane>
        
        <el-tab-pane label="参数">
          <ParamSettings v-model="detectionParams" />
        </el-tab-pane>
      </el-tabs>
      
      <div class="actions">
        <el-button type="primary" @click="saveAll">保存所有配置</el-button>
        <el-button @click="resetConfig">重置</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useConfigStore } from '../stores/config'
import CameraConfig from '../components/CameraConfig.vue'
import ZoneEditor from '../components/ZoneEditor.vue'
import RuleConfig from '../components/RuleConfig.vue'
import ParamSettings from '../components/ParamSettings.vue'

const router = useRouter()
const configStore = useConfigStore()

const cameras = ref([])
const zones = ref([])
const rules = ref([])
const detectionParams = ref({})

onMounted(async () => {
  await configStore.loadConfig()
  cameras.value = [...configStore.cameras]
  zones.value = [...configStore.zones]
  rules.value = [...configStore.rules]
  detectionParams.value = { ...configStore.detectionParams }
})

const saveAll = async () => {
  try {
    await configStore.saveCameras(cameras.value)
    await configStore.saveZones(zones.value)
    await configStore.saveRules(rules.value)
    await configStore.saveDetectionParams(detectionParams.value)
    ElMessage.success('配置已保存')
  } catch (error) {
    ElMessage.error('保存失败: ' + error.message)
  }
}

const resetConfig = () => {
  cameras.value = [...configStore.cameras]
  zones.value = [...configStore.zones]
  rules.value = [...configStore.rules]
  detectionParams.value = { ...configStore.detectionParams }
  ElMessage.info('已重置为上次保存的配置')
}

const goBack = () => {
  router.push('/dashboard')
}
</script>

<style scoped>
.settings {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.settings-content {
  margin-top: 20px;
}

.actions {
  margin-top: 20px;
  text-align: center;
}
</style>
```

**Step 4: 更新 App.vue**

```vue
<template>
  <div id="app">
    <router-view />
  </div>
</template>

<script setup>
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB',
    'Microsoft YaHei', '微软雅黑', Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background-color: #f0f2f5;
}

#app {
  min-height: 100vh;
}
</style>
```

**Step 5: Commit**

```bash
git add frontend/src/views/Dashboard.vue frontend/src/components/ViolationList.vue frontend/src/views/Settings.vue frontend/src/App.vue
git commit -m "feat: add dashboard, violation list and settings page"
```

---

## 阶段八：测试和文档

### Task 15: 创建测试脚本和更新文档

**Files:**
- Create: `backend/test_detection.py`
- Modify: `README.md`
- Create: `docker-compose.yml`

**Step 1: 创建测试脚本 test_detection.py**

```python
#!/usr/bin/env python3
"""
仓库违规检测系统测试脚本
"""

import cv2
import numpy as np
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.detector import YOLODetector
from app.core.violation_checker import ViolationChecker
from app.core.zone_manager import zone_manager
from app.config.manager import config_manager

def test_detector():
    """测试检测器"""
    print("=" * 50)
    print("测试 YOLO 检测器")
    print("=" * 50)
    
    try:
        detector = YOLODetector()
        print("✓ 检测器初始化成功")
        
        # 创建测试图像
        test_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        
        # 测试检测
        persons, poses = detector.detect(test_frame)
        print(f"✓ 检测完成 - 人员: {len(persons)}, 姿态: {len(poses)}")
        
        return True
    except Exception as e:
        print(f"✗ 检测器测试失败: {e}")
        return False

def test_zone_manager():
    """测试区域管理器"""
    print("\n" + "=" * 50)
    print("测试区域管理器")
    print("=" * 50)
    
    try:
        # 添加测试区域
        from app.config.models import Zone
        
        zones = [
            Zone(
                id="zone_a",
                name="Zone_A",
                color="#FF6B6B",
                points=[[100, 100], [300, 100], [300, 300], [100, 300]]
            ),
            Zone(
                id="zone_b",
                name="Zone_B",
                color="#4ECDC4",
                points=[[400, 100], [600, 100], [600, 300], [400, 300]]
            )
        ]
        
        config_manager.update_zones(zones)
        zone_manager.reload()
        
        print(f"✓ 已添加 {len(zones)} 个区域")
        
        # 测试点是否在区域内
        test_point_inside = (200, 200)
        test_point_outside = (500, 500)
        
        zone_inside = zone_manager.get_zone_at_point(test_point_inside)
        zone_outside = zone_manager.get_zone_at_point(test_point_outside)
        
        print(f"✓ 点 {test_point_inside} 在区域: {zone_inside.name if zone_inside else 'None'}")
        print(f"✓ 点 {test_point_outside} 在区域: {zone_outside.name if zone_outside else 'None'}")
        
        return True
    except Exception as e:
        print(f"✗ 区域管理器测试失败: {e}")
        return False

def test_violation_checker():
    """测试违规检测器"""
    print("\n" + "=" * 50)
    print("测试违规检测器")
    print("=" * 50)
    
    try:
        checker = ViolationChecker()
        print("✓ 违规检测器初始化成功")
        
        # 测试状态机
        from app.core.state_machine import PersonState
        
        # 模拟搬起事件
        checker.state_machine.transition_to_carrying(
            "person_001", "zone_a", "box_001"
        )
        
        state = checker.state_machine.get_person_state("person_001")
        assert state.state == PersonState.CARRYING
        print(f"✓ 状态转换成功: IDLE -> CARRYING")
        
        # 模拟放下事件（违规）
        violation = checker.state_machine.transition_to_idle("person_001", "zone_b")
        assert violation is not None
        assert violation['origin_zone'] == "zone_a"
        assert violation['drop_zone'] == "zone_b"
        print(f"✓ 违规检测成功: {violation['origin_zone']} -> {violation['drop_zone']}")
        
        return True
    except Exception as e:
        print(f"✗ 违规检测器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """运行所有测试"""
    print("\n")
    print("╔" + "=" * 48 + "╗")
    print("║" + " " * 10 + "仓库违规检测系统测试" + " " * 16 + "║")
    print("╚" + "=" * 48 + "╝")
    print("\n")
    
    results = []
    
    # 运行测试
    results.append(("YOLO检测器", test_detector()))
    results.append(("区域管理器", test_zone_manager()))
    results.append(("违规检测器", test_violation_checker()))
    
    # 打印结果
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

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
```

**Step 2: 更新 README.md**

```markdown
# 仓库违规检测系统

基于YOLO的仓库作业违规检测系统，支持人员搬运检测、区域管理和违规告警。

## 功能特性

- **实时跟踪与检测**：YOLOv8 + 姿态估计，支持人员和箱子跟踪
- **状态机管理**：IDLE / CARRYING / OCCLUDED 三种状态管理
- **区域配置**：可视化Canvas区域绘制，支持多边形Zone定义
- **违规规则**：灵活配置区域间搬运限制（如 A→B 违规）
- **遮挡处理**：卡尔曼滤波跟踪，遮挡期间保持记忆
- **违规告警**：RabbitMQ推送违规事件，包含时间、轨迹等信息
- **配置管理**：YAML配置文件，前端可视化配置向导

## 技术栈

**后端**
- Python 3.12
- [uv](https://docs.astral.sh/uv/) (包管理工具)
- FastAPI
- YOLOv8 (Ultralytics)
- Redis (状态缓存)
- RabbitMQ (消息队列)
- OpenCV

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

## 快速开始

### 1. 启动依赖服务

```bash
docker-compose up -d
```

这将启动 Redis (6379) 和 RabbitMQ (5673/15673)。

### 2. 安装后端依赖

项目使用 [uv](https://docs.astral.sh/uv/) 作为包管理工具，依赖配置在 `pyproject.toml` 中。

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

### 4. 启动后端服务

```bash
# 使用 uv 运行（推荐）
uv run python backend/run.py
```

后端服务将运行在 http://localhost:8000

### 常用命令

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
save-vision-violation/
├── backend/
│   ├── app/
│   │   ├── api/           # API路由
│   │   ├── config/        # 配置管理
│   │   ├── core/          # 核心逻辑（检测器、状态机、违规检查）
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
├── pyproject.toml         # Python 依赖配置 (uv)
├── .python-version        # Python 版本指定
└── docker-compose.yml     # 依赖服务配置
```

## 配置说明

### config.yml

```yaml
cameras:
  - id: "cam_001"
    name: "入口摄像头"
    source: "./test_video.mp4"  # 或 RTSP地址
    enabled: true
    fps: 25

zones:
  - id: "zone_a"
    name: "Zone_A"
    color: "#FF6B6B"
    points: [[100, 100], [300, 100], [300, 300], [100, 300]]

violation_rules:
  - id: "rule_001"
    name: "A区到B区违规"
    from_zone: "zone_a"
    to_zone: "zone_b"
    enabled: true
```

### RabbitMQ 消息格式

违规事件将推送到 RabbitMQ 队列：

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

## 开发计划

- [x] 基础架构搭建
- [x] YOLO检测器实现
- [x] 状态机和违规检测
- [x] Redis和RabbitMQ集成
- [x] 前端配置向导
- [ ] 箱子检测模型训练
- [ ] SlowFast行为识别集成
- [ ] 实时监控WebSocket推送
- [ ] 违规事件回放

## License

MIT
```

**Step 3: 创建 docker-compose.yml**

```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    container_name: warehouse-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    restart: unless-stopped

  rabbitmq:
    image: rabbitmq:3-management-alpine
    container_name: warehouse-rabbitmq
    ports:
      - "5672:5672"      # AMQP端口
      - "15672:15672"    # 管理界面
    environment:
      RABBITMQ_DEFAULT_USER: guest
      RABBITMQ_DEFAULT_PASS: guest
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
    restart: unless-stopped

volumes:
  redis_data:
  rabbitmq_data:
```

**Step 4: 创建 .gitignore**

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
venv/
env/
ENV/
.venv

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Logs
*.log
logs/

# Model files
*.pt
*.pth
*.onnx

# Video files
*.mp4
*.avi
*.mkv
*.mov

# Config (keep template)
config.yml
!config.yml.example

# Output
output/
clips/
```

**Step 5: Commit**

```bash
git add backend/test_detection.py README.md docker-compose.yml .gitignore
git commit -m "docs: add tests, readme and docker-compose"
```

---

## 总结

**实施计划已完成！** 包含以下主要模块：

1. ✅ **项目基础架构** - 目录结构、配置文件管理
2. ✅ **后端API** - FastAPI路由、配置CRUD
3. ✅ **核心检测逻辑** - YOLO检测、姿态估计、区域管理
4. ✅ **状态机和违规检测** - 卡尔曼滤波、搬起/放下事件检测
5. ✅ **Redis和RabbitMQ** - 状态缓存和消息推送
6. ✅ **视频流处理** - OpenCV视频捕获和帧处理
7. ✅ **前端Vue3** - 配置向导、区域编辑器、监控面板
8. ✅ **测试和文档** - 测试脚本、README、Docker配置

**下一步执行选项：**

1. **Subagent-Driven (推荐)** - 我在本会话中逐个Task执行，每个Task完成后提交
2. **Parallel Session** - 在新会话中使用 executing-plans 批量执行

您希望使用哪种方式执行？