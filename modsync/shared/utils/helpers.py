import os
import hashlib
import re
from pathlib import Path


def validate_path(path):
    """
    Валидация и нормализация пути
    """
    if not path or not isinstance(path, str):
        return None
    
    # Нормализация пути
    normalized = os.path.normpath(path.strip())
    
    # Проверка на потенциально опасные паттерны
    dangerous_patterns = [
        r'\.\./',  # Попытка выхода из директории
        r'\.\.\\', 
        r'%s%',  # Windows переменные окружения
        r'\$HOME|\$USER',  # Unix переменные окружения
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, normalized, re.IGNORECASE):
            return None
    
    # Создание директории если её нет
    try:
        Path(normalized).mkdir(parents=True, exist_ok=True)
        return normalized
    except (OSError, PermissionError):
        return None


def calculate_file_hash(filepath, algorithm='sha256'):
    """
    Вычисление хэша файла
    """
    hash_func = hashlib.new(algorithm)
    try:
        with open(filepath, 'rb') as f:
            # Читаем файл блоками для экономии памяти
            for chunk in iter(lambda: f.read(8192), b""):
                hash_func.update(chunk)
        return hash_func.hexdigest()
    except FileNotFoundError:
        return None


def format_file_size(size_bytes):
    """
    Форматирование размера файла в человекочитаемый вид
    """
    if size_bytes == 0:
        return "0B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024.0 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f}{size_names[i]}"


def sanitize_filename(filename):
    """
    Санитизация имени файла
    """
    # Убираем недопустимые символы для разных ОС
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Убираем точки в начале и пробелы в конце
    sanitized = sanitized.strip('. ')
    
    # Ограничиваем длину имени файла
    if len(sanitized) > 255:
        name, ext = os.path.splitext(sanitized)
        sanitized = name[:255-len(ext)] + ext
    
    return sanitized


def compare_file_lists(list1, list2, key_func=lambda x: x['relpath']):
    """
    Сравнение двух списков файлов
    """
    dict1 = {key_func(item): item for item in list1}
    dict2 = {key_func(item): item for item in list2}
    
    added = [item for relpath, item in dict2.items() if relpath not in dict1]
    removed = [item for relpath, item in dict1.items() if relpath not in dict2]
    unchanged = [item for relpath, item in dict1.items() if relpath in dict2 and item == dict2[relpath]]
    modified = [dict2[relpath] for relpath, item in dict1.items() 
                if relpath in dict2 and item != dict2[relpath]]
    
    return {
        'added': added,
        'removed': removed,
        'unchanged': unchanged,
        'modified': modified
    }


def extract_file_info(filepath):
    """
    Извлечение информации о файле
    """
    path = Path(filepath)
    stat = path.stat()
    
    return {
        'name': path.name,
        'size': stat.st_size,
        'mtime': stat.st_mtime,
        'hash': calculate_file_hash(str(path)),
        'extension': path.suffix.lower(),
        'relpath': str(path.as_posix())  # Для совместимости с веб-путями
    }


def human_readable_time(seconds):
    """
    Преобразование секунд в человекочитаемый формат
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def normalize_mod_name(mod_name):
    """
    Нормализация имени мода для сравнения
    """
    # Убираем версию из имени мода
    normalized = re.sub(r'-v?\d+(\.\d+)*', '', mod_name, flags=re.IGNORECASE)
    normalized = re.sub(r'-[a-zA-Z]+\d+', '', normalized)  # Убираем суффиксы вроде -forge, -fabric
    return normalized.lower().strip('-_ ')


def merge_dicts_deep(dict1, dict2):
    """
    Глубокое слияние словарей
    """
    result = dict1.copy()
    
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts_deep(result[key], value)
        else:
            result[key] = value
    
    return result
