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


class PersonCarryParams(BaseModel):
    """自定义YOLO模型检测搬箱子的人"""

    model: str = "person_carry.pt"  # 模型路径
    confidence: float = 0.5  # 检测置信度
    iou_threshold: float = 0.45  # NMS IoU阈值
    class_id: int = 0  # person_carry类别的ID


class TrackingParams(BaseModel):
    max_age: int = 30
    min_hits: int = 3


class PoseParams(BaseModel):
    """兼容性保留：姿态检测参数（新的检测逻辑不再使用）"""

    model: str = "yolov8n-pose.pt"
    confidence: float = 0.5


class BoxDetectionParams(BaseModel):
    """兼容性保留：箱子检测参数（新的检测逻辑不再使用）"""

    model: str = ""
    confidence: float = 0.5
    iou_threshold: float = 0.45
    class_id: int = 0
    enabled: bool = False


class LiftDetectionParams(BaseModel):
    """兼容性保留（新的检测逻辑不再使用）"""

    hands_below_hip_threshold: int = 0
    hands_distance_threshold: int = 150
    consecutive_frames: int = 5
    speed_variance_threshold: int = 10


class DropDetectionParams(BaseModel):
    """兼容性保留（新的检测逻辑不再使用）"""

    hands_rise_threshold: int = 30
    iou_drop_threshold: float = 0.1
    occlusion_timeout: int = 5


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
    system: SystemConfig = SystemConfig()
    cameras: List[Camera] = []
    zones: List[Zone] = []
    violation_rules: List[ViolationRule] = []
    detection_params: DetectionParams = DetectionParams()
    rabbitmq: RabbitMQConfig = RabbitMQConfig()
    redis: RedisConfig = RedisConfig()
