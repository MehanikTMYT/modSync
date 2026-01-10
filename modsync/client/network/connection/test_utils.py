"""
Connection test utilities for ModSync client
"""

import time
from requests.exceptions import ConnectionError


def test_connection_with_retry():
    """Тестирование соединения с автоматическим переподключением"""
    max_attempts = 3
    attempt = 0
    
    while attempt < max_attempts:
        try:
            # Сначала проверяем доступность сервера
            from modsync.client.network.connection.connection_utils import is_server_available
            if not is_server_available(timeout=3):
                raise ConnectionError("Сервер недоступен")
            
            # Затем выполняем полноценный тест скорости
            from modsync.client.network.speed_test.speed_tester import SpeedTestManager
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