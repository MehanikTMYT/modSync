"""
Connection utilities for ModSync client
"""

import socket
import urllib3.util


# Константа сервера
VDS_SERVER_IP = "http://147.45.184.36:8000"  # ЗАМЕНИТЕ НА ВАШ РЕАЛЬНЫЙ IP И ПОРТ


def is_server_available(timeout=2):
    """Проверка доступности сервера"""
    try:
        # Проверяем доступность через сокет для быстрой проверки
        parsed_url = urllib3.util.parse_url(VDS_SERVER_IP)
        host = parsed_url.host
        port = parsed_url.port or 80
        
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        return False