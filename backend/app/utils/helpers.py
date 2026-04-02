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
    """判断是否为搬运姿态（严格版本）"""
    # 检查手是否在臀部下方
    hands_below = is_hands_below_hips(keypoints)

    # 检查双手距离是否小于阈值（环抱）
    hands_dist = calculate_hands_distance(keypoints)
    hands_close = hands_dist < params.get("hands_distance_threshold", 150)

    return hands_below and hands_close


def is_carrying_pose_relaxed(
    keypoints: np.ndarray, hands_distance_threshold: float = 200
) -> bool:
    """
    判断是否为搬运姿态（宽松版本）

    条件（满足任意一条即认为可能搬起）：
    1. 双手距离较近（可能在抱箱子）
    2. 至少有一只手在身前（x坐标在肩膀之间）且距离身体中心较近
    3. 双手高度在腰部到肩膀之间

    这个版本宁可误报也要确保检测到搬起动作
    """
    LEFT_WRIST = 9
    RIGHT_WRIST = 10
    LEFT_SHOULDER = 5
    RIGHT_SHOULDER = 6
    LEFT_HIP = 11
    RIGHT_HIP = 12

    left_wrist = keypoints[LEFT_WRIST, :2]
    right_wrist = keypoints[RIGHT_WRIST, :2]
    left_shoulder = keypoints[LEFT_SHOULDER, :2]
    right_shoulder = keypoints[RIGHT_SHOULDER, :2]
    left_hip = keypoints[LEFT_HIP, :2]
    right_hip = keypoints[RIGHT_HIP, :2]

    # 条件1: 双手距离较近
    hands_dist = calculate_distance(tuple(left_wrist), tuple(right_wrist))
    hands_close = hands_dist < hands_distance_threshold

    # 条件2: 双手在腰部和肩膀之间的高度
    avg_shoulder_y = (left_shoulder[1] + right_shoulder[1]) / 2
    avg_hip_y = (left_hip[1] + right_hip[1]) / 2
    avg_wrist_y = (left_wrist[1] + right_wrist[1]) / 2

    hands_at_mid_height = avg_hip_y - 50 <= avg_wrist_y <= avg_shoulder_y + 50

    # 条件3: 至少一只手在身前（通过x坐标判断，如果在两肩之间）
    min_shoulder_x = min(left_shoulder[0], right_shoulder[0])
    max_shoulder_x = max(left_shoulder[0], right_shoulder[0])

    left_hand_in_front = min_shoulder_x - 100 <= left_wrist[0] <= max_shoulder_x + 100
    right_hand_in_front = min_shoulder_x - 100 <= right_wrist[0] <= max_shoulder_x + 100

    # 宽松条件：满足(双手靠近) 或 (手在中部高度且在身前)
    is_carrying = hands_close or (
        hands_at_mid_height and (left_hand_in_front or right_hand_in_front)
    )

    return is_carrying


def is_dropping_pose_relaxed(
    keypoints: np.ndarray,
    hands_rise_threshold: float = 50,
    hands_apart_threshold: float = 150,
) -> bool:
    """
    判断是否为放下姿态（宽松版本）

    条件（满足任意一条即认为可能放下）：
    1. 双手明显分开（距离很大）
    2. 双手都在肩膀以上
    3. 双手都在臀部以下且距离较远

    这个版本宁可误报也要确保检测到放下动作
    """
    LEFT_WRIST = 9
    RIGHT_WRIST = 10
    LEFT_SHOULDER = 5
    RIGHT_SHOULDER = 6
    LEFT_HIP = 11
    RIGHT_HIP = 12

    left_wrist = keypoints[LEFT_WRIST, :2]
    right_wrist = keypoints[RIGHT_WRIST, :2]
    left_shoulder = keypoints[LEFT_SHOULDER, :2]
    right_shoulder = keypoints[RIGHT_SHOULDER, :2]
    left_hip = keypoints[LEFT_HIP, :2]
    right_hip = keypoints[RIGHT_HIP, :2]

    # 条件1: 双手距离大（分开）
    hands_dist = calculate_distance(tuple(left_wrist), tuple(right_wrist))
    hands_apart = hands_dist > hands_apart_threshold

    # 条件2: 双手在肩膀以上
    avg_shoulder_y = (left_shoulder[1] + right_shoulder[1]) / 2
    left_hand_up = left_wrist[1] < avg_shoulder_y - hands_rise_threshold
    right_hand_up = right_wrist[1] < avg_shoulder_y - hands_rise_threshold
    hands_above_shoulders = left_hand_up and right_hand_up

    # 条件3: 双手在臀部以下且距离较远（松手后手自然下垂且分开）
    avg_hip_y = (left_hip[1] + right_hip[1]) / 2
    left_hand_down = left_wrist[1] > avg_hip_y + 20
    right_hand_down = right_wrist[1] > avg_hip_y + 20
    hands_below_hips = left_hand_down and right_hand_down
    hands_apart_below = hands_dist > hands_apart_threshold * 0.8

    # 宽松条件：满足(双手分开) 或 (手在肩膀以上) 或 (手在臀部以下且分开)
    is_dropping = (
        hands_apart or hands_above_shoulders or (hands_below_hips and hands_apart_below)
    )

    return is_dropping
