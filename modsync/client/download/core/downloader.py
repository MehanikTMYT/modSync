"""
Core downloader functionality for ModSync client
"""

import os
import time
import threading
from queue import Queue, Empty
from modsync.client.network.connection.connection_utils import VDS_SERVER_IP
from modsync.client.network.connection.retry_utils import ConnectionManager


class Downloader:
    """Core download functionality"""
    
    @staticmethod
    def _download_file_with_retry(url, local_path, file_info, chunk_size=32768, timeout=30, strategy_settings=None):
        """Загрузка файла с повторными попытками при ошибках соединения"""
        if strategy_settings is None:
            strategy_settings = {}
        
        dir_path = os.path.dirname(local_path)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
        
        max_retries = strategy_settings.get('retry_count', 5)
        base_delay = strategy_settings.get('retry_delay', 1)
        
        for attempt in range(max_retries + 1):
            try:
                # Проверяем соединение перед загрузкой
                if attempt > 0 and not ConnectionManager.is_server_available(timeout=2):
                    raise ConnectionError("Сервер недоступен")
                
                response = ConnectionManager.make_request_with_retry(
                    url, timeout=timeout, stream=True
                )
                response.raise_for_status()
                
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                
                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                
                # Проверка целостности
                if total_size > 0 and os.path.getsize(local_path) != total_size:
                    os.remove(local_path)
                    raise Exception(f"Несоответствие размера: ожидаемый {total_size}, получен {os.path.getsize(local_path)}")
                
                return True
                
            except Exception as e:
                if attempt < max_retries:
                    delay = base_delay * (attempt + 1)
                    print(f"[STRATEGY] ⏳ Попытка {attempt + 1}/{max_retries} для {file_info['relpath']} не удалась, повтор через {delay:.1f}с: {str(e)}")
                    time.sleep(delay)
                    continue
                else:
                    if os.path.exists(local_path):
                        os.remove(local_path)
                    raise
        
        return False
    
    @staticmethod
    def _download_with_resume(url, local_path, file_info, chunk_size=131072, retry_count=3, timeout=60, strategy_settings=None):
        """Загрузка с поддержкой возобновления для больших файлов"""
        if strategy_settings is None:
            strategy_settings = {}
        
        file_size = file_info.get('size', 0)
        mode = 'wb'
        downloaded_size = 0
        headers = {}

        # Проверка существующего файла для возобновления
        if os.path.exists(local_path):
            downloaded_size = os.path.getsize(local_path)
            if 0 < downloaded_size < file_size:
                mode = 'ab'
                headers = {'Range': f'bytes={downloaded_size}-'}
            else:
                downloaded_size = 0
                mode = 'wb'
                headers = {}

        for attempt in range(retry_count + 1):
            try:
                # Проверяем соединение
                if attempt > 0 and not ConnectionManager.is_server_available(timeout=3):
                    raise ConnectionError("Сервер недоступен")
                
                response = ConnectionManager.make_request_with_retry(
                    url, timeout=timeout, stream=True, headers=headers
                )

                # Обработка частичного контента
                if mode == 'ab' and response.status_code == 206:
                    print(f"[STRATEGY] 🔄 Возобновление загрузки {file_info['relpath']} с {downloaded_size/1024/1024:.1f}MB")
                elif mode == 'ab':
                    print(f"[STRATEGY] ⚠️ Сервер не поддерживает возобновление, начинаем заново: {file_info['relpath']}")
                    mode = 'wb'
                    downloaded_size = 0
                    headers = {}
                    response = ConnectionManager.make_request_with_retry(
                        url, timeout=timeout, stream=True
                    )

                total_size = file_size
                start_time = time.time()

                with open(local_path, mode) as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)

                # Проверка целостности
                final_size = os.path.getsize(local_path)
                if final_size == file_size:
                    elapsed = time.time() - start_time
                    avg_speed = file_size / elapsed / 1024 / 1024 if elapsed > 0 else 0
                    print(f"[STRATEGY] ✅ {file_info['relpath']} успешно загружен! ({elapsed:.1f}с, {avg_speed:.1f} MB/s)")
                    return True
                else:
                    print(f"[ERROR] ❌ Несоответствие размера файла {file_info['relpath']}: ожидаемый {file_size}, получен {final_size}")
                    if os.path.exists(local_path):
                        os.remove(local_path)
                    return False

            except Exception as e:
                print(f"[ERROR] ❌ Попытка {attempt + 1}/{retry_count + 1} не удалась для {file_info['relpath']}: {str(e)}")
                if attempt < retry_count:
                    time.sleep(2 ** attempt)  # Экспоненциальная задержка
                else:
                    if os.path.exists(local_path):
                        os.remove(local_path)
                    return False

        return False
    
    @staticmethod
    def _download_parallel(files, max_workers=4, chunk_size=32768, timeout=30, strategy_settings=None):
        """Параллельная загрузка файлов с автопереподключением"""
        if strategy_settings is None:
            strategy_settings = {}
        
        results = {}
        queue = Queue()

        for file_info in files:
            queue.put(file_info)

        def worker():
            while not queue.empty():
                try:
                    file_info = queue.get_nowait()
                    url = f"{VDS_SERVER_IP}/{file_info['relpath']}"
                    success = Downloader._download_file_with_retry(
                        url, file_info['local_path'], file_info, chunk_size, timeout, strategy_settings
                    )
                    results[file_info['relpath']] = success

                    queue.task_done()
                except Empty:
                    break
                except Exception as e:
                    print(f"[ERROR] Ошибка в потоке загрузки: {str(e)}")
                    queue.task_done()

        # Запуск потоков
        threads = []
        actual_workers = min(max_workers, len(files), 20)  # Максимум 20 потоков

        for _ in range(actual_workers):
            t = threading.Thread(target=worker, daemon=True)
            t.start()
            threads.append(t)

        # Ожидание завершения
        for t in threads:
            t.join()

        queue.join()

        return results