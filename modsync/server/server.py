#!/usr/bin/env python3
"""
Minecraft Mod Sync Server
Автоматический сервер для синхронизации модов с поддержкой тестов скорости и мониторинга.
"""

import socketserver
import argparse
import os

from modsync.server.models import ServerStats
from modsync.server.services import FileService, ServerInfoService
from modsync.server.utils import setup_logger


class ModSyncServer:
    """HTTP-сервер для синхронизации модов Minecraft"""
    
    def __init__(self, port=8000, mods_directory="./mods", enable_monitoring=True):
        self.port = port
        self.mods_directory = os.path.abspath(mods_directory)
        self.enable_monitoring = enable_monitoring
        
        # Initialize services
        self.stats = ServerStats()
        self.file_service = FileService(self.mods_directory)
        self.server_info_service = ServerInfoService(self.mods_directory)
        
        # Setup logger
        self.logger = setup_logger(__name__)
        
        if self.enable_monitoring:
            self.file_service.setup_file_watcher(self)
    
    def start_server(self):
        """Запуск HTTP-сервера"""
        # Import the request handler here to avoid circular imports
        from modsync.server.handlers import RequestHandler
        
        # Create a partial function to pass the server instance to the handler
        def create_handler_with_instance(*args, **kwargs):
            return RequestHandler(self, *args, **kwargs)
        
        try:
            with socketserver.ThreadingTCPServer(("", self.port), create_handler_with_instance) as httpd:
                self.logger.info(f"ModSync сервер запущен на порту {self.port}")
                self.logger.info(f"Директория модов: {self.mods_directory}")
                self.logger.info(f"Адрес сервера: http://localhost:{self.port}")
                
                httpd.serve_forever()
        except KeyboardInterrupt:
            self.logger.info("Получен сигнал остановки сервера...")
        finally:
            if self.enable_monitoring:
                self.file_service.observer.stop()
                self.file_service.observer.join()


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
