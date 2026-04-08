"""
姿态辅助的人员跟踪器

结合DeepSort + 姿态关键点进行更稳定的跟踪
当外观特征匹配失败时，使用关键点位置进行辅助匹配
"""

import numpy as np
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class PoseTrack:
    """带姿态信息的跟踪对象"""

    track_id: int
    bbox: np.ndarray
    keypoints: np.ndarray  # [17, 3] - x, y, confidence
    center: Tuple[float, float]
    last_seen: int = 0
    keypoints_history: List[np.ndarray] = field(default_factory=list)

    def update_keypoints(self, keypoints: np.ndarray):
        """更新关键点历史"""
        self.keypoints = keypoints
        self.keypoints_history.append(keypoints.copy())
        if len(self.keypoints_history) > 5:  # 保留最近5帧
            self.keypoints_history.pop(0)

    def get_stable_keypoints(self) -> np.ndarray:
        """获取稳定的关键点（历史平均）"""
        if len(self.keypoints_history) < 2:
            return self.keypoints
        # 对历史关键点取平均，减少抖动
        return np.mean(self.keypoints_history, axis=0)


class PoseAssistedTracker:
    """
    姿态辅助跟踪器

    结合运动预测 + 姿态关键点匹配，实现更稳定的ID
    特别适用于：
    1. 俯视角度（外观特征不明显）
    2. 人员做动作（姿态变化大）
    3. 遮挡场景
    """

    def __init__(
        self,
        max_age: int = 30,
        keypoint_threshold: float = 100,  # 关键点匹配阈值（像素）
        iou_threshold: float = 0.3,  # IoU匹配阈值
    ):
        self.tracks: Dict[int, PoseTrack] = {}
        self.next_id = 1
        self.max_age = max_age
        self.keypoint_threshold = keypoint_threshold
        self.iou_threshold = iou_threshold
        self.frame_count = 0

    def update(
        self,
        detections: List[
            Tuple[np.ndarray, np.ndarray, float]
        ],  # (bbox, keypoints, conf)
    ) -> List[PoseTrack]:
        """
        更新跟踪器

        Args:
            detections: 列表，每项为 (bbox, keypoints, confidence)

        Returns:
            当前所有活跃的跟踪对象
        """
        self.frame_count += 1

        # 1. 增加所有现有跟踪的年龄
        for track in self.tracks.values():
            track.last_seen += 1

        # 2. 匹配检测和现有跟踪
        matched_tracks = []
        unmatched_detections = list(range(len(detections)))

        # 优先用关键点匹配（更稳定）
        track_ids = list(self.tracks.keys())
        detection_indices = list(range(len(detections)))

        # 计算代价矩阵（关键点距离）
        cost_matrix = np.full((len(track_ids), len(detections)), np.inf)

        for i, track_id in enumerate(track_ids):
            track = self.tracks[track_id]
            track_kpts = track.get_stable_keypoints()

            for j, det_idx in enumerate(detection_indices):
                bbox, kpts, conf = detections[det_idx]

                # 计算关键点距离（只比较有置信度的点）
                dist = self._compute_keypoint_distance(track_kpts, kpts)
                if dist < self.keypoint_threshold:
                    cost_matrix[i, j] = dist

        # 匈牙利算法匹配
        from scipy.optimize import linear_sum_assignment

        if cost_matrix.size > 0 and not np.all(cost_matrix == np.inf):
            row_indices, col_indices = linear_sum_assignment(cost_matrix)

            matched_pairs = []
            for row, col in zip(row_indices, col_indices):
                if cost_matrix[row, col] < self.keypoint_threshold:
                    track_id = track_ids[row]
                    det_idx = detection_indices[col]
                    matched_pairs.append((track_id, det_idx))
                    unmatched_detections.remove(det_idx)

            # 更新匹配的跟踪
            for track_id, det_idx in matched_pairs:
                bbox, kpts, conf = detections[det_idx]
                self._update_track(track_id, bbox, kpts)
                matched_tracks.append(track_id)

        # 3. 对未匹配的检测，尝试用IoU匹配（短距离移动）
        still_unmatched = []
        for det_idx in unmatched_detections:
            bbox, kpts, conf = detections[det_idx]
            center = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)

            best_match = None
            best_iou = 0

            for track_id, track in self.tracks.items():
                if track_id in matched_tracks:
                    continue
                if track.last_seen > 3:  # 丢失太久的不管
                    continue

                # 计算IoU
                iou = self._compute_iou(track.bbox, bbox)
                # 计算中心点距离
                dist = np.sqrt(
                    (track.center[0] - center[0]) ** 2
                    + (track.center[1] - center[1]) ** 2
                )

                # IoU高且距离近
                if iou > self.iou_threshold and dist < 100:
                    if iou > best_iou:
                        best_iou = iou
                        best_match = track_id

            if best_match:
                self._update_track(best_match, bbox, kpts)
                matched_tracks.append(best_match)
            else:
                still_unmatched.append(det_idx)

        # 4. 为未匹配的检测创建新跟踪
        for det_idx in still_unmatched:
            bbox, kpts, conf = detections[det_idx]
            self._create_track(bbox, kpts)

        # 5. 删除丢失太久的跟踪
        self._remove_stale_tracks()

        # 返回活跃的跟踪
        return [t for t in self.tracks.values() if t.last_seen == 0]

    def _compute_keypoint_distance(self, kpts1: np.ndarray, kpts2: np.ndarray) -> float:
        """
        计算两组关键点的距离
        只比较有置信度的关键点（>0.3）
        """
        # 身体中心关键点（躯干部分更稳定）
        CORE_KEYPOINTS = [5, 6, 11, 12]  # 肩膀和臀部

        distances = []
        for idx in CORE_KEYPOINTS:
            conf1 = kpts1[idx, 2]
            conf2 = kpts2[idx, 2]

            # 两个点都有高置信度才比较
            if conf1 > 0.3 and conf2 > 0.3:
                dist = np.sqrt(
                    (kpts1[idx, 0] - kpts2[idx, 0]) ** 2
                    + (kpts1[idx, 1] - kpts2[idx, 1]) ** 2
                )
                distances.append(dist)

        if not distances:
            return np.inf

        return np.mean(distances)

    def _compute_iou(self, box1: np.ndarray, box2: np.ndarray) -> float:
        """计算两个框的IoU"""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])

        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - inter

        return inter / union if union > 0 else 0

    def _create_track(self, bbox: np.ndarray, keypoints: np.ndarray):
        """创建新跟踪"""
        track_id = self.next_id
        self.next_id += 1

        center = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)

        track = PoseTrack(
            track_id=track_id,
            bbox=bbox.copy(),
            keypoints=keypoints.copy(),
            center=center,
            last_seen=0,
        )
        track.keypoints_history.append(keypoints.copy())

        self.tracks[track_id] = track
        print(f"[NewTrack] Created track {track_id}")

    def _update_track(self, track_id: int, bbox: np.ndarray, keypoints: np.ndarray):
        """更新现有跟踪"""
        track = self.tracks[track_id]
        track.bbox = bbox.copy()
        track.center = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
        track.last_seen = 0
        track.update_keypoints(keypoints.copy())

    def _remove_stale_tracks(self):
        """删除丢失太久的跟踪"""
        stale_ids = [
            track_id
            for track_id, track in self.tracks.items()
            if track.last_seen > self.max_age
        ]
        for track_id in stale_ids:
            del self.tracks[track_id]
            print(f"[RemoveTrack] Removed track {track_id}")


# ============ 使用示例 ============


def example_usage():
    """
    使用示例
    """
    tracker = PoseAssistedTracker(
        max_age=30,
        keypoint_threshold=100,  # 100像素内认为是一个人
        iou_threshold=0.3,
    )

    # 模拟检测数据
    # 第1帧：检测到1个人
    detections_frame1 = [
        (
            np.array([100, 100, 200, 300]),  # bbox
            np.random.rand(17, 3) * 100,  # keypoints
            0.9,  # confidence
        )
    ]
    tracks1 = tracker.update(detections_frame1)
    print(f"Frame 1: {len(tracks1)} tracks")

    # 第2帧：同一个人，关键点略有变化（模拟做动作）
    detections_frame2 = [
        (
            np.array([102, 98, 203, 302]),  # bbox稍微移动
            np.random.rand(17, 3) * 100 + np.random.randn(17, 3) * 5,  # 关键点抖动
            0.85,
        )
    ]
    tracks2 = tracker.update(detections_frame2)
    print(f"Frame 2: {len(tracks2)} tracks, ID: {tracks2[0].track_id}")

    # 第3帧：关键点变化更大，但位置相近
    detections_frame3 = [
        (
            np.array([105, 102, 205, 305]),
            np.random.rand(17, 3) * 100 + np.random.randn(17, 3) * 10,
            0.88,
        )
    ]
    tracks3 = tracker.update(detections_frame3)
    print(f"Frame 3: {len(tracks3)} tracks, ID: {tracks3[0].track_id}")

    # 验证ID是否保持一致
    if tracks1[0].track_id == tracks2[0].track_id == tracks3[0].track_id:
        print("\n✅ ID保持稳定！")
    else:
        print("\n❌ ID发生了变化")


if __name__ == "__main__":
    example_usage()
