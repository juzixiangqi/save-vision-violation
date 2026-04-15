"""
简单的IOU-based轨迹追踪器
为每个person_carry检测分配稳定的track_id
"""

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class Track:
    id: str
    bbox: List[float]
    center: Tuple[float, float]
    bottom_center: Tuple[float, float]
    age: int = 0
    hits: int = 1


def calculate_iou(box1: List[float], box2: List[float]) -> float:
    """计算两个bbox的IOU"""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    if x2 <= x1 or y2 <= y1:
        return 0.0

    intersection = (x2 - x1) * (y2 - y1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - intersection

    return intersection / union if union > 0 else 0.0


def calculate_distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """计算两点之间的欧氏距离"""
    return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5


class SimpleTracker:
    """简单的IOU+距离多目标追踪器，支持快速移动和跨空白区域追踪"""

    def __init__(
        self,
        max_age: int = 30,
        min_hits: int = 3,
        iou_threshold: float = 0.3,
        distance_threshold: float = 400.0,
    ):
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.distance_threshold = distance_threshold
        self.tracks: Dict[str, Track] = {}
        self.next_id = 1

    def update(self, detections: List) -> List[Track]:
        """
        更新追踪器，将检测与现有轨迹匹配
        支持IOU匹配、中心点距离匹配和轨迹复活，适应快速移动与空白区域场景

        Args:
            detections: Detection对象列表

        Returns:
            当前活跃的Track列表
        """
        # 如果没有检测，更新现有轨迹的age
        if not detections:
            for track in list(self.tracks.values()):
                track.age += 1

            # 移除超时的轨迹
            self.tracks = {k: v for k, v in self.tracks.items() if v.age < self.max_age}

            return list(self.tracks.values())

        # 计算IOU+距离矩阵
        matched_tracks = set()
        matched_detections = set()

        for det_idx, det in enumerate(detections):
            best_score = 0.0
            best_track_id = None

            for track_id, track in self.tracks.items():
                if track_id in matched_tracks:
                    continue

                # 优先尝试IOU匹配
                iou = calculate_iou(det.bbox, track.bbox)
                if iou > best_score and iou >= self.iou_threshold:
                    best_score = iou
                    best_track_id = track_id
                    continue

                # IOU不足时尝试中心点距离匹配
                dist = calculate_distance(det.center, track.center)
                if dist < self.distance_threshold:
                    # 使用归一化距离分数 (0~1)，越近分数越高
                    dist_score = 1.0 - dist / self.distance_threshold
                    if dist_score > best_score:
                        best_score = dist_score
                        best_track_id = track_id

            if best_track_id:
                # 匹配成功，更新轨迹
                track = self.tracks[best_track_id]
                track.bbox = det.bbox
                track.center = det.center
                track.bottom_center = det.bottom_center
                track.age = 0
                track.hits += 1
                matched_tracks.add(best_track_id)
                matched_detections.add(det_idx)

                # 更新检测对象的id为track_id
                det.id = best_track_id

        # 对仍未匹配的检测，尝试复活附近丢失的旧轨迹（避免空白区域导致ID切换）
        for det_idx, det in enumerate(detections):
            if det_idx not in matched_detections:
                best_revive_id = None
                best_revive_dist = float("inf")
                for track_id, track in self.tracks.items():
                    if track_id in matched_tracks:
                        continue
                    dist = calculate_distance(det.center, track.center)
                    # 复活阈值放宽到 distance_threshold * 1.5
                    if dist < best_revive_dist and dist < self.distance_threshold * 1.5:
                        best_revive_dist = dist
                        best_revive_id = track_id

                if best_revive_id:
                    track = self.tracks[best_revive_id]
                    track.bbox = det.bbox
                    track.center = det.center
                    track.bottom_center = det.bottom_center
                    track.age = 0
                    track.hits += 1
                    matched_tracks.add(best_revive_id)
                    matched_detections.add(det_idx)
                    det.id = best_revive_id

        # 仍未匹配的检测才创建新轨迹
        new_track_ids = set()
        for det_idx, det in enumerate(detections):
            if det_idx not in matched_detections:
                track_id = f"track_{self.next_id}"
                self.next_id += 1

                self.tracks[track_id] = Track(
                    id=track_id,
                    bbox=det.bbox,
                    center=det.center,
                    bottom_center=det.bottom_center,
                )
                det.id = track_id
                new_track_ids.add(track_id)

        # 增加未匹配轨迹的age（新创建的轨迹和已复活的轨迹除外）
        for track_id in self.tracks:
            if track_id not in matched_tracks and track_id not in new_track_ids:
                self.tracks[track_id].age += 1

        # 移除超时的轨迹
        self.tracks = {k: v for k, v in self.tracks.items() if v.age < self.max_age}

        # 返回满足min_hits的轨迹
        return [
            track
            for track in self.tracks.values()
            if track.hits >= self.min_hits or track.age == 0
        ]

    def reset(self):
        """重置追踪器"""
        self.tracks.clear()
        self.next_id = 1
