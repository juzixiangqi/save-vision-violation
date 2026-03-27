from pydantic import BaseModel, Field
from typing import List, Optional, Tuple
from enum import Enum


class Zone(BaseModel):
    id: str
    name: str
    color: str = "#FF6B6B"
    points: List[List[float]]  # [[x1,y1], [x2,y2], ...]
    reference_width: int = 1920  # 绘制区域时参考图片的宽度
    reference_height: int = 1080  # 绘制区域时参考图片的高度


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


class BoxDetectionParams(BaseModel):
    model: str = ""  # 自定义箱子检测模型路径
    confidence: float = 0.5
    iou_threshold: float = 0.45
    class_id: int = 0  # 箱子类别的ID（如果是单类模型就是0）
    enabled: bool = True  # 是否启用箱子检测


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
    box: BoxDetectionParams = BoxDetectionParams()
    tracking: TrackingParams = TrackingParams()
    lift_detection: LiftDetectionParams = LiftDetectionParams()
    drop_detection: DropDetectionParams = DropDetectionParams()


class RabbitMQConfig(BaseModel):
    host: str = "localhost"
    port: int = 5673
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
