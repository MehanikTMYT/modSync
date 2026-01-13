import hashlib
import json
from pathlib import Path
import shutil
import os
import logging
from datetime import datetime
import platform
from config import ClientConfig

config = ClientConfig()
BACKUPS_DIR = config.get_backups_dir()
LAST_BACKUP_FILE = ".modsync_last_backup.txt"
CACHE_FILE = ".modsync_cache.json"

def sha256(path: Path, chunk_size=8192) -> str:
    """Вычисляет SHA256 хеш файла с оптимизацией для больших файлов"""
    if not path.exists() or not path.is_file():
        return ""
    
    h = hashlib.sha256()
    try:
        file_size = path.stat().st_size
        processed = 0
        
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
                processed += len(chunk)
                
        return h.hexdigest()
    except (IOError, OSError) as e:
        print(f"Ошибка чтения файла {path}: {e}")
        return ""

def load_cache(mods_path: Path) -> dict:
    """Загружает кеш хешей файлов с проверкой целостности"""
    cache_path = mods_path / CACHE_FILE
    if cache_path.exists():
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Проверяем целостность кеша
                if isinstance(data, dict):
                    return data
        except (json.JSONDecodeError, IOError, OSError) as e:
            print(f"Ошибка загрузки кеша: {e}")
            # Пытаемся восстановить из бекапа
            backup_path = cache_path.with_suffix('.bak')
            if backup_path.exists():
                try:
                    with open(backup_path, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except:
                    pass
    return {}

def save_cache(mods_path: Path, data: dict):
    """Сохраняет кеш хешей файлов с созданием бекапа"""
    cache_path = mods_path / CACHE_FILE
    try:
        # Создаем бекап текущего кеша
        if cache_path.exists():
            backup_path = cache_path.with_suffix('.bak')
            shutil.copy2(cache_path, backup_path)
        
        # Сохраняем новый кеш
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except (IOError, OSError) as e:
        print(f"Ошибка сохранения кеша: {e}")
        # Восстанавливаем из бекапа при ошибке
        backup_path = cache_path.with_suffix('.bak')
        if backup_path.exists():
            try:
                shutil.copy2(backup_path, cache_path)
            except:
                pass

def clear_memory_cache(self):
    """Очищает кеш памяти для больших операций"""
    import gc
    gc.collect()
    
    # Очищаем кеш хешей для больших файлов
    if hasattr(sha256, '_cache'):
        sha256._cache.clear()
    self.logger = logging.getLogger("ModSync.Utils")
    self.logger.debug("🧹 Очищен кеш памяти")

def create_backup(mods_path: Path, files: list[str]) -> Path:
    """Создает резервную копию указанных файлов с оптимизацией места"""
    if not files:
        return None
    
    # Группируем файлы по их хешам для экономии места
    file_groups = {}
    total_size = 0
    
    for rel in files:
        src = mods_path / rel
        if src.exists() and src.is_file():
            file_size = src.stat().st_size
            file_hash = sha256(src) if file_size < 100 * 1024 * 1024 else None
            
            if file_hash:
                if file_hash not in file_groups:
                    file_groups[file_hash] = {"size": file_size, "files": []}
                file_groups[file_hash]["files"].append(rel)
                total_size += file_size
            else:
                # Для больших файлов создаем hardlink если возможно
                total_size += file_size
    
    # Проверяем место на диске
    if not check_disk_space(mods_path, total_size * 1.2):  # +20% запаса
        logger.warning(f"⚠ Недостаточно места для бекапа. Требуется: {format_size(total_size * 1.2)}")
        return None
    
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_root = BACKUPS_DIR / stamp
    backup_root.mkdir(parents=True, exist_ok=True)
    
    manifest = {
        "timestamp": stamp,
        "source_path": str(mods_path),
        "files": [],
        "total_size": total_size,
        "hardlinked_files": []
    }
    
    # Создаем файлы с одинаковым хешем только один раз
    for file_hash, group in file_groups.items():
        if group["files"]:
            first_file = group["files"][0]
            src = mods_path / first_file
            dst = backup_root / first_file
            dst.parent.mkdir(parents=True, exist_ok=True)
            
            try:
                shutil.copy2(src, dst)
                # Для остальных файлов с таким же хешем создаем hardlink
                for other_file in group["files"][1:]:
                    other_dst = backup_root / other_file
                    other_dst.parent.mkdir(parents=True, exist_ok=True)
                    if platform.system() != 'Windows':  # Hardlink не всегда работает в Windows
                        os.link(dst, other_dst)
                        manifest["hardlinked_files"].append(other_file)
                    else:
                        shutil.copy2(src, other_dst)
                
                manifest["files"].append({
                    "relative_path": first_file,
                    "size": group["size"],
                    "hash": file_hash
                })
            except Exception as e:
                logger.error(f"Ошибка копирования {first_file}: {e}")
    
    # Сохраняем манифест
    manifest_path = backup_root / "backup_manifest.json"
    try:
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Ошибка сохранения манифеста: {e}")
    
    # Сохраняем путь к последнему бекапу
    last_backup_file = mods_path / LAST_BACKUP_FILE
    try:
        with open(last_backup_file, 'w', encoding='utf-8') as f:
            f.write(str(backup_root))
    except Exception as e:
        logger.error(f"Ошибка сохранения пути к бекапу: {e}")
    
    # Очищаем старые бекапы
    cleanup_old_backups()
    
    backup_size = sum(f.stat().st_size for f in backup_root.rglob('*') if f.is_file())
    logger.info(f"✅ Создан бекап: {len(files)} файлов, фактический размер: {format_size(backup_size)} (экономия: {format_size(total_size - backup_size)})")
    return backup_root

def cleanup_old_backups(max_backups=5):
    """Удаляет старые бекапы, оставляя указанное количество последних"""
    if not BACKUPS_DIR.exists():
        return
    
    backup_dirs = []
    for item in BACKUPS_DIR.iterdir():
        if item.is_dir() and item.name.count('_') >= 2:  # Проверяем формат имени
            try:
                # Пытаемся распарсить дату из имени
                datetime.strptime('_'.join(item.name.split('_')[:2]), "%Y-%m-%d_%H-%M-%S")
                backup_dirs.append(item)
            except ValueError:
                continue
    
    # Сортируем по времени создания (новые первыми)
    backup_dirs.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    
    # Удаляем старые бекапы
    for i, old_backup in enumerate(backup_dirs[max_backups:], start=1):
        try:
            total_size = sum(f.stat().st_size for f in old_backup.rglob('*') if f.is_file())
            print(f"🗑 Удален старый бекап ({i}/{len(backup_dirs)-max_backups}): {old_backup} ({format_size(total_size)})")
            shutil.rmtree(old_backup)
        except (OSError, IOError, shutil.Error) as e:
            print(f"❌ Ошибка удаления бекапа {old_backup}: {e}")

def get_last_backup(mods_path: Path) -> Path | None:
    """Возвращает путь к последнему бекапу"""
    last_backup_file = mods_path / LAST_BACKUP_FILE
    if last_backup_file.exists():
        try:
            backup_path_str = last_backup_file.read_text(encoding="utf-8").strip()
            backup_path = Path(backup_path_str)
            if backup_path.exists() and backup_path.is_dir():
                return backup_path
        except (IOError, OSError, ValueError) as e:
            print(f"Ошибка чтения пути к бекапу: {e}")
    return None

def rollback(mods_path: Path) -> bool:
    """Восстанавливает файлы из последнего бекапа"""
    backup = get_last_backup(mods_path)
    if not backup:
        print("❌ Бекап не найден")
        return False
    
    manifest_path = backup / "backup_manifest.json"
    if not manifest_path.exists():
        print("❌ Манифест бекапа не найден")
        return False
    
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        
        backup_source = Path(manifest["source_path"])
        
        # Проверяем соответствие исходной папки
        if backup_source.name != mods_path.name:
            print(f"⚠ Предупреждение: бекап создан для другой папки ({backup_source.name} vs {mods_path.name})")
        
        restored_count = 0
        total_count = len(manifest['files'])
        
        for file_info in manifest["files"]:
            rel_path = file_info["relative_path"]
            src = backup / rel_path
            dst = mods_path / rel_path
            
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(src, dst)
                    print(f"✅ Восстановлен файл: {rel_path}")
                    restored_count += 1
                except (IOError, OSError, shutil.Error) as e:
                    print(f"❌ Ошибка восстановления {rel_path}: {e}")
        
        print(f"✅ Восстановлено файлов: {restored_count}/{total_count}")
        return restored_count > 0
    except (json.JSONDecodeError, KeyError, IOError, OSError) as e:
        print(f"❌ Ошибка чтения манифеста бекапа: {e}")
        return False

def verify_file_integrity(file_path: Path, expected_hash: str) -> bool:
    """Проверяет целостность файла по хешу"""
    if not file_path.exists() or not file_path.is_file():
        return False
    
    actual_hash = sha256(file_path)
    if actual_hash != expected_hash:
        print(f"❌ Несовпадение хеша для {file_path}:")
        print(f"   Ожидаемый: {expected_hash}")
        print(f"   Фактический: {actual_hash}")
        return False
    return True

def ensure_directory_exists(path: Path):
    """Гарантирует существование директории"""
    if not path.exists():
        try:
            path.mkdir(parents=True, exist_ok=True)
            return True
        except (OSError, IOError) as e:
            print(f"❌ Ошибка создания директории {path}: {e}")
            return False
    return True

def get_free_space(path: Path) -> int:
    """Возвращает свободное место на диске в байтах"""
    try:
        if platform.system() == 'Windows':
            import ctypes
            free_bytes = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(str(path), None, None, ctypes.byref(free_bytes))
            return free_bytes.value
        else:
            statvfs = os.statvfs(path)
            return statvfs.f_frsize * statvfs.f_bavail
    except Exception as e:
        print(f"Ошибка получения свободного места: {e}")
        return 0

def check_disk_space(path: Path, required_bytes: int) -> bool:
    """Проверяет наличие достаточного места на диске"""
    free_space = get_free_space(path)
    return free_space >= required_bytes + 100 * 1024 * 1024  # +100 МБ запаса

def format_size(size_bytes: int) -> str:
    """Форматирует размер в человекочитаемом виде"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.2f} MB"
    else:
        return f"{size_bytes / (1024 ** 3):.2f} GB"

def human_readable_time(seconds: float) -> str:
    """Конвертирует секунды в человекочитаемый формат времени"""
    if seconds < 60:
        return f"{seconds:.1f} сек"
    elif seconds < 3600:
        return f"{seconds / 60:.1f} мин"
    else:
        return f"{seconds / 3600:.1f} час"