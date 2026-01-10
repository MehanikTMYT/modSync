#!/usr/bin/env python3
"""
Minecraft Mod Sync Server
Автоматический сервер для синхронизации модов с поддержкой тестов скорости и мониторинга.
"""
import http.server
import socketserver
import os
import json
import hashlib
import threading
import time
import argparse
import logging
from datetime import datetime, timedelta
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from functools import lru_cache
from typing import Dict, Any, Optional, Tuple

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class ServerConfig:
    """Конфигурация сервера с валидацией"""
    
    def __init__(self, port: int = 8000, mods_dir: str = './mods', 
                 scan_interval: int = 5, enable_watcher: bool = True,
                 max_test_file_size: int = 10 * 1024 * 1024):
        self._validate_port(port)
        self._validate_directory(mods_dir)
        
        self.port = port
        self.mods_dir = os.path.abspath(mods_dir)
        self.scan_interval = max(0, scan_interval)
        self.enable_watcher = enable_watcher
        self.max_test_file_size = max_test_file_size
        self.start_time = time.time()
    
    def _validate_port(self, port: int):
        if not (1024 <= port <= 65535):
            raise ValueError("Порт должен быть в диапазоне 1024-65535")
    
    def _validate_directory(self, directory: str):
        try:
            os.makedirs(directory, exist_ok=True)
            if not os.access(directory, os.W_OK):
                raise PermissionError(f"Нет прав на запись в директорию: {directory}")
        except Exception as e:
            raise ValueError(f"Ошибка валидации директории: {str(e)}")
    
    @property
    def uptime(self) -> timedelta:
        """Возвращает время работы сервера"""
        return timedelta(seconds=time.time() - self.start_time)

class FileHashManager:
    """Менеджер хеширования файлов с кэшированием и оптимизацией"""
    
    def __init__(self, mods_dir: str):
        self.mods_dir = mods_dir
        self.hash_cache = {}
        self.last_scan_time = 0
        self.scan_lock = threading.RLock()
        self.test_files = {
            'speed_test_10kb.bin': 10 * 1024,
            'speed_test_100kb.bin': 100 * 1024,
            'speed_test_1mb.bin': 1 * 1024 * 1024,
            'speed_test_10mb.bin': 10 * 1024 * 1024
        }
        # Паттерны файлов для игнорирования
        self.ignore_patterns = [
            r'\.filepart$',          # Временные файлы WinSCP
            r'^\.',                  # Скрытые файлы
            r'hashes\.json$',        # Файлы хешей
            r'\.hashes\.json$',      # Временные файлы хешей
            r'speed_test_\d+.*\.bin$' # Тестовые файлы скорости
        ]
    
    def _should_ignore_file(self, filename: str, filepath: str) -> bool:
        """Проверяет, нужно ли игнорировать файл"""
        # Игнорирование по расширению .filepart
        if filename.endswith('.filepart'):
            logger.debug(f"Пропуск временного файла WinSCP: {filename}")
            return True
        
        # Игнорирование по паттернам
        import re
        for pattern in self.ignore_patterns:
            if re.search(pattern, filename, re.IGNORECASE):
                logger.debug(f"Пропуск файла по паттерну {pattern}: {filename}")
                return True
        
        # Игнорирование если файл все еще копируется (проверка по времени изменения)
        try:
            file_stat = os.stat(filepath)
            current_time = time.time()
            # Если файл изменялся менее 10 секунд назад - возможно он еще копируется
            if current_time - file_stat.st_mtime < 10:
                # Дополнительная проверка для очень больших файлов
                if file_stat.st_size > 100 * 1024 * 1024:  # >100MB
                    logger.info(f"Пропуск потенциально копирующегося файла (большой размер): {filename}")
                    return True
        except Exception as e:
            logger.warning(f"Ошибка проверки времени файла {filename}: {str(e)}")
        
        return False
    
    def _calculate_file_hash(self, filepath: str, chunk_size: int = 4096) -> str:
        """Вычисляет MD5 хеш файла по частям для экономии памяти"""
        hash_md5 = hashlib.md5()
        try:
            with open(filepath, 'rb') as f:
                for chunk in iter(lambda: f.read(chunk_size), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            logger.error(f"Ошибка хеширования файла {filepath}: {str(e)}")
            raise
    
    @lru_cache(maxsize=128)
    def get_file_info(self, relpath: str) -> Dict[str, Any]:
        """Возвращает информацию о файле с кэшированием"""
        filepath = os.path.join(self.mods_dir, relpath)
        if not os.path.exists(filepath):
            return None
        
        try:
            file_stat = os.stat(filepath)
            return {
                'size': file_stat.st_size,
                'mtime': file_stat.st_mtime,
                'hash': self._calculate_file_hash(filepath)
            }
        except Exception as e:
            logger.error(f"Ошибка получения информации о файле {relpath}: {str(e)}")
            return None
    
    def generate_test_files(self) -> None:
        """Генерация тестовых файлов для измерения скорости соединения"""
        for filename, size in self.test_files.items():
            filepath = os.path.join(self.mods_dir, filename)
            if not os.path.exists(filepath) or os.path.getsize(filepath) != size:
                logger.info(f"Генерация тестового файла: {filename} ({size/1024/1024:.2f} MB)")
                try:
                    with open(filepath, 'wb') as f:
                        # Используем повторяющиеся данные для экономии памяти
                        chunk = b'\x00' * min(1024 * 1024, size)  # 1MB chunk
                        remaining = size
                        while remaining > 0:
                            write_size = min(len(chunk), remaining)
                            f.write(chunk[:write_size])
                            remaining -= write_size
                except Exception as e:
                    logger.error(f"Ошибка генерации тестового файла {filename}: {str(e)}")
    
    def scan_mods_directory(self) -> Dict[str, Any]:
        """Сканирование директории модов и генерация хешей"""
        with self.scan_lock:
            current_time = time.time()
            # Кэширование результатов сканирования (каждые 10 секунд)
            if current_time - self.last_scan_time < 10 and self.hash_cache:
                return self.hash_cache
            
            logger.info("Начало сканирования директории модов...")
            hashes = {}
            total_files = 0
            total_size = 0
            skipped_files = {
                'filepart': 0,
                'patterns': 0,
                'recent_changes': 0
            }
            
            try:
                for root, _, files in os.walk(self.mods_dir):
                    for file in files:
                        filepath = os.path.join(root, file)
                        relpath = os.path.relpath(filepath, self.mods_dir).replace('\\', '/')
                        
                        # Проверка на игнорирование файла
                        if self._should_ignore_file(file, filepath):
                            if file.endswith('.filepart'):
                                skipped_files['filepart'] += 1
                            else:
                                skipped_files['patterns'] += 1
                            continue
                        
                        file_size = os.path.getsize(filepath)
                        
                        try:
                            file_hash = self._calculate_file_hash(filepath)
                            hashes[relpath] = {
                                'hash': file_hash,
                                'size': file_size,
                                'last_modified': os.path.getmtime(filepath)
                            }
                            total_files += 1
                            total_size += file_size
                            
                        except Exception as e:
                            logger.warning(f"Пропущен файл {relpath}: {str(e)}")
                
                # Логирование пропущенных файлов
                total_skipped = sum(skipped_files.values())
                if total_skipped > 0:
                    logger.info(f"Пропущено файлов во время сканирования: {total_skipped}")
                    if skipped_files['filepart'] > 0:
                        logger.info(f"  - Временные файлы WinSCP (.filepart): {skipped_files['filepart']}")
                    if skipped_files['patterns'] > 0:
                        logger.info(f"  - Файлы по паттернам игнорирования: {skipped_files['patterns']}")
                    if skipped_files['recent_changes'] > 0:
                        logger.info(f"  - Файлы с недавними изменениями: {skipped_files['recent_changes']}")
                
                # Обновление кэша
                self.hash_cache = {
                    'generated_at': datetime.now().isoformat(),
                    'file_count': total_files,
                    'total_size': total_size,
                    'files': hashes,
                    'skipped_files': skipped_files
                }
                self.last_scan_time = current_time
                
                logger.info(f"Сканирование завершено: {total_files} файлов, общий размер: {total_size/1024/1024:.2f} MB")
                return self.hash_cache
                
            except Exception as e:
                logger.error(f"Критическая ошибка при сканировании: {str(e)}")
                raise
    
    def save_hashes(self, data: Dict[str, Any]) -> bool:
        """Сохранение хешей в файл"""
        try:
            hashes_path = os.path.join(self.mods_dir, 'hashes.json')
            with open(hashes_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения хешей: {str(e)}")
            return False

class AutoScanner:
    """Автоматический сканер директории с управлением жизненным циклом"""
    
    def __init__(self, hash_manager: FileHashManager, interval_minutes: int):
        self.hash_manager = hash_manager
        self.interval_seconds = interval_minutes * 60
        self.running = False
        self.thread = None
    
    def start(self) -> None:
        """Запуск автоматического сканера"""
        if self.interval_seconds <= 0 or self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._scan_loop, daemon=True)
        self.thread.start()
        logger.info(f"Автоматический сканер запущен (интервал: {self.interval_seconds//60} минут)")
    
    def stop(self) -> None:
        """Остановка автоматического сканера"""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
    
    def _scan_loop(self) -> None:
        """Основной цикл сканирования"""
        while self.running:
            try:
                data = self.hash_manager.scan_mods_directory()
                self.hash_manager.save_hashes(data)
                logger.info(f"Автоматическое сканирование выполнено. Следующее через {self.interval_seconds//60} минут.")
                time.sleep(self.interval_seconds)
            except Exception as e:
                logger.error(f"Ошибка в автоматическом сканере: {str(e)}")
                time.sleep(60)  # Пауза при ошибке

class FileWatcher:
    """Наблюдатель за изменениями в файловой системе"""
    
    class ModFolderHandler(FileSystemEventHandler):
        """Обработчик изменений в папке mods"""
        
        def __init__(self, hash_manager: FileHashManager):
            self.hash_manager = hash_manager
            self.last_update = 0
            self.update_lock = threading.Lock()
            self.min_update_interval = 5  # секунд
        
        def _is_temporary_file(self, filepath: str) -> bool:
            """Проверяет, является ли файл временным"""
            filename = os.path.basename(filepath)
            return (filename.endswith('.filepart') or
                    filename.startswith('.') or
                    filename in ['hashes.json', '.hashes.json'])
        
        def on_any_event(self, event) -> None:
            """Обработка любого события в папке"""
            if event.is_directory:
                return
            
            # Игнорирование временных файлов
            if self._is_temporary_file(event.src_path):
                logger.debug(f"Игнорирование события для временного файла: {event.event_type} - {event.src_path}")
                return
            
            current_time = time.time()
            if current_time - self.last_update < self.min_update_interval:
                return
            
            with self.update_lock:
                if current_time - self.last_update < self.min_update_interval:
                    return
                
                self.last_update = current_time
                logger.info(f"Обнаружено изменение: {event.event_type} - {event.src_path}")
                
                try:
                    data = self.hash_manager.scan_mods_directory()
                    self.hash_manager.save_hashes(data)
                    logger.info("Хеши успешно обновлены после изменения файлов")
                except Exception as e:
                    logger.error(f"Ошибка обновления хешей после изменения: {str(e)}")
    
    def __init__(self, hash_manager: FileHashManager, mods_dir: str):
        self.hash_manager = hash_manager
        self.mods_dir = mods_dir
        self.observer = None
    
    def start(self) -> None:
        """Запуск наблюдателя"""
        if not os.path.exists(self.mods_dir):
            os.makedirs(self.mods_dir)
        
        self.observer = Observer()
        event_handler = self.ModFolderHandler(self.hash_manager)
        self.observer.schedule(event_handler, self.mods_dir, recursive=True)
        self.observer.start()
        logger.info(f"Наблюдатель за файловой системой запущен для: {self.mods_dir}")
    
    def stop(self) -> None:
        """Остановка наблюдателя"""
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=2.0)

class SpeedTestHandler:
    """Обработчик для тестирования скорости соединения с потоковой передачей"""
    
    @staticmethod
    def generate_test_data(size: int, chunk_size: int = 65536):
        """Генератор тестовых данных по частям"""
        remaining = size
        while remaining > 0:
            chunk = b'\x01' * min(chunk_size, remaining)
            yield chunk
            remaining -= len(chunk)
    
    @staticmethod
    def handle_speed_test(handler, file_size: int) -> bool:
        """Обработка запроса на тест скорости с потоковой передачей"""
        try:
            handler.send_response(200)
            handler.send_header('Content-type', 'application/octet-stream')
            handler.send_header('Content-Length', str(file_size))
            handler.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            handler.send_header('Pragma', 'no-cache')
            handler.send_header('Expires', '0')
            handler.end_headers()
            
            # Потоковая передача данных
            for chunk in SpeedTestHandler.generate_test_data(file_size):
                handler.wfile.write(chunk)
                handler.wfile.flush()
            
            return True
        except (ConnectionResetError, BrokenPipeError):
            logger.warning("Клиент разорвал соединение во время теста скорости")
            return False
        except Exception as e:
            logger.error(f"Ошибка при тесте скорости: {str(e)}")
            return False

class ModSyncHandler(http.server.SimpleHTTPRequestHandler):
    """Основной обработчик запросов сервера"""
    
    def __init__(self, *args, **kwargs):
        self.config: ServerConfig = kwargs.pop('config')
        self.hash_manager: FileHashManager = kwargs.pop('hash_manager')
        super().__init__(*args, directory=self.config.mods_dir, **kwargs)
    
    def log_message(self, format: str, *args) -> None:
        """Кастомное логирование запросов"""
        logger.info(f"{self.client_address[0]} - {format % args}")
    
    def send_json_response(self, data: Dict[str, Any], status: int = 200, cache_control: str = 'no-cache') -> None:
        """Отправка JSON ответа"""
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.send_header('Cache-Control', cache_control)
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def do_GET(self) -> None:
        """Обработка GET запросов"""
        # Тесты скорости
        speed_tests = {
            '/speed_test_10kb.bin': 10 * 1024,
            '/speed_test_100kb.bin': 100 * 1024,
            '/speed_test_1mb.bin': 1 * 1024 * 1024,
            '/speed_test_10mb.bin': 10 * 1024 * 1024
        }
        
        if self.path in speed_tests:
            SpeedTestHandler.handle_speed_test(self, speed_tests[self.path])
            return
        
        # Информация о сервере
        if self.path == '/server_info':
            server_info = {
                'server_time': datetime.now().isoformat(),
                'uptime': str(self.config.uptime),
                'mods_dir': self.config.mods_dir,
                'available_test_files': list(speed_tests.keys()),
                'auto_scan_interval': self.config.scan_interval,
                'file_watcher_enabled': self.config.enable_watcher
            }
            self.send_json_response(server_info)
            return
        
        # Хеши файлов
        if self.path == '/hashes.json':
            try:
                data = self.hash_manager.scan_mods_directory()
                data['server_stats'] = {
                    'uptime': str(self.config.uptime),
                    'auto_scan_interval': self.config.scan_interval,
                    'file_watcher_enabled': self.config.enable_watcher,
                    'last_scan_time': datetime.now().isoformat(),
                    'skipped_files_info': data.get('skipped_files', {})
                }
                self.send_json_response(data)
            except Exception as e:
                logger.error(f"Ошибка обработки hashes.json: {str(e)}")
                self.send_json_response({'error': str(e)}, status=500)
            return
        
        # Принудительное обновление хешей
        if self.path == '/force_scan':
            try:
                data = self.hash_manager.scan_mods_directory()
                self.hash_manager.save_hashes(data)
                self.send_json_response({
                    'status': 'success',
                    'message': 'Сканирование успешно выполнено',
                    'timestamp': datetime.now().isoformat(),
                    'file_count': data['file_count'],
                    'total_size_mb': data['total_size'] / 1024 / 1024,
                    'skipped_files': data.get('skipped_files', {})
                })
            except Exception as e:
                self.send_json_response({'status': 'error', 'message': str(e)}, status=500)
            return
        
        # Статус сервера
        if self.path == '/status':
            status = {
                'status': 'online',
                'server_time': datetime.now().isoformat(),
                'uptime': str(self.config.uptime),
                'version': '1.0.0'
            }
            
            try:
                hashes_path = os.path.join(self.config.mods_dir, 'hashes.json')
                if os.path.exists(hashes_path):
                    try:
                        with open(hashes_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            status.update({
                                'mods_count': data.get('file_count', 0),
                                'total_size_mb': data.get('total_size', 0) / 1024 / 1024,
                                'last_scan': data.get('generated_at', 'unknown'),
                                'skipped_files': data.get('skipped_files', {})
                            })
                    except json.JSONDecodeError:
                        status['warning'] = 'Хеши повреждены, требуется пересканирование'
            except Exception as e:
                logger.error(f"Ошибка получения статуса: {str(e)}")
            
            self.send_json_response(status)
            return
        
        # Статическая документация
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(self._get_documentation().encode('utf-8'))
            return
        
        # Обработка остальных запросов
        super().do_GET()
    
    def do_HEAD(self) -> None:
        """Обработка HEAD запросов"""
        # Проверка существования файлов без передачи содержимого
        if self.path.startswith('/speed_test_') or self.path == '/hashes.json':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
        else:
            super().do_HEAD()
    
    def _get_documentation(self) -> str:
        """Возвращает HTML документацию сервера"""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Minecraft Mod Sync Server</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }
                h1 { color: #2c3e50; }
                .endpoint { background: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 5px; }
                .method { background: #e3f2fd; padding: 3px 8px; border-radius: 3px; font-weight: bold; }
                code { background: #e9ecef; padding: 2px 6px; border-radius: 3px; }
            </style>
        </head>
        <body>
            <h1>🎮 Minecraft Mod Sync Server</h1>
            <p><strong>Версия:</strong> 1.0.0</p>
            <p><strong>Время работы:</strong> <span id="uptime"></span></p>
            
            <h2>Доступные endpoints:</h2>
            
            <div class="endpoint">
                <span class="method">GET</span> <code>/hashes.json</code>
                <p>Получение списка всех файлов модов с их хешами и размерами</p>
            </div>
            
            <div class="endpoint">
                <span class="method">GET</span> <code>/server_info</code>
                <p>Информация о сервере: время работы, настройки, доступные тесты</p>
            </div>
            
            <div class="endpoint">
                <span class="method">GET</span> <code>/status</code>
                <p>Текущий статус сервера и статистика модов</p>
            </div>
            
            <div class="endpoint">
                <span class="method">GET</span> <code>/force_scan</code>
                <p>Принудительное обновление списка файлов и хешей</p>
            </div>
            
            <div class="endpoint">
                <span class="method">GET</span> <code>/speed_test_*.bin</code>
                <p>Тесты скорости соединения (10kb, 100kb, 1mb, 10mb)</p>
            </div>
            
            <h2>Особенности обработки файлов:</h2>
            <ul>
                <li>❌ <strong>Игнорируются .filepart файлы</strong> - временные файлы WinSCP во время передачи</li>
                <li>❌ Скрытые файлы (начинающиеся с точки)</li>
                <li>❌ Файлы хешей (hashes.json)</li>
                <li>❌ Тестовые файлы скорости</li>
                <li>⏳ Файлы с недавними изменениями (менее 10 секунд) для больших файлов</li>
            </ul>
            
            <h2>Команды для клиента:</h2>
            <ul>
                <li><code>curl http://localhost:8000/server_info</code> - информация о сервере</li>
                <li><code>curl http://localhost:8000/force_scan</code> - принудительное сканирование</li>
                <li><code>curl http://localhost:8000/status</code> - проверка статуса</li>
            </ul>
            
            <script>
                // Обновление времени работы
                function updateUptime() {
                    fetch('/status')
                        .then(response => response.json())
                        .then(data => {
                            document.getElementById('uptime').textContent = data.uptime || '0:00:00';
                        })
                        .catch(error => console.error('Ошибка:', error));
                }
                updateUptime();
                setInterval(updateUptime, 1000);
            </script>
        </body>
        </html>
        """

def run_server(config: ServerConfig) -> None:
    """Основная функция запуска сервера"""
    logger.info("🚀 Запуск Minecraft Mod Sync Server")
    
    try:
        # Инициализация компонентов
        hash_manager = FileHashManager(config.mods_dir)
        
        # Генерация тестовых файлов
        hash_manager.generate_test_files()
        
        # Начальное сканирование
        initial_data = hash_manager.scan_mods_directory()
        hash_manager.save_hashes(initial_data)
        
        # Запуск фоновых задач
        auto_scanner = None
        file_watcher = None
        
        if config.scan_interval > 0:
            auto_scanner = AutoScanner(hash_manager, config.scan_interval)
            auto_scanner.start()
        
        if config.enable_watcher:
            file_watcher = FileWatcher(hash_manager, config.mods_dir)
            file_watcher.start()
        
        # Настройка обработчика
        class CustomHandler(ModSyncHandler):
            def __init__(self, *args, **kwargs):
                kwargs['config'] = config
                kwargs['hash_manager'] = hash_manager
                super().__init__(*args, **kwargs)
        
        # Запуск HTTP сервера
        with socketserver.TCPServer(("", config.port), CustomHandler) as httpd:
            logger.info(f"✅ Сервер успешно запущен на порту {config.port}")
            logger.info(f"📁 Директория модов: {config.mods_dir}")
            logger.info(f"🔗 Базовый URL: http://localhost:{config.port}")
            logger.info(f"🔄 Автоматическое сканирование: {'каждые ' + str(config.scan_interval) + ' минут' if config.scan_interval > 0 else 'отключено'}")
            logger.info(f"👀 Файловый наблюдатель: {'включен' if config.enable_watcher else 'отключен'}")
            logger.info("💡 Для завершения работы нажмите Ctrl+C")
            
            httpd.serve_forever()
            
    except KeyboardInterrupt:
        logger.info("🛑 Сервер остановлен пользователем")
    except Exception as e:
        logger.critical(f"❌ Критическая ошибка сервера: {str(e)}", exc_info=True)
    finally:
        # Корректное завершение фоновых задач
        if 'auto_scanner' in locals() and auto_scanner:
            auto_scanner.stop()
        if 'file_watcher' in locals() and file_watcher:
            file_watcher.stop()
        
        logger.info("✨ Сервер успешно завершил работу")

def main() -> None:
    """Точка входа приложения"""
    parser = argparse.ArgumentParser(description='Minecraft Mod Sync Server')
    parser.add_argument('--port', type=int, default=8000, help='Порт сервера (1024-65535)')
    parser.add_argument('--mods-dir', default='./mods', help='Директория с модами')
    parser.add_argument('--scan-interval', type=int, default=5, 
                      help='Интервал автоматического сканирования в минутах (0 для отключения)')
    parser.add_argument('--disable-watcher', action='store_true', 
                      help='Отключить наблюдатель за файловой системой')
    parser.add_argument('--debug', action='store_true', help='Режим отладки')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        config = ServerConfig(
            port=args.port,
            mods_dir=args.mods_dir,
            scan_interval=args.scan_interval,
            enable_watcher=not args.disable_watcher
        )
        run_server(config)
    except ValueError as e:
        logger.error(f"❌ Ошибка конфигурации: {str(e)}")
        exit(1)
    except Exception as e:
        logger.critical(f"❌ Неожиданная ошибка: {str(e)}", exc_info=True)
        exit(1)

if __name__ == "__main__":
    main()