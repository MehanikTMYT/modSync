"""
Unified strategy executor for ModSync client
Replaces the complex strategy system with a simplified facade
"""

from modsync.client.download.core.downloader import Downloader


def execute_strategy(strategy, files_to_download, progress_callback=None, 
                    error_callback=None, cancel_requested=False):
    """
    Execute download using the specified strategy
    """
    if cancel_requested:
        return {'success': False, 'results': {}, 'cancelled': True}
    
    strategy_name = strategy['name']
    settings = strategy['settings']
    
    # Classify files by size
    tiny_files = [f for f in files_to_download if f.get('size', 0) < 100 * 1024]  # <100KB
    small_files = [f for f in files_to_download if 100 * 1024 <= f.get('size', 0) < 1 * 1024 * 1024]  # 100KB-1MB
    medium_files = [f for f in files_to_download if 1 * 1024 * 1024 <= f.get('size', 0) < 10 * 1024 * 1024]  # 1-10MB
    huge_files = [f for f in files_to_download if f.get('size', 0) >= 10 * 1024 * 1024]  # >10MB

    results = {}
    total_files = len(files_to_download)
    processed = 0

    # Handle different strategies
    if strategy_name in ['stable_sequential', 'cautious_parallel']:
        # Sequential processing
        for file_info in files_to_download:
            if cancel_requested:
                break
                
            success = Downloader._download_file_with_retry(
                f"http://147.45.184.36:8000/{file_info['relpath']}",
                file_info['local_path'],
                file_info,
                chunk_size=settings.get('chunk_size', 32768),
                timeout=settings.get('timeout', 30),
                strategy_settings=settings
            )
            
            results[file_info['relpath']] = success
            processed += 1
            
            if progress_callback:
                progress_callback(None, processed / total_files * 100, processed, total_files)
    
    else:  # Adaptive strategies
        # Process tiny files
        if tiny_files and not cancel_requested:
            workers = settings.get('tiny_file_workers', 8)
            results.update(Downloader._download_parallel(
                tiny_files,
                max_workers=workers,
                chunk_size=settings.get('chunk_size', 32768),
                timeout=settings.get('timeout', 30),
                strategy_settings=settings
            ))
            processed += len(tiny_files)
            
            if progress_callback:
                progress_callback(None, processed / total_files * 100, processed, total_files)

        # Process small files
        if small_files and not cancel_requested:
            workers = settings.get('small_file_workers', 4)
            results.update(Downloader._download_parallel(
                small_files,
                max_workers=workers,
                chunk_size=settings.get('chunk_size', 32768),
                timeout=settings.get('timeout', 30),
                strategy_settings=settings
            ))
            processed += len(small_files)
            
            if progress_callback:
                progress_callback(None, processed / total_files * 100, processed, total_files)

        # Process medium files
        if medium_files and not cancel_requested:
            workers = settings.get('medium_file_workers', 2)
            results.update(Downloader._download_parallel(
                medium_files,
                max_workers=workers,
                chunk_size=settings.get('chunk_size', 65536),
                timeout=settings.get('timeout', 45),
                strategy_settings=settings
            ))
            processed += len(medium_files)
            
            if progress_callback:
                progress_callback(None, processed / total_files * 100, processed, total_files)

        # Process huge files
        if huge_files and not cancel_requested:
            for file_info in huge_files:
                if cancel_requested:
                    break
                    
                success = Downloader._download_with_resume(
                    f"http://147.45.184.36:8000/{file_info['relpath']}",
                    file_info['local_path'],
                    file_info,
                    chunk_size=settings.get('chunk_size', 131072),
                    retry_count=settings.get('retry_count', 5),
                    timeout=settings.get('timeout', 60),
                    strategy_settings=settings
                )
                
                results[file_info['relpath']] = success
                processed += 1
                
                if progress_callback:
                    progress_callback(None, processed / total_files * 100, processed, total_files)

    return {'success': not cancel_requested, 'results': results, 'cancelled': cancel_requested}