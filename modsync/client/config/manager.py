import os
import sys
import configparser

# Добавляем пути к другим модулям
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from modsync.shared.utils.helpers import validate_path


class ConfigManager:
    """Менеджер конфигурации приложения"""
    
    def __init__(self, config_file="modsync_config.ini"):
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self.load_config()
    
    def load_config(self):
        """Загрузка конфигурации из файла"""
        if os.path.exists(self.config_file):
            try:
                self.config.read(self.config_file, encoding='utf-8')
            except Exception as e:
                print(f"⚠️ Ошибка загрузки конфигурации: {e}. Создается стандартная конфигурация.")
                self.create_default_config()
        else:
            self.create_default_config()
    
    def save_config(self):
        """Сохранение конфигурации в файл"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                self.config.write(f)
            return True
        except Exception as e:
            print(f"❌ Ошибка сохранения конфигурации: {e}")
            return False
    
    def create_default_config(self):
        """Создание стандартной конфигурации"""
        self.config['DEFAULT'] = {}
        self.config['paths'] = {
            'minecraft_folder': './minecraft',
            'mods_folder': './minecraft/mods',
            'backup_folder': './backups'
        }
        self.config['connection'] = {
            'server_url': 'http://147.45.184.36:8000',
            'timeout': '30',
            'max_retries': '3'
        }
        self.config['download'] = {
            'max_workers': '4',
            'chunk_size': '32768',
            'enable_resume': 'True'
        }
        self.config['ui'] = {
            'theme': 'dark',
            'language': 'ru_RU',
            'auto_check_updates': 'True'
        }
    
    def get_path(self, path_type):
        """Получение пути из конфигурации"""
        return self.config.get('paths', path_type, fallback=self._get_default_path(path_type))
    
    def set_path(self, path_type, path):
        """Установка пути в конфигурации"""
        if not hasattr(self, '_validate_and_create_path'):
            self._validate_and_create_path = validate_path
        
        validated_path = self._validate_and_create_path(path)
        if validated_path:
            if 'paths' not in self.config:
                self.config['paths'] = {}
            self.config.set('paths', path_type, validated_path)
            return True
        return False
    
    def _get_default_path(self, path_type):
        """Получение стандартного пути"""
        defaults = {
            'minecraft_folder': './minecraft',
            'mods_folder': './minecraft/mods',
            'backup_folder': './backups'
        }
        return defaults.get(path_type, './default')
    
    def get_connection_settings(self):
        """Получение настроек соединения"""
        return {
            'server_url': self.config.get('connection', 'server_url', fallback='http://147.45.184.36:8000'),
            'timeout': self.config.getint('connection', 'timeout', fallback=30),
            'max_retries': self.config.getint('connection', 'max_retries', fallback=3)
        }
    
    def get_download_settings(self):
        """Получение настроек загрузки"""
        return {
            'max_workers': self.config.getint('download', 'max_workers', fallback=4),
            'chunk_size': self.config.getint('download', 'chunk_size', fallback=32768),
            'enable_resume': self.config.getboolean('download', 'enable_resume', fallback=True)
        }
    
    def get_ui_settings(self):
        """Получение настроек интерфейса"""
        return {
            'theme': self.config.get('ui', 'theme', fallback='dark'),
            'language': self.config.get('ui', 'language', fallback='ru_RU'),
            'auto_check_updates': self.config.getboolean('ui', 'auto_check_updates', fallback=True)
        }
    
    def update_setting(self, section, key, value):
        """Обновление конкретной настройки"""
        if section not in self.config:
            self.config[section] = {}
        self.config.set(section, key, str(value))
    
    def get_setting(self, section, key, fallback=None, setting_type='string'):
        """Получение конкретной настройки с возможностью указания типа"""
        if setting_type == 'int':
            return self.config.getint(section, key, fallback=fallback)
        elif setting_type == 'bool':
            return self.config.getboolean(section, key, fallback=fallback)
        elif setting_type == 'float':
            return self.config.getfloat(section, key, fallback=fallback)
        else:
            return self.config.get(section, key, fallback=fallback)
