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
                print(
                    f"[Detector] 已将 {model_path} 复制到临时文件 {temp_pt_path} 进行加载"
                )
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
