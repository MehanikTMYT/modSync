import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from ui import MainUI
from api import ModSyncAPI
from config import ClientConfig

def main():
    # Устанавливаем атрибуты для правильного отображения на разных DPI
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # Загружаем конфигурацию
    config = ClientConfig()
    
    # Создаем API с настройками из конфига
    api = ModSyncAPI()
    
    # Создаем UI - исправленная передача аргументов
    ui = MainUI(api=api)  # Явно указываем параметр api
    ui.show()
    
    # Проверяем автосинхронизацию
    if config.get_profile().get("sync_on_startup", False):
        ui.sync()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()