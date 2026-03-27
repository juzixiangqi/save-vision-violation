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

        # 加载箱子检测模型（如果配置了）
        self.box_detector = None
        if (
            self.detection_params.box.enabled
            and self.detection_params.box.model
            and len(self.detection_params.box.model) > 0
        ):
            try:
                print(f"[Detector] 加载箱子检测模型: {self.detection_params.box.model}")
                self.box_detector = YOLO(self.detection_params.box.model)
                print("[Detector] 箱子检测模型加载成功")
            except Exception as e:
                print(f"[Detector] 警告: 无法加载箱子检测模型: {e}")

        self.person_id_counter = 0
        self.box_id_counter = 0

    def detect(self, frame: np.ndarray) -> Tuple[List[Detection], List[Pose]]:
        """检测人员和姿态"""
        persons = []
        poses = []

        # 目标检测
        results = self.detector(
            frame,
            conf=self.detection_params.yolo.confidence,
            iou=self.detection_params.yolo.iou_threshold,
        )

        for result in results:
            boxes_data = result.boxes
            for i, box in enumerate(boxes_data):
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                bbox = box.xyxy[0].cpu().numpy().tolist()
                x1, y1, x2, y2 = bbox
                center = ((x1 + x2) / 2, (y1 + y2) / 2)

                # COCO类别: 0=person
                if cls == 0:  # person
                    self.person_id_counter += 1
                    persons.append(
                        Detection(
                            id=f"person_{self.person_id_counter}",
                            bbox=bbox,
                            confidence=conf,
                            class_id=cls,
                            class_name="person",
                            center=center,
                        )
                    )

        # 姿态估计
        pose_results = self.pose_estimator(frame, conf=0.5)
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

        return persons, poses

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
