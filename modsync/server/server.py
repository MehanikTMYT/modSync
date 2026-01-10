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
import re
from datetime import datetime, timedelta
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from functools import lru_cache
from typing import Dict, Any, Optional, Tuple


class ModSyncServer:
    """HTTP-сервер для синхронизации модов Minecraft"""
    
    def __init__(self, port=8000, mods_directory="./mods", enable_monitoring=True):
        self.port = port
        self.mods_directory = os.path.abspath(mods_directory)
        self.enable_monitoring = enable_monitoring
        self.file_hashes = {}
        self.stats = {
            'requests_count': 0,
            'bytes_sent': 0,
            'start_time': datetime.now(),
            'active_connections': 0
        }
        
        # Создаем директорию модов если её нет
        os.makedirs(self.mods_directory, exist_ok=True)
        
        # Сканируем начальные файлы
        self.scan_mods_directory()
        
        # Настраиваем логирование
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        
        if self.enable_monitoring:
            self.setup_file_watcher()
    
    def scan_mods_directory(self):
        """Сканирование директории модов и вычисление хэшей"""
        for root, dirs, files in os.walk(self.mods_directory):
            for file in files:
                filepath = os.path.join(root, file)
                relpath = os.path.relpath(filepath, self.mods_directory)
                self.file_hashes[relpath] = self.calculate_file_hash(filepath)
    
    def calculate_file_hash(self, filepath: str) -> str:
        """Вычисление SHA256 хэша файла"""
        hash_sha256 = hashlib.sha256()
        try:
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            self.logger.error(f"Ошибка вычисления хэша для {filepath}: {e}")
            return ""
    
    def setup_file_watcher(self):
        """Настройка наблюдения за изменениями файлов"""
        class ModFileHandler(FileSystemEventHandler):
            def __init__(self, server_instance):
                self.server = server_instance
            
            def on_modified(self, event):
                if not event.is_directory and event.src_path.endswith('.jar'):
                    relpath = os.path.relpath(event.src_path, self.server.mods_directory)
                    self.server.file_hashes[relpath] = self.server.calculate_file_hash(event.src_path)
                    self.server.logger.info(f"Файл обновлен: {relpath}")
            
            def on_created(self, event):
                if not event.is_directory and event.src_path.endswith('.jar'):
                    relpath = os.path.relpath(event.src_path, self.server.mods_directory)
                    self.server.file_hashes[relpath] = self.server.calculate_file_hash(event.src_path)
                    self.server.logger.info(f"Новый файл: {relpath}")
            
            def on_deleted(self, event):
                if not event.is_directory:
                    relpath = os.path.relpath(event.src_path, self.server.mods_directory)
                    if relpath in self.server.file_hashes:
                        del self.server.file_hashes[relpath]
                        self.server.logger.info(f"Файл удален: {relpath}")
        
        self.observer = Observer()
        self.observer.schedule(ModFileHandler(self), self.mods_directory, recursive=True)
        self.observer.start()
    
    def generate_file_list(self) -> list:
        """Генерация списка файлов модов"""
        file_list = []
        for relpath, filehash in self.file_hashes.items():
            filepath = os.path.join(self.mods_directory, relpath)
            if os.path.exists(filepath):
                stat = os.stat(filepath)
                file_list.append({
                    'relpath': relpath.replace('\\', '/'),  # Всегда использовать Unix-пути
                    'size': stat.st_size,
                    'mtime': stat.st_mtime,
                    'hash': filehash,
                    'name': os.path.basename(relpath)
                })
        return sorted(file_list, key=lambda x: x['relpath'])
    
    def get_server_info(self) -> dict:
        """Получение информации о сервере"""
        uptime = datetime.now() - self.stats['start_time']
        return {
            'version': '1.0.0',
            'mods_count': len(self.file_hashes),
            'uptime_seconds': int(uptime.total_seconds()),
            'requests_served': self.stats['requests_count'],
            'bytes_sent_total': self.stats['bytes_sent'],
            'mods_directory': self.mods_directory,
            'server_time': datetime.now().isoformat(),
            'active_connections_avg': self.stats['active_connections']  # будет обновляться во время работы
        }
    
    def create_request_handler(self):
        """Создание обработчика HTTP-запросов"""
        server_instance = self
        
        class RequestHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                server_instance.logger.info(f"Request: {self.address_string()} - {format % args}")
            
            def send_json_response(self, data: dict, status_code: int = 200):
                """Отправка JSON-ответа"""
                self.send_response(status_code)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')  # CORS
                self.end_headers()
                
                json_data = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
                self.wfile.write(json_data)
                
                server_instance.stats['bytes_sent'] += len(json_data)
            
            def do_GET(self):
                server_instance.stats['requests_count'] += 1
                server_instance.stats['active_connections'] += 1
                
                try:
                    if self.path == '/files' or self.path == '/api/files':
                        # Список файлов
                        file_list = server_instance.generate_file_list()
                        self.send_json_response({
                            'status': 'success',
                            'files': file_list,
                            'total_count': len(file_list)
                        })
                    
                    elif self.path == '/server_info' or self.path == '/api/info':
                        # Информация о сервере
                        info = server_instance.get_server_info()
                        self.send_json_response({
                            'status': 'success',
                            'info': info
                        })
                    
                    elif self.path.startswith('/mods/') or self.path.startswith('/files/'):
                        # Отдача конкретного файла
                        # Извлекаем путь к файлу из URL
                        if self.path.startswith('/mods/'):
                            relpath = self.path[6:]  # '/mods/' -> ''
                        else:
                            relpath = self.path[7:]  # '/files/' -> ''
                        
                        # Декодируем URL-путь и нормализуем
                        import urllib.parse
                        relpath = urllib.parse.unquote(relpath)
                        relpath = os.path.normpath(relpath).replace('\\', '/')
                        
                        # Проверяем, что путь не пытается выйти за пределы директории
                        if '..' in relpath or relpath.startswith('/') or relpath.startswith('../'):
                            self.send_error(403, "Forbidden")
                            return
                        
                        filepath = os.path.join(server_instance.mods_directory, relpath)
                        
                        if os.path.exists(filepath) and os.path.isfile(filepath):
                            # Отправляем файл
                            self.send_response(200)
                            self.send_header('Content-type', 'application/octet-stream')
                            self.send_header('Content-Disposition', f'attachment; filename="{os.path.basename(filepath)}"')
                            self.send_header('Content-Length', str(os.path.getsize(filepath)))
                            self.send_header('Access-Control-Allow-Origin', '*')
                            self.end_headers()
                            
                            with open(filepath, 'rb') as f:
                                while True:
                                    chunk = f.read(8192)
                                    if not chunk:
                                        break
                                    self.wfile.write(chunk)
                                    server_instance.stats['bytes_sent'] += len(chunk)
                        else:
                            self.send_error(404, "File not found")
                    
                    elif self.path.startswith('/speed_test_') and self.path.endswith('.bin'):
                        # Тест скорости - генерация файлов разного размера
                        size_match = re.search(r'speed_test_(\d+)([km])b\.bin$', self.path, re.IGNORECASE)
                        if size_match:
                            size_val = int(size_match.group(1))
                            size_unit = size_match.group(2).lower()
                            
                            if size_unit == 'k':
                                size_bytes = size_val * 1024
                            elif size_unit == 'm':
                                size_bytes = size_val * 1024 * 1024
                            else:
                                self.send_error(400, "Invalid size unit")
                                return
                            
                            # Ограничиваем размер файла
                            size_bytes = min(size_bytes, 100 * 1024 * 1024)  # Максимум 100MB
                            
                            self.send_response(200)
                            self.send_header('Content-type', 'application/octet-stream')
                            self.send_header('Content-Length', str(size_bytes))
                            self.send_header('Cache-Control', 'no-cache')
                            self.end_headers()
                            
                            # Отправляем случайные данные для теста скорости
                            sent = 0
                            while sent < size_bytes:
                                chunk_size = min(8192, size_bytes - sent)
                                chunk = os.urandom(chunk_size)  # Генерируем случайные данные
                                self.wfile.write(chunk)
                                sent += chunk_size
                                server_instance.stats['bytes_sent'] += chunk_size
                        else:
                            self.send_error(400, "Invalid speed test file request")
                    
                    else:
                        # Корневой путь - информация о сервере
                        if self.path == '/' or self.path == '/api':
                            info = server_instance.get_server_info()
                            self.send_json_response({
                                'status': 'success',
                                'message': 'ModSync Server API v1.0',
                                'info': info
                            })
                        else:
                            self.send_error(404, "Not Found")
                
                finally:
                    server_instance.stats['active_connections'] -= 1
        
        return RequestHandler
    
    def start_server(self):
        """Запуск HTTP-сервера"""
        handler = self.create_request_handler()
        
        try:
            with socketserver.ThreadingTCPServer(("", self.port), handler) as httpd:
                self.logger.info(f"ModSync сервер запущен на порту {self.port}")
                self.logger.info(f"Директория модов: {self.mods_directory}")
                self.logger.info(f"Адрес сервера: http://localhost:{self.port}")
                
                httpd.serve_forever()
        except KeyboardInterrupt:
            self.logger.info("Получен сигнал остановки сервера...")
        finally:
            if self.enable_monitoring:
                self.observer.stop()
                self.observer.join()


def main():
    parser = argparse.ArgumentParser(description='Minecraft Mod Sync Server')
    parser.add_argument('--port', type=int, default=8000, help='Порт для сервера (по умолчанию: 8000)')
    parser.add_argument('--mods-dir', type=str, default='./mods', help='Директория с модами (по умолчанию: ./mods)')
    parser.add_argument('--no-monitoring', action='store_true', help='Отключить мониторинг изменений файлов')
    
    args = parser.parse_args()
    
    server = ModSyncServer(
        port=args.port,
        mods_directory=args.mods_dir,
        enable_monitoring=not args.no_monitoring
    )
    
    server.start_server()


if __name__ == "__main__":
    main()
