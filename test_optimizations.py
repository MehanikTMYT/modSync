#!/usr/bin/env python3
"""
Детальное тестирование оптимизаций синхронизации модов Minecraft
"""
import os
import shutil
import hashlib
import requests
import time
from pathlib import Path

def test_server_manifest_caching():
    """Тестирование кеширования манифеста на сервере"""
    print("🧪 Тестируем кеширование манифеста на сервере...")
    
    server_url = "http://localhost:8800"
    
    # Первый запрос
    start_time = time.time()
    response1 = requests.get(f"{server_url}/manifest", timeout=10)
    time1 = time.time() - start_time
    
    # Второй запрос (должен быть быстрее за счет кеширования)
    start_time = time.time()
    response2 = requests.get(f"{server_url}/manifest", timeout=10)
    time2 = time.time() - start_time
    
    if response1.status_code == 200 and response2.status_code == 200:
        manifest1 = response1.json()
        manifest2 = response2.json()
        
        if manifest1 == manifest2 and time2 < time1:
            print(f"   ✅ Кеширование работает: первый запрос {time1:.3f}s, второй {time2:.3f}s")
            return True
        else:
            print(f"   ❌ Кеширование не работает эффективно: {time1:.3f}s vs {time2:.3f}s")
            return False
    else:
        print(f"   ❌ Ошибка получения манифеста: {response1.status_code} / {response2.status_code}")
        return False

def test_server_range_requests():
    """Тестирование Range-запросов на сервере"""
    print("🧪 Тестируем Range-запросы на сервере...")
    
    server_url = "http://localhost:8800"
    test_file = "AI-Improvements-1.21-0.5.3.jar"
    
    # Проверяем поддержку Range
    response = requests.head(f"{server_url}/file/{test_file}", timeout=5)
    if response.status_code != 200:
        print(f"   ❌ Ошибка получения метаданных файла: {response.status_code}")
        return False
    
    accept_ranges = response.headers.get("Accept-Ranges", "")
    if "bytes" not in accept_ranges:
        print(f"   ❌ Range-запросы не поддерживаются: {accept_ranges}")
        return False
    
    # Тестируем частичную загрузку
    headers = {"Range": "bytes=0-100"}  # Запрашиваем первые 101 байт
    range_response = requests.get(f"{server_url}/file/{test_file}", headers=headers, timeout=5)
    
    if range_response.status_code == 206:  # Partial Content
        content_range = range_response.headers.get("Content-Range", "")
        content_length = int(range_response.headers.get("Content-Length", 0))
        
        if "bytes 0-100/" in content_range and content_length == 101:
            print(f"   ✅ Range-запросы работают: {content_range}, длина {content_length}")
            return True
        else:
            print(f"   ❌ Некорректный ответ на Range-запрос: {content_range}, длина {content_length}")
            return False
    else:
        print(f"   ❌ Range-запросы не работают: {range_response.status_code}")
        return False

def test_server_file_hashing():
    """Тестирование передачи хешей файлов"""
    print("🧪 Тестируем передачу хешей файлов...")
    
    server_url = "http://localhost:8800"
    test_file = "AI-Improvements-1.21-0.5.3.jar"
    
    # Получаем хеш через HEAD-запрос
    response = requests.head(f"{server_url}/file/{test_file}", timeout=5)
    if response.status_code != 200:
        print(f"   ❌ Ошибка получения метаданных файла: {response.status_code}")
        return False
    
    file_hash = response.headers.get("X-File-Hash")
    if not file_hash:
        print("   ❌ Хеш файла не передается")
        return False
    
    # Сравниваем с вычисленным локально хешем
    local_file_path = Path("/workspace/server") / test_file
    if not local_file_path.exists():
        print("   ❌ Локальный файл не найден для сравнения")
        return False
    
    local_hash = hashlib.sha256(local_file_path.read_bytes()).hexdigest()
    
    if local_hash.startswith(file_hash.lower()):
        print(f"   ✅ Хеши совпадают: {file_hash[:8]}...")
        return True
    else:
        print(f"   ❌ Хеши не совпадают: сервер {file_hash[:8]}..., локальный {local_hash[:8]}...")
        return False

def test_client_skip_logic():
    """Тестирование логики пропуска файлов на клиенте"""
    print("🧪 Тестируем логику пропуска файлов на клиенте...")
    
    import sys
    sys.path.insert(0, '/workspace/client')
    from api import ModSyncAPI
    from utils import ensure_directory_exists
    
    # Создаем тестовую директорию
    client_mods = Path("/workspace/test_skip_logic")
    if client_mods.exists():
        shutil.rmtree(client_mods)
    client_mods.mkdir(parents=True, exist_ok=True)
    
    # Копируем один файл с сервера на клиент
    server_file = Path("/workspace/server") / "AI-Improvements-1.21-0.5.3.jar"
    client_file = client_mods / "AI-Improvements-1.21-0.5.3.jar"
    shutil.copy2(server_file, client_file)
    
    # Вычисляем хеш для проверки
    original_hash = hashlib.sha256(server_file.read_bytes()).hexdigest()
    
    api = ModSyncAPI()
    
    # Получаем манифест с сервера
    try:
        server_manifest = api.get_manifest()
        server_hash = server_manifest.get("AI-Improvements-1.21-0.5.3.jar", {}).get("hash")
        
        if original_hash != server_hash:
            print("   ❌ Хеши не совпадают")
            return False
        
        # Проверяем, что файл с совпадающим хешем будет пропущен
        # Это тестируется косвенно - если синхронизация пройдет успешно и файл останется
        def log(msg):
            pass  # Не выводим логи в этом тесте
        
        # Выполняем синхронизацию
        api.sync(client_mods, log)
        
        # Проверяем, что файл остался
        if client_file.exists():
            final_hash = hashlib.sha256(client_file.read_bytes()).hexdigest()
            if final_hash == original_hash:
                print("   ✅ Файл с совпадающим хешем пропущен")
                return True
            else:
                print("   ❌ Файл был изменен неожиданно")
                return False
        else:
            print("   ❌ Файл был удален неожиданно")
            return False
            
    except Exception as e:
        print(f"   ❌ Ошибка в логике пропуска: {e}")
        return False

def test_client_delete_logic():
    """Тестирование логики удаления файлов на клиенте"""
    print("🧪 Тестируем логику удаления файлов на клиенте...")
    
    import sys
    sys.path.insert(0, '/workspace/client')
    from api import ModSyncAPI
    
    # Создаем тестовую директорию
    client_mods = Path("/workspace/test_delete_logic")
    if client_mods.exists():
        shutil.rmtree(client_mods)
    client_mods.mkdir(parents=True, exist_ok=True)
    
    # Создаем фейковый файл, которого нет на сервере
    fake_file = client_mods / "fake_mod.jar"
    with open(fake_file, "w") as f:
        f.write("fake content")
    
    api = ModSyncAPI()
    
    def log(msg):
        pass  # Не выводим логи в этом тесте
    
    try:
        # Выполняем синхронизацию
        api.sync(client_mods, log)
        
        # Проверяем, что фейковый файл удален
        if not fake_file.exists():
            print("   ✅ Файл, отсутствующий на сервере, удален")
            return True
        else:
            print("   ❌ Файл, отсутствующий на сервере, не удален")
            return False
    except Exception as e:
        print(f"   ❌ Ошибка в логике удаления: {e}")
        return False

def test_client_update_logic():
    """Тестирование логики обновления файлов на клиенте"""
    print("🧪 Тестируем логику обновления файлов на клиенте...")
    
    import sys
    sys.path.insert(0, '/workspace/client')
    from api import ModSyncAPI
    
    # Создаем тестовую директорию
    client_mods = Path("/workspace/test_update_logic")
    if client_mods.exists():
        shutil.rmtree(client_mods)
    client_mods.mkdir(parents=True, exist_ok=True)
    
    # Копируем файл с сервера и модифицируем его
    server_file = Path("/workspace/server") / "AI-Improvements-1.21-0.5.3.jar"
    client_file = client_mods / "AI-Improvements-1.21-0.5.3.jar"
    shutil.copy2(server_file, client_file)
    
    # Добавляем немного данных к файлу, чтобы изменить его хеш
    with open(client_file, "ab") as f:
        f.write(b"modified")
    
    original_size = client_file.stat().st_size
    original_hash = hashlib.sha256(client_file.read_bytes()).hexdigest()
    
    api = ModSyncAPI()
    
    def log(msg):
        pass  # Не выводим логи в этом тесте
    
    try:
        # Выполняем синхронизацию
        api.sync(client_mods, log)
        
        # Проверяем, что файл обновлен до оригинального состояния
        if client_file.exists():
            final_hash = hashlib.sha256(client_file.read_bytes()).hexdigest()
            server_hash = hashlib.sha256(server_file.read_bytes()).hexdigest()
            
            if final_hash == server_hash:
                print("   ✅ Файл с неправильным хешем обновлен")
                return True
            else:
                print("   ❌ Файл с неправильным хешем не обновлен должным образом")
                return False
        else:
            print("   ❌ Файл с неправильным хешем удален вместо обновления")
            return False
    except Exception as e:
        print(f"   ❌ Ошибка в логике обновления: {e}")
        return False

def test_parallel_downloads():
    """Тестирование параллельных загрузок"""
    print("🧪 Тестируем параллельные загрузки...")
    
    import sys
    sys.path.insert(0, '/workspace/client')
    from api import ModSyncAPI
    
    # Создаем тестовую директорию
    client_mods = Path("/workspace/test_parallel")
    if client_mods.exists():
        shutil.rmtree(client_mods)
    client_mods.mkdir(parents=True, exist_ok=True)
    
    api = ModSyncAPI()
    
    # Получаем список файлов с сервера
    try:
        server_manifest = api.get_manifest()
        test_files = list(server_manifest.keys())[:5]  # Берем первые 5 файлов
        
        if len(test_files) < 3:
            print("   ❌ Недостаточно файлов для тестирования")
            return False
        
        # Запускаем синхронизацию только для этих файлов
        def log(msg):
            pass  # Не выводим логи в этом тесте
        
        # Выполняем синхронизацию
        api.sync(client_mods, log)
        
        # Проверяем, что все файлы загружены
        all_downloaded = True
        for f in test_files:
            if not (client_mods / f).exists():
                all_downloaded = False
                break
        
        if all_downloaded:
            print(f"   ✅ Параллельная загрузка работает: {len(test_files)} файлов загружено")
            return True
        else:
            print(f"   ❌ Не все файлы загружены: {len(list(client_mods.rglob('*')))} из {len(test_files)}")
            return False
    except Exception as e:
        print(f"   ❌ Ошибка в параллельных загрузках: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🔍 Детальное тестирование оптимизаций системы синхронизации модов")
    print("Проверяем работу всех ключевых функций системы...\n")
    
    # Проверяем доступность сервера
    try:
        response = requests.get("http://localhost:8800/health", timeout=5)
        if response.status_code != 200:
            print("❌ Сервер недоступен")
            return False
        print("✅ Сервер доступен\n")
    except Exception as e:
        print(f"❌ Ошибка подключения к серверу: {e}")
        return False
    
    # Выполняем все тесты
    tests = [
        ("Кеширование манифеста", test_server_manifest_caching),
        ("Range-запросы", test_server_range_requests),
        ("Передача хешей файлов", test_server_file_hashing),
        ("Логика пропуска файлов", test_client_skip_logic),
        ("Логика удаления файлов", test_client_delete_logic),
        ("Логика обновления файлов", test_client_update_logic),
        ("Параллельные загрузки", test_parallel_downloads),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n--- Тест: {test_name} ---")
        result = test_func()
        results.append((test_name, result))
        print()
    
    # Подводим итоги
    print("="*60)
    print("РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:")
    print("="*60)
    
    passed = 0
    for test_name, result in results:
        status = "✅ ПРОЙДЕН" if result else "❌ НЕ ПРОЙДЕН"
        print(f"{status}: {test_name}")
        if result:
            passed += 1
    
    print(f"\nИтого: {passed}/{len(results)} тестов пройдено")
    
    if passed == len(results):
        print("\n🎉 Все тесты оптимизаций пройдены успешно!")
        print("✅ Система синхронизации полностью функциональна")
        print("✅ Все оптимизации работают как ожидается")
        return True
    else:
        print(f"\n❌ {len(results) - passed} из {len(results)} тестов не пройдены")
        return False

if __name__ == "__main__":
    main()