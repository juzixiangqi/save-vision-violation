import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional
from app.core.detector import Detection, Pose, YOLODetector
from app.core.violation_checker import ViolationChecker
from app.core.zone_manager import zone_manager
from app.config.manager import config_manager


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
        persons: List[Detection],
        poses: List[Pose],
        boxes: List[Detection],
        violations: List[Dict],
        camera_id: str,
        frame_info: str = "",
    ) -> np.ndarray:
        """在帧上绘制所有检测结果"""
        img = frame.copy()

        # 绘制区域
        self._draw_zones(img)

        # 绘制箱子
        for box in boxes:
            self._draw_bbox(img, box.bbox, box.id, "箱子", self.COLORS["box_bbox"])

        # 绘制人员和姿态
        for person in persons:
            self._draw_bbox(
                img, person.bbox, person.id, "人员", self.COLORS["person_bbox"]
            )

        # 找到对应的人员姿态并绘制
        for pose in poses:
            self._draw_pose(img, pose)

        # 绘制违规标记
        for violation in violations:
            self._draw_violation(img, violation)

        # 绘制信息面板
        self._draw_info_panel(img, persons, poses, boxes, violations, frame_info)

        return img

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
            # 在区域中心显示名称
            center = np.mean(points, axis=0)[0].astype(int)
            cv2.putText(
                img,
                zone.name,
                tuple(center),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                self.COLORS["zone"],
                2,
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

    def _draw_pose(self, img: np.ndarray, pose: Pose):
        """绘制姿态关键点"""
        keypoints = pose.keypoints  # [17, 3] - x, y, conf

        # 绘制骨架线
        for connection in self.SKELETON:
            pt1_idx, pt2_idx = connection
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
        persons: List[Detection],
        poses: List[Pose],
        boxes: List[Detection],
        violations: List[Dict],
        frame_info: str,
    ):
        """绘制信息面板"""
        # 右侧信息面板
        panel_width = 250
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

        info_lines = [
            "=== 检测信息 ===",
            f"",
            f"人员数量: {len(persons)}",
            f"姿态数量: {len(poses)}",
            f"箱子数量: {len(boxes)}",
            f"违规数量: {len(violations)}",
            f"",
            f"=== 人员详情 ===",
        ]

        for person in persons:
            info_lines.append(f"  {person.id}: {person.confidence:.2f}")

        if violations:
            info_lines.append(f"")
            info_lines.append(f"=== 违规详情 ===")
            for v in violations:
                info_lines.append(f"  {v.get('type', '违规')}")

        if frame_info:
            info_lines.append(f"")
            info_lines.append(f"=== 帧信息 ===")
            info_lines.append(frame_info)

        for line in info_lines:
            cv2.putText(
                img,
                line,
                (panel_x + 10, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                self.COLORS["text"],
                1,
            )
            y_offset += line_height


def process_video_frame_debug(
    video_path: str,
    frame_number: int = 0,
    camera_id: str = "debug",
) -> Tuple[Optional[np.ndarray], Dict]:
    """
    处理视频文件的指定帧用于调试

    Returns:
        处理后的图像, 检测信息字典
    """
    detector = YOLODetector()
    violation_checker = ViolationChecker()
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

    # 处理帧
    persons, poses = detector.detect(frame)
    boxes = []  # TODO: 实现箱子检测

    # 检查违规
    violations = violation_checker.process_frame(persons, poses, boxes, camera_id)

    # 创建可视化
    visualizer = DebugVisualizer(frame.shape[1], frame.shape[0])
    frame_info = f"帧号: {frame_number}/{total_frames}\nFPS: {fps:.1f}"
    processed_frame = visualizer.draw_detections(
        frame, persons, poses, boxes, violations, camera_id, frame_info
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
                "center": p.center,
            }
            for p in persons
        ],
        "poses": [
            {
                "id": p.id,
                "bbox": p.bbox,
                "confidence": p.confidence,
                "keypoints_count": len(p.keypoints),
            }
            for p in poses
        ],
        "violations": violations,
        "zones": [
            {"id": z.id, "name": z.name} for z in config_manager.get_config().zones
        ],
    }

    return processed_frame, detection_info
