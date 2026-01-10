"""
Adaptive download strategy implementation
"""

import time
from modsync.client.download.strategies.base_strategy import BaseDownloadStrategy
from modsync.client.download.core.downloader import Downloader


class AdaptiveStrategy(BaseDownloadStrategy):
    """Adaptive download strategy - classifies files by size and applies different techniques"""
    
    def execute_download(self, files_to_download, file_distribution=None):
        """Execute adaptive download"""
        settings = self.config['settings']
        
        # Classify files by size
        tiny_files = [f for f in files_to_download if f.get('size', 0) < 100 * 1024]  # <100KB
        small_files = [f for f in files_to_download if 100 * 1024 <= f.get('size', 0) < 1 * 1024 * 1024]  # 100KB-1MB
        medium_files = [f for f in files_to_download if 1 * 1024 * 1024 <= f.get('size', 0) < 10 * 1024 * 1024]  # 1-10MB
        huge_files = [f for f in files_to_download if f.get('size', 0) >= 10 * 1024 * 1024]  # >10MB
        
        results = {}
        total_files = len(files_to_download)
        processed = 0
        
        # Download tiny files (maximum parallelism)
        if tiny_files:
            self._log_info(f"⚡ Загрузка {len(tiny_files)} мелких файлов (<100KB) с {settings.get('tiny_file_workers', 8)} потоками")
            tiny_results = Downloader._download_parallel(
                tiny_files,
                max_workers=settings.get('tiny_file_workers', 8),
                chunk_size=settings.get('chunk_size', 32768),
                timeout=settings.get('timeout', 30),
                strategy_settings=settings
            )
            results.update(tiny_results)
            processed += len(tiny_files)
            
            if self.progress_callback:
                self.progress_callback(None, processed / total_files * 100, processed, total_files)
        
        # Download small files
        if small_files:
            self._log_info(f"🚀 Загрузка {len(small_files)} файлов (100KB-1MB) с {settings.get('small_file_workers', 4)} потоками")
            small_results = Downloader._download_parallel(
                small_files,
                max_workers=settings.get('small_file_workers', 4),
                chunk_size=settings.get('chunk_size', 32768),
                timeout=settings.get('timeout', 30),
                strategy_settings=settings
            )
            results.update(small_results)
            processed += len(small_files)
            
            if self.progress_callback:
                self.progress_callback(None, processed / total_files * 100, processed, total_files)
        
        # Download medium files
        if medium_files:
            self._log_info(f"🟡 Загрузка {len(medium_files)} файлов (1-10MB) с {settings.get('medium_file_workers', 2)} потоками")
            medium_results = Downloader._download_parallel(
                medium_files,
                max_workers=settings.get('medium_file_workers', 2),
                chunk_size=settings.get('chunk_size', 65536),
                timeout=settings.get('timeout', 45),
                strategy_settings=settings
            )
            results.update(medium_results)
            processed += len(medium_files)
            
            if self.progress_callback:
                self.progress_callback(None, processed / total_files * 100, processed, total_files)
        
        # Download huge files (sequentially with resume support)
        if huge_files:
            self._log_info(f"🔴 Загрузка {len(huge_files)} ГИГАНТСКИХ файлов (>10MB) с возобновлением")
            for file_info in huge_files:
                processed += 1
                
                if self.progress_callback:
                    self.progress_callback(None, processed / total_files * 100, processed, total_files)
                
                url = f"http://147.45.184.36:8000/{file_info['relpath']}"
                success = Downloader._download_with_resume(
                    url,
                    file_info['local_path'],
                    file_info,
                    chunk_size=settings.get('chunk_size', 131072),
                    retry_count=settings.get('retry_count', 5),
                    timeout=settings.get('timeout', 60),
                    strategy_settings=settings
                )
                results[file_info['relpath']] = success
        
        return {'success': True, 'results': results}