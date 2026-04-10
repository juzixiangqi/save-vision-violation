import numpy as np
from typing import List, Tuple, Optional, Dict
from datetime import datetime
from dataclasses import dataclass

from app.core.detector import Detection, Pose
from app.core.state_machine import StateMachine, PersonState
from app.core.zone_manager import zone_manager
from app.core.kalman import BoxKalmanFilter
from app.core.byte_tracker import ByteTrackWrapper  # 使用 ByteTrack
from app.utils.helpers import (
    calculate_iou,
    calculate_distance,
    is_carrying_pose_overhead,
    is_dropping_pose_relaxed,
    calculate_velocity,
    calculate_variance,
    calculate_center,
    calculate_bottom_center,
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
        """
        初始化违规检测器
        """
        self.state_machine = StateMachine()
        # 使用 ByteTrack 纯运动跟踪（不依赖外观特征）
        self.person_tracker = ByteTrackWrapper(
            max_age=50,  # 增加最大丢失帧数
            min_hits=1,  # 降低确认阈值，第1帧就确认
            match_thresh=0.3,  # 降低匹配阈值，提高跟踪稳定性
            track_thresh=0.3,  # 降低检测分数阈值，适应YOLO-pose的confidence
        )
        # 箱子追踪器（使用 ByteTrack）
        self.box_tracker = ByteTrackWrapper(
            max_age=50,
            min_hits=1,
            match_thresh=0.3,
            track_thresh=0.3,
        )
        self.box_trackers: Dict[str, BoxKalmanFilter] = {}
        self.box_positions: Dict[str, List[Tuple[float, float]]] = {}
        self.box_trajectories: Dict[
            str, List[Tuple[float, float]]
        ] = {}  # 追踪ID -> 轨迹列表
        self.box_id_counter = 0
        self.box_id_mapping = {}  # 原始ID -> 追踪ID 映射
        self.last_frame_data = {}
        self.config = config_manager.get_config()
        self.frame_buffer = {}  # person_id -> consecutive_frames_count

    def process_frame(
        self,
        poses: List[Pose],
        boxes: List[Detection],
        camera_id: str = "default",
        frame: np.ndarray = None,
    ) -> Tuple[List[Dict], Dict[str, str], Dict[str, any]]:
        """
        处理一帧数据，检测违规（使用姿态数据，包含bbox和关键点）
        返回违规事件列表、track_id 到 pose_id 的映射，以及箱子追踪信息

        改进点：
        1. 使用人员跟踪器实现跨帧跟踪
        2. 使用箱子跟踪器为箱子分配稳定的追踪ID
        3. 记录被搬运箱子的轨迹
        4. 可选使用宽松的搬起/放下检测条件
        """
        violations = []
        track_to_pose_mapping = {}  # track_id -> pose_id 映射，用于可视化
        current_time = datetime.now()

        # 使用 ByteTrack 追踪箱子
        tracked_boxes, box_id_mapping = self._track_boxes_with_byte_track(boxes)

        # 更新箱子跟踪（使用追踪后的ID）
        self._update_box_tracking(tracked_boxes)

        # 使用 DeepSort 进行人员追踪
        detections_for_tracking = []
        for pose in poses:
            # DeepSort 需要 [x1, y1, x2, y2] 格式的 bbox，class_id 为 0
            bbox = pose.bbox  # 已经是 [x1, y1, x2, y2] 格式
            confidence = pose.confidence
            detections_for_tracking.append((bbox, confidence, 0))  # class_id=0 表示人

        tracks = self.person_tracker.update_tracks(detections_for_tracking, frame=frame)

        # 获取当前所有被搬运的箱子ID（用于轨迹记录）
        carried_box_ids = set()
        for person_id, person_data in self.state_machine.persons.items():
            if person_data.locked_box_id:
                carried_box_ids.add(person_data.locked_box_id)

        # 处理每个跟踪到的人员
        for track in tracks:
            # 暂时不跳过未确认的跟踪，看看问题在哪
            if not track.is_confirmed():
                print(f"[Debug] Track {track.track_id} not confirmed, skipping")
                continue

            person_id = str(track.track_id)
            bbox = track.to_tlbr()  # [x1, y1, x2, y2]
            # 计算底部中点（用于区域判定）和中心点（用于其他功能）
            person_bottom_center = calculate_bottom_center(bbox)
            person_center = calculate_center(bbox)
            person_bbox = bbox

            print(
                f"[Debug] Processing person {person_id} at bottom {person_bottom_center}"
            )

            # 找到对应的姿态
            person_keypoints = None
            person_confidence = 0.0
            matched_pose = None
            for pose in poses:
                # 使用姿态bbox的底部中点进行比较
                pose_bottom_center = calculate_bottom_center(pose.bbox)
                if (
                    calculate_distance(person_bottom_center, pose_bottom_center) < 50
                ):  # 50像素阈值
                    person_keypoints = pose.keypoints
                    person_confidence = pose.confidence
                    matched_pose = pose
                    break

            # 记录 track_id 到 pose_id 的映射
            if matched_pose:
                track_to_pose_mapping[person_id] = matched_pose.id

            # 获取当前区域（使用底部中点）
            current_zone = zone_manager.get_zone_at_point(person_bottom_center)
            current_zone_id = current_zone.id if current_zone else None

            # 获取人员状态（用于区域记忆）
            person_state = self.state_machine.get_person_state(person_id)

            # 区域记忆：如果当前无区域但有上一个已知区域，则使用上一个区域
            if (
                current_zone_id is None
                and person_state
                and person_state.last_known_zone
            ):
                current_zone_id = person_state.last_known_zone
                print(
                    f"[Zone Memory] Person {person_id}: using last known zone {current_zone_id}"
                )
            elif current_zone_id is not None:
                # 更新上一个已知区域
                if person_state:
                    person_state.last_known_zone = current_zone_id

            # 更新位置历史（使用底部中点作为位置）
            self.state_machine.update_position(
                person_id, person_bottom_center, current_zone_id
            )

            # 创建临时Detection对象用于兼容原有函数
            person_detection = Detection(
                id=person_id,
                bbox=person_bbox,
                confidence=person_confidence,
                class_id=0,
                class_name="person",
                center=person_center,
            )

            # 创建Pose对象
            pose = Pose(
                id=person_id,
                keypoints=person_keypoints,
                bbox=person_bbox,
                confidence=person_confidence,
            )

            if person_state is None or person_state.state == PersonState.IDLE:
                print(f"[Debug] Person {person_id} in IDLE state, checking lift")
                # 尝试检测搬起事件（使用追踪后的箱子）
                lift_event = self._detect_lift_event(
                    person_detection, pose, tracked_boxes, current_zone_id
                )
                if lift_event:
                    self.state_machine.transition_to_carrying(
                        person_id, lift_event.origin_zone, lift_event.box_id
                    )
                    print(
                        f"[LIFT] Person {person_id} lifted box {lift_event.box_id} from {lift_event.origin_zone}"
                    )
                else:
                    print(f"[Debug] No lift detected for person {person_id}")

            elif person_state.state == PersonState.CARRYING:
                # 记录被搬运箱子的轨迹
                if person_state.locked_box_id:
                    self._record_box_trajectory(
                        person_state.locked_box_id, tracked_boxes
                    )

                # 检查是否遮挡
                if self._is_occluded(
                    person_detection, tracked_boxes, person_state.locked_box_id
                ):
                    self.state_machine.transition_to_occluded(person_id)
                    print(f"[OCCLUSION] Person {person_id} occluded")
                else:
                    # 检查是否放下
                    drop_event = self._detect_drop_event(
                        person_detection, pose, tracked_boxes, person_state
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
                    # 尝试重识别箱子（使用追踪后的箱子）
                    if self._reidentify_box(
                        person_detection, tracked_boxes, person_state.locked_box_id
                    ):
                        self.state_machine.transition_from_occluded(person_id)
                        print(f"[REIDENTIFY] Person {person_id} box reidentified")
                    else:
                        # 检查是否放下（通过姿态）
                        drop_event = self._detect_drop_by_pose_only(
                            person_detection, pose, current_zone_id
                        )
                        if drop_event:
                            violation_data = self.state_machine.transition_to_idle(
                                person_id, drop_event.drop_zone
                            )
                            if violation_data:
                                violation_data["camera_id"] = camera_id
                                violations.append(violation_data)

        # 构建箱子追踪信息
        box_tracking_info = {
            "tracked_boxes": tracked_boxes,
            "box_id_mapping": box_id_mapping,  # 原始ID -> 追踪ID
            "box_trajectories": self.box_trajectories,  # 追踪ID -> 轨迹列表
            "carried_box_ids": list(carried_box_ids),  # 被搬运的箱子ID列表
        }

        self.last_frame_data = {
            "poses": poses,
            "boxes": tracked_boxes,  # 使用追踪后的箱子
            "tracks": tracks,
            "track_to_pose_mapping": track_to_pose_mapping,
            "box_tracking_info": box_tracking_info,  # 添加箱子追踪信息
        }

        return violations, track_to_pose_mapping, box_tracking_info

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

    def _track_boxes_with_byte_track(
        self, boxes: List[Detection]
    ) -> Tuple[List[Detection], Dict[str, str]]:
        """
        使用 ByteTrack 追踪箱子

        Args:
            boxes: 原始检测到的箱子列表

        Returns:
            tracked_boxes: 追踪后的箱子列表（ID已更新为追踪ID）
            box_id_mapping: 原始ID到追踪ID的映射
        """
        if not boxes:
            return [], {}

        # 准备检测数据用于 ByteTrack
        detections_for_tracking = []
        for box in boxes:
            bbox = box.bbox  # [x1, y1, x2, y2]
            confidence = box.confidence
            detections_for_tracking.append((bbox, confidence, 1))  # class_id=1 表示箱子

        # 使用 ByteTrack 更新追踪
        tracks = self.box_tracker.update_tracks(detections_for_tracking)

        # 建立原始检测与追踪结果的对应关系
        tracked_boxes = []
        box_id_mapping = {}  # 原始ID -> 追踪ID

        # 为每个箱子找到对应的追踪结果
        for i, box in enumerate(boxes):
            # 找到最佳匹配的追踪结果
            best_track = None
            min_distance = float("inf")

            for track in tracks:
                if not track.is_confirmed():
                    continue

                track_bbox = track.to_tlbr()
                track_center = (
                    (track_bbox[0] + track_bbox[2]) / 2,
                    (track_bbox[1] + track_bbox[3]) / 2,
                )
                dist = calculate_distance(box.center, track_center)

                # 使用IoU和距离综合判断
                iou = self._compute_iou(box.bbox, track_bbox)
                if iou > 0.3 or dist < 100:  # IoU > 0.3 或距离 < 100px
                    if dist < min_distance:
                        min_distance = dist
                        best_track = track

            if best_track:
                track_id = str(best_track.track_id)
                box_id_mapping[box.id] = track_id

                # 创建新的 Detection 对象，使用追踪ID
                tracked_box = Detection(
                    id=track_id,
                    bbox=best_track.to_tlbr().tolist(),
                    confidence=box.confidence,
                    class_id=box.class_id,
                    class_name=box.class_name,
                    center=(
                        (best_track.to_tlbr()[0] + best_track.to_tlbr()[2]) / 2,
                        (best_track.to_tlbr()[1] + best_track.to_tlbr()[3]) / 2,
                    ),
                )
                tracked_boxes.append(tracked_box)
            else:
                # 没有匹配的追踪结果，保留原始ID
                tracked_boxes.append(box)
                box_id_mapping[box.id] = box.id

        return tracked_boxes, box_id_mapping

    def _compute_iou(self, box1: List[float], box2: np.ndarray) -> float:
        """计算两个边界框的IoU"""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])

        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - inter

        return inter / union if union > 0 else 0

    def _record_box_trajectory(self, box_id: str, tracked_boxes: List[Detection]):
        """记录箱子的轨迹（仅在箱子运动时）"""
        # 找到对应的箱子
        for box in tracked_boxes:
            if box.id == box_id:
                # 检查箱子是否在运动
                if not self._is_box_moving(box_id):
                    # 箱子静止，清空轨迹避免显示静止轨迹
                    if box_id in self.box_trajectories:
                        self.box_trajectories[box_id] = []
                    return

                # 记录轨迹点
                if box_id not in self.box_trajectories:
                    self.box_trajectories[box_id] = []

                self.box_trajectories[box_id].append(box.center)

                # 限制轨迹长度，保留最近30个点
                if len(self.box_trajectories[box_id]) > 30:
                    self.box_trajectories[box_id] = self.box_trajectories[box_id][-30:]

                break

    def _update_box_tracking(self, boxes: List[Detection]):
        """更新箱子跟踪（使用追踪后的ID）"""
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
        """
        检测搬起事件（宽松模式）
        """
        if not pose:
            print(f"[Debug Lift] No pose for person {person.id}")
            return None
        if not current_zone:
            print(f"[Debug Lift] No current zone for person {person.id}")
            return None
        if pose.keypoints is None:
            print(f"[Debug Lift] No keypoints for person {person.id}")
            return None

        person_id = person.id

        # 宽松模式：使用俯视版姿态检测
        is_lifting_pose = is_carrying_pose_overhead(
            pose.keypoints,
            hands_distance_threshold=250,  # 较大的距离阈值
        )

        print(f"[Debug Lift] Person {person_id} is_lifting_pose: {is_lifting_pose}")

        # 查找人员附近的箱子
        person_box = self._find_box_near_person(person, boxes, distance_threshold=200)

        if person_box:
            print(f"[Debug Lift] Found box {person_box.id} near person {person_id}")
        else:
            print(f"[Debug Lift] No box found near person {person_id}")

        # 宽松条件：只要姿态像搬起，且有箱子在附近即可
        if is_lifting_pose and person_box:
            # 增加连续帧计数（用于简单防抖）
            if person_id not in self.frame_buffer:
                self.frame_buffer[person_id] = 0
            self.frame_buffer[person_id] += 1

            # 只需连续2帧即可
            if self.frame_buffer[person_id] >= 2:
                self.frame_buffer[person_id] = 0
                print(
                    f"[Debug Lift] *** LIFT DETECTED: {person_id} -> {person_box.id} ***"
                )
                return LiftEvent(
                    person_id=person_id,
                    box_id=person_box.id,
                    origin_zone=current_zone,
                    timestamp=datetime.now(),
                )
            else:
                print(
                    f"[Debug Lift] Frame count {self.frame_buffer[person_id]}/2 for {person_id}"
                )
        else:
            # 重置帧计数
            if person_id in self.frame_buffer:
                self.frame_buffer[person_id] = 0

        return None

    def _detect_drop_event(
        self,
        person: Detection,
        pose: Optional[Pose],
        boxes: List[Detection],
        person_state,
    ) -> Optional[DropEvent]:
        """检测放下事件"""
        if not pose or pose.keypoints is None:
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
        if not pose or pose.keypoints is None:
            return None

        params = self.config.detection_params.drop_detection

        if self._detect_drop_by_pose(pose, params):
            return DropEvent(
                person_id=person.id, drop_zone=current_zone_id, timestamp=datetime.now()
            )

        return None

    def _detect_drop_by_pose(self, pose: Pose, params) -> bool:
        """
        通过姿态判断是否为放下动作（宽松模式）
        """
        return is_dropping_pose_relaxed(
            pose.keypoints,
            hands_rise_threshold=30,  # 更小的上升阈值
            hands_apart_threshold=120,  # 更小的张开阈值
        )

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

    def _find_box_near_person(
        self, person: Detection, boxes: List[Detection], distance_threshold: float = 200
    ) -> Optional[Detection]:
        """
        查找人员附近的箱子（不限制必须在下方）

        Args:
            person: 人员检测对象
            boxes: 箱子列表
            distance_threshold: 距离阈值（像素）

        Returns:
            距离最近的箱子，如果没有在阈值内的则返回None
        """
        person_center = person.center
        best_box = None
        min_distance = float("inf")

        for box in boxes:
            dist = calculate_distance(person_center, box.center)
            if dist < min_distance and dist < distance_threshold:
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
        self, person: Detection, boxes: List[Detection], locked_box_id: Optional[str]
    ) -> bool:
        """检查箱子是否被遮挡"""
        for box in boxes:
            if box.id == locked_box_id:
                iou = calculate_iou(person.bbox, box.bbox)
                return iou < 0.1

        return True

    def _reidentify_box(
        self, person: Detection, boxes: List[Detection], locked_box_id: Optional[str]
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
