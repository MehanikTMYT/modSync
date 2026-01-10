import socket
import time
import urllib3.util
import requests
from requests.exceptions import RequestException, ConnectionError, Timeout

# Константа сервера
VDS_SERVER_IP = "http://147.45.184.36:8000"  # ЗАМЕНИТЕ НА ВАШ РЕАЛЬНЫЙ IP И ПОРТ


class ConnectionManager:
    """Менеджер сетевых подключений с автоматическим переподключением"""
    MAX_RETRIES = 5
    BASE_DELAY = 1.0  # секунды
    MAX_DELAY = 30.0  # секунды
    
    @staticmethod
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
    
    @staticmethod
    def make_request_with_retry(url, method='get', **kwargs):
        """Выполнение запроса с автоматическим переподключением"""
        retries = 0
        last_error = None
        
        while retries < ConnectionManager.MAX_RETRIES:
            try:
                if method.lower() == 'get':
                    response = requests.get(url, **kwargs)
                elif method.lower() == 'head':
                    response = requests.head(url, **kwargs)
                else:
                    raise ValueError(f"Unsupported method: {method}")
                
                response.raise_for_status()
                return response
            except (ConnectionError, Timeout, RequestException) as e:
                last_error = e
                retries += 1
                if retries >= ConnectionManager.MAX_RETRIES:
                    raise
                
                # Экспоненциальная задержка с jitter
                delay = min(ConnectionManager.BASE_DELAY * (2 ** (retries - 1)), ConnectionManager.MAX_DELAY)
                jitter = delay * 0.1 * (1 if retries % 2 == 0 else -1)  # ±10% jitter
                actual_delay = max(0.5, delay + jitter)  # Минимальная задержка 0.5с
                time.sleep(actual_delay)
        
        raise last_error
    
    @staticmethod
    def test_connection_with_retry():
        """Тестирование соединения с автоматическим переподключением"""
        max_attempts = 3
        attempt = 0
        
        while attempt < max_attempts:
            try:
                # Сначала проверяем доступность сервера
                if not ConnectionManager.is_server_available(timeout=3):
                    raise ConnectionError("Сервер недоступен")
                
                # Затем выполняем полноценный тест скорости
                from modsync.client.network.speed_test_manager import SpeedTestManager
                results = SpeedTestManager.test_connection_speed()
                if 'error' in results:
                    raise Exception(results['error'])
                
                return results
                
            except Exception as e:
                attempt += 1
                if attempt >= max_attempts:
                    return {'error': f'Не удалось подключиться к серверу после {max_attempts} попыток: {str(e)}'}
                time.sleep(2 ** attempt)  # Экспоненциальная задержка
        
        return {'error': 'Не удалось установить соединение с сервером'}
