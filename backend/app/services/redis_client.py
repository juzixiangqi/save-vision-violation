import redis
import json
from typing import Optional, Dict
from datetime import datetime
from app.config.manager import config_manager


class RedisClient:
    """Redis客户端 - 用于运行时状态缓存"""

    def __init__(self):
        config = config_manager.get_config().redis
        self.client = redis.Redis(
            host=config.host, port=config.port, db=config.db, decode_responses=True
        )

    def save_person_state(self, person_id: str, state_data: Dict):
        """保存人员状态到Redis"""
        key = f"person:{person_id}"
        state_data["last_update"] = datetime.now().isoformat()
        self.client.setex(key, 3600, json.dumps(state_data))  # 1小时过期

    def get_person_state(self, person_id: str) -> Optional[Dict]:
        """从Redis获取人员状态"""
        key = f"person:{person_id}"
        data = self.client.get(key)
        if data:
            return json.loads(data)
        return None

    def delete_person_state(self, person_id: str):
        """删除人员状态"""
        key = f"person:{person_id}"
        self.client.delete(key)

    def save_box_state(self, box_id: str, state_data: Dict):
        """保存箱子状态到Redis"""
        key = f"box:{box_id}"
        state_data["last_update"] = datetime.now().isoformat()
        self.client.setex(key, 3600, json.dumps(state_data))

    def get_box_state(self, box_id: str) -> Optional[Dict]:
        """从Redis获取箱子状态"""
        key = f"box:{box_id}"
        data = self.client.get(key)
        if data:
            return json.loads(data)
        return None

    def save_frame_cache(self, camera_id: str, frame_data: bytes, timestamp: float):
        """保存帧缓存用于提取片段"""
        key = f"frame:{camera_id}:{int(timestamp * 1000)}"
        self.client.setex(key, 10, frame_data)  # 10秒过期

    def get_system_status(self) -> Dict:
        """获取系统状态"""
        return {
            "connected": self.client.ping(),
            "persons_tracked": len(self.client.keys("person:*")),
            "boxes_tracked": len(self.client.keys("box:*")),
        }


# 全局Redis客户端实例
redis_client = RedisClient()
