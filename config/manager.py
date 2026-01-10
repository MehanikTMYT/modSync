class ConfigManager:
    """Менеджер конфигурации приложения"""
    
    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config_file = Path(CONFIG_FILE)
        self.default_config = {
            'Settings': {
                'mods_path': '',
                'auto_strategy': 'true',
                'last_speed_test': '',
                'manual_strategy': 'balanced_adaptive',
                'max_parallel_workers': '6',
                'chunk_size': '32768',
                'auto_sync_interval': '0'
            }
        }
        self.load_or_create_config()
    
    def load_or_create_config(self):
        """Загрузка или создание конфигурации"""
        if self.config_file.exists():
            self.config.read(self.config_file)
        else:
            self.config.read_dict(self.default_config)
            self.save_config()
    
    def get(self, section, option, fallback=None):
        """Получение значения из конфигурации"""
        try:
            return self.config.get(section, option)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback
    
    def getboolean(self, section, option, fallback=False):
        """Получение булева значения из конфигурации"""
        try:
            return self.config.getboolean(section, option)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return fallback
    
    def set(self, section, option, value):
        """Установка значения в конфигурацию"""
        if section not in self.config:
            self.config[section] = {}
        self.config[section][option] = str(value)
    
    def save_config(self):
        """Сохранение конфигурации"""
        try:
            with open(self.config_file, 'w') as configfile:
                self.config.write(configfile)
            return True
        except Exception as e:
            print(f"Ошибка сохранения конфига: {e}")
            return False
    
    def clear_config(self):
        """Очистка конфигурации"""
        if self.config_file.exists():
            try:
                self.config_file.unlink()
                self.config.read_dict(self.default_config)
                return True
            except Exception as e:
                print(f"Ошибка удаления конфига: {e}")
                return False
        return True