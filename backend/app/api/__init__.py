from .config import router as config_router
from .zones import router as zones_router
from .rules import router as rules_router
from .monitor import router as monitor_router

__all__ = ["config_router", "zones_router", "rules_router", "monitor_router"]
