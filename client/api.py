from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import ClientConfig
from utils import (
    load_cache, save_cache, rollback,
    verify_file_integrity, ensure_directory_exists,
)
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import threading


class ModSyncAPI:
    def __init__(self):
        self.config = ClientConfig()
        self.server_url = self.config.get_server_url().rstrip("/")
        self.logger = logging.getLogger("ModSyncAPI")

        self.session = requests.Session()
        sync_settings = self.config.get_sync_settings()

        retries = Retry(
            total=sync_settings.get("max_retries", 3),
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504]
        )
        self.session.mount("http://", HTTPAdapter(max_retries=retries))
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

        self.timeout = sync_settings.get("timeout", 30)
        self.chunk_size = sync_settings.get("chunk_size", 131072)
        self.max_workers = sync_settings.get("max_workers", 4)

        self.cancel_requested = False

    # ------------------------------------------------------------------ MANIFEST

    def get_manifest(self):
        try:
            r = self.session.get(
                f"{self.server_url}/manifest",
                timeout=self.timeout
            )
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, dict):
                raise ValueError("Некорректный формат манифеста")
            return data
        except requests.RequestException as e:
            raise ConnectionError(f"Ошибка подключения к серверу: {str(e)}")

    # ------------------------------------------------------------------ DOWNLOAD SMART

    def download_file_smart(self, rel_path, dest, file_info, on_progress=None):
        file_size = file_info["size"]
        dest.parent.mkdir(parents=True, exist_ok=True)

        if file_size <= 0:
            raise ValueError(f"Некорректный размер файла: {rel_path}")

        # Resume при наличии файла
        if dest.exists():
            if dest.stat().st_size == file_size:
                return file_size
            return self.download_file_resume(rel_path, dest, file_info, on_progress)

        if file_size < 1 * 1024 * 1024:
            return self.download_file(rel_path, dest, on_progress)

        if file_size < 50 * 1024 * 1024:
            return self.download_file_resume(rel_path, dest, file_info, on_progress)

        # Проверка Range
        supports_ranges = False
        try:
            head = self.session.head(
                f"{self.server_url}/file/{rel_path}",
                timeout=self.timeout
            )
            if head.status_code < 400:
                supports_ranges = "bytes" in head.headers.get("Accept-Ranges", "")
        except requests.RequestException:
            pass

        if supports_ranges:
            return self.download_file_parallel(rel_path, dest, file_info, on_progress)

        return self.download_file_resume(rel_path, dest, file_info, on_progress)

    # ------------------------------------------------------------------ RESUME

    def download_file_resume(self, rel_path, dest, file_info, on_progress=None, max_attempts=5):
        """Улучшенная версия с автоматическим восстановлением после сбоя сети"""
        file_size = file_info["size"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        temp_dest = dest.with_suffix(dest.suffix + ".tmp")
        
        for attempt in range(max_attempts):
            try:
                downloaded = temp_dest.stat().st_size if temp_dest.exists() else 0
                headers = {"Range": f"bytes={downloaded}-"} if downloaded else {}
                
                with self.session.get(
                    f"{self.server_url}/file/{rel_path}",
                    headers=headers,
                    stream=True,
                    timeout=(self.timeout, 60)  # Увеличенный таймаут для больших файлов
                ) as r:
                    r.raise_for_status()
                    
                    if downloaded > 0 and r.status_code != 206:
                        # Сервер не поддерживает resume, начинаем заново
                        if temp_dest.exists():
                            temp_dest.unlink()
                        downloaded = 0
                    
                    remaining = int(r.headers.get("Content-Length", file_size - downloaded))
                    total = downloaded + remaining
                    
                    mode = "ab" if downloaded else "wb"
                    with open(temp_dest, mode) as f:
                        for chunk in r.iter_content(self.chunk_size):
                            if self.cancel_requested:
                                raise Exception("Операция отменена пользователем")
                            if not chunk:
                                continue
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            # Проверка целостности каждые 10MB
                            if downloaded % (10 * 1024 * 1024) == 0 and file_info.get("hash"):
                                if not self._check_partial_hash(temp_dest, file_info["hash"], downloaded):
                                    logger.warning(f"⚠️ Частичная проверка хеша не совпала на {downloaded} байтах")
                            
                            if on_progress:
                                on_progress(downloaded, total)
                    
                    # Финальная проверка целостности
                    if file_info.get("hash") and not verify_file_integrity(temp_dest, file_info["hash"]):
                        raise IOError("Хеш файла не совпадает после загрузки")
                    
                    if downloaded != total:
                        raise IOError(f"Неполная загрузка: {downloaded}/{total} байт")
                    
                    # Атомарное переименование
                    if dest.exists():
                        dest.unlink()
                    temp_dest.rename(dest)
                    return total
                    
            except (requests.exceptions.RequestException, IOError, OSError) as e:
                logger.warning(f"⚠️ Попытка {attempt + 1}/{max_attempts} не удалась: {str(e)}")
                if attempt == max_attempts - 1:
                    if temp_dest.exists():
                        temp_dest.unlink(missing_ok=True)
                    raise
                time.sleep(1 + attempt * 0.5)  # Экспоненциальная задержка
        
        if temp_dest.exists():
            temp_dest.unlink(missing_ok=True)
        raise Exception("Не удалось завершить загрузку после всех попыток")

    # ------------------------------------------------------------------ PARALLEL

    def download_file_parallel(self, rel_path, dest, file_info, on_progress=None):
        file_size = file_info["size"]
        dest.parent.mkdir(parents=True, exist_ok=True)

        part_count = max(2, min(self.max_workers, file_size // (50 * 1024 * 1024)))
        part_size = file_size // part_count

        temp_files = [dest.with_suffix(dest.suffix + f".part{i}") for i in range(part_count)]
        downloaded_total = 0
        lock = threading.Lock()

        def download_part(i, start, end):
            nonlocal downloaded_total
            headers = {"Range": f"bytes={start}-{end}"}
            with self.session.get(
                f"{self.server_url}/file/{rel_path}",
                headers=headers,
                stream=True,
                timeout=(self.timeout, None)
            ) as r:
                if r.status_code != 206:
                    raise IOError("Range не поддерживается")
                with open(temp_files[i], "wb") as f:
                    for chunk in r.iter_content(self.chunk_size):
                        if self.cancel_requested:
                            raise Exception("Операция отменена пользователем")
                        if chunk:
                            f.write(chunk)
                            with lock:
                                downloaded_total += len(chunk)
                                if on_progress:
                                    on_progress(downloaded_total, file_size)

        try:
            with ThreadPoolExecutor(max_workers=part_count) as pool:
                futures = []
                for i in range(part_count):
                    start = i * part_size
                    end = file_size - 1 if i == part_count - 1 else (i + 1) * part_size - 1
                    futures.append(pool.submit(download_part, i, start, end))
                for f in futures:
                    f.result()

            with open(dest, "wb") as out:
                for part in temp_files:
                    with open(part, "rb") as p:
                        shutil.copyfileobj(p, out)
                    part.unlink()

            if dest.stat().st_size != file_size:
                raise IOError("Размер итогового файла не совпадает")

            return file_size

        finally:
            for p in temp_files:
                p.unlink(missing_ok=True)

    # ------------------------------------------------------------------ SIMPLE

    def download_file(self, rel_path, dest, on_progress=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.session.get(
                f"{self.server_url}/file/{rel_path}",
                stream=True,
                timeout=(self.timeout, None)
            ) as r:
                r.raise_for_status()
                total = int(r.headers.get("Content-Length", 0))
                downloaded = 0
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(self.chunk_size):
                        if self.cancel_requested:
                            raise Exception("Операция отменена пользователем")
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if on_progress:
                                on_progress(downloaded, total)
                return total
        except Exception:
            dest.unlink(missing_ok=True)
            raise
    # ------------------------------------------------------------------ PARALLEL DOWNLOADS
    def download_files_parallel(
    self,
    mods_path: Path,
    files: list[str],
    server_manifest: dict,
    cache: dict,
    on_file_start=None,
    on_file_progress=None,
    on_total_progress=None,
):
        """
        Параллельная загрузка нескольких файлов
        Использует download_file_smart для каждого файла
        """

        total_bytes = sum(server_manifest[f]["size"] for f in files)
        completed_bytes = 0
        completed_lock = threading.Lock()

        # Для хранения прогресса каждого файла
        file_progress_map = {f: 0 for f in files}

        def make_progress_callback(rel_path, file_size):
            def progress(current, total):
                nonlocal completed_bytes

                with completed_lock:
                    prev = file_progress_map[rel_path]
                    delta = current - prev
                    file_progress_map[rel_path] = current
                    completed_bytes += max(0, delta)

                    if on_file_progress:
                        on_file_progress(rel_path, current, total)

                    if on_total_progress:
                        on_total_progress(completed_bytes, total_bytes)
            return progress

        def worker(rel_path):
            if self.cancel_requested:
                raise Exception("Операция отменена пользователем")

            dest = mods_path / rel_path
            info = server_manifest[rel_path]

            if on_file_start:
                on_file_start(rel_path, info["size"])

            try:
                size = self.download_file_smart(
                    rel_path,
                    dest,
                    info,
                    on_progress=make_progress_callback(rel_path, info["size"])
                )

                if not verify_file_integrity(dest, info["hash"]):
                    raise IOError("Хеш не совпадает")

                cache[rel_path] = info["hash"]
                return rel_path, size, None

            except Exception as e:
                dest.unlink(missing_ok=True)
                cache.pop(rel_path, None)
                return rel_path, 0, str(e)

        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(worker, f) for f in files]

            for future in futures:
                try:
                    results.append(future.result())
                except Exception as e:
                    results.append((None, 0, str(e)))

        return results


    # ------------------------------------------------------------------ SYNC

    def sync(self, mods_path, log, dry_run=False,
             on_start=None, on_file_start=None,
             on_file_progress=None, on_total_progress=None):

        mods_path = Path(mods_path)
        ensure_directory_exists(mods_path)

        server_manifest = self.get_manifest()
        cache = load_cache(mods_path)

        local_files = {
            (Path(root) / f).relative_to(mods_path).as_posix()
            for root, _, files in os.walk(mods_path)
            for f in files
            if not f.startswith(".modsync_")
        }

        server_files = set(server_manifest.keys())
        to_delete = local_files - server_files
        to_update = set()
        total_download_size = 0

        for f, info in server_manifest.items():
            p = mods_path / f
            if not p.exists() or p.stat().st_size != info["size"] or cache.get(f) != info["hash"]:
                to_update.add(f)
                total_download_size += info["size"]

        if on_start:
            on_start(total_download_size)

        if dry_run:
            for f in to_delete:
                log(f"🗑️ {f}")
            for f in to_update:
                log(f"⬇️ {f}")
            return

        self.cancel_requested = False
        completed_bytes = 0

        try:
            for f in to_delete:
                (mods_path / f).unlink(missing_ok=True)
                cache.pop(f, None)

            for f in sorted(to_update):
                info = server_manifest[f]
                dest = mods_path / f

                if on_file_start:
                    on_file_start(f, info["size"])

                def progress(c, t):
                    if on_file_progress:
                        on_file_progress(c, t)
                    if on_total_progress:
                        on_total_progress(completed_bytes + c, total_download_size)

                size = self.download_file_smart(f, dest, info, progress)

                if not verify_file_integrity(dest, info["hash"]):
                    raise IOError("Хеш не совпадает")

                cache[f] = info["hash"]
                completed_bytes += size
                log(f"✅ {f}")

            save_cache(mods_path, cache)
            log("✅ Синхронизация завершена")

        except Exception:
            rollback(mods_path)
            raise