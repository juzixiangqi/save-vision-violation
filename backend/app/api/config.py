from fastapi import APIRouter, HTTPException
from app.config.manager import config_manager
from app.config.models import (
    Config,
    Camera,
    Zone,
    ViolationRule,
    DetectionParams,
    RedisConfig,
    RabbitMQConfig,
)
from app.services.redis_client import redis_client
from app.services.rabbitmq_client import rabbitmq_client
import redis
import pika

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("", response_model=Config)
async def get_config():
    return config_manager.get_config()


@router.put("", response_model=Config)
async def update_config(config: Config):
    config_manager.update_config(config)
    return config


@router.get("/cameras")
async def get_cameras():
    return config_manager.get_config().cameras


@router.put("/cameras")
async def update_cameras(cameras: list[Camera]):
    config_manager.update_cameras(cameras)
    return cameras


@router.get("/zones")
async def get_zones():
    return config_manager.get_config().zones


@router.put("/zones")
async def update_zones(zones: list[Zone]):
    config_manager.update_zones(zones)
    return zones


@router.get("/rules")
async def get_rules():
    return config_manager.get_config().violation_rules


@router.put("/rules")
async def update_rules(rules: list[ViolationRule]):
    config_manager.update_rules(rules)
    return rules


@router.get("/detection-params")
async def get_detection_params():
    return config_manager.get_config().detection_params


@router.put("/detection-params")
async def update_detection_params(params: DetectionParams):
    config_manager.update_detection_params(params)
    return params


@router.get("/services")
async def get_services_config():
    """获取服务配置（Redis和RabbitMQ）"""
    config = config_manager.get_config()
    return {"redis": config.redis, "rabbitmq": config.rabbitmq}


@router.put("/services")
async def update_services_config(data: dict):
    """更新服务配置"""
    if "redis" in data:
        redis_config = RedisConfig(**data["redis"])
        config_manager.update_redis(redis_config)
    if "rabbitmq" in data:
        rabbitmq_config = RabbitMQConfig(**data["rabbitmq"])
        config_manager.update_rabbitmq(rabbitmq_config)
    return {"message": "服务配置更新成功"}


@router.get("/services/status")
async def get_services_status():
    """检查服务连接状态（使用已保存的配置）"""
    redis_status = {"connected": False, "error": None}
    rabbitmq_status = {"connected": False, "error": None}

    # 检查 Redis
    try:
        redis_status["connected"] = redis_client._get_client().ping()
    except Exception as e:
        redis_status["error"] = str(e)

    # 检查 RabbitMQ
    try:
        rabbitmq_status["connected"] = rabbitmq_client.test_connection()
    except Exception as e:
        rabbitmq_status["error"] = str(e)

    return {
        "redis": redis_status,
        "rabbitmq": rabbitmq_status,
        "all_connected": redis_status["connected"] and rabbitmq_status["connected"],
    }


@router.post("/services/test")
async def test_services_connection(data: dict):
    """测试服务连接（使用传入的配置，不依赖已保存的配置）"""
    redis_status = {"connected": False, "error": None}
    rabbitmq_status = {"connected": False, "error": None}

    # 测试 Redis 连接
    if "redis" in data:
        try:
            redis_config = data["redis"]
            connection_kwargs = {
                "host": redis_config.get("host", "localhost"),
                "port": redis_config.get("port", 6379),
                "db": redis_config.get("db", 0),
                "decode_responses": True,
                "socket_connect_timeout": 3,
            }
            if redis_config.get("password"):
                connection_kwargs["password"] = redis_config["password"]

            # 创建临时客户端测试连接
            client = redis.Redis(**connection_kwargs)
            redis_status["connected"] = client.ping()
            client.close()
        except Exception as e:
            redis_status["error"] = str(e)

    # 测试 RabbitMQ 连接
    if "rabbitmq" in data:
        try:
            rabbitmq_config = data["rabbitmq"]
            credentials = pika.PlainCredentials(
                rabbitmq_config.get("username", "guest"),
                rabbitmq_config.get("password", "guest"),
            )
            parameters = pika.ConnectionParameters(
                host=rabbitmq_config.get("host", "localhost"),
                port=rabbitmq_config.get("port", 5673),  # 默认使用 Docker 映射端口
                credentials=credentials,
                connection_attempts=1,
                retry_delay=0,
                socket_timeout=3,
            )
            connection = pika.BlockingConnection(parameters)
            connection.close()
            rabbitmq_status["connected"] = True
        except Exception as e:
            rabbitmq_status["error"] = str(e)

    return {
        "redis": redis_status,
        "rabbitmq": rabbitmq_status,
        "all_connected": redis_status["connected"] and rabbitmq_status["connected"],
    }
