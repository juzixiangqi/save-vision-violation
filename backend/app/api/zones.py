from fastapi import APIRouter, HTTPException
from app.config.manager import config_manager
from app.config.models import Zone
from typing import List

router = APIRouter(prefix="/api/zones", tags=["zones"])


@router.get("", response_model=List[Zone])
async def list_zones():
    return config_manager.get_config().zones


@router.post("", response_model=Zone)
async def create_zone(zone: Zone):
    zones = config_manager.get_config().zones
    zones.append(zone)
    config_manager.update_zones(zones)
    return zone


@router.put("/{zone_id}", response_model=Zone)
async def update_zone(zone_id: str, zone: Zone):
    zones = config_manager.get_config().zones
    for i, z in enumerate(zones):
        if z.id == zone_id:
            zones[i] = zone
            config_manager.update_zones(zones)
            return zone
    raise HTTPException(status_code=404, detail="Zone not found")


@router.delete("/{zone_id}")
async def delete_zone(zone_id: str):
    zones = config_manager.get_config().zones
    zones = [z for z in zones if z.id != zone_id]
    config_manager.update_zones(zones)
    return {"message": "Zone deleted"}
