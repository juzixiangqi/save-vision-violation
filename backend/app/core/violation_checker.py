import numpy as np
from typing import List, Tuple, Optional, Dict
from datetime import datetime
from dataclasses import dataclass

from app.core.detector import Detection, Pose
from app.core.state_machine import StateMachine, PersonState
from app.core.zone_manager import zone_manager
from app.core.kalman import BoxKalmanFilter
from app.utils.helpers import (
    calculate_iou,
    calculate_distance,
    is_carrying_pose,
    calculate_velocity,
    calculate_variance,
    calculate_center,
)
from app.config.manager import config_manager


@dataclass
class LiftEvent:
    person_id: str
    box_id: str
    origin_zone: str
    timestamp: datetime


@dataclass
class DropEvent:
    person_id: str
    drop_zone: str
    timestamp: datetime
    is_violation: bool = False
    origin_zone: Optional[str] = None


class ViolationChecker:
    """违规检测器 - 核心逻辑"""

    def __init__(self):
        self.state_machine = StateMachine()
        self.box_trackers: Dict[str, BoxKalmanFilter] = {}
        self.box_positions: Dict[str, List[Tuple[float, float]]] = {}
        self.last_frame_data = {}
        self.config = config_manager.get_config()
        self.frame_buffer = {}  # person_id -> consecutive_frames_count

    def process_frame(
        self,
        persons: List[Detection],
        poses: List[Pose],
        boxes: List[Detection],
        camera_id: str = "default",
    ) -> List[Dict]:
        """
        处理一帧数据，检测违规
        返回违规事件列表
        """
        violations = []
        current_time = datetime.now()

        # 更新箱子跟踪
        self._update_box_tracking(boxes)

        # 处理每个人
        for person in persons:
            person_id = person.id
            person_center = person.center

            # 查找对应姿态
            pose = self._find_pose_for_person(person, poses)

            # 获取当前区域
            current_zone = zone_manager.get_zone_at_point(person_center)
            current_zone_id = current_zone.id if current_zone else None

            # 更新位置历史
            self.state_machine.update_position(
                person_id, person_center, current_zone_id
            )

            # 获取人员状态
            person_state = self.state_machine.get_person_state(person_id)

            if person_state is None or person_state.state == PersonState.IDLE:
                # 尝试检测搬起事件
                lift_event = self._detect_lift_event(
                    person, pose, boxes, current_zone_id
                )
                if lift_event:
                    self.state_machine.transition_to_carrying(
                        person_id, lift_event.origin_zone, lift_event.box_id
                    )
                    print(
                        f"[LIFT] Person {person_id} lifted box {lift_event.box_id} from {lift_event.origin_zone}"
                    )

            elif person_state.state == PersonState.CARRYING:
                # 检查是否遮挡
                if self._is_occluded(person, boxes, person_state.locked_box_id):
                    self.state_machine.transition_to_occluded(person_id)
                    print(f"[OCCLUSION] Person {person_id} occluded")
                else:
                    # 检查是否放下
                    drop_event = self._detect_drop_event(
                        person, pose, boxes, person_state
                    )
                    if drop_event:
                        violation_data = self.state_machine.transition_to_idle(
                            person_id, drop_event.drop_zone
                        )
                        if violation_data:
                            violation_data["camera_id"] = camera_id
                            violation_data["confidence"] = 0.9
                            violations.append(violation_data)
                            print(
                                f"[VIOLATION] Person {person_id}: {violation_data['origin_zone']} -> {drop_event.drop_zone}"
                            )

            elif person_state.state == PersonState.OCCLUDED:
                # 检查遮挡超时
                if self.state_machine.check_occlusion_timeout(
                    person_id,
                    self.config.detection_params.drop_detection.occlusion_timeout,
                ):
                    # 超时强制放下
                    violation_data = self.state_machine.transition_to_idle(
                        person_id, current_zone_id
                    )
                    if violation_data:
                        violation_data["camera_id"] = camera_id
                        violations.append(violation_data)
                        print(
                            f"[VIOLATION-TIMEOUT] Person {person_id}: {violation_data['origin_zone']} -> {current_zone_id}"
                        )
                else:
                    # 尝试重识别箱子
                    if self._reidentify_box(person, boxes, person_state.locked_box_id):
                        self.state_machine.transition_from_occluded(person_id)
                        print(f"[REIDENTIFY] Person {person_id} box reidentified")
                    else:
                        # 检查是否放下（通过姿态）
                        drop_event = self._detect_drop_by_pose_only(
                            person, pose, current_zone_id
                        )
                        if drop_event:
                            violation_data = self.state_machine.transition_to_idle(
                                person_id, drop_event.drop_zone
                            )
                            if violation_data:
                                violation_data["camera_id"] = camera_id
                                violations.append(violation_data)

        self.last_frame_data = {"persons": persons, "poses": poses, "boxes": boxes}

        return violations

    def _find_pose_for_person(
        self, person: Detection, poses: List[Pose]
    ) -> Optional[Pose]:
        """为人员找到对应的姿态"""
        person_center = calculate_center(person.bbox)
        best_pose = None
        min_distance = float("inf")

        for pose in poses:
            pose_center = calculate_center(pose.bbox)
            dist = calculate_distance(person_center, pose_center)
            if dist < min_distance and dist < 100:  # 100像素阈值
                min_distance = dist
                best_pose = pose

        return best_pose

    def _update_box_tracking(self, boxes: List[Detection]):
        """更新箱子跟踪"""
        for box in boxes:
            if box.id not in self.box_trackers:
                self.box_trackers[box.id] = BoxKalmanFilter()
                self.box_trackers[box.id].init(box.center[0], box.center[1])
                self.box_positions[box.id] = []
            else:
                self.box_trackers[box.id].update(box.center[0], box.center[1])

            self.box_positions[box.id].append(box.center)
            if len(self.box_positions[box.id]) > 10:
                self.box_positions[box.id] = self.box_positions[box.id][-10:]

    def _detect_lift_event(
        self,
        person: Detection,
        pose: Optional[Pose],
        boxes: List[Detection],
        current_zone: Optional[str],
    ) -> Optional[LiftEvent]:
        """检测搬起事件"""
        if not pose or not current_zone:
            return None

        params = self.config.detection_params.lift_detection

        # 检查姿态
        if not is_carrying_pose(pose.keypoints, params.model_dump()):
            return None

        # 查找人员下方的箱子
        person_box = self._find_box_below_person(person, boxes)
        if not person_box:
            return None

        # 检查箱子是否在运动
        if not self._is_box_moving(person_box.id):
            return None

        # 防抖：需要连续多帧满足条件
        person_id = person.id
        if person_id not in self.frame_buffer:
            self.frame_buffer[person_id] = 0

        self.frame_buffer[person_id] += 1

        if self.frame_buffer[person_id] >= params.consecutive_frames:
            self.frame_buffer[person_id] = 0
            return LiftEvent(
                person_id=person_id,
                box_id=person_box.id,
                origin_zone=current_zone,
                timestamp=datetime.now(),
            )

        return None

    def _detect_drop_event(
        self,
        person: Detection,
        pose: Optional[Pose],
        boxes: List[Detection],
        person_state,
    ) -> Optional[DropEvent]:
        """检测放下事件"""
        if not pose:
            return None

        params = self.config.detection_params.drop_detection
        current_zone = zone_manager.get_zone_at_point(person.center)
        current_zone_id = current_zone.id if current_zone else None

        # 方法1: 通过姿态检测（手快速上升且张开）
        if self._detect_drop_by_pose(pose, params):
            return DropEvent(
                person_id=person.id, drop_zone=current_zone_id, timestamp=datetime.now()
            )

        # 方法2: 通过IoU检测（人箱分离）
        locked_box = self._find_box_by_id(boxes, person_state.locked_box_id)
        if locked_box:
            iou = calculate_iou(person.bbox, locked_box.bbox)
            if iou < params.iou_drop_threshold:
                return DropEvent(
                    person_id=person.id,
                    drop_zone=current_zone_id,
                    timestamp=datetime.now(),
                )

        return None

    def _detect_drop_by_pose_only(
        self, person: Detection, pose: Optional[Pose], current_zone_id: Optional[str]
    ) -> Optional[DropEvent]:
        """仅通过姿态检测放下（用于遮挡期间）"""
        if not pose:
            return None

        params = self.config.detection_params.drop_detection

        if self._detect_drop_by_pose(pose, params):
            return DropEvent(
                person_id=person.id, drop_zone=current_zone_id, timestamp=datetime.now()
            )

        return None

    def _detect_drop_by_pose(self, pose: Pose, params) -> bool:
        """通过姿态判断是否为放下动作"""
        # 获取手腕位置
        left_wrist = pose.keypoints[9, :2]
        right_wrist = pose.keypoints[10, :2]

        # 检查双手是否快速上升
        left_hip = pose.keypoints[11, :2]
        right_hip = pose.keypoints[12, :2]
        avg_hip_y = (left_hip[1] + right_hip[1]) / 2

        avg_wrist_y = (left_wrist[1] + right_wrist[1]) / 2
        hands_distance = calculate_distance(tuple(left_wrist), tuple(right_wrist))

        # 手在臀部上方且距离大于阈值（张开）
        hands_up = avg_wrist_y < avg_hip_y - params.hands_rise_threshold
        hands_open = hands_distance > 200  # 双手张开的阈值

        return hands_up and hands_open

    def _find_box_below_person(
        self, person: Detection, boxes: List[Detection]
    ) -> Optional[Detection]:
        """查找人员下方的箱子"""
        person_center = person.center
        best_box = None
        min_distance = float("inf")

        for box in boxes:
            # 检查箱子是否在人员下方（y坐标更大）
            if box.center[1] > person_center[1]:
                dist = calculate_distance(person_center, box.center)
                if dist < min_distance and dist < 150:  # 150像素阈值
                    min_distance = dist
                    best_box = box

        return best_box

    def _find_box_by_id(
        self, boxes: List[Detection], box_id: str
    ) -> Optional[Detection]:
        """通过ID查找箱子"""
        for box in boxes:
            if box.id == box_id:
                return box
        return None

    def _is_box_moving(self, box_id: str) -> bool:
        """判断箱子是否在运动"""
        if box_id not in self.box_positions:
            return False

        positions = self.box_positions[box_id]
        if len(positions) < 2:
            return False

        # 计算速度方差
        velocities = []
        for i in range(1, len(positions)):
            vx = positions[i][0] - positions[i - 1][0]
            vy = positions[i][1] - positions[i - 1][1]
            velocities.append(np.sqrt(vx**2 + vy**2))

        variance = calculate_variance(velocities)
        threshold = self.config.detection_params.lift_detection.speed_variance_threshold

        return variance > threshold

    def _is_occluded(
        self, person: Detection, boxes: List[Detection], locked_box_id: str
    ) -> bool:
        """检查箱子是否被遮挡"""
        for box in boxes:
            if box.id == locked_box_id:
                iou = calculate_iou(person.bbox, box.bbox)
                return iou < 0.1

        return True

    def _reidentify_box(
        self, person: Detection, boxes: List[Detection], locked_box_id: str
    ) -> bool:
        """重识别箱子"""
        if locked_box_id not in self.box_trackers:
            return False

        predicted_pos = self.box_trackers[locked_box_id].predict()

        for box in boxes:
            dist = calculate_distance(predicted_pos, box.center)
            if dist < 100:
                box.id = locked_box_id
                self.box_trackers[locked_box_id].update(box.center[0], box.center[1])
                return True

        return False
