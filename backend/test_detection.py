#!/usr/bin/env python3
"""
仓库违规检测系统测试脚本
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.zone_manager import zone_manager
from app.config.manager import config_manager
from app.config.models import Zone


def test_zone_manager():
    """测试区域管理器"""
    print("=" * 50)
    print("测试区域管理器")
    print("=" * 50)

    try:
        zones = [
            Zone(
                id="zone_a",
                name="Zone_A",
                color="#FF6B6B",
                points=[[100, 100], [300, 100], [300, 300], [100, 300]],
            ),
            Zone(
                id="zone_b",
                name="Zone_B",
                color="#4ECDC4",
                points=[[400, 100], [600, 100], [600, 300], [400, 300]],
            ),
        ]

        config_manager.update_zones(zones)
        zone_manager.reload()

        print(f"✓ 已添加 {len(zones)} 个区域")

        test_point_inside = (200, 200)
        test_point_outside = (500, 500)

        zone_inside = zone_manager.get_zone_at_point(test_point_inside)
        zone_outside = zone_manager.get_zone_at_point(test_point_outside)

        print(
            f"✓ 点 {test_point_inside} 在区域: {zone_inside.name if zone_inside else 'None'}"
        )
        print(
            f"✓ 点 {test_point_outside} 在区域: {zone_outside.name if zone_outside else 'None'}"
        )

        return True
    except Exception as e:
        print(f"✗ 区域管理器测试失败: {e}")
        return False


def test_state_machine():
    """测试状态机"""
    print("\n" + "=" * 50)
    print("测试状态机")
    print("=" * 50)

    try:
        from app.core.state_machine import StateMachine, PersonState

        sm = StateMachine(zone_debounce_frames=1)
        rules = [{"from_zone": "zone_a", "to_zone": "zone_b", "name": "A到B违规"}]

        # 测试区域追踪违规检测
        sm.start_tracking("person_001", "zone_a")
        state = sm.get_track("person_001")
        assert state.state == PersonState.TRACKING
        assert state.origin_zone == "zone_a"
        print(f"✓ 开始追踪: origin_zone = zone_a")

        sm.update_position("person_001", (100, 100), "zone_a")
        violation = sm.check_violation("person_001", rules)
        assert violation is None, "在起点区域不应触发违规"
        print(f"✓ 仍在zone_a，未触发违规")

        sm.update_position("person_001", (500, 500), "zone_b")
        violation = sm.check_violation("person_001", rules)
        assert violation is not None
        assert violation["from_zone"] == "zone_a"
        assert violation["to_zone"] == "zone_b"
        print(f"✓ 违规检测: {violation['from_zone']} -> {violation['to_zone']}")

        return True
    except Exception as e:
        print(f"✗ 状态机测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n")
    print("╔" + "=" * 48 + "╗")
    print("║" + " " * 10 + "仓库违规检测系统测试" + " " * 16 + "║")
    print("╚" + "=" * 48 + "╝")
    print("\n")

    results = []
    results.append(("区域管理器", test_zone_manager()))
    results.append(("状态机", test_state_machine()))

    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{name:20s} {status}")

    print("-" * 50)
    print(f"总计: {passed}/{total} 通过")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
