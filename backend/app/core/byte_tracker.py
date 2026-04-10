"""
ByteTrack 纯运动跟踪器封装

基于运动信息（IoU + 距离）进行跟踪，不依赖外观特征
特别适合俯视角度场景
"""

import numpy as np
from typing import List, Dict, Tuple, Optional
from collections import deque

from app.core.kalman import BoxKalmanFilter


class Track:
    """跟踪对象"""

    def __init__(self, track_id: int, bbox: np.ndarray, score: float):
        self.track_id = track_id
        self.bbox = bbox.copy()  # [x1, y1, x2, y2] - 用于匹配的原始 BBox
        self.center = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
        self.score = score

        # 预测用的 BBox（卡尔曼滤波预测后的）
        self.predicted_bbox = bbox.copy()
        self.predicted_center = self.center

        # 状态
        self._confirmed = False  # 是否已确认
        self.is_deleted = False
        self.time_since_update = 0

        # 历史
        self.bbox_history = deque(maxlen=10)
        self.score_history = deque(maxlen=10)
        self.bbox_history.append(bbox.copy())
        self.score_history.append(score)

        # 卡尔曼滤波
        self.kalman = BoxKalmanFilter()
        self.kalman.init(self.center[0], self.center[1])

    def to_tlbr(self) -> np.ndarray:
        """返回边界框 [x1, y1, x2, y2]（兼容 DeepSort 接口）"""
        return self.bbox.copy()

    def is_confirmed(self) -> bool:
        """是否已确认（兼容 DeepSort 接口）

        修改：只要有历史记录就算确认，不等待多帧
        """
        return len(self.bbox_history) >= 1  # 只要有1帧就算确认

    def predict(self):
        """预测下一帧位置，但不改变原始 bbox"""
        predicted_center = self.kalman.predict()
        # 计算偏移量
        dx = predicted_center[0] - self.center[0]
        dy = predicted_center[1] - self.center[1]
        # 只更新预测的 bbox，保留原始 bbox 用于匹配
        self.predicted_bbox = self.bbox.copy()
        self.predicted_bbox[0] += dx
        self.predicted_bbox[1] += dy
        self.predicted_bbox[2] += dx
        self.predicted_bbox[3] += dy
        self.predicted_center = predicted_center
        self.time_since_update += 1

    def update(self, bbox: np.ndarray, score: float):
        """更新跟踪状态"""
        self.bbox = bbox.copy()
        self.center = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
        self.score = score
        self.time_since_update = 0
        self.bbox_history.append(bbox.copy())
        self.score_history.append(score)

        # 同步更新预测 bbox
        self.predicted_bbox = bbox.copy()
        self.predicted_center = self.center

        # 更新卡尔曼滤波
        self.kalman.update(self.center[0], self.center[1])

        # 确认跟踪（连续3帧匹配后确认）
        if not self._confirmed and len(self.bbox_history) >= 3:
            self._confirmed = True

    def mark_deleted(self):
        """标记为删除"""
        self.is_deleted = True


class ByteTrack:
    """
    ByteTrack 纯运动跟踪器

    算法流程：
    1. 用卡尔曼滤波预测所有跟踪目标位置
    2. 用匈牙利算法匹配检测和跟踪（基于IoU）
    3. 未匹配的高分检测创建新跟踪
    4. 未匹配的跟踪用预测值更新（最多max_age帧）

    特点：
    - 纯运动跟踪，不依赖外观特征
    - 适合俯视角度（外观不明显）
    - 人做动作时ID稳定（只要中心点位置相近）
    """

    def __init__(
        self,
        track_thresh: float = 0.3,  # 检测分数阈值（降低以接受更多检测）
        match_thresh: float = 0.3,  # 匹配阈值（IoU，降低以更容易匹配）
        track_buffer: int = 50,  # 丢失后保留帧数（增加）
        frame_rate: int = 30,  # 帧率
    ):
        self.track_thresh = track_thresh
        self.match_thresh = match_thresh
        self.max_time_lost = track_buffer
        self.frame_id = 0
        self.next_id = 1

        # 跟踪列表
        self.tracked_tracks: List[Track] = []  # 已确认的跟踪
        self.lost_tracks: List[Track] = []  # 丢失的跟踪
        self.removed_tracks: List[Track] = []  # 已删除的跟踪

    def update(self, detections: List[Tuple[np.ndarray, float]]) -> List[Track]:
        """
        更新跟踪器

        Args:
            detections: 列表，每项为 (bbox, score)
                       bbox: [x1, y1, x2, y2]

        Returns:
            当前所有活跃的跟踪对象
        """
        self.frame_id += 1

        # 1. 预测所有跟踪位置
        for track in self.tracked_tracks:
            track.predict()

        # 2. 合并跟踪列表（已确认 + 丢失的）
        tracks = self.tracked_tracks + self.lost_tracks
        tracked_len = len(self.tracked_tracks)  # 记录 tracked 数量，用于区分 track 类型

        # 3. 分离高低分检测
        dets_high = []
        dets_low = []
        for i, (bbox, score) in enumerate(detections):
            if score >= self.track_thresh:
                dets_high.append((i, bbox, score))
            else:
                dets_low.append((i, bbox, score))

        # 4. 第一次匹配：高分检测 vs 所有跟踪
        matched, unmatched_dets, unmatched_tracks = self._match(
            tracks, [d[1] for d in dets_high]
        )

        print(
            f"[ByteTrack] Frame {self.frame_id}: {len(tracks)} tracks, {len(dets_high)} high dets"
        )
        print(
            f"[ByteTrack]   Matched: {len(matched)}, Unmatched dets: {len(unmatched_dets)}, Unmatched tracks: {len(unmatched_tracks)}"
        )

        # 更新匹配的跟踪
        for det_idx, track_idx in matched:
            track = tracks[track_idx]
            det_bbox = dets_high[det_idx][1]
            det_score = dets_high[det_idx][2]
            track.update(det_bbox, det_score)
            print(f"[ByteTrack]   Updated track {track.track_id}")

        # 5. 第二次匹配：未匹配的跟踪 vs 低分检测
        if unmatched_tracks and dets_low:
            remaining_tracks = [tracks[i] for i in unmatched_tracks]
            matched2, unmatched_dets2, unmatched_tracks2 = self._match(
                remaining_tracks, [d[1] for d in dets_low]
            )

            for det_idx, track_idx in matched2:
                track = remaining_tracks[track_idx]
                det_bbox = dets_low[det_idx][1]
                det_score = dets_low[det_idx][2]
                track.update(det_bbox, det_score)

            # 未匹配的跟踪标记为丢失
            for track_idx in unmatched_tracks2:
                track = remaining_tracks[track_idx]
                # 只有 lost tracks 需要增加计数（tracked 已在 predict 中加过）
                original_idx = unmatched_tracks[track_idx]
                if original_idx >= tracked_len:
                    track.time_since_update += 1
                if track.time_since_update > self.max_time_lost:
                    track.mark_deleted()
        else:
            # 没有低分检测，未匹配的直接标记为丢失
            # 注意：只有 lost tracks 需要增加计数（tracked 已在 predict 中加过）
            for track_idx in unmatched_tracks:
                track = tracks[track_idx]
                # track_idx >= tracked_len 说明是 lost track
                if track_idx >= tracked_len:
                    track.time_since_update += 1
                if track.time_since_update > self.max_time_lost:
                    track.mark_deleted()

        # 6. 未匹配的高分检测创建新跟踪
        for det_idx in unmatched_dets:
            det_bbox = dets_high[det_idx][1]
            det_score = dets_high[det_idx][2]
            self._create_track(det_bbox, det_score)

        # 7. 更新跟踪列表
        # 先保存当前所有未删除的跟踪（合并 tracked + lost + 新创建的）
        all_tracks = [
            t for t in self.tracked_tracks + self.lost_tracks if not t.is_deleted
        ]

        # 分离为 tracked（刚更新）和 lost（未匹配）
        self.tracked_tracks = [t for t in all_tracks if t.time_since_update == 0]
        self.lost_tracks = [t for t in all_tracks if t.time_since_update > 0]

        # 8. 返回结果
        output_tracks = self.tracked_tracks + self.lost_tracks
        return output_tracks

    def _match(
        self, tracks: List[Track], detections: List[np.ndarray]
    ) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
        """
        使用匈牙利算法匹配跟踪和检测
        改进：同时使用 IoU 和中心点距离，更宽容的匹配

        Returns:
            matched: [(det_idx, track_idx), ...]
            unmatched_detections: [det_idx, ...]
            unmatched_tracks: [track_idx, ...]
        """
        if len(tracks) == 0 or len(detections) == 0:
            return [], list(range(len(detections))), list(range(len(tracks)))

        # 计算代价矩阵（综合考虑 IoU 和中心点距离）
        cost_matrix = np.zeros((len(detections), len(tracks)))
        for i, det_bbox in enumerate(detections):
            det_center = (
                (det_bbox[0] + det_bbox[2]) / 2,
                (det_bbox[1] + det_bbox[3]) / 2,
            )
            for j, track in enumerate(tracks):
                # IoU 代价（使用原始 bbox，不是预测的）
                iou = self._compute_iou(det_bbox, track.bbox)
                iou_cost = 1 - iou

                # 中心点距离代价（归一化到 0-1）
                dist = np.sqrt(
                    (det_center[0] - track.center[0]) ** 2
                    + (det_center[1] - track.center[1]) ** 2
                )
                # 假设最大距离为 200 像素
                dist_cost = min(dist / 200.0, 1.0)

                # 综合代价：IoU 权重 0.5，距离权重 0.5
                # 这样即使 BBox 形状变化很大，只要中心点接近就能匹配
                cost_matrix[i, j] = iou_cost * 0.5 + dist_cost * 0.5

        # 匈牙利算法
        from scipy.optimize import linear_sum_assignment

        det_indices, track_indices = linear_sum_assignment(cost_matrix)

        matched = []
        unmatched_dets = list(range(len(detections)))
        unmatched_tracks = list(range(len(tracks)))

        for det_idx, track_idx in zip(det_indices, track_indices):
            # 宽松的匹配条件：代价 < 0.7（对应 IoU > 0.3 或距离 < 140px）
            if cost_matrix[det_idx, track_idx] < 0.7:
                matched.append((det_idx, track_idx))
                unmatched_dets.remove(det_idx)
                unmatched_tracks.remove(track_idx)

                # 打印匹配信息
                iou = self._compute_iou(detections[det_idx], tracks[track_idx].bbox)
                print(
                    f"[ByteTrack Match] Track {tracks[track_idx].track_id}: IoU={iou:.2f}, cost={cost_matrix[det_idx, track_idx]:.2f}"
                )

        return matched, unmatched_dets, unmatched_tracks

    def _compute_iou(self, box1: np.ndarray, box2: np.ndarray) -> float:
        """计算IoU"""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])

        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - inter

        return inter / union if union > 0 else 0

    def _create_track(self, bbox: np.ndarray, score: float):
        """创建新跟踪"""
        track = Track(
            track_id=self.next_id,
            bbox=bbox.copy(),
            score=score,
        )
        self.next_id += 1
        self.tracked_tracks.append(track)
        print(f"[ByteTrack] *** NEW TRACK {track.track_id} ***")

    def reset(self):
        """重置跟踪器"""
        self.frame_id = 0
        self.next_id = 1
        self.tracked_tracks.clear()
        self.lost_tracks.clear()
        self.removed_tracks.clear()


# ============ 用于替换 DeepSort 的接口适配器 ============


class ByteTrackWrapper:
    """
    ByteTrack 包装器，提供与 DeepSort 兼容的接口

    可以直接替换 violation_checker.py 中的 DeepSort
    """

    def __init__(
        self, max_age: int = 30, min_hits: int = 3, match_thresh: float = 0.5, **kwargs
    ):
        """
        参数兼容 DeepSort 的接口

        Args:
            max_age: 最大丢失帧数（对应 ByteTrack 的 track_buffer）
            min_hits: 最小确认帧数（ByteTrack 不需要，但保留接口兼容）
            match_thresh: 匹配阈值（IoU）
        """
        self.tracker = ByteTrack(
            track_thresh=0.5,
            match_thresh=match_thresh,
            track_buffer=max_age,
        )
        self.min_hits = min_hits

    def update_tracks(
        self, detections: List[Tuple[List[float], float, int]], frame=None
    ) -> List:
        """
        更新跟踪（兼容 DeepSort 的接口）

        Args:
            detections: [(bbox, confidence, class_id), ...]
                       bbox: [x1, y1, x2, y2]
            frame: 图像帧（ByteTrack 不需要，但为了接口兼容保留）

        Returns:
            跟踪对象列表，每个对象有 track_id, bbox 等属性
        """
        # 转换为 ByteTrack 格式
        dets = []
        for bbox, conf, _ in detections:
            dets.append((np.array(bbox), conf))

        # 更新跟踪
        tracks = self.tracker.update(dets)

        return tracks

    def reset(self):
        """重置跟踪器"""
        self.tracker.reset()


# ============ 使用示例 ============


def example_usage():
    """使用示例"""
    tracker = ByteTrackWrapper(max_age=30)

    # 模拟数据：同一个人站在原地，BBox 略有变化
    print("=== 模拟同一个人站在原地做动作 ===\n")

    for frame_id in range(10):
        # BBox 轻微抖动（模拟做动作）
        bbox = [
            100 + np.random.randint(-10, 10),  # x1
            100 + np.random.randint(-10, 10),  # y1
            200 + np.random.randint(-10, 10),  # x2
            300 + np.random.randint(-10, 10),  # y2
        ]

        detections = [(bbox, 0.9, 0)]  # (bbox, confidence, class_id)
        tracks = tracker.update_tracks(detections, frame=None)

        if tracks:
            print(f"Frame {frame_id}: Track ID = {tracks[0].track_id}")

    print("\n=== 测试完成 ===")
    print("如果ID保持为1，说明跟踪稳定！")


if __name__ == "__main__":
    example_usage()
