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
        # API模式
        from app.services.model_api_client import ModelAPIClient

        self.api_client = ModelAPIClient(self.detection_params.model_api)
        print(f"[Detector] 使用API模式: {self.detection_params.model_api.url}")

        self.id_counter = 0

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """检测搬箱子的人"""
        # 检查是否需要缩放（使用配置中的 max_frame_size）
        import time
        detect_start = time.time()

        max_size = getattr(self.detection_params.async_detection, 'max_frame_size', 1280)
        h, w = frame.shape[:2]
        original_shape = (h, w)
        scale = 1.0

        if max_size and max(h, w) > max_size:
            scale = max_size / max(h, w)
            new_w = int(w * scale)
            new_h = int(h * scale)
            resize_start = time.time()
            frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
            resize_time = (time.time() - resize_start) * 1000
            print(f"[Detector] 帧已缩放: {original_shape} -> {frame.shape[:2]}, scale={scale:.3f}, resize耗时:{resize_time:.1f}ms")
        else:
            print(f"[Detector] 帧未缩放: {frame.shape[:2]}, max_size={max_size}")

        result = self.api_client.detect(
            frame,
            imgsz=self.detection_params.model_api.imgsz,
            conf=self.detection_params.model_api.confidence,
        )

        # 如果帧被缩放过，将bbox坐标映射回原始尺寸
        if scale != 1.0 and result:
            for detection in result:
                detection.bbox = [
                    detection.bbox[0] / scale,
                    detection.bbox[1] / scale,
                    detection.bbox[2] / scale,
                    detection.bbox[3] / scale,
                ]
                detection.center = (detection.center[0] / scale, detection.center[1] / scale)
                detection.bottom_center = (detection.bottom_center[0] / scale, detection.bottom_center[1] / scale)

        total_time = (time.time() - detect_start) * 1000
        print(f"[Detector] detect() 总耗时: {total_time:.1f}ms, 检测到{len(result)}个目标")
        return result
