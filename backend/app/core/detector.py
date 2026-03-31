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

        # 加载姿态模型（同时检测人员和关键点）
        self.pose_estimator = load_yolo_model(self.detection_params.pose.model)

        # 加载箱子检测模型（如果配置了）
        self.box_detector = None
        if (
            self.detection_params.box.enabled
            and self.detection_params.box.model
            and len(self.detection_params.box.model) > 0
        ):
            try:
                print(f"[Detector] 加载箱子检测模型: {self.detection_params.box.model}")
                self.box_detector = load_yolo_model(self.detection_params.box.model)
                print("[Detector] 箱子检测模型加载成功")
            except Exception as e:
                print(f"[Detector] 警告: 无法加载箱子检测模型: {e}")

        self.person_id_counter = 0
        self.box_id_counter = 0

    def detect(self, frame: np.ndarray) -> List[Pose]:
        """检测人员姿态（使用姿态模型同时检测人员和关键点）"""
        poses = []

        # 姿态估计（同时返回人体框和关键点）
        pose_results = self.pose_estimator(
            frame,
            conf=self.detection_params.pose.confidence,
        )
        for result in pose_results:
            if result.keypoints is not None:
                for i, kpts in enumerate(result.keypoints):
                    self.person_id_counter += 1
                    keypoints = kpts.xy.cpu().numpy()  # [17, 2] 或 [1, 17, 2]

                    # 确保 keypoints 是 2D
                    if keypoints.ndim == 3:
                        keypoints = keypoints.squeeze(0)

                    conf = (
                        kpts.conf.cpu().numpy()
                        if hasattr(kpts, "conf")
                        else np.ones(17)
                    )

                    # 确保 conf 也是 1D
                    if conf.ndim == 2:
                        conf = conf.squeeze(0)

                    keypoints_3d = np.concatenate(
                        [keypoints, conf.reshape(-1, 1)], axis=1
                    )

                    # 获取bbox
                    if result.boxes:
                        bbox = result.boxes[i].xyxy[0].cpu().numpy().tolist()
                    else:
                        bbox = [0, 0, 0, 0]

                    poses.append(
                        Pose(
                            id=f"person_{self.person_id_counter}",
                            keypoints=keypoints_3d,
                            bbox=bbox,
                            confidence=float(result.boxes[i].conf[0])
                            if result.boxes
                            else 0.5,
                        )
                    )

        return poses

    def detect_boxes(self, frame: np.ndarray) -> List[Detection]:
        """
        检测箱子 - 使用自定义训练的YOLO模型
        """
        boxes = []

        if self.box_detector is None:
            # 未配置箱子检测模型
            return boxes

        try:
            results = self.box_detector(
                frame,
                conf=self.detection_params.box.confidence,
                iou=self.detection_params.box.iou_threshold,
            )

            for result in results:
                if result.boxes is None:
                    continue

                for i, box in enumerate(result.boxes):
                    cls = int(box.cls[0])
                    conf = float(box.conf[0])
                    bbox = box.xyxy[0].cpu().numpy().tolist()
                    x1, y1, x2, y2 = bbox
                    center = ((x1 + x2) / 2, (y1 + y2) / 2)

                    # 只检测指定的箱子类别
                    if cls == self.detection_params.box.class_id:
                        self.box_id_counter += 1
                        boxes.append(
                            Detection(
                                id=f"box_{self.box_id_counter}",
                                bbox=[float(x) for x in bbox],
                                confidence=conf,
                                class_id=cls,
                                class_name="box",
                                center=center,
                            )
                        )

        except Exception as e:
            print(f"[DetectBoxes] 检测箱子时出错: {e}")

        return boxes


# 17个关键点索引 (COCO格式)
POSE_KEYPOINTS = {
    "nose": 0,
    "left_eye": 1,
    "right_eye": 2,
    "left_ear": 3,
    "right_ear": 4,
    "left_shoulder": 5,
    "right_shoulder": 6,
    "left_elbow": 7,
    "right_elbow": 8,
    "left_wrist": 9,
    "right_wrist": 10,
    "left_hip": 11,
    "right_hip": 12,
    "left_knee": 13,
    "right_knee": 14,
    "left_ankle": 15,
    "right_ankle": 16,
}
