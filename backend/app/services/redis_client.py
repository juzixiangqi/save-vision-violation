import redis
import json
from typing import Optional, Dict
from datetime import datetime
from app.config.manager import config_manager


class RedisClient:
    """Redis客户端 - 用于运行时状态缓存"""

    def __init__(self):
        self._config = None
        self._client = None

    def _get_config(self):
        """延迟获取配置"""
        if self._config is None:
            self._config = config_manager.get_config().redis
        return self._config

    def _get_client(self):
        """延迟初始化客户端"""
        if self._client is None:
            config = self._get_config()
            connection_kwargs = {
                "host": config.host,
                "port": config.port,
                "db": config.db,
                "decode_responses": True,
            }
            # 如果有密码则添加
            if config.password:
                connection_kwargs["password"] = config.password

            self._client = redis.Redis(**connection_kwargs)
            print(f"[Redis] Connected to {config.host}:{config.port}")
        return self._client

    def save_person_state(self, person_id: str, state_data: Dict):
        """保存人员状态到Redis"""
        key = f"person:{person_id}"
        state_data["last_update"] = datetime.now().isoformat()
        self._get_client().setex(key, 3600, json.dumps(state_data))

    def get_person_state(self, person_id: str) -> Optional[Dict]:
        """从Redis获取人员状态"""
        key = f"person:{person_id}"
        data = self._get_client().get(key)
        if data:
            return json.loads(data)
        return None

    def delete_person_state(self, person_id: str):
        """删除人员状态"""
        key = f"person:{person_id}"
        self._get_client().delete(key)

    def save_box_state(self, box_id: str, state_data: Dict):
        """保存箱子状态到Redis"""
        key = f"box:{box_id}"
        state_data["last_update"] = datetime.now().isoformat()
        self._get_client().setex(key, 3600, json.dumps(state_data))

    def get_box_state(self, box_id: str) -> Optional[Dict]:
        """从Redis获取箱子状态"""
        key = f"box:{box_id}"
        data = self._get_client().get(key)
        if data:
            return json.loads(data)
        return None

    def save_frame_cache(self, camera_id: str, frame_data: bytes, timestamp: float):
        """保存帧缓存用于提取片段"""
        key = f"frame:{camera_id}:{int(timestamp * 1000)}"
        self._get_client().setex(key, 10, frame_data)

    def get_system_status(self) -> Dict:
        """获取系统状态"""
        try:
            client = self._get_client()
            return {
                "connected": client.ping(),
                "persons_tracked": len(client.keys("person:*")),
                "boxes_tracked": len(client.keys("box:*")),
            }
        except Exception as e:
            print(f"[Redis] Status check failed: {e}")
            return {"connected": False, "persons_tracked": 0, "boxes_tracked": 0}


# 全局Redis客户端实例（延迟初始化）
redis_client = RedisClient()
