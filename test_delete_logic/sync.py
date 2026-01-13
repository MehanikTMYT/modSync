import os
import logging
import time
from pathlib import Path
from typing import Dict, Set
from hashing import sha256

# Глобальные переменные для кеширования
_manifest_cache: Dict[str, str] = {}
_last_manifest_update: float = 0.0
MANIFEST_CACHE_TIME: int = 60  # 60 секунд кеширования

def get_mods_directory() -> Path:
    """Возвращает путь к директории модов из конфигурации"""
    from config import CONFIG
    return CONFIG.get_mods_directory()

def ensure_mods_directory() -> None:
    """Гарантирует существование директории модов"""
    mods_dir = get_mods_directory()
    if not mods_dir.exists():
        logger = logging.getLogger("modsync_server")
        logger.info(f"📁 Создание директории модов: {mods_dir}")
        mods_dir.mkdir(parents=True, exist_ok=True)

def should_skip_file(file_path: Path) -> bool:
    """Проверяет, нужно ли пропустить файл при обработке"""
    # Пропускаем скрытые файлы и директории
    if file_path.name.startswith('.') or any(part.startswith('.') for part in file_path.parts):
        return True
    
    # Пропускаем системные файлы и директории
    skip_patterns = [
        '__pycache__',
        '.git',
        '.modsync_backups',
        '.modsync_cache.json',
        '.modsync_last_backup.txt',
        'server.log'
    ]
    
    return any(pattern in str(file_path) for pattern in skip_patterns)

def build_manifest(force: bool = False, max_cache_time: int = 60) -> dict:
    """
    Создает манифест всех файлов в директории модов с интеллектуальным кешированием.
    """
    global _manifest_cache, _last_manifest_update
    
    now = time.time()
    cache_valid = (
        _manifest_cache and 
        now - _last_manifest_update < max_cache_time and
        not force
    )
    
    if cache_valid:
        # Проверяем, не изменились ли ключевые файлы
        mods_dir = get_mods_directory()
        last_modified = max(
            (p.stat().st_mtime for p in mods_dir.rglob('*') 
             if p.is_file() and not should_skip_file(p)),
            default=0
        )
        
        if last_modified <= _last_manifest_update:
            return _manifest_cache
    
    # Перестраиваем манифест
    mods_dir = get_mods_directory()
    manifest = {}
    file_count = 0
    
    for root, dirs, files in os.walk(mods_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for name in files:
            path = Path(root) / name
            if should_skip_file(path):
                continue
            
            rel = path.relative_to(mods_dir).as_posix()
            stat = path.stat()
            
            # Кешируем хеш только для файлов < 50MB для экономии памяти
            file_hash = sha256(path) if stat.st_size < 50 * 1024 * 1024 else None
            
            manifest[rel] = {
                "size": stat.st_size,
                "mtime": int(stat.st_mtime),
                "hash": file_hash
            }
            file_count += 1
    
    _manifest_cache = manifest
    _last_manifest_update = now
    logger = logging.getLogger("modsync_server")
    logger.info(f"✅ Манифест обновлен: {file_count} файлов")
    return manifest

def invalidate_manifest_cache() -> None:
    """Сбрасывает кеш манифеста"""
    global _manifest_cache, _last_manifest_update
    _manifest_cache = {}
    _last_manifest_update = 0
    logger = logging.getLogger("modsync_server")
    logger.info("🧹 Кеш манифеста очищен")