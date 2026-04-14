from typing import List, Dict, Tuple, Optional
from app.config.manager import config_manager
from app.config.models import Zone


class ZoneManager:
    """区域管理器 - 判断点是否在区域内"""

    def __init__(self):
        self.zones = []
        self._load_zones()

    def _load_zones(self):
        self.zones = config_manager.get_config().zones

    def reload(self):
        """重新加载区域配置"""
        self._load_zones()

    def get_zone_at_point(self, point: Tuple[float, float]) -> Optional[Zone]:
        """判断点是否在哪个区域内"""
        for zone in self.zones:
            if self._point_in_polygon(point, zone.points):
                return zone
        return None

    def get_zone_at_point_scaled(
        self, point: Tuple[float, float], frame_width: int, frame_height: int
    ) -> Optional[Zone]:
        """判断点是否在哪个区域内（根据实际帧尺寸缩放区域坐标）"""
        x, y = point
        for zone in self.zones:
            ref_width = getattr(zone, "reference_width", 1920)
            ref_height = getattr(zone, "reference_height", 1080)
            scale_x = frame_width / ref_width
            scale_y = frame_height / ref_height
            scaled_points = [[p[0] * scale_x, p[1] * scale_y] for p in zone.points]
            if self._point_in_polygon((x, y), scaled_points):
                return zone
        return None

    def get_zone_id_at_point_scaled(
        self, point: Tuple[float, float], frame_width: int, frame_height: int
    ) -> Optional[str]:
        """获取点所在区域的ID（根据实际帧尺寸缩放）"""
        zone = self.get_zone_at_point_scaled(point, frame_width, frame_height)
        return zone.id if zone else None

    def _point_in_polygon(
        self, point: Tuple[float, float], polygon: List[List[float]]
    ) -> bool:
        """射线法判断点是否在多边形内"""
        x, y = point
        n = len(polygon)
        inside = False

        p1x, p1y = polygon[0]
        for i in range(n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        else:
                            xinters = p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y

        return inside

    def get_all_zones(self) -> List[Zone]:
        """获取所有区域"""
        return self.zones


# 全局区域管理器实例
zone_manager = ZoneManager()
