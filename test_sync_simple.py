#!/usr/bin/env python3
"""
Тестирование сценариев синхронизации модов Minecraft
"""
import os
import shutil
import hashlib
import requests
import time
from pathlib import Path
from threading import Thread

def start_server():
    """Запускает сервер в отдельном потоке"""
    import subprocess
    import sys
    # Запускаем сервер на фоне
    server_process = subprocess.Popen([
        sys.executable, "-c", 
        """
import sys
import os
sys.path.insert(0, '/workspace/server')
os.chdir('/workspace/server')
from main import main
main()
        """
    ])
    return server_process

def calculate_sha256(file_path):
    """Вычисляет SHA256 хеш файла"""
    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()

def test_sync_scenarios():
    """Тестирует все сценарии синхронизации"""
    print("🚀 Запуск тестирования сценариев синхронизации...")
    
    # Очищаем директорию клиента для теста
    client_mods = Path("/workspace/test_client_mods")
    if client_mods.exists():
        shutil.rmtree(client_mods)
    client_mods.mkdir(parents=True, exist_ok=True)
    
    # Подключаемся к серверу (предполагаем, что он уже запущен)
    server_url = "http://localhost:8800"
    
    # Ждем немного, чтобы сервер запустился
    time.sleep(3)
    
    try:
        # Проверяем доступность сервера
        response = requests.get(f"{server_url}/health", timeout=5)
        if response.status_code != 200:
            print("❌ Сервер недоступен")
            return False
        print("✅ Сервер доступен")
    except Exception as e:
        print(f"❌ Ошибка подключения к серверу: {e}")
        return False
    
    # Получаем манифест с сервера
    try:
        response = requests.get(f"{server_url}/manifest", timeout=10)
        server_manifest = response.json()
        print(f"📋 Манифест получен: {len(server_manifest)} файлов")
    except Exception as e:
        print(f"❌ Ошибка получения манифеста: {e}")
        return False
    
    # Подготовим тестовые сценарии
    test_files = list(server_manifest.keys())[:3]  # Возьмем первые 3 файла для теста
    
    if len(test_files) < 3:
        print("❌ Недостаточно файлов для тестирования")
        return False
    
    # 1. Сценарий: файл есть на клиенте и совпадает с сервером
    print("\n--- Сценарий 1: файл совпадает с сервером ---")
    matching_file = test_files[0]
    server_file_path = Path("/workspace/server") / matching_file
    client_file_path = client_mods / matching_file
    
    # Копируем файл с сервера на клиент
    client_file_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(server_file_path, client_file_path)
    print(f"📦 Скопирован файл: {matching_file}")
    
    # Проверяем, что хеши совпадают
    original_hash = calculate_sha256(server_file_path)
    client_hash = calculate_sha256(client_file_path)
    server_hash = server_manifest[matching_file]["hash"]
    
    print(f"   Оригинал: {original_hash[:8]}...")
    print(f"   Клиент:   {client_hash[:8]}...")
    print(f"   Сервер:   {server_hash[:8]}...")
    
    if original_hash == client_hash == server_hash:
        print("✅ Хеши совпадают")
    else:
        print("❌ Хеши не совпадают")
        return False
    
    # 2. Сценарий: файл есть на клиенте, но его нет на сервере
    print("\n--- Сценарий 2: файл есть на клиенте, но нет на сервере ---")
    fake_file = "test_fake_mod-1.0.0.jar"
    fake_file_path = client_mods / fake_file
    with open(fake_file_path, "w") as f:
        f.write("fake mod content")
    print(f"📦 Создан фейковый файл: {fake_file}")
    
    # 3. Сценарий: файл есть на клиенте, но хеш не совпадает с сервером
    print("\n--- Сценарий 3: файл на клиенте с несовпадающим хешем ---")
    modified_file = test_files[1]
    server_file_path = Path("/workspace/server") / modified_file
    client_file_path = client_mods / modified_file
    
    # Копируем файл с сервера на клиент
    client_file_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(server_file_path, client_file_path)
    
    # Модифицируем файл на клиенте
    with open(client_file_path, "a") as f:
        f.write("modified content")
    
    # Проверяем, что хеши не совпадают
    original_hash = calculate_sha256(server_file_path)
    modified_hash = calculate_sha256(client_file_path)
    server_hash = server_manifest[modified_file]["hash"]
    
    print(f"   Оригинал: {original_hash[:8]}...")
    print(f"   Модифиц.: {modified_hash[:8]}...")
    print(f"   Сервер:   {server_hash[:8]}...")
    
    if original_hash == server_hash and original_hash != modified_hash:
        print("✅ Хеши корректно различаются")
    else:
        print("❌ Ошибка в проверке хешей")
        return False
    
    # 4. Сценарий: файла нет на клиенте, но есть на сервере
    print("\n--- Сценарий 4: файл есть на сервере, но нет на клиенте ---")
    missing_file = test_files[2]
    print(f"📦 Файл {missing_file} отсутствует на клиенте (ожидается загрузка)")
    
    # Проверяем начальное состояние
    print(f"📁 Состояние клиентской директории до синхронизации:")
    for f in client_mods.rglob("*"):
        if f.is_file():
            print(f"   {f.name}")
    
    # Запускаем синхронизацию через API клиента
    print("\n🔄 Запуск синхронизации...")
    import sys
    sys.path.insert(0, '/workspace/client')
    from api import ModSyncAPI
    
    api = ModSyncAPI()
    
    # Выполняем синхронизацию
    def log(msg):
        print(f"   {msg}")
    
    try:
        api.sync(client_mods, log)
        print("✅ Синхронизация завершена успешно")
    except Exception as e:
        print(f"❌ Ошибка синхронизации: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Проверяем результаты
    print(f"\n📁 Состояние клиентской директории после синхронизации:")
    client_files_after = list(client_mods.rglob("*"))
    for f in client_files_after:
        if f.is_file():
            print(f"   {f.relative_to(client_mods)}")
    
    # Проверяем, что:
    # 1. matching_file остался (совпадает с сервером)
    if (client_mods / matching_file).exists():
        print(f"✅ {matching_file} остался (должен быть пропущен)")
    else:
        print(f"❌ {matching_file} удален (должен остаться)")
        return False
    
    # 2. fake_file удален (его нет на сервере)
    if not (client_mods / fake_file).exists():
        print(f"✅ {fake_file} удален (его нет на сервере)")
    else:
        print(f"❌ {fake_file} остался (должен быть удален)")
        return False
    
    # 3. modified_file обновлен (хеш не совпадал)
    if (client_mods / modified_file).exists():
        final_hash = calculate_sha256(client_mods / modified_file)
        if final_hash == server_manifest[modified_file]["hash"]:
            print(f"✅ {modified_file} обновлен с правильным хешем")
        else:
            print(f"❌ {modified_file} обновлен с неправильным хешем")
            return False
    else:
        print(f"❌ {modified_file} отсутствует после синхронизации")
        return False
    
    # 4. missing_file загружен
    if (client_mods / missing_file).exists():
        final_hash = calculate_sha256(client_mods / missing_file)
        if final_hash == server_manifest[missing_file]["hash"]:
            print(f"✅ {missing_file} загружен с правильным хешем")
        else:
            print(f"❌ {missing_file} загружен с неправильным хешем")
            return False
    else:
        print(f"❌ {missing_file} не загружен")
        return False
    
    print("\n🎉 Все сценарии синхронизации прошли успешно!")
    return True

def test_server_optimizations():
    """Тестирование оптимизаций на сервере"""
    print("\n🚀 Тестирование оптимизаций на сервере...")
    
    server_url = "http://localhost:8800"
    
    # Ждем немного, чтобы сервер запустился
    time.sleep(1)
    
    try:
        # Тестируем кеширование манифеста
        print("   Тестируем кеширование манифеста...")
        start_time = time.time()
        response1 = requests.get(f"{server_url}/manifest", timeout=10)
        time1 = time.time() - start_time
        
        time.sleep(0.1)  # Небольшая задержка
        
        start_time = time.time()
        response2 = requests.get(f"{server_url}/manifest", timeout=10)
        time2 = time.time() - start_time
        
        if response1.status_code == 200 and response2.status_code == 200:
            print(f"   Время первого запроса: {time1:.3f}s")
            print(f"   Время второго запроса: {time2:.3f}s")
            if time2 < time1:
                print("   ✅ Кеширование работает (второй запрос быстрее)")
            else:
                print("   ⚠️ Кеширование может не работать (второй запрос не быстрее)")
        else:
            print("   ❌ Ошибка получения манифеста")
            return False
        
        # Тестируем Range-запросы для докачки
        print("\n   Тестируем Range-запросы...")
        test_file = "AI-Improvements-1.21-0.5.3.jar"  # Маленький файл для теста
        response = requests.head(f"{server_url}/file/{test_file}", timeout=5)
        
        if response.status_code == 200:
            accept_ranges = response.headers.get("Accept-Ranges", "")
            print(f"   Accept-Ranges: {accept_ranges}")
            
            if "bytes" in accept_ranges:
                # Проверяем Range-запрос
                headers = {"Range": "bytes=0-100"}  # Запрашиваем первые 101 байт
                range_response = requests.get(f"{server_url}/file/{test_file}", 
                                            headers=headers, timeout=5)
                
                if range_response.status_code == 206:  # Partial Content
                    content_range = range_response.headers.get("Content-Range", "")
                    print(f"   Content-Range: {content_range}")
                    print("   ✅ Range-запросы поддерживаются")
                else:
                    print(f"   ❌ Range-запросы не работают (код: {range_response.status_code})")
                    return False
            else:
                print("   ❌ Range-запросы не поддерживаются")
                return False
        else:
            print(f"   ❌ Ошибка получения метаданных файла: {response.status_code}")
            return False
        
        # Тестируем хеши файлов
        print("\n   Тестируем хеши файлов...")
        response = requests.head(f"{server_url}/file/{test_file}", timeout=5)
        if response.status_code == 200:
            file_hash = response.headers.get("X-File-Hash")
            if file_hash:
                print(f"   X-File-Hash: {file_hash[:8]}...")
                print("   ✅ Хеши файлов работают")
            else:
                print("   ⚠️ Хеши файлов не передаются")
        else:
            print("   ❌ Ошибка получения хеша файла")
            return False
        
        print("\n✅ Все оптимизации сервера работают корректно!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования оптимизаций сервера: {e}")
        return False

def test_client_optimizations():
    """Тестирование оптимизаций на клиенте"""
    print("\n🚀 Тестирование оптимизаций на клиенте...")
    
    # Проверяем кеширование
    print("   Тестируем кеширование на клиенте...")
    
    # Создаем тестовую директорию
    client_mods = Path("/workspace/test_client_cache")
    if client_mods.exists():
        shutil.rmtree(client_mods)
    client_mods.mkdir(parents=True, exist_ok=True)
    
    # Импортируем утилиты клиента
    import sys
    sys.path.insert(0, '/workspace/client')
    from utils import load_cache, save_cache
    
    # Тестируем сохранение и загрузку кеша
    test_cache = {
        "test_mod-1.0.jar": "test_hash_12345",
        "another_mod-2.0.jar": "another_hash_67890"
    }
    
    save_cache(client_mods, test_cache)
    loaded_cache = load_cache(client_mods)
    
    if loaded_cache == test_cache:
        print("   ✅ Кеширование клиента работает")
    else:
        print("   ❌ Кеширование клиента не работает")
        return False
    
    # Проверяем обработку прерванных загрузок
    print("\n   Тестируем обработку прерванных загрузок...")
    from utils import rollback
    
    # Создаем временные файлы для теста отката
    temp_file = client_mods / "temp_test.jar.tmp"
    backup_dir = client_mods / ".modsync_backups"
    
    with open(temp_file, "w") as f:
        f.write("temporary content")
    
    # Проверяем, что rollback не падает
    rollback(client_mods)
    print("   ✅ Откат работает без ошибок")
    
    # Проверяем целостность файлов
    print("\n   Тестируем проверку целостности файлов...")
    from utils import verify_file_integrity
    
    test_file = client_mods / "integrity_test.jar"
    with open(test_file, "w") as f:
        f.write("test content for integrity check")
    
    # Вычисляем хеш
    import hashlib
    hash_obj = hashlib.sha256()
    with open(test_file, "rb") as f:
        hash_obj.update(f.read())
    correct_hash = hash_obj.hexdigest()
    
    # Проверяем правильный хеш
    result = verify_file_integrity(test_file, correct_hash)
    if result:
        print("   ✅ Проверка целостности работает для правильного файла")
    else:
        print("   ❌ Проверка целостности не работает для правильного файла")
        return False
    
    # Проверяем неправильный хеш
    wrong_hash = "0" * 64  # Неправильный хеш
    result = verify_file_integrity(test_file, wrong_hash)
    if not result:
        print("   ✅ Проверка целостности работает для неправильного файла")
    else:
        print("   ❌ Проверка целостности не работает для неправильного файла")
        return False
    
    print("\n✅ Все оптимизации клиента работают корректно!")
    return True

def main():
    print("🧪 Начинаем комплексное тестирование системы синхронизации модов")
    
    # Запускаем сервер
    print("\n🔌 Запускаем сервер...")
    server_process = start_server()
    
    try:
        # Ждем запуска сервера
        time.sleep(5)
        
        # Выполняем тесты
        success = True
        success &= test_server_optimizations()
        success &= test_client_optimizations()
        success &= test_sync_scenarios()
        
        if success:
            print("\n🎉 Все тесты пройдены успешно!")
            print("✅ Система синхронизации работает корректно")
            print("✅ Все оптимизации на сервере и клиенте функционируют")
            print("✅ Все сценарии синхронизации работают как ожидается")
        else:
            print("\n❌ Один или несколько тестов не прошли")
            
    finally:
        # Останавливаем сервер
        try:
            server_process.terminate()
            server_process.wait(timeout=5)
        except:
            try:
                server_process.kill()
            except:
                pass
    
    return success

if __name__ == "__main__":
    main()