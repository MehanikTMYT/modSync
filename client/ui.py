import os
from pathlib import Path
from datetime import datetime, timedelta, time
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QProgressBar, QTextEdit, QFileDialog, QMessageBox,
    QSystemTrayIcon, QMenu, QCheckBox, QLineEdit, QGroupBox,
    QSpinBox, QDoubleSpinBox, QFormLayout, QDialog,
    QListWidget, QListWidgetItem, QScrollArea,
    QFrame, QAbstractItemView
)
from PySide6.QtCore import (
    Qt, Signal, Slot, QThread, QObject, QTimer,
    QRegularExpression
)
from PySide6.QtGui import (
    QIcon, QColor, QRegularExpressionValidator,
    QCloseEvent, QAction, QFont, QTextCursor, QPixmap, QPainter
)
from api import ModSyncAPI
from config import ClientConfig
from utils import (
    format_size, get_free_space
)

class BackupDialog(QDialog):
    """Диалог подтверждения создания бекапа"""
    def __init__(self, parent=None, affected_files=None, total_size=0):
        super().__init__(parent)
        self.setWindowTitle("Создание резервной копии")
        self.setModal(True)
        self.setMinimumWidth(600)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Информация о бекапе
        info_text = (
            f"<h3>⚠️ Будут созданы резервные копии следующих файлов:</h3>"
            f"<p><b>Всего файлов:</b> {len(affected_files) if affected_files else 0}</p>"
            f"<p><b>Общий размер:</b> {format_size(total_size)}</p>"
            f"<p style='color: #e74c3c;'><b>Внимание:</b> Это может занять некоторое время в зависимости от размера файлов.</p>"
        )
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        info_label.setTextFormat(Qt.RichText)
        layout.addWidget(info_label)
        
        # Список файлов с прокруткой
        if affected_files:
            files_group = QGroupBox("Список файлов для бекапа")
            files_layout = QVBoxLayout()
            
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setFrameShape(QFrame.NoFrame)
            
            files_container = QWidget()
            files_container_layout = QVBoxLayout(files_container)
            files_container_layout.setContentsMargins(10, 10, 10, 10)
            files_container_layout.setSpacing(5)
            
            self.files_list = QListWidget()
            self.files_list.setSelectionMode(QAbstractItemView.NoSelection)
            self.files_list.setStyleSheet("""
                QListWidget {
                    background-color: #2d2d2d;
                    border: 1px solid #444;
                    border-radius: 4px;
                }
                QListWidget::item {
                    padding: 4px;
                    border-bottom: 1px solid #3a3a3a;
                }
                QListWidget::item:last {
                    border-bottom: none;
                }
            """)
            
            for file in sorted(affected_files):
                item = QListWidgetItem(file)
                item.setToolTip(file)
                self.files_list.addItem(item)
            
            files_container_layout.addWidget(self.files_list)
            scroll_area.setWidget(files_container)
            files_layout.addWidget(scroll_area)
            files_group.setLayout(files_layout)
            layout.addWidget(files_group)
        
        # Галочка "Больше не спрашивать"
        self.remember_checkbox = QCheckBox("☑️ Больше не спрашивать и всегда создавать бекапы")
        self.remember_checkbox.setStyleSheet("color: #f39c12;")
        layout.addWidget(self.remember_checkbox)
        
        # Кнопки
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton("❌ Отменить")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        
        ok_btn = QPushButton("✅ Создать бекап")
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
        """)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(ok_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)

class SyncWorker(QObject):
    """Рабочий поток для синхронизации с асинхронной обработкой"""
    finished = Signal(dict)
    error = Signal(str)
    progress_file = Signal(int, int, str, float, str)  # current, total, filename, speed, eta
    progress_total = Signal(int, int, int, float, str)  # current_bytes, total_bytes, percent, speed, eta
    log_message = Signal(str)
    request_backup_dialog = Signal(list, int)
    cancel_requested = Signal()
    
    def __init__(self, api, mods_path, dry_run):
        super().__init__()
        self.api = api
        self.mods_path = mods_path
        self.dry_run = dry_run
        self.total_bytes = 0
        self.downloaded_bytes = 0
        self._cancelled = False
        self.current_file = ""
        self.start_time = None
        self.file_start_time = None
        self.speed_history = []
        self.last_update_time = 0
    
    def calculate_speed(self, bytes_downloaded, time_elapsed):
        """Рассчитывает текущую скорость с учетом истории"""
        if time_elapsed <= 0:
            return 0
        
        current_speed = bytes_downloaded / time_elapsed
        self.speed_history.append(current_speed)
        
        # Удерживаем только последние 10 измерений для сглаживания
        if len(self.speed_history) > 10:
            self.speed_history.pop(0)
        
        # Используем медиану для устойчивости к всплескам
        sorted_speeds = sorted(self.speed_history)
        return sorted_speeds[len(sorted_speeds) // 2]
    
    def format_eta(self, seconds):
        """Форматирует ETA в человекочитаемый вид"""
        if seconds < 0 or seconds > 3600 * 24:  # Более 24 часов
            return "∞"
        if seconds < 60:
            return f"{int(seconds)} сек"
        if seconds < 3600:
            return f"{int(seconds // 60)} мин"
        return f"{int(seconds // 3600)} час"
    
    def on_file_start(self, filename, file_size):
        """Обработчик начала загрузки файла"""
        self.current_file = filename
        self.file_start_time = time.time()
        self.log_message.emit(f"📥 Начало загрузки: {filename} ({format_size(file_size)})")
    
    def on_file_progress(self, current, total):
        """Обработчик прогресса с оценкой времени"""
        if not self._cancelled and self.current_file and self.file_start_time:
            elapsed = time.time() - self.file_start_time
            if elapsed > 0.1:  # Ждем немного для точности
                speed = self.calculate_speed(current, elapsed)
                eta = (total - current) / speed if speed > 0 else float('inf')
                
                eta_str = self.format_eta(eta)
                speed_str = format_size(speed) + "/сек"
                
                self.progress_file.emit(current, total, self.current_file, speed, eta_str)
                
                # Отправляем общий прогресс только при значительных изменениях
                current_time = time.time()
                if current_time - self.last_update_time > 1.0:  # Раз в секунду
                    total_elapsed = time.time() - self.start_time if self.start_time else 0
                    overall_speed = self.downloaded_bytes / total_elapsed if total_elapsed > 0 else 0
                    overall_eta = (self.total_bytes - self.downloaded_bytes) / overall_speed if overall_speed > 0 else float('inf')
                    
                    self.progress_total.emit(
                        self.downloaded_bytes, 
                        self.total_bytes, 
                        int((self.downloaded_bytes / self.total_bytes * 100) if self.total_bytes > 0 else 0),
                        overall_speed,
                        self.format_eta(overall_eta)
                    )
                    self.last_update_time = current_time
    
    def on_start(self, total_bytes):
        """Обработчик начала загрузки"""
        self.total_bytes = total_bytes
        self.downloaded_bytes = 0
        self.start_time = time.time()
        self.log_message.emit(f"📊 Общий размер загрузки: {format_size(total_bytes)}")
        self.progress_total.emit(0, total_bytes, 0, 0, "∞")
    """Рабочий поток для синхронизации с оценкой времени"""
    finished = Signal(dict)
    error = Signal(str)
    progress_file = Signal(int, int, str, float, str)  # current, total, filename, speed, eta
    progress_total = Signal(int, int, int, float, str)  # current_bytes, total_bytes, percent, speed, eta
    log_message = Signal(str)
    request_backup_dialog = Signal(list, int)
    cancel_requested = Signal()
    
    def __init__(self, api, mods_path, dry_run):
        super().__init__()
        self.api = api
        self.mods_path = mods_path
        self.dry_run = dry_run
        self.total_bytes = 0
        self.downloaded_bytes = 0
        self._cancelled = False
        self.current_file = ""
        self.start_time = None
        self.file_start_time = None
        self.speed_history = []
        self.last_update_time = 0
    
    def calculate_speed(self, bytes_downloaded, time_elapsed):
        """Рассчитывает текущую скорость с учетом истории"""
        if time_elapsed <= 0:
            return 0
        
        current_speed = bytes_downloaded / time_elapsed
        self.speed_history.append(current_speed)
        
        # Удерживаем только последние 10 измерений для сглаживания
        if len(self.speed_history) > 10:
            self.speed_history.pop(0)
        
        # Используем медиану для устойчивости к всплескам
        sorted_speeds = sorted(self.speed_history)
        return sorted_speeds[len(sorted_speeds) // 2]
    
    def format_eta(self, seconds):
        """Форматирует ETA в человекочитаемый вид"""
        if seconds < 0 or seconds > 3600 * 24:  # Более 24 часов
            return "∞"
        if seconds < 60:
            return f"{int(seconds)} сек"
        if seconds < 3600:
            return f"{int(seconds // 60)} мин"
        return f"{int(seconds // 3600)} час"
    
    def on_file_start(self, filename, file_size):
        """Обработчик начала загрузки файла с инициализацией времени"""
        self.current_file = filename
        self.file_start_time = time.time()
        self.log_message.emit(f"📥 Начало загрузки: {filename} ({format_size(file_size)})")
    
    def on_file_progress(self, current, total, current_hash=None):
        """Обработчик прогресса текущего файла с оценкой скорости и ETA"""
        if not self._cancelled and self.current_file and self.file_start_time:
            elapsed = time.time() - self.file_start_time
            if elapsed > 0.1:  # Ждем немного для точности
                speed = self.calculate_speed(current, elapsed)
                eta = (total - current) / speed if speed > 0 else float('inf')
                
                eta_str = self.format_eta(eta)
                speed_str = format_size(speed) + "/сек"
                
                self.progress_file.emit(current, total, self.current_file, speed, eta_str)class SettingsDialog(QDialog):
    """Диалог настроек приложения"""
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("⚙️ Настройки ModSync")
        self.setMinimumWidth(650)
        self.setMinimumHeight(500)
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Группа сервера
        server_group = QGroupBox("🌐 Настройки сервера")
        server_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #444;
                border-radius: 5px;
                margin-top: 1ex;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        server_layout = QFormLayout()
        server_layout.setLabelAlignment(Qt.AlignRight)
        server_layout.setSpacing(15)
        
        self.server_url_input = QLineEdit(self.config.get_server_url())
        self.server_url_input.setPlaceholderText("http://example.com:8800")
        url_validator = QRegularExpressionValidator(QRegularExpression(
            r'^(https?:\/\/)?([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,6}(:\d+)?(\/.*)?$'
        ))
        self.server_url_input.setValidator(url_validator)
        server_layout.addRow("🌐 URL сервера:", self.server_url_input)
        
        self.sync_interval_spin = QSpinBox()
        self.sync_interval_spin.setRange(0, 1440)
        self.sync_interval_spin.setValue(self.config.get_sync_interval())
        self.sync_interval_spin.setSuffix(" минут")
        self.sync_interval_spin.setToolTip("0 - отключить автосинхронизацию")
        server_layout.addRow("⏱️ Интервал автосинхронизации:", self.sync_interval_spin)
        
        server_group.setLayout(server_layout)
        main_layout.addWidget(server_group)
        
        # Группа синхронизации
        sync_group = QGroupBox("⚡ Настройки синхронизации")
        sync_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #444;
                border-radius: 5px;
                margin-top: 1ex;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        sync_layout = QFormLayout()
        sync_layout.setLabelAlignment(Qt.AlignRight)
        sync_layout.setSpacing(15)
        
        self.chunk_size_spin = QSpinBox()
        self.chunk_size_spin.setRange(1, 1024)
        self.chunk_size_spin.setValue(self.config.get_sync_settings().get("chunk_size", 128) // 1024)
        self.chunk_size_spin.setSuffix(" КБ")
        sync_layout.addRow("📦 Размер чанка:", self.chunk_size_spin)
        
        self.max_workers_spin = QSpinBox()
        self.max_workers_spin.setRange(1, 16)
        self.max_workers_spin.setValue(self.config.get_sync_settings().get("max_workers", 4))
        sync_layout.addRow("🧵 Макс. потоков загрузки:", self.max_workers_spin)
        
        self.max_retries_spin = QSpinBox()
        self.max_retries_spin.setRange(0, 10)
        self.max_retries_spin.setValue(self.config.get_sync_settings().get("max_retries", 3))
        sync_layout.addRow("🔄 Макс. попыток при ошибке:", self.max_retries_spin)
        
        self.timeout_spin = QDoubleSpinBox()
        self.timeout_spin.setRange(1, 300)
        self.timeout_spin.setValue(self.config.get_sync_settings().get("timeout", 30))
        self.timeout_spin.setSuffix(" сек")
        sync_layout.addRow("⏱️ Таймаут соединения:", self.timeout_spin)
        
        sync_group.setLayout(sync_layout)
        main_layout.addWidget(sync_group)
        
        # Группа бекапов
        backup_group = QGroupBox("💾 Настройки резервных копий")
        backup_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #444;
                border-radius: 5px;
                margin-top: 1ex;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        backup_layout = QVBoxLayout()
        backup_layout.setSpacing(10)
        
        self.backup_checkbox = QCheckBox("✅ Создавать резервные копии перед синхронизацией")
        self.backup_checkbox.setChecked(self.config.should_create_backups())
        backup_layout.addWidget(self.backup_checkbox)
        
        self.backup_dialog_checkbox = QCheckBox("💬 Показывать диалог подтверждения перед созданием бекапа")
        self.backup_dialog_checkbox.setChecked(self.config.should_show_backup_dialog())
        backup_layout.addWidget(self.backup_dialog_checkbox)
        
        max_backups_layout = QHBoxLayout()
        max_backups_layout.addWidget(QLabel("🗄️ Максимальное количество сохраняемых бекапов:"))
        self.max_backups_spin = QSpinBox()
        self.max_backups_spin.setRange(1, 50)
        self.max_backups_spin.setValue(self.config.get_max_backups())
        self.max_backups_spin.setSuffix(" шт")
        max_backups_layout.addWidget(self.max_backups_spin)
        max_backups_layout.addStretch()
        backup_layout.addLayout(max_backups_layout)
        
        backup_group.setLayout(backup_layout)
        main_layout.addWidget(backup_group)
        
        # Группа уведомлений
        notification_group = QGroupBox("🔔 Настройки уведомлений")
        notification_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #444;
                border-radius: 5px;
                margin-top: 1ex;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        notification_layout = QVBoxLayout()
        notification_layout.setSpacing(10)
        
        self.tray_checkbox = QCheckBox("⏺️ Показывать иконку в системном трее")
        self.tray_checkbox.setChecked(self.config.should_show_tray_icon())
        notification_layout.addWidget(self.tray_checkbox)
        
        self.notifications_checkbox = QCheckBox("🔔 Показывать уведомления о завершении синхронизации")
        self.notifications_checkbox.setChecked(self.config.should_show_notifications())
        notification_layout.addWidget(self.notifications_checkbox)
        
        self.confirmation_checkbox = QCheckBox("❓ Показывать диалог подтверждения перед синхронизацией")
        self.confirmation_checkbox.setChecked(self.config.should_show_confirmation_dialog())
        notification_layout.addWidget(self.confirmation_checkbox)
        
        notification_group.setLayout(notification_layout)
        main_layout.addWidget(notification_group)
        
        # Кнопки
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        apply_btn = QPushButton("✅ Применить")
        apply_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        apply_btn.clicked.connect(self.apply_settings)
        
        cancel_btn = QPushButton("❌ Отмена")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        
        ok_btn = QPushButton("✅ OK")
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
        """)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        
        button_layout.addWidget(apply_btn)
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(ok_btn)
        
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)
    
    def apply_settings(self):
        """Применяет настройки без закрытия диалога"""
        try:
            # Валидация URL
            server_url = self.server_url_input.text().strip()
            if server_url and not server_url.startswith(('http://', 'https://')):
                raise ValueError("URL должен начинаться с http:// или https://")
            
            if not server_url:
                server_url = "http://147.45.184.36:8800"
            
            # Сохраняем настройки
            self.config.set_server_url(server_url)
            self.config.set_sync_interval(self.sync_interval_spin.value())
            
            sync_settings = {
                "chunk_size": self.chunk_size_spin.value() * 1024,
                "max_workers": self.max_workers_spin.value(),
                "max_retries": self.max_retries_spin.value(),
                "timeout": self.timeout_spin.value(),
                "verify_hashes": True,
                "delete_unmatched_files": True
            }
            self.config.set_sync_settings(sync_settings)
            
            self.config.set_create_backups(self.backup_checkbox.isChecked())
            self.config.set_show_backup_dialog(self.backup_dialog_checkbox.isChecked())
            self.config.set_max_backups(self.max_backups_spin.value())
            
            self.config.set_show_tray_icon(self.tray_checkbox.isChecked())
            self.config.set_show_notifications(self.notifications_checkbox.isChecked())
            self.config.set_show_confirmation_dialog(self.confirmation_checkbox.isChecked())
            
            QMessageBox.information(self, "✅ Успех", "Настройки успешно применены!")
            
        except Exception as e:
            QMessageBox.warning(self, "❌ Ошибка", f"Ошибка при применении настроек:\n{str(e)}")

class MainUI(QWidget):
    """Основной интерфейс приложения"""
    def __init__(self, api=None):
        super().__init__()
        self.setWindowTitle("ModSync Client")
        
        # Инициализация конфигурации и API
        self.config = ClientConfig()
        width, height = self.config.get_window_size()
        self.setMinimumSize(800, 600)
        self.resize(width, height)
        
        # Иконка приложения
        icon_path = Path(__file__).parent / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        else:
            # Создаем временную иконку
            pixmap = QPixmap(32, 32)
            pixmap.fill(QColor(45, 45, 45))
            painter = QPainter(pixmap)
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Arial", 16, QFont.Bold))
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "M")
            painter.end()
            self.setWindowIcon(QIcon(pixmap))
        
        # Используем переданный API или создаем новый экземпляр
        self.api = api or ModSyncAPI()
        
        # Состояние синхронизации
        self.is_syncing = False
        self.sync_thread = None
        self.sync_worker = None
        
        # Инициализация системного трея
        self.tray_icon = None
        self.setup_system_tray()
        
        # Настройка UI
        self.setup_ui()
        
        # Проверка пути к папке mods
        mods_path = self.config.get_mods_path()
        if mods_path and not os.path.exists(mods_path):
            self.handle_missing_mods_folder(mods_path)
        
        # Таймер автосинхронизации
        self.auto_sync_timer = QTimer()
        self.auto_sync_timer.timeout.connect(self.auto_sync)
        self.update_auto_sync_timer()
        
        # Обновление информации о диске
        self.update_disk_space_info()

    def update_progress_throttled(self, current, total, filename, speed, eta):
        """Обновляет прогресс с ограничением частоты для предотвращения лагов"""
        current_time = time.time()
        if hasattr(self, '_last_progress_update') and current_time - self._last_progress_update < 0.1:
            return
        
        self._last_progress_update = current_time
        self.file_progress_label.setText(f"📝 {filename}: {format_size(current)}/{format_size(total)} " +
                                        f"({speed / 1024 / 1024:.1f} MB/сек, ETA: {eta})")
        percent = int((current / total * 100)) if total > 0 else 0
        self.file_progress.setValue(percent)
    
    def handle_missing_mods_folder(self, mods_path):
        """Обработка случая, когда папка mods не существует"""
        reply = QMessageBox.question(
            self,
            "📁 Папка не существует",
            f"Сохраненная папка mods не существует:\n{mods_path}\n\nХотите выбрать новую папку?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            self.select_mods_folder()
        else:
            self.config.set_mods_path("")
            self.folder_path_label.setText("Папка mods не выбрана")
    
    def setup_ui(self):
        """Настраивает пользовательский интерфейс"""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Верхняя панель с кнопками
        top_layout = QHBoxLayout()
        top_layout.setSpacing(15)
        
        # Кнопка выбора папки mods
        self.folder_btn = QPushButton("📂 Выбрать папку mods")
        self.folder_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #7f8c8d;
            }
        """)
        self.folder_btn.clicked.connect(self.select_mods_folder)
        top_layout.addWidget(self.folder_btn)
        
        # Текущий путь к папке mods
        self.folder_path_label = QLabel("Папка mods не выбрана")
        self.folder_path_label.setStyleSheet("""
            QLabel {
                color: #e74c3c;
                font-weight: bold;
                padding: 5px;
                background-color: #2d2d2d;
                border-radius: 4px;
                min-height: 25px;
            }
        """)
        self.folder_path_label.setWordWrap(True)
        top_layout.addWidget(self.folder_path_label, 1)
        
        # Кнопка настроек
        self.settings_btn = QPushButton("⚙️ Настройки")
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
        """)
        self.settings_btn.clicked.connect(self.show_settings)
        top_layout.addWidget(self.settings_btn)
        
        main_layout.addLayout(top_layout)
        
        # Информация о состоянии
        status_layout = QFormLayout()
        status_layout.setLabelAlignment(Qt.AlignRight)
        status_layout.setSpacing(15)
        
        self.last_sync_label = QLabel("Никогда")
        self.last_sync_label.setStyleSheet("color: #f39c12;")
        status_layout.addRow("🕒 Последняя синхронизация:", self.last_sync_label)
        
        self.next_sync_label = QLabel("Отключено")
        self.next_sync_label.setStyleSheet("color: #3498db;")
        status_layout.addRow("⏰ Следующая синхронизация:", self.next_sync_label)
        
        self.space_label = QLabel("🔄 Проверка...")
        self.space_label.setStyleSheet("color: #2ecc71;")
        status_layout.addRow("💾 Свободно на диске:", self.space_label)
        
        status_group = QGroupBox("📊 Состояние системы")
        status_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #444;
                border-radius: 5px;
                margin-top: 1ex;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        status_group.setLayout(status_layout)
        main_layout.addWidget(status_group)
        
        # Прогресс-бары
        progress_group = QGroupBox("📈 Прогресс синхронизации")
        progress_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #444;
                border-radius: 5px;
                margin-top: 1ex;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        progress_layout = QVBoxLayout()
        progress_layout.setSpacing(10)
        
        # Файловый прогресс
        self.file_progress_label = QLabel("📝 Файл: не выбран")
        self.file_progress_label.setStyleSheet("font-weight: bold;")
        progress_layout.addWidget(self.file_progress_label)
        
        self.file_progress = QProgressBar()
        self.file_progress.setValue(0)
        self.file_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #444;
                border-radius: 4px;
                text-align: center;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #3498db;
                width: 10px;
            }
        """)
        progress_layout.addWidget(self.file_progress)
        
        # Общий прогресс
        self.total_progress_label = QLabel("📊 Общий прогресс: 0%")
        self.total_progress_label.setStyleSheet("font-weight: bold;")
        progress_layout.addWidget(self.total_progress_label)
        
        self.total_progress = QProgressBar()
        self.total_progress.setValue(0)
        self.total_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #444;
                border-radius: 4px;
                text-align: center;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #2ecc71;
                width: 10px;
            }
        """)
        progress_layout.addWidget(self.total_progress)
        
        progress_group.setLayout(progress_layout)
        main_layout.addWidget(progress_group)
        
        # Лог
        log_group = QGroupBox("📋 Лог операций")
        log_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #444;
                border-radius: 5px;
                margin-top: 1ex;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        log_layout = QVBoxLayout()
        log_layout.setContentsMargins(10, 10, 10, 10)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #2d2d2d;
                color: #f8f8f2;
                border: 1px solid #444;
                border-radius: 4px;
            }
        """)
        self.log_text.setLineWrapMode(QTextEdit.NoWrap)
        log_layout.addWidget(self.log_text)
        
        # Чекбокс dry-run
        self.dry_run_checkbox = QCheckBox("🧪 Dry-run режим (только показать изменения, без применения)")
        self.dry_run_checkbox.setStyleSheet("color: #f39c12; font-weight: bold;")
        self.dry_run_checkbox.setChecked(False)
        log_layout.addWidget(self.dry_run_checkbox)
        
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)
        
        # Нижняя панель с кнопками
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(15)
        
        # Кнопка синхронизации
        self.sync_btn = QPushButton("🔄 Синхронизировать")
        self.sync_btn.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                min-height: 50px;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
            QPushButton:disabled {
                background-color: #7f8c8d;
            }
        """)
        self.sync_btn.clicked.connect(self.sync)
        bottom_layout.addWidget(self.sync_btn, 2)
        
        # Кнопка отмены
        self.cancel_btn = QPushButton("⏹ Отменить")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                min-height: 50px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
            QPushButton:disabled {
                background-color: #7f8c8d;
            }
        """)
        self.cancel_btn.clicked.connect(self.cancel_sync)
        bottom_layout.addWidget(self.cancel_btn, 1)
        
        main_layout.addLayout(bottom_layout)
        self.setLayout(main_layout)
        
        # Добавляем приветственное сообщение
        self.append_log("✅ ModSync клиент запущен")
        self.append_log("ℹ️ Выберите папку mods для начала синхронизации")
        
        # Обновляем состояние кнопок
        mods_path = self.config.get_mods_path()
        self.sync_btn.setEnabled(bool(mods_path))
    
    def setup_system_tray(self):
        """Настраивает системный трей"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        
        self.tray_icon = QSystemTrayIcon(self)
        
        # Пытаемся загрузить иконку
        icon_path = Path(__file__).parent / "icon.png"
        if icon_path.exists():
            self.tray_icon.setIcon(QIcon(str(icon_path)))
        else:
            # Создаем простую иконку
            pixmap = QPixmap(32, 32)
            pixmap.fill(QColor(45, 45, 45))
            painter = QPainter(pixmap)
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Arial", 16, QFont.Bold))
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "M")
            painter.end()
            self.tray_icon.setIcon(QIcon(pixmap))
        
        tray_menu = QMenu()
        
        self.tray_sync_action = QAction("🔄 Синхронизировать", self)
        self.tray_sync_action.triggered.connect(self.sync)
        tray_menu.addAction(self.tray_sync_action)
        
        tray_menu.addSeparator()
        
        show_action = QAction("👁️ Показать окно", self)
        show_action.triggered.connect(self.show_window)
        tray_menu.addAction(show_action)
        
        settings_action = QAction("⚙️ Настройки", self)
        settings_action.triggered.connect(self.show_settings)
        tray_menu.addAction(settings_action)
        
        tray_menu.addSeparator()
        
        exit_action = QAction("❌ Выход", self)
        exit_action.triggered.connect(self.close)
        tray_menu.addAction(exit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        
        # Обработчик двойного клика
        self.tray_icon.activated.connect(self.tray_icon_activated)
        
        # Показываем иконку если настройки разрешают
        if self.config.should_show_tray_icon():
            self.tray_icon.show()
            self.tray_icon.setToolTip("ModSync Client")
    
    def tray_icon_activated(self, reason):
        """Обработчик активации иконки в трее"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window()
    
    def show_window(self):
        """Показывает главное окно"""
        self.show()
        self.raise_()
        self.activateWindow()
    
    def closeEvent(self, event: QCloseEvent):
        """Обработчик закрытия окна"""
        if self.is_syncing:
            reply = QMessageBox.question(
                self,
                "CloseOperation❓",
                "Синхронизация выполняется. Вы уверены, что хотите закрыть приложение?\n\n"
                "⚠️ Синхронизация будет прервана и изменения могут быть частично применены.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                event.ignore()
                return
        
        # Сохраняем геометрию окна
        self.config.set_window_size(self.width(), self.height())
        
        # Скрываем иконку в трее
        if self.tray_icon:
            self.tray_icon.hide()
        
        event.accept()
    
    def select_mods_folder(self):
        """Открывает диалог выбора папки mods"""
        current_path = self.config.get_mods_path()
        if not current_path or not os.path.exists(current_path):
            current_path = str(Path.home())
        
        folder = QFileDialog.getExistingDirectory(
            self,
            "📂 Выберите папку mods",
            current_path,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        
        if folder:
            # Проверяем, существует ли папка и есть ли права на запись
            if not os.path.exists(folder):
                try:
                    os.makedirs(folder, exist_ok=True)
                except Exception as e:
                    QMessageBox.critical(self, "❌ Ошибка", f"Невозможно создать папку:\n{str(e)}")
                    return
            
            if not os.access(folder, os.W_OK):
                QMessageBox.critical(self, "❌ Ошибка", "Нет прав на запись в выбранную папку")
                return
            
            self.config.set_mods_path(folder)
            self.folder_path_label.setText(folder)
            self.folder_path_label.setStyleSheet("""
                QLabel {
                    color: #2ecc71;
                    font-weight: bold;
                    padding: 5px;
                    background-color: #2d2d2d;
                    border-radius: 4px;
                    min-height: 25px;
                }
            """)
            self.append_log(f"✅ Выбрана папка mods: {folder}")
            self.update_disk_space_info()
            self.sync_btn.setEnabled(True)
    
    def update_disk_space_info(self):
        """Обновляет информацию о свободном месте на диске"""
        mods_path = self.config.get_mods_path()
        if not mods_path:
            self.space_label.setText("📁 Папка mods не выбрана")
            self.space_label.setStyleSheet("color: #e74c3c;")
            return
        
        try:
            if not os.path.exists(mods_path):
                self.space_label.setText("❌ Папка не существует")
                self.space_label.setStyleSheet("color: #e74c3c;")
                return
            
            free_space = get_free_space(Path(mods_path))
            self.space_label.setText(f"{format_size(free_space)} свободно")
            
            # Предупреждение если мало места
            if free_space < 1 * 1024 ** 3:  # 1 ГБ
                self.space_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
            elif free_space < 5 * 1024 ** 3:  # 5 ГБ
                self.space_label.setStyleSheet("color: #f39c12; font-weight: bold;")
            else:
                self.space_label.setStyleSheet("color: #2ecc71; font-weight: bold;")
                
        except Exception as e:
            self.space_label.setText(f"❌ Ошибка: {str(e)}")
            self.space_label.setStyleSheet("color: #e74c3c;")
    
    def show_settings(self):
        """Показывает диалог настроек"""
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() == QDialog.Accepted:
            # Обновляем состояние после изменения настроек
            self.update_auto_sync_timer()
            
            if self.config.should_show_tray_icon():
                if self.tray_icon:
                    self.tray_icon.show()
            else:
                if self.tray_icon:
                    self.tray_icon.hide()
    
    def update_auto_sync_timer(self):
        """Обновляет таймер автосинхронизации"""
        interval = self.config.get_sync_interval()
        if interval > 0:
            self.auto_sync_timer.start(interval * 60 * 1000)  # в миллисекундах
            next_sync = datetime.now() + timedelta(minutes=interval)
            self.next_sync_label.setText(next_sync.strftime("%Y-%m-%d %H:%M:%S"))
            self.next_sync_label.setStyleSheet("color: #3498db;")
        else:
            self.auto_sync_timer.stop()
            self.next_sync_label.setText("Отключено")
            self.next_sync_label.setStyleSheet("color: #e74c3c;")
    
    def auto_sync(self):
        """Выполняет автоматическую синхронизацию"""
        if self.is_syncing:
            self.append_log("⚠️ Автосинхронизация пропущена: уже выполняется синхронизация")
            return
        
        mods_path = self.config.get_mods_path()
        if not mods_path or not os.path.exists(mods_path):
            self.append_log("⚠️ Автосинхронизация пропущена: папка mods не настроена")
            return
        
        if not self.config.get_sync_settings().get("auto_sync", True):
            return
        
        self.append_log("⏰ Автоматическая синхронизация запущена...")
        self.sync()
    
    def sync(self):
        """Запускает синхронизацию"""
        if self.is_syncing:
            QMessageBox.warning(self, "🔄 Синхронизация", "🔄 Синхронизация уже выполняется")
            return
        
        mods_path = self.config.get_mods_path()
        if not mods_path:
            QMessageBox.warning(self, "❌ Ошибка", "❌ Папка mods не выбрана")
            return
        
        if not os.path.exists(mods_path):
            reply = QMessageBox.question(
                self,
                "📁 Папка не существует",
                f"Папка {mods_path} не существует. Создать её?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                try:
                    os.makedirs(mods_path, exist_ok=True)
                    self.append_log(f"✅ Создана папка: {mods_path}")
                except Exception as e:
                    QMessageBox.critical(self, "❌ Ошибка", f"❌ Ошибка создания папки:\n{str(e)}")
                    return
            else:
                return
        
        dry_run = self.dry_run_checkbox.isChecked()
        
        # Подтверждение для реальной синхронизации
        if not dry_run and self.config.should_show_confirmation_dialog():
            msg = "❓ Вы уверены, что хотите начать синхронизацию?\n\n"
            msg += "Будут загружены новые файлы и удалены устаревшие.\n"
            msg += "Рекомендуется создать резервную копию перед продолжением."
            
            reply = QMessageBox.question(
                self,
                "Подтверждение синхронизации",
                msg,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply != QMessageBox.Yes:
                return
        
        # Начинаем синхронизацию
        self.continue_sync()
    
    def continue_sync(self):
        """Продолжает синхронизацию после обработки бекапа"""
        mods_path = self.config.get_mods_path()
        if not mods_path:
            return
        
        dry_run = self.dry_run_checkbox.isChecked()
        
        # Запускаем синхронизацию в отдельном потоке
        self.sync_worker = SyncWorker(self.api, mods_path, dry_run)
        self.sync_thread = QThread()
        self.sync_worker.moveToThread(self.sync_thread)
        
        # Подключаем сигналы
        self.sync_thread.started.connect(self.sync_worker.run)
        self.sync_worker.finished.connect(self.on_sync_complete)
        self.sync_worker.error.connect(self.on_sync_error)
        self.sync_worker.progress_file.connect(self.update_file_progress)
        self.sync_worker.progress_total.connect(self.update_total_progress)
        self.sync_worker.log_message.connect(self.append_log)
        self.sync_worker.request_backup_dialog.connect(self.show_backup_dialog)
        self.sync_worker.cancel_requested.connect(self.on_cancel_requested)
        
        # Завершение потока
        self.sync_worker.finished.connect(self.sync_thread.quit)
        self.sync_worker.error.connect(self.sync_thread.quit)
        self.sync_worker.cancel_requested.connect(self.sync_thread.quit)
        self.sync_thread.finished.connect(self.sync_thread.deleteLater)
        self.sync_worker.deleteLater()
        
        # Блокируем интерфейс
        self.is_syncing = True
        self.sync_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.folder_btn.setEnabled(False)
        self.settings_btn.setEnabled(False)
        
        if dry_run:
            self.sync_btn.setText("🧪 Dry-run...")
            self.sync_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f39c12;
                    color: white;
                    border: none;
                    padding: 12px 24px;
                    border-radius: 4px;
                    font-size: 14px;
                    font-weight: bold;
                    min-height: 50px;
                }
                QPushButton:hover {
                    background-color: #e67e22;
                }
                QPushButton:disabled {
                    background-color: #7f8c8d;
                }
            """)
            self.append_log("🧪 Запуск dry-run режима...")
        else:
            self.sync_btn.setText("🔄 Синхронизация...")
            self.sync_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    border: none;
                    padding: 12px 24px;
                    border-radius: 4px;
                    font-size: 14px;
                    font-weight: bold;
                    min-height: 50px;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QPushButton:disabled {
                    background-color: #7f8c8d;
                }
            """)
            self.append_log("🔄 Начинаю синхронизацию...")
        
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                min-height: 50px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        
        if self.tray_icon:
            self.tray_sync_action.setEnabled(False)
        
        self.sync_thread.start()
    
    def show_backup_dialog(self, affected_files, total_bytes):
        """Показывает диалог подтверждения создания бекапа"""
        dialog = BackupDialog(self, affected_files, total_bytes)
        if dialog.exec() == QDialog.Accepted:
            # Сохраняем настройку "больше не спрашивать"
            if dialog.remember_checkbox.isChecked():
                self.config.set_show_backup_dialog(False)
                self.config.set_create_backups(True)
            
            # Продолжаем синхронизацию
            self.continue_sync()
        else:
            self.is_syncing = False
            self.sync_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            self.folder_btn.setEnabled(True)
            self.settings_btn.setEnabled(True)
            self.sync_btn.setText("🔄 Синхронизировать")
            self.sync_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2ecc71;
                    color: white;
                    border: none;
                    padding: 12px 24px;
                    border-radius: 4px;
                    font-size: 14px;
                    font-weight: bold;
                    min-height: 50px;
                }
                QPushButton:hover {
                    background-color: #27ae60;
                }
                QPushButton:disabled {
                    background-color: #7f8c8d;
                }
            """)
            if self.tray_icon:
                self.tray_sync_action.setEnabled(True)
            self.append_log("❌ Синхронизация отменена пользователем")
    
    def cancel_sync(self):
        """Отменяет текущую синхронизацию"""
        if self.is_syncing and self.sync_worker:
            self.append_log("⏹ Запрос на отмену синхронизации...")
            self.sync_worker.cancel()
            self.cancel_btn.setEnabled(False)
    
    @Slot()
    def on_cancel_requested(self):
        """Обработка отмены синхронизации"""
        self.is_syncing = False
        self.sync_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.folder_btn.setEnabled(True)
        self.settings_btn.setEnabled(True)
        self.sync_btn.setText("🔄 Синхронизировать")
        self.sync_btn.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                min-height: 50px;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
            QPushButton:disabled {
                background-color: #7f8c8d;
            }
        """)
        if self.tray_icon:
            self.tray_sync_action.setEnabled(True)
        self.append_log("✅ Синхронизация отменена")
    
    @Slot(int, int, str)
    def update_file_progress(self, current, total, filename):
        """Обновляет прогресс-бар текущего файла"""
        if total > 0:
            current_mb = current / 1024 / 1024
            total_mb = total / 1024 / 1024
            percent = (current / total) * 100
            self.file_progress_label.setText(f"📝 {filename}: {current_mb:.1f}/{total_mb:.1f} MB ({percent:.1f}%)")
            self.file_progress.setValue(int(percent))
        else:
            self.file_progress_label.setText(f"📝 {filename}: {current / 1024 / 1024:.1f} MB")
            self.file_progress.setValue(0)
    
    @Slot(int, int, int)
    def update_total_progress(self, current_bytes, total_bytes, percent):
        """Обновляет общий прогресс-бар"""
        self.total_progress.setValue(percent)
        
        if total_bytes > 0:
            current_mb = current_bytes / 1024 / 1024
            total_mb = total_bytes / 1024 / 1024
            self.total_progress_label.setText(f"📊 Общий прогресс: {current_mb:.1f}/{total_mb:.1f} MB ({percent:.1f}%)")
        else:
            self.total_progress_label.setText(f"📊 Общий прогресс: {percent:.1f}%")
    
    @Slot(dict)
    def on_sync_complete(self, result):
        """Обработка завершения синхронизации"""
        self.is_syncing = False
        self.sync_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.folder_btn.setEnabled(True)
        self.settings_btn.setEnabled(True)
        self.sync_btn.setText("🔄 Синхронизировать")
        self.sync_btn.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                min-height: 50px;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
            QPushButton:disabled {
                background-color: #7f8c8d;
            }
        """)
        if self.tray_icon:
            self.tray_sync_action.setEnabled(True)
        
        # Обновляем информацию
        self.last_sync_label.setText(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.last_sync_label.setStyleSheet("color: #2ecc71;")
        self.update_disk_space_info()
        
        # Показываем результаты
        deleted = result.get("deleted_count", 0)
        downloaded = result.get("downloaded_count", 0)
        total_size = result.get("total_downloaded", 0)
        
        summary = (
            f"✅ Синхронизация завершена успешно!\n"
            f"🗑️ Удалено файлов: {deleted}\n"
            f"📥 Загружено/обновлено файлов: {downloaded}\n"
            f"📊 Общий размер загрузки: {format_size(total_size)}"
        )
        self.append_log(summary)
        
        # Показываем уведомление
        if not self.dry_run_checkbox.isChecked() and self.config.should_show_notifications() and self.tray_icon:
            message = f"Синхронизация завершена!\n"
            message += f"Удалено: {deleted} файлов\n"
            message += f"Загружено: {downloaded} файлов"
            self.tray_icon.showMessage(
                "ModSync", message, QSystemTrayIcon.Information, 5000
            )
    
    @Slot(str)
    def on_sync_error(self, error_message):
        """Обработка ошибки синхронизации"""
        self.is_syncing = False
        self.sync_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.folder_btn.setEnabled(True)
        self.settings_btn.setEnabled(True)
        self.sync_btn.setText("🔄 Синхронизировать")
        self.sync_btn.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                min-height: 50px;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
            QPushButton:disabled {
                background-color: #7f8c8d;
            }
        """)
        if self.tray_icon:
            self.tray_sync_action.setEnabled(True)
        
        self.append_log(f"❌ Ошибка синхронизации: {error_message}")
        
        # Показываем уведомление об ошибке
        if self.config.should_show_notifications() and self.tray_icon:
            self.tray_icon.showMessage(
                "ModSync Error", error_message, QSystemTrayIcon.Critical, 5000
            )
    
    def append_log(self, message):
        """Добавляет сообщение в лог"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        if "✅" in message or "успешно" in message.lower():
            formatted_message = f"<span style='color: #2ecc71;'>{formatted_message}</span>"
        elif "❌" in message or "ошибка" in message.lower():
            formatted_message = f"<span style='color: #e74c3c;'>{formatted_message}</span>"
        elif "⚠️" in message or "внимание" in message.lower():
            formatted_message = f"<span style='color: #f39c12;'>{formatted_message}</span>"
        elif "🔄" in message or "синхронизация" in message.lower():
            formatted_message = f"<span style='color: #3498db;'>{formatted_message}</span>"
        elif "📥" in message or "загрузка" in message.lower():
            formatted_message = f"<span style='color: #9b59b6;'>{formatted_message}</span>"
        
        self.log_text.append(formatted_message)
        self.log_text.setTextCursor(cursor)
        self.log_text.ensureCursorVisible()