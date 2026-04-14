import cv2
import numpy as np
from ultralytics import YOLO
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import os
import tempfile
import shutil
from app.config.manager import config_manager


@dataclass
class Detection:
    id: str  # track_id
    bbox: List[float]  # [x1, y1, x2, y2]
    confidence: float
    center: Tuple[float, float]
    class_name: str = "person_carry"

    def __post_init__(self):
        """确保bbox字段存在（兼容旧代码）"""
        pass


def load_yolo_model(model_path: str) -> YOLO:
    """
    加载YOLO模型，支持 .pt 和 .pth 后缀
    ultralytics 默认只接受 .pt，如果是 .pth 则临时复制为 .pt 加载
    """
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"模型文件不存在: {model_path}")

    file_ext = os.path.splitext(model_path)[1].lower()

    if file_ext == ".pt":
        # 正常加载 .pt 文件
        return YOLO(model_path)
    elif file_ext == ".pth":
        # 对于 .pth 文件，创建一个临时 .pt 文件来加载
        # 因为 ultralytics 会检查后缀名
        temp_pt_path = None
        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as tmp:
                temp_pt_path = tmp.name

            # 复制文件内容
            shutil.copy2(model_path, temp_pt_path)
            print(
                f"[Detector] 已将 {model_path} 复制到临时文件 {temp_pt_path} 进行加载"
            )

            # 加载模型
            model = YOLO(temp_pt_path)

            # 清理临时文件
            try:
                os.unlink(temp_pt_path)
            except:
                pass

            return model
        except Exception as e:
            # 确保清理临时文件
            if temp_pt_path and os.path.exists(temp_pt_path):
                try:
                    os.unlink(temp_pt_path)
                except:
                    pass
            raise e
    else:
        raise ValueError(f"不支持的模型格式: {file_ext}，只支持 .pt 或 .pth")


class YOLODetector:
    def __init__(self):
        config = config_manager.get_config()
        self.detection_params = config.detection_params

        # 加载person_carry检测模型
        self.model = load_yolo_model(self.detection_params.person_carry.model)
        print(
            f"[Detector] 已加载person_carry检测模型: {self.detection_params.person_carry.model}"
        )

        self.id_counter = 0

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """检测搬箱子的人"""
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

                self.id_counter += 1
                detections.append(
                    Detection(
                        id=f"person_carry_{self.id_counter}",
                        bbox=[float(x) for x in bbox],
                        confidence=conf,
                        center=center,
                    )
                )

        return detections
