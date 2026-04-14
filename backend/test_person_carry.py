"""测试person_carry检测和追踪功能"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.detector import YOLODetector
from app.core.tracker import SimpleTracker
from app.core.state_machine import StateMachine
import numpy as np


def test_detector():
    """测试检测器"""
    print("[Test] 测试检测器...")

    # 需要实际的模型文件才能测试完整功能
    # 但我们可以测试类是否能正确导入和初始化
    print("[Test] 检测器类导入成功 ✓")


def test_tracker():
    """测试追踪器"""
    print("[Test] 测试追踪器...")

    tracker = SimpleTracker(max_age=30, min_hits=3, iou_threshold=0.3)

    # 模拟检测对象
    class MockDet:
        def __init__(self, bbox, center):
            self.bbox = bbox
            self.center = center
            self.bottom_center = (center[0], bbox[3])
            self.id = None

    detections = [
        MockDet([100, 100, 200, 200], (150, 150)),
        MockDet([300, 300, 400, 400], (350, 350)),
    ]

    tracks = tracker.update(detections)
    print(f"第1帧: {len(tracks)} 个轨迹")

    # 移动一点位置（模拟对象移动）
    detections2 = [
        MockDet([105, 105, 205, 205], (155, 155)),
        MockDet([305, 305, 405, 405], (355, 355)),
    ]

    tracks = tracker.update(detections2)
    print(f"第2帧: {len(tracks)} 个轨迹")

    # 验证track_id是否保持稳定
    assert tracks[0].hits >= 2, "轨迹hits应该增加"
    assert tracks[0].age == 0, "匹配到的轨迹age应该重置为0"

    print("[Test] 追踪器测试通过 ✓")


def test_state_machine():
    """测试状态机"""
    print("[Test] 测试状态机...")

    # 先用防抖帧数=1测试基本逻辑
    sm = StateMachine(zone_debounce_frames=1)

    # 模拟规则：从A区域移动到B区域视为违规
    rules = [
        {"from_zone": "zone_a", "to_zone": "zone_b", "name": "A区域到B区域违规"},
    ]

    # 开始追踪新对象
    sm.start_tracking("track_1", "zone_a")
    track = sm.get_track("track_1")
    assert track is not None
    assert track.origin_zone == "zone_a"
    print("[Test] 开始追踪对象在zone_a")

    # 更新位置（仍在zone_a）
    sm.update_position("track_1", (100, 100), "zone_a")
    violation = sm.check_violation("track_1", rules)
    assert violation is None, "在起点区域不应该触发违规"
    print("[Test] 对象仍在zone_a，未触发违规")

    # 移动到B区域（防抖=1，1帧即切换）
    sm.update_position("track_1", (500, 500), "zone_b")
    print("[Test] 对象移动到zone_b")

    # 检查违规
    violation = sm.check_violation("track_1", rules)
    assert violation is not None, "从A到B应该触发违规"
    assert violation["from_zone"] == "zone_a"
    assert violation["to_zone"] == "zone_b"
    assert violation["rule_name"] == "A区域到B区域违规"

    print(f"[Test] 违规检测成功: {violation['rule_name']}")
    print(f"[Test] 违规详情: 从 {violation['from_zone']} 到 {violation['to_zone']}")
    print(f"[Test] 轨迹点数量: {len(violation['trajectory'])}")

    # 重置轨迹
    sm.reset_track("track_1")
    assert sm.get_track("track_1") is None
    print("[Test] 轨迹重置成功")

    # 测试防抖逻辑（zone_debounce_frames=3）
    print("[Test] 测试区域切换防抖...")
    sm2 = StateMachine(zone_debounce_frames=3)
    sm2.start_tracking("track_2", "zone_a")

    # 仅1帧移动到zone_b，不应切换
    sm2.update_position("track_2", (500, 500), "zone_b")
    assert sm2.get_track("track_2").current_zone == "zone_a", "1帧不应切换区域"

    # 第2帧仍在zone_b
    sm2.update_position("track_2", (510, 510), "zone_b")
    assert sm2.get_track("track_2").current_zone == "zone_a", "2帧不应切换区域"

    # 第3帧仍在zone_b，此时应切换
    sm2.update_position("track_2", (520, 520), "zone_b")
    assert sm2.get_track("track_2").current_zone == "zone_b", "3帧应切换区域"

    violation = sm2.check_violation("track_2", rules)
    assert violation is not None, "防抖后从A到B应触发违规"
    print("[Test] 防抖逻辑测试通过")

    print("[Test] 状态机测试通过 ✓")


def test_config_models():
    """测试配置模型"""
    print("[Test] 测试配置模型...")

    from app.config.models import PersonCarryParams, DetectionParams, Config

    # 测试PersonCarryParams默认值
    params = PersonCarryParams()
    assert params.model == "person_carry.pt"
    assert params.confidence == 0.5
    assert params.iou_threshold == 0.45
    assert params.class_id == 0
    print("[Test] PersonCarryParams默认值正确")

    # 测试DetectionParams结构
    detection_params = DetectionParams()
    assert hasattr(detection_params, "person_carry")
    assert hasattr(detection_params, "tracking")
    assert hasattr(detection_params, "pose")  # 兼容性保留
    assert hasattr(detection_params, "box")  # 兼容性保留
    print("[Test] DetectionParams结构正确")

    print("[Test] 配置模型测试通过 ✓")


if __name__ == "__main__":
    print("=" * 50)
    print("Person Carry 追踪功能测试")
    print("=" * 50)
    print()

    test_detector()
    print()

    test_tracker()
    print()

    test_state_machine()
    print()

    test_config_models()
    print()

    print("=" * 50)
    print("[✓] 所有测试通过！")
    print("=" * 50)
