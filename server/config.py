import json
from pathlib import Path
import os

class ServerConfig:
    def __init__(self):
        self.config_path = Path.home() / ".modsync_server_config.json"
        self.default_config = {
            "mods_directory": str(Path(__file__).parent),
            "cache_duration": 60,
            "port": 8800,
            "host": "0.0.0.0",
            "log_level": "info"
        }
        
        if self.config_path.exists():
            try:
                self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
                self._ensure_defaults()
            except (json.JSONDecodeError, KeyError):
                self.config = self.default_config.copy()
                self.save()
        else:
            self.config = self.default_config.copy()
            self.save()
    
    def _ensure_defaults(self):
        """Гарантирует наличие всех необходимых полей"""
        for key, value in self.default_config.items():
            if key not in self.config:
                self.config[key] = value
    
    def save(self):
        """Сохраняет конфигурацию"""
        self.config_path.write_text(
            json.dumps(self.config, indent=4, ensure_ascii=False),
            encoding="utf-8"
        )
    
    def get_mods_directory(self) -> Path:
        """Возвращает путь к директории модов"""
        return Path(self.config["mods_directory"])
    
    def get_cache_duration(self) -> int:
        """Возвращает длительность кеширования манифеста в секундах"""
        return self.config["cache_duration"]
    
    def get_port(self) -> int:
        """Возвращает порт сервера"""
        return self.config["port"]
    
    def get_host(self) -> str:
        """Возвращает хост сервера"""
        return self.config["host"]
    
    def get_log_level(self) -> str:
        """Возвращает уровень логирования"""
        return self.config["log_level"]

# Глобальный экземпляр конфигурации
CONFIG = ServerConfig()