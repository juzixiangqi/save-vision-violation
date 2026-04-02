import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque
from app.utils.helpers import calculate_iou, calculate_center, calculate_distance
from app.core.kalman import BoxKalmanFilter


@dataclass
class TrackedPerson:
    """跟踪的人员对象"""

    id: str
    bbox: List[float]  # [x1, y1, x2, y2]
    keypoints: np.ndarray  # [17, 3]
    confidence: float
    center: Tuple[float, float]
    age: int = 0  # 跟踪的帧数
    missed_frames: int = 0  # 丢失的帧数

    # 历史记录
    bbox_history: deque = field(default_factory=lambda: deque(maxlen=30))
    center_history: deque = field(default_factory=lambda: deque(maxlen=30))
    keypoints_history: deque = field(default_factory=lambda: deque(maxlen=10))
    zone_history: deque = field(default_factory=lambda: deque(maxlen=10))

    # 动作状态记录
    hands_close_frames: int = 0  # 双手靠近的连续帧数
    hands_apart_frames: int = 0  # 双手张开的连续帧数
    box_nearby_frames: int = 0  # 箱子在附近的连续帧数

    def __post_init__(self):
        self.bbox_history.append(self.bbox)
        self.center_history.append(self.center)
        self.keypoints_history.append(self.keypoints.copy())


class PersonTracker:
    """人员跟踪器 - 使用IOU+卡尔曼滤波实现跨帧跟踪"""

    def __init__(
        self,
        max_missed: int = 10,  # 最多丢失10帧
        iou_threshold: float = 0.3,  # IOU匹配阈值
        distance_threshold: float = 150,
    ):  # 距离匹配阈值（像素）
        self.persons: Dict[str, TrackedPerson] = {}
        self.kalman_filters: Dict[str, BoxKalmanFilter] = {}
        self.next_id = 0
        self.max_missed = max_missed
        self.iou_threshold = iou_threshold
        self.distance_threshold = distance_threshold

    def update(
        self, detections: List[Tuple[List[float], np.ndarray, float]]
    ) -> List[TrackedPerson]:
        """
        更新跟踪器，传入检测结果，返回跟踪后的人员列表

        Args:
            detections: 列表，每项为 (bbox, keypoints, confidence)

        Returns:
            List[TrackedPerson]: 当前跟踪的所有人员
        """
        current_time = len(self.persons)  # 简单的时间戳

        # 如果没有现有的人员，直接创建新的
        if not self.persons:
            for bbox, keypoints, conf in detections:
                self._create_new_person(bbox, keypoints, conf)
            return list(self.persons.values())

        # 准备匹配
        matched_ids = set()
        unmatched_detections = []

        # 对每个检测尝试匹配现有的人员
        for bbox, keypoints, conf in detections:
            center = calculate_center(bbox)
            best_match_id = None
            best_match_score = 0

            for pid, person in self.persons.items():
                if pid in matched_ids:
                    continue

                # 计算IOU
                iou = calculate_iou(bbox, person.bbox)

                # 计算预测位置距离（如果有卡尔曼滤波器）
                if pid in self.kalman_filters:
                    predicted = self.kalman_filters[pid].predict()
                    dist = calculate_distance(center, predicted)
                    # 归一化距离分数（越近分数越高）
                    dist_score = max(0, 1 - dist / self.distance_threshold)
                else:
                    dist_score = 0

                # 综合匹配分数 (IOU权重更高)
                match_score = iou * 0.7 + dist_score * 0.3

                if match_score > best_match_score and (
                    iou > self.iou_threshold or dist_score > 0.5
                ):
                    best_match_score = match_score
                    best_match_id = pid

            if best_match_id:
                # 匹配成功，更新人员信息
                self._update_person(best_match_id, bbox, keypoints, conf)
                matched_ids.add(best_match_id)
            else:
                # 未匹配，可能是新人员
                unmatched_detections.append((bbox, keypoints, conf))

        # 处理未匹配的人员（标记为丢失）
        for pid in list(self.persons.keys()):
            if pid not in matched_ids:
                self.persons[pid].missed_frames += 1
                # 更新卡尔曼滤波器（只用预测值）
                if pid in self.kalman_filters:
                    predicted = self.kalman_filters[pid].predict()
                    self.persons[pid].center_history.append(predicted)

        # 删除丢失太久的人员
        self._remove_stale_persons()

        # 为未匹配的检测创建新人员
        for bbox, keypoints, conf in unmatched_detections:
            self._create_new_person(bbox, keypoints, conf)

        return list(self.persons.values())

    def _create_new_person(
        self, bbox: List[float], keypoints: np.ndarray, confidence: float
    ):
        """创建新的人员跟踪对象"""
        self.next_id += 1
        person_id = f"person_{self.next_id}"
        center = calculate_center(bbox)

        person = TrackedPerson(
            id=person_id,
            bbox=bbox,
            keypoints=keypoints,
            confidence=confidence,
            center=center,
        )

        self.persons[person_id] = person

        # 初始化卡尔曼滤波器
        self.kalman_filters[person_id] = BoxKalmanFilter()
        self.kalman_filters[person_id].init(center[0], center[1])

        return person_id

    def _update_person(
        self,
        person_id: str,
        bbox: List[float],
        keypoints: np.ndarray,
        confidence: float,
    ):
        """更新现有的人员信息"""
        person = self.persons[person_id]
        center = calculate_center(bbox)

        person.bbox = bbox
        person.keypoints = keypoints
        person.confidence = confidence
        person.center = center
        person.age += 1
        person.missed_frames = 0

        person.bbox_history.append(bbox)
        person.center_history.append(center)
        person.keypoints_history.append(keypoints.copy())

        # 更新卡尔曼滤波器
        if person_id in self.kalman_filters:
            self.kalman_filters[person_id].update(center[0], center[1])

    def _remove_stale_persons(self):
        """删除丢失太久的人员"""
        stale_ids = [
            pid
            for pid, person in self.persons.items()
            if person.missed_frames > self.max_missed
        ]
        for pid in stale_ids:
            del self.persons[pid]
            if pid in self.kalman_filters:
                del self.kalman_filters[pid]

    def get_person(self, person_id: str) -> Optional[TrackedPerson]:
        """获取指定ID的人员"""
        return self.persons.get(person_id)

    def get_all_persons(self) -> List[TrackedPerson]:
        """获取所有正在跟踪的人员"""
        return list(self.persons.values())

    def get_trajectory(
        self, person_id: str, n_frames: int = 30
    ) -> List[Tuple[float, float]]:
        """获取人员最近N帧的轨迹"""
        person = self.persons.get(person_id)
        if not person:
            return []
        return list(person.center_history)[-n_frames:]

    def get_velocity(self, person_id: str) -> Tuple[float, float]:
        """计算人员的速度（像素/帧）"""
        person = self.persons.get(person_id)
        if not person or len(person.center_history) < 2:
            return (0.0, 0.0)

        centers = list(person.center_history)
        p1 = centers[-2]
        p2 = centers[-1]
        return (p2[0] - p1[0], p2[1] - p1[1])

    def reset(self):
        """重置跟踪器"""
        self.persons.clear()
        self.kalman_filters.clear()
        self.next_id = 0


class SimplePersonTracker:
    """简化版人员跟踪器 - 基于IOU匹配，计算更简单"""

    def __init__(self, max_missed: int = 5, iou_threshold: float = 0.2):
        self.persons: Dict[str, TrackedPerson] = {}
        self.next_id = 0
        self.max_missed = max_missed
        self.iou_threshold = iou_threshold

    def update(
        self, detections: List[Tuple[List[float], np.ndarray, float]]
    ) -> List[TrackedPerson]:
        """更新跟踪"""
        # 增加所有现有人员的丢失帧数
        for person in self.persons.values():
            person.missed_frames += 1

        matched_ids = set()

        for bbox, keypoints, conf in detections:
            best_match_id = None
            best_iou = 0

            for pid, person in self.persons.items():
                if pid in matched_ids:
                    continue

                iou = calculate_iou(bbox, person.bbox)
                if iou > best_iou and iou > self.iou_threshold:
                    best_iou = iou
                    best_match_id = pid

            if best_match_id:
                # 更新现有人员
                self._update_person(best_match_id, bbox, keypoints, conf)
                matched_ids.add(best_match_id)
            else:
                # 创建新人员
                self._create_new_person(bbox, keypoints, conf)

        # 删除丢失太久的人员
        self._remove_stale_persons()

        return list(self.persons.values())

    def _create_new_person(
        self, bbox: List[float], keypoints: np.ndarray, confidence: float
    ):
        """创建新人员"""
        self.next_id += 1
        person_id = f"person_{self.next_id}"
        center = calculate_center(bbox)

        person = TrackedPerson(
            id=person_id,
            bbox=bbox,
            keypoints=keypoints,
            confidence=confidence,
            center=center,
        )
        self.persons[person_id] = person

    def _update_person(
        self,
        person_id: str,
        bbox: List[float],
        keypoints: np.ndarray,
        confidence: float,
    ):
        """更新人员"""
        person = self.persons[person_id]
        person.bbox = bbox
        person.keypoints = keypoints
        person.confidence = confidence
        person.center = calculate_center(bbox)
        person.age += 1
        person.missed_frames = 0

        person.bbox_history.append(bbox)
        person.center_history.append(person.center)
        person.keypoints_history.append(keypoints.copy())

    def _remove_stale_persons(self):
        """删除丢失的人员"""
        stale_ids = [
            pid
            for pid, person in self.persons.items()
            if person.missed_frames > self.max_missed
        ]
        for pid in stale_ids:
            del self.persons[pid]

    def get_person(self, person_id: str) -> Optional[TrackedPerson]:
        return self.persons.get(person_id)

    def get_all_persons(self) -> List[TrackedPerson]:
        return list(self.persons.values())

    def get_trajectory(
        self, person_id: str, n_frames: int = 30
    ) -> List[Tuple[float, float]]:
        person = self.persons.get(person_id)
        if not person:
            return []
        return list(person.center_history)[-n_frames:]

    def reset(self):
        self.persons.clear()
        self.next_id = 0
