import os
import time
import threading
from queue import Queue, Empty

from modsync.client.network.connection_utils import VDS_SERVER_IP
from modsync.client.network.connection_utils import ConnectionManager
from modsync.client.download.simple_strategy import DownloadStrategy


class DownloadManager:
    """Менеджер загрузки файлов с адаптивными стратегиями и автопереподключением"""
    
    def __init__(self, strategy=None):
        self.strategy = strategy or DownloadStrategy.get_manual_strategies()['balanced_adaptive']
        self.progress_callback = None
        self.error_callback = None
        self.speed_stats = {}
        self.cancel_requested = False
    
    def set_progress_callback(self, callback):
        """Установка callback для прогресса"""
        self.progress_callback = callback
    
    def set_error_callback(self, callback):
        """Установка callback для ошибок"""
        self.error_callback = callback
    
    def cancel_download(self):
        """Отмена текущей загрузки"""
        self.cancel_requested = True
    
    def download_files(self, files_to_download, file_distribution=None):
        """Основной метод загрузки файлов с выбранной стратегией"""
        if not files_to_download:
            return {'success': True, 'results': {}}
        
        self.cancel_requested = False
        strategy_name = self.strategy['name']
        
        if strategy_name == 'adaptive_auto' and file_distribution:
            # Автоматическое определение стратегии на основе распределения файлов
            optimal_strategy = DownloadStrategy.get_optimal_strategy(
                self.speed_stats.get('connection_quality', 'medium'),
                file_distribution
            )
            self.strategy = optimal_strategy
        
        # Выбор метода загрузки на основе стратегии
        if strategy_name in ['stable_sequential', 'cautious_parallel']:
            return self._download_sequential(files_to_download)
        elif strategy_name in ['balanced_adaptive', 'medium_optimized', 'fast_balanced', 'max_performance']:
            return self._download_adaptive(files_to_download)
        elif strategy_name == 'tiny_files_optimized':
            return self._download_tiny_files_optimized(files_to_download)
        elif strategy_name == 'gaming_priority':
            return self._download_gaming_priority(files_to_download)
        else:
            # Стратегия по умолчанию
            return self._download_adaptive(files_to_download)
    
    def _download_sequential(self, files_to_download):
        """Последовательная загрузка файлов с автопереподключением"""
        results = {}
        total_files = len(files_to_download)
        processed = 0
        settings = self.strategy['settings']
        chunk_size = settings.get('chunk_size', 32768)
        retry_count = settings.get('retry_count', 5)
        timeout = settings.get('timeout', 30)
        
        for file_info in files_to_download:
            if self.cancel_requested:
                break
            
            processed += 1
            url = f"{VDS_SERVER_IP}/{file_info['relpath']}"
            success = False
            
            for attempt in range(retry_count + 1):
                if self.cancel_requested:
                    break
                
                try:
                    success = self._download_file_with_retry(url, file_info['local_path'], file_info, chunk_size, timeout)
                    if success:
                        break
                except Exception as e:
                    if attempt < retry_count and not self.cancel_requested:
                        delay = settings.get('retry_delay', 1) * (attempt + 1)
                        self._log_strategy_info(f"⏳ Попытка {attempt + 1}/{retry_count} не удалась для {file_info['relpath']}, повтор через {delay:.1f}с: {str(e)}")
                        time.sleep(delay)
                        continue
                    else:
                        self._log_error(f"❌ Все попытки загрузки {file_info['relpath']} неудачны: {str(e)}")
            
            results[file_info['relpath']] = success
            
            if self.progress_callback and not self.cancel_requested:
                self.progress_callback(None, processed / total_files * 100, processed, total_files)
        
        return {'success': not self.cancel_requested, 'results': results, 'cancelled': self.cancel_requested}
    
    def _download_adaptive(self, files_to_download):
        """Адаптивная загрузка с классификацией по размерам и автопереподключением"""
        if self.cancel_requested:
            return {'success': False, 'results': {}, 'cancelled': True}
        
        settings = self.strategy['settings']
        
        # Классификация файлов
        tiny_files = [f for f in files_to_download if f.get('size', 0) < 100 * 1024]  # <100KB
        small_files = [f for f in files_to_download if 100 * 1024 <= f.get('size', 0) < 1 * 1024 * 1024]  # 100KB-1MB
        medium_files = [f for f in files_to_download if 1 * 1024 * 1024 <= f.get('size', 0) < 10 * 1024 * 1024]  # 1-10MB
        huge_files = [f for f in files_to_download if f.get('size', 0) >= 10 * 1024 * 1024]  # >10MB
        
        results = {}
        total_files = len(files_to_download)
        processed = 0
        
        # Загрузка мелких файлов (максимальная параллельность)
        if tiny_files and not self.cancel_requested:
            self._log_strategy_info(f"⚡ Загрузка {len(tiny_files)} мелких файлов (<100KB) с {settings.get('tiny_file_workers', 8)} потоками")
            tiny_results = self._download_parallel(
                tiny_files,
                max_workers=settings.get('tiny_file_workers', 8),
                chunk_size=settings.get('chunk_size', 32768),
                timeout=settings.get('timeout', 30)
            )
            results.update(tiny_results)
            processed += len(tiny_files)
            
            if self.progress_callback and not self.cancel_requested:
                self.progress_callback(None, processed / total_files * 100, processed, total_files)
        
        # Загрузка средних файлов
        if small_files and not self.cancel_requested:
            self._log_strategy_info(f"🚀 Загрузка {len(small_files)} файлов (100KB-1MB) с {settings.get('small_file_workers', 4)} потоками")
            small_results = self._download_parallel(
                small_files,
                max_workers=settings.get('small_file_workers', 4),
                chunk_size=settings.get('chunk_size', 32768),
                timeout=settings.get('timeout', 30)
            )
            results.update(small_results)
            processed += len(small_files)
            
            if self.progress_callback and not self.cancel_requested:
                self.progress_callback(None, processed / total_files * 100, processed, total_files)
        
        # Загрузка крупных файлов
        if medium_files and not self.cancel_requested:
            self._log_strategy_info(f"🟡 Загрузка {len(medium_files)} файлов (1-10MB) с {settings.get('medium_file_workers', 2)} потоками")
            medium_results = self._download_parallel(
                medium_files,
                max_workers=settings.get('medium_file_workers', 2),
                chunk_size=settings.get('chunk_size', 65536),
                timeout=settings.get('timeout', 45)
            )
            results.update(medium_results)
            processed += len(medium_files)
            
            if self.progress_callback and not self.cancel_requested:
                self.progress_callback(None, processed / total_files * 100, processed, total_files)
        
        # Загрузка гигантских файлов (последовательно с возобновлением)
        if huge_files and not self.cancel_requested:
            self._log_strategy_info(f"🔴 Загрузка {len(huge_files)} ГИГАНТСКИХ файлов (>10MB) с возобновлением")
            for file_info in huge_files:
                if self.cancel_requested:
                    break
                
                processed += 1
                
                if self.progress_callback and not self.cancel_requested:
                    self.progress_callback(None, processed / total_files * 100, processed, total_files)
                
                url = f"{VDS_SERVER_IP}/{file_info['relpath']}"
                success = self._download_with_resume(
                    url,
                    file_info['local_path'],
                    file_info,
                    chunk_size=settings.get('chunk_size', 131072),
                    retry_count=settings.get('retry_count', 5),
                    timeout=settings.get('timeout', 60)
                )
                results[file_info['relpath']] = success
        
        return {'success': not self.cancel_requested, 'results': results, 'cancelled': self.cancel_requested}
    
    def _download_file_with_retry(self, url, local_path, file_info, chunk_size=32768, timeout=30):
        """Загрузка файла с повторными попытками при ошибках соединения"""
        dir_path = os.path.dirname(local_path)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
        
        max_retries = self.strategy['settings'].get('retry_count', 5)
        base_delay = self.strategy['settings'].get('retry_delay', 1)
        
        for attempt in range(max_retries + 1):
            if self.cancel_requested:
                return False
            
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
                        if self.cancel_requested:
                            f.close()
                            if os.path.exists(local_path):
                                os.remove(local_path)
                            return False
                        
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            if self.progress_callback and file_info:
                                progress = (downloaded / total_size * 100) if total_size > 0 else 0
                                self.progress_callback(file_info, progress, downloaded, total_size)
                
                # Проверка целостности
                if total_size > 0 and os.path.getsize(local_path) != total_size:
                    os.remove(local_path)
                    raise Exception(f"Несоответствие размера: ожидаемый {total_size}, получен {os.path.getsize(local_path)}")
                
                return True
                
            except Exception as e:
                if attempt < max_retries and not self.cancel_requested:
                    delay = base_delay * (attempt + 1)
                    self._log_strategy_info(f"⏳ Попытка {attempt + 1}/{max_retries} для {file_info['relpath']} не удалась, повтор через {delay:.1f}с: {str(e)}")
                    time.sleep(delay)
                    continue
                else:
                    if os.path.exists(local_path):
                        os.remove(local_path)
                    raise
        
        return False
    
    def _download_with_resume(self, url, local_path, file_info, chunk_size=131072, retry_count=3, timeout=60):
        """Загрузка с поддержкой возобновления для больших файлов"""
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
            if self.cancel_requested:
                if os.path.exists(local_path):
                    os.remove(local_path)
                return False
            
            try:
                # Проверяем соединение
                if attempt > 0 and not ConnectionManager.is_server_available(timeout=3):
                    raise ConnectionError("Сервер недоступен")
                
                response = ConnectionManager.make_request_with_retry(
                    url, timeout=timeout, stream=True, headers=headers
                )
                
                # Обработка частичного контента
                if mode == 'ab' and response.status_code == 206:
                    self._log_strategy_info(f"🔄 Возобновление загрузки {file_info['relpath']} с {downloaded_size/1024/1024:.1f}MB")
                elif mode == 'ab':
                    self._log_strategy_info(f"⚠️ Сервер не поддерживает возобновление, начинаем заново: {file_info['relpath']}")
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
                        if self.cancel_requested:
                            f.close()
                            if os.path.exists(local_path):
                                os.remove(local_path)
                            return False
                        
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            
                            # Обновление прогресса для больших файлов
                            if file_size > 10 * 1024 * 1024 and self.progress_callback:
                                progress = downloaded_size / total_size * 100
                                elapsed = time.time() - start_time
                                speed = downloaded_size / elapsed / 1024 / 1024 if elapsed > 0 else 0
                                self.progress_callback(
                                    file_info,
                                    progress,
                                    downloaded_size,
                                    total_size,
                                    extra_info=f"{speed:.1f} MB/s"
                                )
                
                # Проверка целостности
                final_size = os.path.getsize(local_path)
                if final_size == file_size:
                    elapsed = time.time() - start_time
                    avg_speed = file_size / elapsed / 1024 / 1024 if elapsed > 0 else 0
                    self._log_strategy_info(f"✅ {file_info['relpath']} успешно загружен! ({elapsed:.1f}с, {avg_speed:.1f} MB/s)")
                    return True
                else:
                    self._log_error(f"❌ Несоответствие размера файла {file_info['relpath']}: ожидаемый {file_size}, получен {final_size}")
                    if os.path.exists(local_path):
                        os.remove(local_path)
                    return False
            
            except Exception as e:
                self._log_error(f"❌ Попытка {attempt + 1}/{retry_count + 1} не удалась для {file_info['relpath']}: {str(e)}")
                if attempt < retry_count and not self.cancel_requested:
                    time.sleep(2 ** attempt)  # Экспоненциальная задержка
                else:
                    if os.path.exists(local_path):
                        os.remove(local_path)
                    return False
        
        return False
    
    def _download_parallel(self, files, max_workers=4, chunk_size=32768, timeout=30):
        """Параллельная загрузка файлов с автопереподключением"""
        results = {}
        queue = Queue()
        
        for file_info in files:
            queue.put(file_info)
        
        def worker():
            while not queue.empty() and not self.cancel_requested:
                try:
                    file_info = queue.get_nowait()
                    if self.cancel_requested:
                        queue.task_done()
                        break
                    
                    url = f"{VDS_SERVER_IP}/{file_info['relpath']}"
                    success = self._download_file_with_retry(url, file_info['local_path'], file_info, chunk_size, timeout)
                    results[file_info['relpath']] = success
                    
                    queue.task_done()
                except Empty:
                    break
                except Exception as e:
                    if self.error_callback:
                        self.error_callback(f"Ошибка в потоке загрузки: {str(e)}")
                    queue.task_done()
        
        # Запуск потоков
        threads = []
        actual_workers = min(max_workers, len(files), 20)  # Максимум 20 потоков
        
        for _ in range(actual_workers):
            if self.cancel_requested:
                break
            t = threading.Thread(target=worker, daemon=True)
            t.start()
            threads.append(t)
        
        # Ожидание завершения или отмены
        while any(t.is_alive() for t in threads) and not self.cancel_requested:
            time.sleep(0.1)
        
        # Если отмена запрошена, очищаем очередь
        if self.cancel_requested:
            while not queue.empty():
                try:
                    queue.get_nowait()
                    queue.task_done()
                except Empty:
                    break
        
        queue.join()
        
        return results
    
    def _log_strategy_info(self, message):
        """Логирование информации о стратегии"""
        if self.error_callback:
            self.error_callback(message)
        else:
            print(f"[STRATEGY] {message}")
    
    def _log_error(self, message):
        """Логирование ошибок"""
        if self.error_callback:
            self.error_callback(message)
        else:
            print(f"[ERROR] {message}")