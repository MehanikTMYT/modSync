"""
Sequential download strategy implementation
"""

import time
from modsync.client.download.strategies.base_strategy import BaseDownloadStrategy
from modsync.client.download.core.downloader import Downloader


class SequentialStrategy(BaseDownloadStrategy):
    """Sequential download strategy - downloads files one by one with maximum reliability"""
    
    def execute_download(self, files_to_download, file_distribution=None):
        """Execute sequential download"""
        if not files_to_download:
            return {'success': True, 'results': {}}
        
        results = {}
        total_files = len(files_to_download)
        processed = 0
        settings = self.config['settings']
        chunk_size = settings.get('chunk_size', 32768)
        retry_count = settings.get('retry_count', 5)
        timeout = settings.get('timeout', 30)
        
        for file_info in files_to_download:
            processed += 1
            url = f"http://147.45.184.36:8000/{file_info['relpath']}"
            success = False
            
            for attempt in range(retry_count + 1):
                try:
                    success = Downloader._download_file_with_retry(
                        url, file_info['local_path'], file_info, chunk_size, timeout, settings
                    )
                    if success:
                        break
                except Exception as e:
                    if attempt < retry_count:
                        delay = settings.get('retry_delay', 1) * (attempt + 1)
                        self._log_info(f"⏳ Попытка {attempt + 1}/{retry_count} не удалась для {file_info['relpath']}, повтор через {delay:.1f}с: {str(e)}")
                        time.sleep(delay)
                        continue
                    else:
                        self._log_error(f"❌ Все попытки загрузки {file_info['relpath']} неудачны: {str(e)}")
            
            results[file_info['relpath']] = success
            
            if self.progress_callback:
                self.progress_callback(None, processed / total_files * 100, processed, total_files)
        
        return {'success': True, 'results': results}