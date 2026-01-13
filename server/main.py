import sys
import time
import logging
import asyncio
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

# Импортируем модули в зависимости от режима запуска
try:
    from hashing import sha256 as utils_sha256
    from config import CONFIG
    from sync import build_manifest, invalidate_manifest_cache, get_mods_directory
except ImportError:
    # Если импорты не работают (в собранном виде), пробуем другой путь
    from .hashing import sha256 as utils_sha256
    from .config import CONFIG
    from .sync import build_manifest, invalidate_manifest_cache, get_mods_directory

from fastapi import FastAPI, HTTPException, Header, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
import threading

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, CONFIG.get_log_level().upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("server.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("modsync_server")

# Глобальные переменные для кеширования
MANIFEST_CACHE: Dict[str, str] = {}
MANIFEST_TIMESTAMP: float = 0.0
MANIFEST_LOCK = threading.Lock()

def get_safe_file_path(path: str) -> Path:
    """Возвращает безопасный путь к файлу, предотвращая path traversal"""
    mods_dir = get_mods_directory()
    file_path = (mods_dir / path).resolve()
    
    # Проверяем, что путь находится внутри директории модов
    if not str(file_path).startswith(str(mods_dir.resolve())):
        logger.warning(f"Попытка path traversal: {path} -> {file_path}")
        raise HTTPException(status_code=403, detail="Access denied")
    
    return file_path

def generate_manifest() -> Dict[str, str]:
    """Генерирует манифест файлов с их хешами"""
    global MANIFEST_CACHE, MANIFEST_TIMESTAMP
    
    with MANIFEST_LOCK:
        try:
            mods_dir = get_mods_directory()
            if not mods_dir.exists():
                logger.warning(f"Директория модов не существует, создаю: {mods_dir}")
                mods_dir.mkdir(parents=True, exist_ok=True)
            
            manifest = build_manifest(force=True)
            MANIFEST_CACHE = manifest
            MANIFEST_TIMESTAMP = time.time()
            
            logger.info(f"✅ Манифест успешно сгенерирован: {len(manifest)} файлов")
            return manifest
        except Exception as e:
            logger.error(f"❌ Ошибка генерации манифеста: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to generate manifest: {str(e)}")

def get_cached_manifest() -> Dict[str, str]:
    """Возвращает кешированный манифест или генерирует новый при необходимости"""
    cache_duration = CONFIG.get_cache_duration()
    
    with MANIFEST_LOCK:
        current_time = time.time()
        if current_time - MANIFEST_TIMESTAMP > cache_duration:
            logger.info("⏰ Кеш манифеста устарел, генерирую новый")
            return generate_manifest()
        
        logger.debug(f"📦 Использую кешированный манифест ({len(MANIFEST_CACHE)} файлов)")
        return MANIFEST_CACHE.copy()

def handle_range_request(file_path: Path, file_size: int, file_hash: Optional[str], 
                        range_header: str, last_modified: str):
    """Обрабатывает Range запросы для докачки файлов"""
    try:
        # Парсим Range заголовок
        byte_range = range_header.replace("bytes=", "").strip().split("-")
        start = int(byte_range[0])
        end = int(byte_range[1]) if byte_range[1] and byte_range[1].strip() else None
        
        # Валидация диапазона
        if start >= file_size:
            logger.warning(f"❌ Недопустимый диапазон: start={start} >= file_size={file_size}")
            raise HTTPException(status_code=416, detail="Requested range not satisfiable")
        
        if end is None or end >= file_size:
            end = file_size - 1
        
        if start > end:
            logger.warning(f"❌ Недопустимый диапазон: start={start} > end={end}")
            raise HTTPException(status_code=416, detail="Invalid range")
        
        content_length = end - start + 1
        logger.debug(f"📤 Частичный файл: {file_path.name} [{start}-{end}/{file_size}]")
        
        # Формируем ответ
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
            "Content-Type": "application/octet-stream",
            "Last-Modified": last_modified
        }
        
        if file_hash:
            headers["X-File-Hash"] = file_hash
        
        # Открываем файл и читаем запрошенный диапазон
        def file_generator():
            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = content_length
                chunk_size = 8192  # 8KB chunks
                
                while remaining > 0:
                    chunk = f.read(min(chunk_size, remaining))
                    if not chunk:
                        break
                    yield chunk
                    remaining -= len(chunk)
        
        return StreamingResponse(
            file_generator(),
            status_code=206,  # Partial Content
            headers=headers,
            media_type="application/octet-stream"
        )
        
    except (ValueError, IndexError) as e:
        logger.error(f"❌ Ошибка парсинга Range заголовка '{range_header}': {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid range header: {str(e)}")
    except Exception as e:
        logger.error(f"❌ Ошибка обработки Range запроса: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing range request: {str(e)}")

def handle_full_file_request(file_path: Path, file_size: int, file_hash: Optional[str], last_modified: str):
    """Обрабатывает обычные GET запросы для полных файлов"""
    logger.info(f"📥 Отправка файла: {file_path.name} ({file_size / 1024 / 1024:.2f} MB)")
    headers = {
        "Accept-Ranges": "bytes",
        "Last-Modified": last_modified,
        "Content-Type": "application/octet-stream"
    }
    if file_hash:
        headers["X-File-Hash"] = file_hash
    
    def file_iterator():
        chunk_size = 256 * 1024  # 256KB для баланса производительности
        try:
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
        except Exception as e:
            logger.error(f"❌ Ошибка чтения файла {file_path}: {str(e)}")
            raise HTTPException(status_code=500, detail="Error reading file")
    
    return StreamingResponse(
        file_iterator(),
        headers=headers,
        media_type="application/octet-stream",
        status_code=200
    )

def format_size(size_bytes: int) -> str:
    """Форматирует размер в человекочитаемый вид"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

# Создаем lifespan manager вместо устаревших событий
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управляет жизненным циклом приложения"""
    logger.info("🚀 Запуск ModSync сервера...")
    
    # Проверяем и создаем директорию модов
    mods_dir = get_mods_directory()
    logger.info(f"📁 Директория модов: {mods_dir.absolute()}")
    
    if not mods_dir.exists():
        logger.warning(f"⚠️ Директория не существует, создаю: {mods_dir}")
        mods_dir.mkdir(parents=True, exist_ok=True)
    
    # Генерируем начальный манифест
    try:
        generate_manifest()
        logger.info("✅ Начальный манифест успешно сгенерирован")
    except Exception as e:
        logger.error(f"❌ Ошибка при генерации начального манифеста: {str(e)}")
    
    yield  # Здесь приложение запущено и обрабатывает запросы
    
    # Код после yield выполняется при завершении работы
    logger.info("🛑 Завершение работы ModSync сервера...")
    # Здесь можно добавить дополнительную очистку при необходимости

# Создаем приложение с lifespan
app = FastAPI(
    title="ModSync Server",
    description="Сервер для синхронизации модов с поддержкой докачки и контроля целостности",
    version="1.1.0",
    lifespan=lifespan
)

# Настройки CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "HEAD", "POST"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """Проверка состояния сервера"""
    mods_dir = get_mods_directory()
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "server_version": "1.1.0",
        "mods_directory": str(mods_dir),
        "mods_directory_exists": mods_dir.exists(),
        "file_count": len(MANIFEST_CACHE),
        "last_manifest_update": datetime.fromtimestamp(MANIFEST_TIMESTAMP).isoformat() if MANIFEST_TIMESTAMP else None,
        "uptime_seconds": time.time() - MANIFEST_TIMESTAMP if MANIFEST_TIMESTAMP else 0
    }

@app.get("/manifest")
async def get_manifest():
    """Возвращает манифест всех файлов с их хешами"""
    try:
        manifest = get_cached_manifest()
        logger.info(f"📋 Отправлен манифест: {len(manifest)} файлов")
        return JSONResponse(manifest)
    except Exception as e:
        logger.error(f"❌ Ошибка при получении манифеста: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get manifest: {str(e)}")

@app.head("/file/{path:path}")
@app.get("/file/{path:path}")
async def get_file(request: Request, path: str, range: Optional[str] = Header(None)):
    """
    Возвращает файл с продвинутой поддержкой:
    - Range запросов для докачки больших файлов
    - HEAD запросов для получения метаданных
    - Контроля целостности через X-File-Hash
    """
    try:
        # Получаем безопасный путь к файлу
        file_path = get_safe_file_path(path)
        
        # Проверяем существование файла
        if not file_path.exists() or not file_path.is_file():
            logger.warning(f"❌ Файл не найден: {file_path}")
            raise HTTPException(status_code=404, detail="File not found")
        
        # Получаем информацию о файле
        file_size = file_path.stat().st_size
        last_modified = datetime.fromtimestamp(file_path.stat().st_mtime).strftime('%a, %d %b %Y %H:%M:%S GMT')
        
        # Вычисляем хеш для небольших файлов (<100MB) для кеширования
        file_hash = None
        if file_size < 100 * 1024 * 1024:  # 100 MB
            try:
                file_hash = utils_sha256(file_path)
                logger.debug(f"🔑 Хеш файла {path}: {file_hash[:8]}...")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка вычисления хеша для {path}: {str(e)}")
        
        # Обработка HEAD запросов - только метаданные
        if request.method == "HEAD":
            headers = {
                "Content-Length": str(file_size),
                "Content-Type": "application/octet-stream",
                "Accept-Ranges": "bytes",
                "Last-Modified": last_modified
            }
            if file_hash:
                headers["X-File-Hash"] = file_hash
            
            logger.debug(f"HEAD запрос для {path}: {file_size} bytes")
            return Response(headers=headers, status_code=200)
        
        # Обработка Range запросов для докачки
        if range and range.startswith("bytes="):
            return handle_range_request(file_path, file_size, file_hash, range, last_modified)
        
        # Обычный GET запрос - полный файл
        return handle_full_file_request(file_path, file_size, file_hash, last_modified)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при обработке файла {path}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/config")
async def get_config():
    """Возвращает конфигурацию сервера"""
    mods_dir = get_mods_directory()
    return {
        "server_version": "1.1.0",
        "mods_directory": str(mods_dir),
        "mods_directory_exists": mods_dir.exists(),
        "cache_duration_seconds": CONFIG.get_cache_duration(),
        "file_count": len(MANIFEST_CACHE),
        "last_manifest_update": datetime.fromtimestamp(MANIFEST_TIMESTAMP).isoformat() if MANIFEST_TIMESTAMP else None
    }

@app.post("/refresh")
async def refresh_manifest():
    """Принудительно обновляет манифест"""
    try:
        invalidate_manifest_cache()
        manifest = generate_manifest()
        logger.info(f"🔄 Манифест успешно обновлен: {len(manifest)} файлов")
        return {
            "status": "ok",
            "file_count": len(manifest),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"❌ Ошибка обновления манифеста: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to refresh manifest: {str(e)}")

@app.get("/stats")
async def get_stats():
    """Возвращает подробную статистику по файлам"""
    try:
        manifest = get_cached_manifest()
        mods_dir = get_mods_directory()
        
        total_size = 0
        file_types = {}
        file_sizes = []
        
        for rel_path, file_hash in manifest.items():
            file_path = mods_dir / rel_path
            if file_path.exists():
                file_size = file_path.stat().st_size
                total_size += file_size
                file_sizes.append(file_size)
                
                ext = file_path.suffix.lower() or "no_extension"
                file_types[ext] = file_types.get(ext, 0) + 1
        
        # Вычисляем статистику по размерам
        avg_size = total_size / len(manifest) if manifest else 0
        max_size = max(file_sizes) if file_sizes else 0
        min_size = min(file_sizes) if file_sizes else 0
        
        return {
            "total_files": len(manifest),
            "total_size_bytes": total_size,
            "total_size_human": format_size(total_size),
            "average_file_size": avg_size,
            "largest_file_size": max_size,
            "smallest_file_size": min_size,
            "file_types": file_types,
            "last_update": datetime.fromtimestamp(MANIFEST_TIMESTAMP).isoformat() if MANIFEST_TIMESTAMP else None,
            "cache_duration_seconds": CONFIG.get_cache_duration(),
            "mods_directory": str(mods_dir)
        }
    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")

def main():
    """Запуск сервера"""
    host = CONFIG.get_host()
    port = CONFIG.get_port()
    log_level = CONFIG.get_log_level()
    
    logger.info(f"🚀 Запуск сервера на http://{host}:{port}")
    logger.info(f"📝 Уровень логирования: {log_level}")
    logger.info(f"📁 Директория модов: {get_mods_directory().absolute()}")
    
    # Определяем, запущено ли приложение как собранное в один бинарный файл
    is_frozen = getattr(sys, 'frozen', False)
    
    if is_frozen:
        # Для собранного приложения передаем объект app напрямую
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level=log_level,
            reload=False,
            workers=1
        )
    else:
        # Для режима разработки используем строку импорта
        uvicorn.run(
            "main:app",
            host=host,
            port=port,
            log_level=log_level,
            reload=False,
            workers=1
        )

if __name__ == "__main__":
    main()