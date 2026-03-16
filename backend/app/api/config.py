from fastapi import APIRouter, HTTPException
from app.config.manager import config_manager
from app.config.models import Config, Camera, Zone, ViolationRule, DetectionParams

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
