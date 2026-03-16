import pika
import json
from datetime import datetime
from typing import Dict
from app.config.manager import config_manager


class RabbitMQClient:
    """RabbitMQ客户端 - 用于违规告警推送 (端口5673)"""

    def __init__(self):
        config = config_manager.get_config().rabbitmq
        self.config = config
        self.connection = None
        self.channel = None
        self._connect()

    def _connect(self):
        """建立连接"""
        try:
            credentials = pika.PlainCredentials(
                self.config.username, self.config.password
            )
            parameters = pika.ConnectionParameters(
                host=self.config.host,
                port=self.config.port,  # 使用配置中的端口 (5673)
                credentials=credentials,
            )
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            self.channel.queue_declare(queue=self.config.queue, durable=True)
            print(f"[RabbitMQ] Connected to {self.config.host}:{self.config.port}")
        except Exception as e:
            print(f"[RabbitMQ] Connection failed: {e}")
            self.connection = None

    def publish_violation(self, violation_data: Dict):
        """发布违规告警"""
        if not self.connection or self.connection.is_closed:
            self._connect()

        if not self.connection:
            print("[RabbitMQ] Cannot publish, not connected")
            return False

        message = {
            "event_type": "violation",
            "timestamp": datetime.now().isoformat(),
            "camera_id": violation_data.get("camera_id", "unknown"),
            "person_id": violation_data.get("person_id"),
            "box_id": violation_data.get("box_id"),
            "origin_zone": violation_data.get("origin_zone"),
            "drop_zone": violation_data.get("drop_zone"),
            "trajectory": violation_data.get("trajectory", []),
            "confidence": violation_data.get("confidence", 1.0),
        }

        try:
            self.channel.basic_publish(
                exchange="",
                routing_key=self.config.queue,
                body=json.dumps(message, ensure_ascii=False),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # 持久化
                    content_type="application/json",
                ),
            )
            print(f"[RabbitMQ] Published violation: {message['person_id']}")
            return True
        except Exception as e:
            print(f"[RabbitMQ] Publish failed: {e}")
            return False

    def close(self):
        """关闭连接"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()


# 全局RabbitMQ客户端实例
rabbitmq_client = RabbitMQClient()
