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

        # API模式
        from app.services.model_api_client import ModelAPIClient

        self.api_client = ModelAPIClient(self.detection_params.model_api)
        print(f"[Detector] 使用API模式: {self.detection_params.model_api.url}")

        self.id_counter = 0

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """检测搬箱子的人"""
        return self.api_client.detect(
            frame,
            imgsz=self.detection_params.model_api.imgsz,
            conf=self.detection_params.model_api.confidence,
        )
