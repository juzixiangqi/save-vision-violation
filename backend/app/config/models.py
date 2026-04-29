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
    camera_code: Optional[str] = None  # 监控点indexCode，用于通过API获取RTSP流


class YoloParams(BaseModel):
    model: str = "yolov8n.pt"
    confidence: float = 0.5
    iou_threshold: float = 0.45


class ModelAPIConfig(BaseModel):
    """模型API配置"""

    url: str = "http://10.190.28.23:31674/predict"
    timeout: int = 30
    imgsz: int = 640
    confidence: float = 0.2


class AsyncDetectionConfig(BaseModel):
    """异步检测配置

    注意：检测频率由 VideoStream.detection_interval 控制，
    本配置只负责 API 超时保护和并发控制
    """

    enabled: bool = True  # 是否启用异步检测
    api_timeout: float = 0.18  # API超时时间（秒）
    max_pending: int = 2  # 最大并发请求数


class TrackingParams(BaseModel):
    max_age: int = 30
    min_hits: int = 3


class DetectionParams(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_api: ModelAPIConfig = ModelAPIConfig()
    tracking: TrackingParams = TrackingParams()
    async_detection: AsyncDetectionConfig = AsyncDetectionConfig()


class RabbitMQConfig(BaseModel):
    host: str = "localhost"
    port: int = 5673
    username: str = "guest"
    password: str = "guest"
    virtual_host: str = "/"  # 虚拟主机
    exchange: str = ""  # 交换机名称，空字符串表示使用默认交换机
    exchange_type: str = "fanout"  # 交换机类型：direct, fanout, topic, headers
    routing_key: str = ""  # 路由键，fanout模式下不需要
    queue: str = ""  # 队列名称，空字符串表示不声明队列


class RedisConfig(BaseModel):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None  # Redis密码，null表示无密码


class SystemConfig(BaseModel):
    name: str = "仓库违规检测系统"
    version: str = "1.0.0"


class Config(BaseModel):
    model_config = {"protected_namespaces": ()}

    system: SystemConfig = SystemConfig()
    cameras: List[Camera] = []
    zones: List[Zone] = []
    violation_rules: List[ViolationRule] = []
    detection_params: DetectionParams = DetectionParams()
    rabbitmq: RabbitMQConfig = RabbitMQConfig()
    redis: RedisConfig = RedisConfig()
