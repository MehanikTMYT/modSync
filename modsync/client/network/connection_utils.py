import requests
import time
import json
from urllib3.exceptions import InsecureRequestWarning
import urllib3

urllib3.disable_warnings(InsecureRequestWarning)

# Global server IP - can be overridden
VDS_SERVER_IP = "http://147.45.184.36:8000"  # Default server IP


class ConnectionManager:
    """
    Менеджер соединения с сервером, включая тестирование скорости и автопереподключение
    """
    
    @staticmethod
    def is_server_available(timeout=5):
        """
        Проверка доступности сервера
        """
        try:
            response = requests.get(f"{VDS_SERVER_IP}/ping", timeout=timeout)
            return response.status_code == 200
        except:
            return False
    
    @staticmethod
    def make_request_with_retry(url, timeout=30, max_retries=3, **kwargs):
        """
        Выполнение HTTP-запроса с повторными попытками
        """
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                response = requests.get(url, timeout=timeout, **kwargs)
                return response
            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    raise last_exception
        
        raise last_exception
    
    @staticmethod
    def test_connection_with_retry():
        """
        Тестирование скорости соединения с автопереподключением
        """
        try:
            # Test download speed with a sample file
            test_url = f"{VDS_SERVER_IP}/speedtest"
            start_time = time.time()
            
            try:
                response = ConnectionManager.make_request_with_retry(test_url, timeout=30)
                download_time = time.time() - start_time
                content_length = len(response.content)
                
                if content_length > 0 and download_time > 0:
                    speed_mbps = (content_length * 8) / (download_time * 1024 * 1024)  # Convert to Mbps
                else:
                    # Fallback to ping test if download test fails
                    start_time = time.time()
                    ConnectionManager.make_request_with_retry(f"{VDS_SERVER_IP}/ping", timeout=10)
                    ping_time = (time.time() - start_time) * 1000  # Convert to ms
                    
                    # Estimate connection quality based on ping
                    if ping_time < 50:
                        speed_mbps = 50.0  # Very fast connection
                    elif ping_time < 100:
                        speed_mbps = 20.0  # Fast connection
                    elif ping_time < 200:
                        speed_mbps = 5.0   # Medium connection
                    elif ping_time < 500:
                        speed_mbps = 1.0   # Slow connection
                    else:
                        speed_mbps = 0.5   # Very slow connection
            
            except Exception:
                # If speed test fails, use ping-based estimation
                start_time = time.time()
                ConnectionManager.make_request_with_retry(f"{VDS_SERVER_IP}/ping", timeout=10)
                ping_time = (time.time() - start_time) * 1000
                
                if ping_time < 50:
                    speed_mbps = 20.0
                elif ping_time < 100:
                    speed_mbps = 10.0
                elif ping_time < 200:
                    speed_mbps = 5.0
                elif ping_time < 500:
                    speed_mbps = 1.0
                else:
                    speed_mbps = 0.5
            
            # Determine connection quality based on speed
            if speed_mbps >= 20:
                quality = 'very_fast'
            elif speed_mbps >= 5:
                quality = 'fast'
            elif speed_mbps >= 1:
                quality = 'medium'
            elif speed_mbps >= 0.5:
                quality = 'slow'
            else:
                quality = 'very_slow'
            
            return {
                'average_speed_mbps': round(speed_mbps, 2),
                'connection_quality': quality,
                'timestamp': time.time(),
                'ping_time_ms': round(ping_time, 2) if 'ping_time' in locals() else None
            }
            
        except Exception as e:
            return {
                'error': str(e),
                'timestamp': time.time()
            }