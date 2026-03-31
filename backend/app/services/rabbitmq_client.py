import pika
import json
from datetime import datetime
from typing import Dict
from app.config.manager import config_manager


class RabbitMQClient:
    """RabbitMQ客户端 - 用于违规告警推送"""

    def __init__(self):
        self._config = None
        self._connection = None
        self._channel = None

    def _get_config(self):
        """延迟获取配置"""
        if self._config is None:
            self._config = config_manager.get_config().rabbitmq
        return self._config

    def _connect(self):
        """建立连接"""
        config = self._get_config()
        try:
            credentials = pika.PlainCredentials(config.username, config.password)
            parameters = pika.ConnectionParameters(
                host=config.host,
                port=config.port,
                virtual_host=config.virtual_host,
                credentials=credentials,
            )
            self._connection = pika.BlockingConnection(parameters)
            self._channel = self._connection.channel()

            # 如果配置了非默认交换机，则声明交换机
            if config.exchange:
                self._channel.exchange_declare(
                    exchange=config.exchange,
                    exchange_type=config.exchange_type,
                    durable=True,
                )

            # 如果配置了队列，则声明队列
            if config.queue:
                self._channel.queue_declare(queue=config.queue, durable=True)

                # 如果配置了交换机，绑定队列到交换机
                if config.exchange:
                    self._channel.queue_bind(
                        queue=config.queue,
                        exchange=config.exchange,
                    )

            print(f"[RabbitMQ] Connected to {config.host}:{config.port}")
        except Exception as e:
            print(f"[RabbitMQ] Connection failed: {e}")
            self._connection = None

    def publish_violation(self, violation_data: Dict):
        """发布违规告警"""
        if not self._connection or self._connection.is_closed:
            self._connect()

        if not self._connection:
            print("[RabbitMQ] Cannot publish, not connected")
            return False

        config = self._get_config()
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
            # 使用配置的 exchange，fanout 模式下不需要 routing_key
            exchange = config.exchange if config.exchange else ""
            routing_key = "" if config.exchange else config.queue

            self._channel.basic_publish(
                exchange=exchange,
                routing_key=routing_key,
                body=json.dumps(message, ensure_ascii=False),
                properties=pika.BasicProperties(
                    delivery_mode=2,
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
        if self._connection and not self._connection.is_closed:
            self._connection.close()

    def test_connection(self) -> bool:
        """测试RabbitMQ连接"""
        try:
            config = self._get_config()
            credentials = pika.PlainCredentials(config.username, config.password)
            parameters = pika.ConnectionParameters(
                host=config.host,
                port=config.port,
                virtual_host=config.virtual_host,
                credentials=credentials,
                connection_attempts=1,
                retry_delay=0,
            )
            connection = pika.BlockingConnection(parameters)
            connection.close()
            return True
        except Exception:
            return False


# 全局RabbitMQ客户端实例（延迟初始化）
rabbitmq_client = RabbitMQClient()
