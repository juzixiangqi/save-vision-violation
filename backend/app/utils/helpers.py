import numpy as np
from typing import List, Tuple


def calculate_iou(box1: List[float], box2: List[float]) -> float:
    """计算两个边界框的IoU"""
    x1_1, y1_1, x2_1, y2_1 = box1
    x1_2, y1_2, x2_2, y2_2 = box2

    # 计算交集
    x1_i = max(x1_1, x1_2)
    y1_i = max(y1_1, y1_2)
    x2_i = min(x2_1, x2_2)
    y2_i = min(y2_1, y2_2)

    if x2_i <= x1_i or y2_i <= y1_i:
        return 0.0

    intersection = (x2_i - x1_i) * (y2_i - y1_i)

    # 计算并集
    area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
    area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
    union = area1 + area2 - intersection

    return intersection / union if union > 0 else 0.0


def calculate_distance(
    point1: Tuple[float, float], point2: Tuple[float, float]
) -> float:
    """计算两点之间的欧氏距离"""
    return np.sqrt((point1[0] - point2[0]) ** 2 + (point1[1] - point2[1]) ** 2)


def calculate_center(bbox: List[float]) -> Tuple[float, float]:
    """计算边界框中心点"""
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def calculate_velocity(
    positions: List[Tuple[float, float]], dt: float = 1.0
) -> Tuple[float, float]:
    """计算速度 (使用最近2帧)"""
    if len(positions) < 2:
        return (0.0, 0.0)

    p1 = positions[-2]
    p2 = positions[-1]
    vx = (p2[0] - p1[0]) / dt
    vy = (p2[1] - p1[1]) / dt
    return (vx, vy)


def calculate_variance(values: List[float]) -> float:
    """计算方差"""
    if len(values) < 2:
        return 0.0
    return np.var(values)


def is_hands_below_hips(keypoints: np.ndarray) -> bool:
    """判断双手是否在臀部下方"""
    # 关键点索引
    LEFT_WRIST = 9
    RIGHT_WRIST = 10
    LEFT_HIP = 11
    RIGHT_HIP = 12

    left_wrist_y = keypoints[LEFT_WRIST, 1]
    right_wrist_y = keypoints[RIGHT_WRIST, 1]
    left_hip_y = keypoints[LEFT_HIP, 1]
    right_hip_y = keypoints[RIGHT_HIP, 1]

    avg_wrist_y = (left_wrist_y + right_wrist_y) / 2
    avg_hip_y = (left_hip_y + right_hip_y) / 2

    return avg_wrist_y > avg_hip_y


def calculate_hands_distance(keypoints: np.ndarray) -> float:
    """计算双手之间的距离"""
    LEFT_WRIST = 9
    RIGHT_WRIST = 10

    left_wrist = keypoints[LEFT_WRIST, :2]
    right_wrist = keypoints[RIGHT_WRIST, :2]

    return calculate_distance(tuple(left_wrist), tuple(right_wrist))


def is_carrying_pose(keypoints: np.ndarray, params: dict) -> bool:
    """判断是否为搬运姿态"""
    # 检查手是否在臀部下方
    hands_below = is_hands_below_hips(keypoints)

    # 检查双手距离是否小于阈值（环抱）
    hands_dist = calculate_hands_distance(keypoints)
    hands_close = hands_dist < params.get("hands_distance_threshold", 150)

    return hands_below and hands_close
