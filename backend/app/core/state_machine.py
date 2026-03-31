from enum import Enum
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime
import json


class PersonState(Enum):
    IDLE = "idle"
    CARRYING = "carrying"
    OCCLUDED = "occluded"


@dataclass
class PersonStateData:
    person_id: str
    state: PersonState
    origin_zone: Optional[str] = None
    locked_box_id: Optional[str] = None
    last_update: datetime = field(default_factory=datetime.now)
    occlusion_start: Optional[datetime] = None
    position_history: List[Dict] = field(default_factory=list)
    frame_count: int = 0  # 用于防抖计数


class StateMachine:
    """人员搬运状态机"""

    def __init__(self):
        self.persons: Dict[str, PersonStateData] = {}

    def get_person_state(self, person_id: str) -> Optional[PersonStateData]:
        """获取人员状态"""
        return self.persons.get(person_id)

    def transition_to_carrying(
        self, person_id: str, origin_zone: str, locked_box_id: str
    ) -> bool:
        """状态转换: IDLE -> CARRYING"""
        if person_id not in self.persons:
            self.persons[person_id] = PersonStateData(
                person_id=person_id, state=PersonState.IDLE
            )

        person = self.persons[person_id]

        if person.state == PersonState.IDLE:
            person.state = PersonState.CARRYING
            person.origin_zone = origin_zone
            person.locked_box_id = locked_box_id
            person.last_update = datetime.now()
            return True

        return False

    def transition_to_occluded(self, person_id: str) -> bool:
        """状态转换: CARRYING -> OCCLUDED"""
        person = self.persons.get(person_id)
        if person and person.state == PersonState.CARRYING:
            person.state = PersonState.OCCLUDED
            person.occlusion_start = datetime.now()
            person.last_update = datetime.now()
            return True
        return False

    def transition_from_occluded(self, person_id: str) -> bool:
        """状态转换: OCCLUDED -> CARRYING"""
        person = self.persons.get(person_id)
        if person and person.state == PersonState.OCCLUDED:
            person.state = PersonState.CARRYING
            person.occlusion_start = None
            person.last_update = datetime.now()
            return True
        return False

    def transition_to_idle(
        self, person_id: str, drop_zone: Optional[str]
    ) -> Optional[Dict]:
        """状态转换: CARRYING/OCCLUDED -> IDLE，返回违规事件数据"""
        person = self.persons.get(person_id)
        if not person:
            return None

        if person.state in [PersonState.CARRYING, PersonState.OCCLUDED]:
            # 记录可能的违规
            violation_data = None
            if person.origin_zone and person.origin_zone != drop_zone:
                violation_data = {
                    "person_id": person_id,
                    "origin_zone": person.origin_zone,
                    "drop_zone": drop_zone,
                    "box_id": person.locked_box_id,
                    "trajectory": person.position_history.copy(),
                }

            # 重置状态
            person.state = PersonState.IDLE
            person.origin_zone = None
            person.locked_box_id = None
            person.occlusion_start = None
            person.position_history = []
            person.frame_count = 0
            person.last_update = datetime.now()

            return violation_data

        return None

    def update_position(self, person_id: str, position: tuple, zone: Optional[str]):
        """更新人员位置历史"""
        if person_id not in self.persons:
            self.persons[person_id] = PersonStateData(
                person_id=person_id, state=PersonState.IDLE
            )

        person = self.persons[person_id]
        person.position_history.append(
            {
                "position": position,
                "zone": zone,
                "timestamp": datetime.now().isoformat(),
            }
        )

        # 保持最近100个位置记录
        if len(person.position_history) > 100:
            person.position_history = person.position_history[-100:]

    def check_occlusion_timeout(self, person_id: str, timeout_seconds: int = 5) -> bool:
        """检查遮挡是否超时"""
        person = self.persons.get(person_id)
        if not person or person.state != PersonState.OCCLUDED:
            return False

        if person.occlusion_start:
            elapsed = (datetime.now() - person.occlusion_start).total_seconds()
            return elapsed > timeout_seconds

        return False

    def increment_frame_count(self, person_id: str) -> int:
        """增加帧计数"""
        if person_id not in self.persons:
            self.persons[person_id] = PersonStateData(
                person_id=person_id, state=PersonState.IDLE
            )
        self.persons[person_id].frame_count += 1
        return self.persons[person_id].frame_count

    def reset_frame_count(self, person_id: str):
        """重置帧计数"""
        if person_id in self.persons:
            self.persons[person_id].frame_count = 0
