import yaml
import os
from pathlib import Path
from .models import Config


class ConfigManager:
    def __init__(self, config_path: str = None):
        if config_path is None:
            # 默认使用backend目录下的config.yml
            current_file = Path(__file__)
            backend_dir = current_file.parent.parent.parent
            config_path = backend_dir / "config.yml"
        self.config_path = Path(config_path)
        self._config = None
        self._load_config()

    def _load_config(self):
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                self._config = Config(**data)
        else:
            self._config = Config()
            self._save_config()

    def _save_config(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(
                self._config.model_dump(),
                f,
                allow_unicode=True,
                default_flow_style=False,
            )

    def get_config(self) -> Config:
        return self._config

    def update_config(self, config: Config):
        self._config = config
        self._save_config()

    def update_cameras(self, cameras: list):
        self._config.cameras = cameras
        self._save_config()

    def update_zones(self, zones: list):
        self._config.zones = zones
        self._save_config()

    def update_rules(self, rules: list):
        self._config.violation_rules = rules
        self._save_config()

    def update_detection_params(self, params):
        self._config.detection_params = params
        self._save_config()

    def update_redis(self, redis_config):
        """更新Redis配置"""
        self._config.redis = redis_config
        self._save_config()

    def update_rabbitmq(self, rabbitmq_config):
        """更新RabbitMQ配置"""
        self._config.rabbitmq = rabbitmq_config
        self._save_config()


config_manager = ConfigManager()
