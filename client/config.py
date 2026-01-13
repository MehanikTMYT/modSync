import json
from pathlib import Path
import sys
from datetime import timedelta

# Определяем базовый путь для приложения
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

CONFIG_PATH = Path.home() / ".modsync_config.json"
BACKUPS_DIR = BASE_DIR / ".modsync_backups"
LOGS_DIR = BASE_DIR / "logs"

DEFAULT_CONFIG = {
    "active_profile": "default",
    "server_url": "http://147.45.184.36:8800",
    "backups_dir": str(BACKUPS_DIR),
    "logs_dir": str(LOGS_DIR),
    "sync_interval": 60,  # в минутах
    "max_backups": 5,
    "profiles": {
        "default": {
            "mods_path": "",
            "auto_sync": False,
            "sync_on_startup": False
        }
    },
    "ui": {
        "window_width": 800,
        "window_height": 600,
        "tray_enabled": True,
        "show_backup_dialog": True,
        "enable_backups": True,
        "always_show_confirmation": True,
        "show_notifications": True,
        "dark_theme": True
    },
    "sync": {
        "chunk_size": 131072,  # 128 KB
        "timeout": 30,
        "max_retries": 3,
        "max_workers": 4,
        "verify_hashes": True,
        "delete_unmatched_files": True,
        "cache_duration": 60  # в секундах
    }
}

class ClientConfig:
    def __init__(self):
        self.base_dir = BASE_DIR
        self.ensure_directories_exist()
        
        if CONFIG_PATH.exists():
            try:
                self.data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                self._ensure_default_structure()
            except (json.JSONDecodeError, KeyError, IOError) as e:
                print(f"Ошибка загрузки конфига: {e}. Использую настройки по умолчанию.")
                self.data = DEFAULT_CONFIG.copy()
                self.save()
        else:
            self.data = DEFAULT_CONFIG.copy()
            self.save()
        
        # Обновляем пути к директориям
        self.backups_dir = Path(self.data.get("backups_dir", str(BACKUPS_DIR)))
        self.logs_dir = Path(self.data.get("logs_dir", str(LOGS_DIR)))
        self.ensure_directories_exist()

    def ensure_directories_exist(self):
        """Создает необходимые директории если они не существуют"""
        directories = [
            self.backups_dir if hasattr(self, 'backups_dir') else BACKUPS_DIR,
            self.logs_dir if hasattr(self, 'logs_dir') else LOGS_DIR
        ]
        
        for directory in directories:
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                print(f"Ошибка создания директории {directory}: {e}")

    def _ensure_default_structure(self):
        """Гарантирует наличие всех необходимых полей в конфиге"""
        # Проверяем и добавляем отсутствующие секции
        for key, value in DEFAULT_CONFIG.items():
            if key not in self.data:
                self.data[key] = value
        
        # Проверяем структуру профилей
        if "profiles" not in self.data:
            self.data["profiles"] = DEFAULT_CONFIG["profiles"]
        
        if self.data["active_profile"] not in self.data["profiles"]:
            self.data["active_profile"] = "default"
        
        # Проверяем наличие sync настроек
        if "sync" not in self.data:
            self.data["sync"] = DEFAULT_CONFIG["sync"]
        
        # Проверяем наличие ui настроек
        if "ui" not in self.data:
            self.data["ui"] = DEFAULT_CONFIG["ui"]
        
        # Добавляем новые поля если их нет
        ui_defaults = DEFAULT_CONFIG["ui"]
        for key, value in ui_defaults.items():
            if key not in self.data["ui"]:
                self.data["ui"][key] = value
        
        sync_defaults = DEFAULT_CONFIG["sync"]
        for key, value in sync_defaults.items():
            if key not in self.data["sync"]:
                self.data["sync"][key] = value
        
        # Проверяем обязательные поля
        if "backups_dir" not in self.data:
            self.data["backups_dir"] = str(BACKUPS_DIR)
        if "logs_dir" not in self.data:
            self.data["logs_dir"] = str(LOGS_DIR)
        if "sync_interval" not in self.data:
            self.data["sync_interval"] = DEFAULT_CONFIG["sync_interval"]
        if "max_backups" not in self.data:
            self.data["max_backups"] = DEFAULT_CONFIG["max_backups"]

    def save(self):
        """Сохраняет конфигурацию в файл"""
        try:
            CONFIG_PATH.write_text(
                json.dumps(self.data, indent=4, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception as e:
            print(f"Ошибка сохранения конфига: {e}")

    def get_server_url(self) -> str:
        """Возвращает URL сервера из конфига"""
        return self.data.get("server_url", DEFAULT_CONFIG["server_url"])

    def set_server_url(self, url: str):
        """Устанавливает URL сервера"""
        if not url.startswith(('http://', 'https://')):
            raise ValueError("URL должен начинаться с http:// или https://")
        self.data["server_url"] = url.strip()
        self.save()

    def get_profile(self):
        """Возвращает текущий профиль"""
        return self.data["profiles"][self.data["active_profile"]]

    def get_mods_path(self) -> str:
        """Возвращает путь к папке модов"""
        return self.get_profile().get("mods_path", "")

    def set_mods_path(self, path: str):
        """Устанавливает путь к папке модов"""
        self.get_profile()["mods_path"] = path
        self.save()

    def get_backups_dir(self) -> Path:
        """Возвращает путь к директории бекапов"""
        return self.backups_dir

    def get_logs_dir(self) -> Path:
        """Возвращает путь к директории логов"""
        return self.logs_dir

    def get_sync_settings(self) -> dict:
        """Возвращает настройки синхронизации"""
        return self.data.get("sync", DEFAULT_CONFIG["sync"])

    def get_ui_settings(self) -> dict:
        """Возвращает настройки UI"""
        return self.data.get("ui", DEFAULT_CONFIG["ui"])

    def get_sync_interval(self) -> int:
        """Возвращает интервал автосинхронизации в минутах"""
        return self.data.get("sync_interval", DEFAULT_CONFIG["sync_interval"])

    def set_sync_interval(self, minutes: int):
        """Устанавливает интервал автосинхронизации"""
        if minutes < 0:
            raise ValueError("Интервал не может быть отрицательным")
        self.data["sync_interval"] = minutes
        self.save()

    def get_max_backups(self) -> int:
        """Возвращает максимальное количество бекапов"""
        return self.data.get("max_backups", DEFAULT_CONFIG["max_backups"])

    def set_max_backups(self, count: int):
        """Устанавливает максимальное количество бекапов"""
        if count < 1:
            raise ValueError("Минимальное количество бекапов - 1")
        self.data["max_backups"] = count
        self.save()

    def should_create_backups(self) -> bool:
        """Проверяет, нужно ли создавать бекапы"""
        return self.get_ui_settings().get("enable_backups", True)

    def should_show_backup_dialog(self) -> bool:
        """Проверяет, нужно ли показывать диалог о создании бекапа"""
        return self.get_ui_settings().get("show_backup_dialog", True)

    def should_show_confirmation_dialog(self) -> bool:
        """Проверяет, нужно ли показывать диалог подтверждения"""
        return self.get_ui_settings().get("always_show_confirmation", True)

    def should_show_tray_icon(self) -> bool:
        """Проверяет, нужно ли показывать иконку в трее"""
        return self.get_ui_settings().get("tray_enabled", True)

    def should_show_notifications(self) -> bool:
        """Проверяет, нужно ли показывать уведомления"""
        return self.get_ui_settings().get("show_notifications", True)

    def set_create_backups(self, enable: bool):
        """Устанавливает настройку создания бекапов"""
        self.data["ui"]["enable_backups"] = enable
        self.save()

    def set_show_backup_dialog(self, show: bool):
        """Устанавливает настройку показа диалога бекапов"""
        self.data["ui"]["show_backup_dialog"] = show
        self.save()

    def set_show_tray_icon(self, show: bool):
        """Устанавливает настройку показа иконки в трее"""
        self.data["ui"]["tray_enabled"] = show
        self.save()

    def set_show_notifications(self, show: bool):
        """Устанавливает настройку показа уведомлений"""
        self.data["ui"]["show_notifications"] = show
        self.save()

    def set_show_confirmation_dialog(self, show: bool):
        """Устанавливает настройку показа диалога подтверждения"""
        self.data["ui"]["always_show_confirmation"] = show
        self.save()

    def set_sync_settings(self, settings: dict):
        """Устанавливает настройки синхронизации"""
        self.data["sync"] = settings
        self.save()

    def get_window_size(self):
        """Возвращает размер окна"""
        ui_settings = self.get_ui_settings()
        return (
            ui_settings.get("window_width", 800),
            ui_settings.get("window_height", 600)
        )

    def set_window_size(self, width: int, height: int):
        """Устанавливает размер окна"""
        self.data["ui"]["window_width"] = width
        self.data["ui"]["window_height"] = height
        self.save()