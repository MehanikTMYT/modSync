"""
Retry utilities for ModSync client
"""

import time
import requests
from requests.exceptions import RequestException, ConnectionError, Timeout


class ConnectionManager:
    """Менеджер сетевых подключений с автоматическим переподключением"""
    MAX_RETRIES = 5
    BASE_DELAY = 1.0  # секунды
    MAX_DELAY = 30.0  # секунды
    
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