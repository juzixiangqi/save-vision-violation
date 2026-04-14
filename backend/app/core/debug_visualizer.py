import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
import os
from app.core.detector import Detection, Pose, YOLODetector
from app.core.violation_checker import ViolationChecker
from app.core.zone_manager import zone_manager
from app.core.state_machine import PersonState
from app.config.manager import config_manager


def get_chinese_font(size: int = 20) -> Optional[ImageFont.FreeTypeFont]:
    """获取中文字体"""
    # 尝试常见的中文字体路径
    font_paths = [
        "C:/Windows/Fonts/simhei.ttf",  # 黑体
        "C:/Windows/Fonts/simsun.ttc",  # 宋体
        "C:/Windows/Fonts/msyh.ttc",  # 微软雅黑
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",  # Linux
        "/System/Library/Fonts/PingFang.ttc",  # macOS
    ]

    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except:
                continue

    # 如果找不到中文字体，使用默认字体
    return ImageFont.load_default()


def cv2_put_chinese_text(
    img: np.ndarray,
    text: str,
    position: Tuple[int, int],
    font_size: int = 20,
    color: Tuple[int, int, int] = (255, 255, 255),
) -> np.ndarray:
    """
    在OpenCV图像上绘制中文文本

    Args:
        img: OpenCV图像 (BGR格式)
        text: 要绘制的文本
        position: 文本左上角位置 (x, y)
        font_size: 字体大小
        color: 文本颜色 (B, G, R)

    Returns:
        绘制后的OpenCV图像
    """
    # OpenCV图像转为PIL图像
    pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)

    # 获取字体
    font = get_chinese_font(font_size)

    # 绘制文本
    draw.text(position, text, font=font, fill=color[::-1])  # RGB to BGR

    # PIL转回OpenCV
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


class DebugVisualizer:
    """调试可视化器 - 在图像上绘制检测结果"""

    # 颜色定义 (BGR格式)
    COLORS = {
        "person_bbox": (0, 255, 0),  # 绿色 - 人员框
        "box_bbox": (255, 165, 0),  # 橙色 - 箱子框
        "keypoint": (0, 255, 255),  # 黄色 - 关键点
        "keypoint_line": (255, 0, 0),  # 蓝色 - 骨架线
        "violation": (0, 0, 255),  # 红色 - 违规标记
        "zone": (128, 0, 128),  # 紫色 - 区域
        "text": (255, 255, 255),  # 白色 - 文字
        "info_bg": (0, 0, 0),  # 黑色 - 信息背景
    }

    # 关键点连接关系 (COCO格式)
    SKELETON = [
        [15, 13],
        [13, 11],  # 左腿
        [16, 14],
        [14, 12],  # 右腿
        [11, 12],  # 臀部
        [5, 11],
        [6, 12],  # 躯干
        [5, 6],  # 肩膀
        [5, 7],
        [7, 9],  # 左臂
        [6, 8],
        [8, 10],  # 右臂
        [1, 2],  # 眼睛
        [0, 1],
        [0, 2],  # 鼻子到眼睛
        [1, 3],
        [2, 4],  # 眼睛到耳朵
        [3, 5],
        [4, 6],  # 耳朵到肩膀
    ]

    def __init__(self, frame_width: int = 1280, frame_height: int = 720):
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.scale = min(frame_width / 1920, frame_height / 1080)

    def draw_detections(
        self,
        frame: np.ndarray,
        poses: List[Pose],
        boxes: List[Detection],
        violations: List[Dict],
        camera_id: str,
        frame_info: str = "",
        state_machine=None,
        track_to_pose_mapping: Dict[
            str, str
        ] = None,  # 新增：track_id 到 pose_id 的映射，默认为 None
        box_tracking_info: Dict = None,  # 新增：箱子追踪信息
    ) -> np.ndarray:
        """在帧上绘制所有检测结果"""
        img = frame.copy()

        # 绘制区域
        self._draw_zones(img)

        # 获取被抱起的箱子ID列表和违规箱子ID列表
        carried_box_ids = set()
        violation_box_ids = set()

        if state_machine:
            # 从状态机获取追踪中的人员（新的状态机没有 locked_box_id）
            carried_box_ids = set()

        # 从违规列表获取违规箱子
        for violation in violations:
            if violation.get("box_id"):
                violation_box_ids.add(violation.get("box_id"))

        # 如果有箱子追踪信息，使用它来获取被搬运的箱子ID
        if box_tracking_info and box_tracking_info.get("carried_box_ids"):
            carried_box_ids.update(box_tracking_info["carried_box_ids"])

        # 创建 pose_id 到 track_id 的反向映射
        pose_to_track_mapping = {}
        if track_to_pose_mapping:
            for track_id, pose_id in track_to_pose_mapping.items():
                pose_to_track_mapping[pose_id] = track_id

        # 绘制人员（带ID和状态）
        for pose in poses:
            # 优先使用 track_id 显示，如果没有则使用 pose.id
            if pose_to_track_mapping and pose.id in pose_to_track_mapping:
                person_id = pose_to_track_mapping[pose.id]
            else:
                person_id = pose.id

            person_state = None
            current_zone = None

            if state_machine:
                person_data = state_machine.get_track(person_id)
                if person_data:
                    person_state = person_data.state
                    # 获取当前区域（从位置历史最后一个）
                    if person_data.position_history:
                        current_zone = person_data.position_history[-1].get("zone")

            # 绘制带状态的人员
            self._draw_person_with_status(
                img, pose, person_id, person_state, current_zone
            )

        # 只绘制被抱起的箱子
        if box_tracking_info:
            # 使用箱子追踪信息绘制
            tracked_boxes = box_tracking_info.get("tracked_boxes", [])
            box_trajectories = box_tracking_info.get("box_trajectories", {})

            for box in tracked_boxes:
                if box.id in carried_box_ids:
                    # 被抱起的箱子 - 高亮显示（黄色）
                    self._draw_bbox(
                        img, box.bbox, box.id, "箱子(搬运中)", (0, 255, 255)
                    )

                    # 绘制箱子轨迹
                    if box.id in box_trajectories:
                        trajectory = box_trajectories[box.id]
                        self._draw_box_trajectory(img, trajectory, (0, 255, 255))
                elif box.id in violation_box_ids:
                    # 违规箱子 - 红色
                    self._draw_bbox(
                        img, box.bbox, box.id, "箱子(违规)", self.COLORS["violation"]
                    )
        else:
            # 向后兼容：如果没有箱子追踪信息，使用旧逻辑
            for box in boxes:
                if box.id in violation_box_ids:
                    # 违规箱子 - 红色
                    self._draw_bbox(
                        img, box.bbox, box.id, "箱子(违规)", self.COLORS["violation"]
                    )
                elif box.id in carried_box_ids:
                    # 被抱起的箱子 - 高亮颜色（黄色）
                    self._draw_bbox(
                        img, box.bbox, box.id, "箱子(搬运中)", (0, 255, 255)
                    )

        # 绘制信息面板（包含箱子总数）
        self._draw_info_panel(
            img,
            poses,
            boxes,
            violations,
            frame_info,
            carried_box_ids,
            violation_box_ids,
            state_machine,
        )

        return img

    def _draw_person_with_status(
        self,
        img: np.ndarray,
        pose: Pose,
        person_id: str,
        person_state: Optional[PersonState],
        current_zone: Optional[str],
    ):
        """绘制人员，包括ID和状态信息"""
        # 根据状态选择颜色（适配新的状态机）
        if person_state == PersonState.TRACKING:
            color = (0, 255, 255)  # 黄色 - 追踪中
            status_text = "追踪中"
        else:
            color = (0, 255, 0)  # 绿色 - 空闲
            status_text = "空闲"

        bbox = pose.bbox
        x1, y1, x2, y2 = map(int, bbox)

        # 绘制边界框
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)

        # 准备显示文本
        display_id = person_id.replace("person_", "P")
        zone_text = f"[{current_zone}]" if current_zone else ""
        label_text = f"{display_id} {status_text} {zone_text}".strip()

        # 使用中文绘制
        img[:] = cv2_put_chinese_text(
            img, label_text, (x1, y1 - 30), font_size=18, color=(255, 255, 255)
        )

        # 绘制姿态关键点
        self._draw_pose(img, pose)

    def _draw_zones(self, img: np.ndarray):
        """绘制区域边界"""
        config = config_manager.get_config()
        frame_height, frame_width = img.shape[:2]

        for zone in config.zones:
            # 获取区域参考尺寸（如果未设置则使用默认值）
            ref_width = getattr(zone, "reference_width", 1920)
            ref_height = getattr(zone, "reference_height", 1080)

            # 计算缩放比例
            scale_x = frame_width / ref_width
            scale_y = frame_height / ref_height

            # 将区域坐标缩放到当前帧尺寸
            scaled_points = []
            for p in zone.points:
                scaled_x = int(p[0] * scale_x)
                scaled_y = int(p[1] * scale_y)
                scaled_points.append([scaled_x, scaled_y])

            points = np.array(scaled_points, np.int32)
            points = points.reshape((-1, 1, 2))
            cv2.polylines(img, [points], True, self.COLORS["zone"], 2)
            # 在区域中心显示名称（使用中文）
            center = np.mean(points, axis=0)[0].astype(int)
            img[:] = cv2_put_chinese_text(
                img, zone.name, tuple(center), font_size=18, color=self.COLORS["zone"]
            )

    def _draw_bbox(
        self, img: np.ndarray, bbox: List[float], obj_id: str, label: str, color: tuple
    ):
        """绘制边界框"""
        x1, y1, x2, y2 = map(int, bbox)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)

        # 绘制标签背景
        label_text = f"{label}: {obj_id}"
        text_size = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
        cv2.rectangle(
            img, (x1, y1 - text_size[1] - 8), (x1 + text_size[0] + 8, y1), color, -1
        )
        cv2.putText(
            img,
            label_text,
            (x1 + 4, y1 - 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            self.COLORS["text"],
            1,
        )

    def _draw_box_trajectory(
        self, img: np.ndarray, trajectory: List[Tuple[float, float]], color: tuple
    ):
        """绘制箱子轨迹"""
        if len(trajectory) < 2:
            return

        # 将轨迹点转换为整数坐标
        points = [(int(p[0]), int(p[1])) for p in trajectory]

        # 绘制轨迹线
        for i in range(1, len(points)):
            # 根据点的位置调整透明度（越新的点越亮）
            alpha = 0.3 + 0.7 * (i / len(points))
            thickness = 1 + int(2 * (i / len(points)))

            # 创建带透明度的颜色
            overlay = img.copy()
            cv2.line(overlay, points[i - 1], points[i], color, thickness)
            cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)

        # 绘制轨迹点
        for i, point in enumerate(points):
            if (
                i % 3 == 0 or i == len(points) - 1
            ):  # 每隔3个点绘制一次，并始终绘制最后一个点
                radius = 2 + int(3 * (i / len(points)))
                cv2.circle(img, point, radius, color, -1)

    def _draw_pose(self, img: np.ndarray, pose: Pose):
        """绘制姿态关键点"""
        keypoints = pose.keypoints  # [17, 3] - x, y, conf

        # 如果没有关键点数据，跳过绘制
        if keypoints is None or len(keypoints) == 0:
            return

        # 确保 keypoints 是 numpy 数组
        if not isinstance(keypoints, np.ndarray):
            return

        # 绘制骨架线
        for connection in self.SKELETON:
            pt1_idx, pt2_idx = connection
            if pt1_idx >= len(keypoints) or pt2_idx >= len(keypoints):
                continue
            pt1 = keypoints[pt1_idx]
            pt2 = keypoints[pt2_idx]

            # 只绘制置信度足够的关键点
            if pt1[2] > 0.5 and pt2[2] > 0.5:
                pt1_coord = (int(pt1[0]), int(pt1[1]))
                pt2_coord = (int(pt2[0]), int(pt2[1]))
                cv2.line(img, pt1_coord, pt2_coord, self.COLORS["keypoint_line"], 2)

        # 绘制关键点
        for i, kp in enumerate(keypoints):
            if kp[2] > 0.5:  # 置信度阈值
                x, y = int(kp[0]), int(kp[1])
                cv2.circle(img, (x, y), 4, self.COLORS["keypoint"], -1)
                cv2.circle(img, (x, y), 4, (0, 0, 0), 1)  # 边框

    def _draw_violation(self, img: np.ndarray, violation: Dict):
        """绘制违规标记"""
        # 在图像顶部绘制醒目的违规警告
        person_id = violation.get("person_id", "未知")
        origin_zone = violation.get("origin_zone", "未知")
        drop_zone = violation.get("drop_zone", "未知")

        # 绘制顶部警告条
        bar_height = 50
        overlay = img.copy()
        cv2.rectangle(
            overlay, (0, 0), (img.shape[1], bar_height), self.COLORS["violation"], -1
        )
        cv2.addWeighted(overlay, 0.7, img, 0.3, 0, img)

        # 绘制违规文字
        warning_text = f"Violation: {person_id} moved from {origin_zone} to {drop_zone}"
        cv2.putText(
            img,
            warning_text,
            (20, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
        )

    def _draw_info_panel(
        self,
        img: np.ndarray,
        poses: List[Pose],
        boxes: List[Detection],
        violations: List[Dict],
        frame_info: str,
        carried_box_ids=None,
        violation_box_ids=None,
        state_machine=None,
    ):
        """绘制信息面板"""
        # 右侧信息面板
        panel_width = 300
        panel_x = img.shape[1] - panel_width

        # 绘制半透明背景
        overlay = img.copy()
        cv2.rectangle(
            overlay,
            (panel_x, 0),
            (img.shape[1], img.shape[0]),
            self.COLORS["info_bg"],
            -1,
        )
        cv2.addWeighted(overlay, 0.7, img, 0.3, 0, img)

        # 绘制信息
        y_offset = 30
        line_height = 25

        # 统计各状态的人员数量（适配新的状态机）
        idle_count = 0
        tracking_count = 0

        if state_machine:
            for person_data in state_machine.tracks.values():
                if person_data.state == PersonState.IDLE:
                    idle_count += 1
                elif person_data.state == PersonState.TRACKING:
                    tracking_count += 1

        info_lines = [
            "=== 检测信息 ===",
            "",
            f"人员总数: {len(poses)}",
            f"  - 空闲: {idle_count}",
            f"  - 追踪中: {tracking_count}",
            f"箱子总数: {len(boxes)}",
        ]

        # 添加被搬运箱子数量
        if carried_box_ids:
            info_lines.append(f"搬运中: {len(carried_box_ids)}")
        else:
            info_lines.append(f"搬运中: 0")

        # 添加违规箱子数量
        if violation_box_ids:
            info_lines.append(f"违规箱子: {len(violation_box_ids)}")

        info_lines.extend(
            [
                f"违规数量: {len(violations)}",
                "",
                "=== 违规详情 ===",
            ]
        )

        if violations:
            for v in violations:
                person_id = v.get("person_id", "未知")
                origin = v.get("origin_zone", "未知")
                drop = v.get("drop_zone", "未知")
                info_lines.append(f"  {person_id}: {origin}->{drop}")
        else:
            info_lines.append(f"  无违规")

        if frame_info:
            info_lines.append("")
            info_lines.append(f"=== 帧信息 ===")
            info_lines.append(frame_info)

        # 使用中文绘制信息
        for line in info_lines:
            img[:] = cv2_put_chinese_text(
                img, line, (panel_x + 10, y_offset), font_size=16, color=(255, 255, 255)
            )
            y_offset += line_height


def process_video_frame_debug(
    video_path: str,
    frame_number: int = 0,
    camera_id: str = "debug",
    detector: YOLODetector = None,
    tracker=None,
    state_machine=None,
) -> Tuple[Optional[np.ndarray], Dict]:
    """
    处理视频文件的指定帧用于调试 - 适配新的检测逻辑

    Args:
        video_path: 视频文件路径
        frame_number: 要处理的帧号
        camera_id: 摄像头ID
        detector: 检测器实例（可选，用于保持状态）
        tracker: 追踪器实例（可选，用于保持跟踪状态）
        state_machine: 状态机实例（可选，用于保持状态）

    Returns:
        处理后的图像, 检测信息字典
    """
    from app.core.tracker import SimpleTracker
    from app.core.state_machine import StateMachine

    # 如果没有传入实例，创建新的（保持向后兼容）
    if detector is None:
        detector = YOLODetector()
    if tracker is None:
        tracker = SimpleTracker(max_age=30, min_hits=3, iou_threshold=0.3)
    if state_machine is None:
        state_machine = StateMachine()
    zone_manager.reload()

    # 打开视频
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None, {"error": f"无法打开视频: {video_path}"}

    # 获取视频信息
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    # 调整帧号
    if frame_number >= total_frames:
        frame_number = total_frames - 1
    if frame_number < 0:
        frame_number = 0

    # 跳转到指定帧
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        return None, {"error": f"无法读取第 {frame_number} 帧"}

    # 处理帧 - 使用新的检测逻辑
    detections = detector.detect(frame)
    tracks = tracker.update(detections)

    # 准备违规规则
    from app.config.manager import config_manager

    config = config_manager.get_config()
    violation_rules = [
        {
            "from_zone": rule.from_zone,
            "to_zone": rule.to_zone,
            "name": rule.name,
        }
        for rule in config.violation_rules
        if rule.enabled
    ]

    # 计算区域并更新状态机
    frame_height, frame_width = frame.shape[:2]
    violations = []
    track_zones = {}

    for track in tracks:
        current_zone = zone_manager.get_zone_id_at_point_scaled(
            track.center, frame_width, frame_height
        )
        track_zones[track.id] = current_zone

        if track.hits == 1:
            state_machine.start_tracking(track.id, current_zone)

        state_machine.update_position(track.id, track.center, current_zone)

        violation = state_machine.check_violation(track.id, violation_rules)
        if violation:
            violations.append(violation)
            state_machine.reset_track(track.id)

    # 将 tracks 转换为 poses 以兼容可视化器
    poses = []
    for track in tracks:
        poses.append(
            Pose(
                id=track.id,
                bbox=track.bbox,
                confidence=0.9,
                keypoints=np.zeros((17, 3), dtype=np.float32),
            )
        )

    # 创建可视化
    visualizer = DebugVisualizer(frame.shape[1], frame.shape[0])
    frame_info = f"帧号: {frame_number}/{total_frames}\nFPS: {fps:.1f}"
    processed_frame = visualizer.draw_detections(
        frame,
        poses,
        [],  # boxes
        violations,
        camera_id,
        frame_info,
        state_machine=state_machine,
    )

    # 构建返回信息
    detection_info = {
        "frame_number": frame_number,
        "total_frames": total_frames,
        "fps": fps,
        "persons": [
            {
                "id": p.id,
                "bbox": p.bbox,
                "confidence": p.confidence,
                "center": ((p.bbox[0] + p.bbox[2]) / 2, (p.bbox[1] + p.bbox[3]) / 2),
                "zone": track_zones.get(p.id),
            }
            for p in poses
        ],
        "poses": [
            {
                "id": p.id,
                "bbox": p.bbox,
                "confidence": p.confidence,
                "keypoints_count": len(p.keypoints),
                "zone": track_zones.get(p.id),
            }
            for p in poses
        ],
        "violations": violations,
        "track_zones": track_zones,
        "zones": [{"id": z.id, "name": z.name} for z in config.zones],
    }

    return processed_frame, detection_info
