"""
Speed test manager for ModSync client
"""

import time
import datetime
from modsync.client.network.connection.connection_utils import VDS_SERVER_IP
from modsync.client.network.connection.retry_utils import ConnectionManager


class SpeedTestManager:
    """Менеджер тестирования скорости соединения"""
    
    TEST_FILES = {
        '10kb': {'size': 10 * 1024, 'url': '/speed_test_10kb.bin'},
        '100kb': {'size': 100 * 1024, 'url': '/speed_test_100kb.bin'},
        '1mb': {'size': 1 * 1024 * 1024, 'url': '/speed_test_1mb.bin'},
        '10mb': {'size': 10 * 1024 * 1024, 'url': '/speed_test_10mb.bin'}
    }
    
    @staticmethod
    def test_connection_speed():
        """Тестирование скорости соединения с сервером"""
        results = {}
        timeout = 30  # Увеличенный таймаут для надежности
        
        try:
            # Проверка доступности сервера
            server_info_url = f"{VDS_SERVER_IP}/server_info"
            response = ConnectionManager.make_request_with_retry(server_info_url, timeout=10)
            if response.status_code != 200:
                return {'error': f'Сервер недоступен. Код ответа: {response.status_code}'}
            
            server_info = response.json()
            results['server_info'] = server_info
            
            # Тестирование скорости для разных размеров файлов
            successful_tests = []
            
            for size_name, test_info in SpeedTestManager.TEST_FILES.items():
                try:
                    start_time = time.time()
                    url = f"{VDS_SERVER_IP}{test_info['url']}"
                    
                    # Используем stream=True для больших файлов
                    stream_mode = size_name in ['1mb', '10mb']
                    response = ConnectionManager.make_request_with_retry(
                        url, timeout=timeout, stream=stream_mode
                    )
                    
                    # Измеряем время для больших файлов при потоковой загрузке
                    if stream_mode:
                        total_bytes = 0
                        for chunk in response.iter_content(chunk_size=8192):
                            total_bytes += len(chunk)
                        end_time = time.time()
                        actual_size = total_bytes
                    else:
                        end_time = time.time()
                        actual_size = len(response.content)
                    
                    elapsed_time = end_time - start_time
                    speed_bps = actual_size / elapsed_time if elapsed_time > 0 else 0
                    speed_mbps = speed_bps * 8 / 1_000_000
                    
                    results[size_name] = {
                        'expected_size': test_info['size'],
                        'actual_size': actual_size,
                        'time_seconds': elapsed_time,
                        'speed_bps': speed_bps,
                        'speed_mbps': speed_mbps,
                        'success': True
                    }
                    successful_tests.append(results[size_name])
                    
                    # Небольшая задержка между тестами
                    if size_name != '10kb':
                        time.sleep(0.5)
                        
                except Exception as e:
                    results[size_name] = {
                        'error': str(e),
                        'success': False
                    }
            
            # Расчет общей статистики только по успешным тестам
            if successful_tests:
                avg_speed_mbps = sum(r['speed_mbps'] for r in successful_tests) / len(successful_tests)
                results['average_speed_mbps'] = avg_speed_mbps
                results['connection_quality'] = SpeedTestManager._determine_connection_quality(avg_speed_mbps)
                results['successful_tests_count'] = len(successful_tests)
            else:
                results['error'] = "Ни один тест скорости не завершился успешно"
            
            results['timestamp'] = datetime.datetime.now().isoformat()
            return results
            
        except Exception as e:
            return {'error': f'Ошибка при тестировании скорости: {str(e)}'}
    
    @staticmethod
    def _determine_connection_quality(avg_speed_mbps):
        """Определение качества соединения на основе средней скорости"""
        if avg_speed_mbps < 0.5:
            return 'very_slow'
        elif avg_speed_mbps < 2:
            return 'slow'
        elif avg_speed_mbps < 10:
            return 'medium'
        elif avg_speed_mbps < 50:
            return 'fast'
        else:
            return 'very_fast'