from enum import Enum
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime
import json


class PersonState(Enum):
    IDLE = "idle"
    TRACKING = "tracking"  # 正在追踪中


@dataclass
class PersonStateData:
    track_id: str
    state: PersonState
    origin_zone: Optional[str] = None
    current_zone: Optional[str] = None
    pending_zone: Optional[str] = None
    pending_zone_count: int = 0
    last_known_zone: Optional[str] = None  # 空白区域保持用
    last_update: datetime = field(default_factory=datetime.now)
    position_history: List[Dict] = field(default_factory=list)
    last_seen: datetime = field(default_factory=datetime.now)


class StateMachine:
    """person_carry对象轨迹追踪状态机（含区域切换防抖）"""

    def __init__(self, zone_debounce_frames: int = 3):
        self.tracks: Dict[str, PersonStateData] = {}
        self.zone_debounce_frames = zone_debounce_frames

    def get_track(self, track_id: str) -> Optional[PersonStateData]:
        """获取追踪对象状态"""
        return self.tracks.get(track_id)

    def start_tracking(self, track_id: str, zone: Optional[str]) -> bool:
        """开始追踪新对象"""
        if track_id not in self.tracks:
            # 如果有初始区域，直接设置为TRACKING状态
            initial_state = (
                PersonState.TRACKING if zone is not None else PersonState.IDLE
            )
            self.tracks[track_id] = PersonStateData(
                track_id=track_id,
                state=initial_state,
                origin_zone=zone,
                current_zone=zone,
                pending_zone=zone,
                pending_zone_count=1,
                last_known_zone=zone,
            )
            return True
        return False

    def update_position(self, track_id: str, position: tuple, zone: Optional[str]):
        """更新对象位置和区域（含连续帧防抖、空白区域保持上一个区域）"""
        if track_id not in self.tracks:
            self.tracks[track_id] = PersonStateData(
                track_id=track_id,
                state=PersonState.IDLE,
                pending_zone=zone,
                pending_zone_count=1,
                last_known_zone=zone,
            )

        track = self.tracks[track_id]
        track.last_seen = datetime.now()

        # 记录首次出现的区域为origin_zone
        if track.origin_zone is None and zone is not None:
            track.origin_zone = zone
            track.state = PersonState.TRACKING
            track.current_zone = zone
            track.pending_zone = zone
            track.pending_zone_count = 1
            track.last_known_zone = zone

        # 区域切换防抖逻辑
        elif zone is not None:
            track.last_known_zone = zone
            if zone == track.pending_zone:
                track.pending_zone_count += 1
            else:
                track.pending_zone = zone
                track.pending_zone_count = 1

            # 连续 N 帧在同一新区域才正式切换
            if track.pending_zone_count >= self.zone_debounce_frames:
                track.current_zone = track.pending_zone

        # zone 为 None（空白区域）时：
        # 1. current_zone 保持上一个已知区域不变；
        # 2. pending_zone 也不重置，避免从 A 去 B 经过空白地带时打断防抖计数；
        # 3. effective_zone 使用 last_known_zone，确保位置历史和外显区域不会变成"无区域"。
        else:
            # 明确保持 current_zone：如果已有 known zone 则保持不变
            if track.last_known_zone is not None and track.current_zone is None:
                track.current_zone = track.last_known_zone

        # 记录位置历史（保留原始 zone 用于调试）
        effective_zone = (
            track.current_zone
            if track.current_zone is not None
            else track.last_known_zone
            if track.last_known_zone is not None
            else zone
        )
        track.position_history.append(
            {
                "position": position,
                "zone": effective_zone,
                "raw_zone": zone,
                "timestamp": datetime.now().isoformat(),
            }
        )

        # 保持最近100个位置
        if len(track.position_history) > 100:
            track.position_history = track.position_history[-100:]

        track.last_update = datetime.now()

    def check_violation(self, track_id: str, rules: List[Dict]) -> Optional[Dict]:
        """
        检查是否违反规则
        规则格式: {"from_zone": "A", "to_zone": "B", "name": "规则名称"}
        返回违规数据或None
        """
        track = self.tracks.get(track_id)
        if not track:
            return None

        if track.state != PersonState.TRACKING:
            return None

        # 检查是否满足任何规则
        for rule in rules:
            if track.origin_zone == rule.get(
                "from_zone"
            ) and track.current_zone == rule.get("to_zone"):
                # 违规！
                violation = {
                    "track_id": track_id,
                    "rule_name": rule.get("name", "未知规则"),
                    "from_zone": track.origin_zone,
                    "to_zone": track.current_zone,
                    "origin_zone_name": rule.get("from_zone"),
                    "target_zone_name": rule.get("to_zone"),
                    "trajectory": track.position_history.copy(),
                    "timestamp": datetime.now().isoformat(),
                }
                return violation

        return None

    def reset_track(self, track_id: str):
        """重置追踪对象状态"""
        if track_id in self.tracks:
            del self.tracks[track_id]

    def cleanup_stale_tracks(self, timeout_seconds: int = 30) -> List[str]:
        """清理长时间未见的追踪对象，返回被清理的track_id列表"""
        now = datetime.now()
        stale_ids = []

        for track_id, track in list(self.tracks.items()):
            elapsed = (now - track.last_seen).total_seconds()
            if elapsed > timeout_seconds:
                stale_ids.append(track_id)
                del self.tracks[track_id]

        return stale_ids
