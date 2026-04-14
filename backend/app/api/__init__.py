from .config import router as config_router
from .zones import router as zones_router
from .rules import router as rules_router
from .monitor import router as monitor_router
# from .debug_stream import router as debug_stream_router  # 暂时禁用，需要适配新的检测逻辑

__all__ = [
    "config_router",
    "zones_router",
    "rules_router",
    "monitor_router",
    # "debug_stream_router",
]
