import os
import sys
import threading
import time
import json
import hashlib
import re
from tkinter import filedialog, messagebox, scrolledtext, ttk

# Добавляем пути к другим модулям
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

import tkinter as tk
from modsync.client.config.manager import ConfigManager
from modsync.client.network.connection_utils import ConnectionManager
from modsync.client.network.speed_test_manager import SpeedTestManager
from modsync.client.download.manager import DownloadManager
from modsync.client.download.simple_strategy import DownloadStrategy

# Константа сервера
VDS_SERVER_IP = "http://147.45.184.36:8000"  # ЗАМЕНИТЕ НА ВАШ РЕАЛЬНЫЙ IP И ПОРТ
CONFIG_FILE = "modsync_config.ini"

class ModSyncApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Minecraft Mod Sync")
        self.root.geometry("900x750")
        self.root.resizable(True, True)
        
        # Менеджер конфигурации
        self.config_manager = ConfigManager()
        
        # Состояние автоопределения стратегии
        self.auto_strategy = self.config_manager.getboolean('Settings', 'auto_strategy', fallback=True)
        
        # Менеджер загрузки
        self.download_manager = None
        
        # Переменные
        self.mods_path = tk.StringVar(value=self.config_manager.get('Settings', 'mods_path', ''))
        self.running = False
        self.speed_test_results = None
        self.file_distribution = None
        self.connection_status = tk.StringVar(value="⏳ Ожидание инициализации...")
        
        # Создаем начальный интерфейс
        self.create_initial_interface()
    
    def create_initial_interface(self):
        """Создание начального интерфейса перед тестированием скорости"""
        for widget in self.root.winfo_children():
            widget.destroy()
        
        frame = ttk.Frame(self.root, padding=30)
        frame.pack(fill=tk.BOTH, expand=True, pady=50)
        
        ttk.Label(frame, text="🎮 Minecraft Mod Sync",
                 font=('Arial', 16, 'bold'), foreground="#0066cc").pack(pady=20)
        
        ttk.Label(frame, text="Инициализация приложения...",
                 font=('Arial', 12), foreground="#666").pack(pady=10)
        
        ttk.Label(frame, textvariable=self.connection_status,
                 font=('Arial', 10, 'bold'),
                 foreground="#4169E1").pack(pady=10)
        
        progress = ttk.Progressbar(frame, mode='indeterminate', maximum=100)
        progress.pack(fill=tk.X, padx=50, pady=20)
        progress.start()
        
        ttk.Label(frame, text=f"Сервер: {VDS_SERVER_IP}",
                 font=('Arial', 9), foreground="#666").pack(pady=10)
        
        # Запускаем тест скорости после создания интерфейса
        self.root.after(500, self.run_startup_speed_test)
    
    def run_startup_speed_test(self):
        """Запуск теста скорости при старте приложения"""
        self.connection_status.set("🔍 Проверка соединения с сервером...")
        
        def speed_test_thread():
            try:
                # Проверяем доступность сервера
                if not ConnectionManager.is_server_available(timeout=3):
                    self.connection_status.set("🔴 Сервер недоступен")
                    self.speed_test_results = {'error': 'Сервер недоступен'}
                    self.log_message("❌ Сервер недоступен. Проверьте соединение и настройки сервера.", "error")
                    self.create_interface_after_test()
                    return
                
                # Выполняем тест скорости с переподключением
                results = ConnectionManager.test_connection_with_retry()
                self.speed_test_results = results
                
                if 'error' in results:
                    self.connection_status.set("🟡 Не удалось протестировать скорость")
                    self.log_message(f"⚠️ {results['error']}", "warning")
                else:
                    avg_speed = results.get('average_speed_mbps', 0)
                    quality = results.get('connection_quality', 'unknown')
                    self.connection_status.set(f"🟢 Соединение стабильно: {avg_speed:.2f} Mbps ({quality})")
                    self.log_message(f"✅ Тест скорости завершен: {avg_speed:.2f} Mbps ({quality})", "success")
                    
                    # Сохраняем результаты теста
                    self.config_manager.set('Settings', 'last_speed_test', json.dumps({
                        'timestamp': results['timestamp'],
                        'average_speed_mbps': avg_speed,
                        'connection_quality': quality
                    }))
                    self.config_manager.save_config()
                
                self.create_interface_after_test()
                
            except Exception as e:
                self.connection_status.set("🔴 Ошибка соединения")
                self.speed_test_results = {'error': str(e)}
                self.log_message(f"❌ Критическая ошибка при запуске: {str(e)}", "error")
                self.create_interface_after_test()
        
        threading.Thread(target=speed_test_thread, daemon=True).start()
    
    def create_interface_after_test(self):
        """Создание интерфейса после завершения теста скорости"""
        if self.mods_path.get() and os.path.exists(self.mods_path.get()):
            self.create_main_interface()
        else:
            self.show_folder_selection_screen()
    
    def show_folder_selection_screen(self):
        """Экран выбора папки при первом запуске"""
        for widget in self.root.winfo_children():
            widget.destroy()
        
        frame = ttk.Frame(self.root, padding=30)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Статус соединения в заголовке
        ttk.Label(frame, textvariable=self.connection_status,
                 font=('Arial', 10, 'bold'),
                 foreground="#FF0000" if "недоступен" in self.connection_status.get() else "#008000").pack(pady=5)
        
        ttk.Label(frame, text="🎮 Minecraft Mod Sync",
                 font=('Arial', 16, 'bold'), foreground="#0066cc").pack(pady=15)
        
        ttk.Label(frame, text="Пожалуйста, выберите папку для синхронизации модов",
                 font=('Arial', 11)).pack(pady=10)
        
        ttk.Label(frame, text="⚠️ Внимание: Все файлы в этой папке будут автоматически\n"
                             "синхронизированы с сервером (лишние файлы будут удалены!)",
                 font=('Arial', 9), foreground="#FF0000", justify=tk.CENTER).pack(pady=10)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=20)
        
        ttk.Button(btn_frame, text="📁 Выбрать папку",
                  command=self.select_initial_folder, width=25).pack(pady=5)
        
        ttk.Button(btn_frame, text="⚙️ Настройки",
                  command=self.show_settings_screen, width=25).pack(pady=5)
        
        ttk.Label(frame, text=f"Сервер: {VDS_SERVER_IP}",
                 font=('Arial', 9), foreground="#666").pack(pady=10)
        
        # Кнопка переподключения
        reconnect_frame = ttk.Frame(frame)
        reconnect_frame.pack(pady=10)
        
        ttk.Button(reconnect_frame, text="🔄 Переподключиться",
                  command=self.retry_connection, width=20).pack()
        
        ttk.Label(reconnect_frame, text="Нажмите, если соединение было восстановлено",
                 font=('Arial', 8), foreground="#666").pack(pady=2)
    
    def retry_connection(self):
        """Попытка переподключения к серверу"""
        self.connection_status.set("⏳ Попытка переподключения...")
        
        def reconnect_thread():
            try:
                results = ConnectionManager.test_connection_with_retry()
                self.speed_test_results = results
                
                if 'error' in results:
                    self.connection_status.set("🔴 Сервер недоступен")
                    self.log_message(f"❌ Не удалось переподключиться: {results['error']}", "error")
                else:
                    avg_speed = results.get('average_speed_mbps', 0)
                    quality = results.get('connection_quality', 'unknown')
                    self.connection_status.set(f"🟢 Соединение восстановлено: {avg_speed:.2f} Mbps ({quality})")
                    self.log_message(f"✅ Переподключение успешно! Скорость: {avg_speed:.2f} Mbps", "success")
                    
                    # Обновляем интерфейс
                    self.show_folder_selection_screen()
            
            except Exception as e:
                self.connection_status.set("🔴 Ошибка переподключения")
                self.log_message(f"❌ Ошибка переподключения: {str(e)}", "error")
        
        threading.Thread(target=reconnect_thread, daemon=True).start()
    
    def select_initial_folder(self):
        """Выбор папки при первом запуске"""
        # Проверяем соединение перед выбором папки
        if self.connection_status.get().startswith("🔴"):
            if not messagebox.askyesno("⚠️ Сервер недоступен",
                                     "Сервер недоступен. Вы все равно хотите выбрать папку?\n"
                                     "Синхронизация будет невозможна до восстановления соединения."):
                return
        
        folder = filedialog.askdirectory(initialdir=os.path.expanduser("~"),
                                        title="Выберите папку для синхронизации модов")
        if folder:
            self.mods_path.set(folder)
            self.config_manager.set('Settings', 'mods_path', folder)
            if self.config_manager.save_config():
                self.create_main_interface()
            else:
                messagebox.showerror("Ошибка", "Не удалось сохранить настройки")
    
    def show_settings_screen(self):
        """Экран настроек с управлением стратегиями"""
        for widget in self.root.winfo_children():
            widget.destroy()
        
        frame = ttk.Frame(self.root, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Статус соединения в заголовке
        ttk.Label(frame, textvariable=self.connection_status,
                 font=('Arial', 10, 'bold'),
                 foreground="#FF0000" if "недоступен" in self.connection_status.get() else "#008000").pack(pady=5)
        
        ttk.Label(frame, text="⚙️ Настройки",
                 font=('Arial', 16, 'bold'), foreground="#0066cc").pack(pady=15)
        
        # Настройки папки
        folder_frame = ttk.LabelFrame(frame, text="Папка синхронизации", padding=10)
        folder_frame.pack(fill=tk.X, pady=10)
        
        current_path = self.mods_path.get() or "Не выбрана"
        ttk.Label(folder_frame, text=f"Текущая папка:", font=('Arial', 9, 'bold')).pack(anchor=tk.W)
        ttk.Label(folder_frame, text=current_path, wraplength=700, foreground="#666").pack(anchor=tk.W, pady=2)
        
        ttk.Button(folder_frame, text="📁 Изменить папку",
                  command=self.change_mods_folder, width=20).pack(pady=10)
        
        # Настройки стратегии скачивания
        strategy_frame = ttk.LabelFrame(frame, text="Стратегия скачивания файлов", padding=10)
        strategy_frame.pack(fill=tk.X, pady=10)
        
        # Автоопределение стратегии
        auto_var = tk.BooleanVar(value=self.auto_strategy)
        ttk.Checkbutton(strategy_frame, text="Автоопределение стратегии (рекомендуется)",
                       variable=auto_var, command=lambda: self.toggle_auto_strategy(auto_var.get())).pack(anchor=tk.W, pady=5)
        
        # Тест скорости
        test_frame = ttk.Frame(strategy_frame)
        test_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(test_frame, text="⚡ Протестировать скорость",
                  command=self.manual_speed_test, width=20).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(test_frame, text="🔄 Переподключиться",
                  command=self.retry_connection, width=20).pack(side=tk.LEFT, padx=5)
        
        if self.speed_test_results:
            avg_speed = self.speed_test_results.get('average_speed_mbps', 0)
            quality = self.speed_test_results.get('connection_quality', 'unknown')
            ttk.Label(test_frame, text=f"Текущая скорость: {avg_speed:.2f} Mbps ({quality})",
                     foreground="#008000").pack(side=tk.LEFT, padx=10)
        
        # Ручной выбор стратегии (доступен только если выключено автоопределение)
        manual_frame = ttk.LabelFrame(strategy_frame, text="Ручной выбор стратегии", padding=10)
        manual_frame.pack(fill=tk.X, pady=10)
        
        # Определяем состояние фрейма в зависимости от автоопределения
        frame_state = 'disabled' if self.auto_strategy else 'normal'
        
        strategy_var = tk.StringVar(value=self.config_manager.get('Settings', 'manual_strategy', 'balanced_adaptive'))
        strategies = DownloadStrategy.get_manual_strategies()
        
        for strategy_id, strategy_info in strategies.items():
            rb = ttk.Radiobutton(manual_frame, text=strategy_info['name'],
                               variable=strategy_var, value=strategy_id,
                               command=lambda s=strategy_id: self.change_manual_strategy(s))
            rb.pack(anchor=tk.W, pady=2)
            rb.config(state=frame_state)
            
            desc = strategy_info['description']
            ttk.Label(manual_frame, text=desc, font=('Arial', 8),
                     foreground="#666", wraplength=600).pack(anchor=tk.W, padx=20, pady=(0, 5))
        
        # Обновляем состояние всех виджетов в manual_frame
        for child in manual_frame.winfo_children():
            if isinstance(child, (ttk.Radiobutton, ttk.Label)):
                child.config(state=frame_state)
        
        # Дополнительные настройки
        advanced_frame = ttk.LabelFrame(frame, text="Дополнительные настройки", padding=10)
        advanced_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(advanced_frame, text="Интервал автосинхронизации (минуты):",
                 font=('Arial', 9)).pack(anchor=tk.W)
        
        auto_var = tk.StringVar(value=self.config_manager.get('Settings', 'auto_sync_interval', '0'))
        ttk.Spinbox(advanced_frame, from_=0, to=1440, width=5, textvariable=auto_var,
                   command=lambda: self.config_manager.set('Settings', 'auto_sync_interval', auto_var.get())).pack(pady=5)
        
        ttk.Label(advanced_frame, text="0 = отключено", font=('Arial', 8),
                 foreground="#666").pack(anchor=tk.W)
        
        # Кнопки
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=15)
        
        ttk.Button(btn_frame, text="💾 Сохранить настройки",
                  command=lambda: [self.config_manager.save_config(),
                                  messagebox.showinfo("Успех", "Настройки сохранены")],
                  width=20).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(btn_frame, text="🧹 Очистить конфигурацию",
                  command=self.clear_configuration, width=20).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(btn_frame, text="🏠 Вернуться в главное меню",
                  command=lambda: self.root.after(100, self.__init__, self.root), width=25).pack(side=tk.LEFT, padx=5)
        
        # Информация о сервере
        ttk.Label(frame, text=f"Сервер синхронизации: {VDS_SERVER_IP}",
                 font=('Arial', 9), foreground="#666", pady=10).pack(pady=10)
    
    def toggle_auto_strategy(self, enabled):
        """Включение/выключение автоопределения стратегии"""
        self.auto_strategy = enabled
        self.config_manager.set('Settings', 'auto_strategy', str(enabled).lower())
        self.show_settings_screen()
    
    def manual_speed_test(self):
        """Ручной тест скорости"""
        def test_thread():
            try:
                results = ConnectionManager.test_connection_with_retry()
                self.speed_test_results = results
                
                if 'error' in results:
                    messagebox.showerror("Ошибка", f"Не удалось протестировать скорость:\n{results['error']}")
                else:
                    avg_speed = results.get('average_speed_mbps', 0)
                    quality = results.get('connection_quality', 'unknown')
                    messagebox.showinfo("✅ Успех",
                                      f"Тест скорости завершен!\n"
                                      f"Средняя скорость: {avg_speed:.2f} Mbps\n"
                                      f"Качество соединения: {quality}\n"
                                      f"Стратегия будет автоматически обновлена при следующей синхронизации.")
                    
                    # Обновляем статус соединения
                    self.connection_status.set(f"🟢 Соединение стабильно: {avg_speed:.2f} Mbps ({quality})")
                    
                    # Обновляем интерфейс настроек
                    self.show_settings_screen()
            
            except Exception as e:
                messagebox.showerror("❌ Ошибка", f"Критическая ошибка теста скорости:\n{str(e)}")
        
        threading.Thread(target=test_thread, daemon=True).start()
    
    def change_manual_strategy(self, strategy_id):
        """Изменение ручной стратегии"""
        self.config_manager.set('Settings', 'manual_strategy', strategy_id)
    
    def change_mods_folder(self):
        """Изменение папки"""
        folder = filedialog.askdirectory(initialdir=self.mods_path.get() or os.path.expanduser("~"),
                                        title="Выберите новую папку для синхронизации")
        if folder:
            self.mods_path.set(folder)
            self.config_manager.set('Settings', 'mods_path', folder)
            if self.config_manager.save_config():
                messagebox.showinfo("Успех", "Папка успешно изменена")
            else:
                messagebox.showerror("Ошибка", "Не удалось сохранить настройки")
    
    def clear_configuration(self):
        """Очистка конфигурации"""
        if messagebox.askyesno("Подтверждение", "Очистить конфигурацию?\n"
                                              "При следующем запуске потребуется выбрать папку снова."):
            if self.config_manager.clear_config():
                self.mods_path.set("")
                self.root.after(100, self.__init__, self.root)
                messagebox.showinfo("Успех", "Конфигурация очищена")
            else:
                messagebox.showerror("Ошибка", "Не удалось очистить конфигурацию")
    
    def create_main_interface(self):
        """Основной интерфейс приложения"""
        for widget in self.root.winfo_children():
            widget.destroy()
        
        # Верхняя панель
        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Статус соединения
        ttk.Label(top_frame, textvariable=self.connection_status,
                 font=('Arial', 10, 'bold'),
                 foreground="#FF0000" if "недоступен" in self.connection_status.get() else "#008000").pack(side=tk.LEFT, padx=5)
        
        server_info = f"Сервер: {VDS_SERVER_IP}"
        if self.speed_test_results and 'average_speed_mbps' in self.speed_test_results:
            avg_speed = self.speed_test_results['average_speed_mbps']
            quality = self.speed_test_results['connection_quality']
            server_info += f" | Скорость: {avg_speed:.1f} Mbps ({quality})"
        
        ttk.Label(top_frame, text=server_info,
                 font=('Arial', 9, 'bold'), foreground="#0066cc").pack(side=tk.LEFT, padx=10)
        
        ttk.Button(top_frame, text="⚙️ Настройки",
                  command=self.show_settings_screen, width=10).pack(side=tk.RIGHT, padx=5)
        
        # Папка mods
        folder_frame = ttk.LabelFrame(self.root, text="Синхронизируемая папка", padding=10)
        folder_frame.pack(fill=tk.X, padx=10, pady=5)
        
        path_frame = ttk.Frame(folder_frame)
        path_frame.pack(fill=tk.X)
        
        ttk.Entry(path_frame, textvariable=self.mods_path, state='readonly', width=60).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(path_frame, text="📁 Изменить", command=self.change_mods_folder, width=10).pack(side=tk.RIGHT)
        
        # Стратегия скачивания
        strategy_frame = ttk.LabelFrame(self.root, text="Текущая стратегия скачивания", padding=10)
        strategy_frame.pack(fill=tk.X, padx=10, pady=5)
        
        strategy_info = self.get_current_strategy_info()
        strategy_name = strategy_info['name']
        strategy_desc = strategy_info['description']
        
        ttk.Label(strategy_frame, text=strategy_name,
                 font=('Arial', 10, 'bold'), foreground="#0066cc").pack(anchor=tk.W)
        
        ttk.Label(strategy_frame, text=strategy_desc,
                 font=('Arial', 9), foreground="#666", wraplength=800).pack(anchor=tk.W, pady=(2, 0))
        
        if self.auto_strategy:
            ttk.Label(strategy_frame, text="ℹ️ Стратегия определена автоматически на основе скорости соединения",
                     font=('Arial', 8), foreground="#4169E1").pack(anchor=tk.W, pady=(2, 0))
        
        # Кнопка синхронизации
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.sync_button = ttk.Button(btn_frame, text="🔄 Синхронизировать моды",
                                     command=self.start_sync, style='Accent.TButton')
        self.sync_button.pack(fill=tk.X, ipady=5)
        
        # Кнопка отмены (изначально скрыта)
        self.cancel_button = ttk.Button(btn_frame, text="🛑 Отменить синхронизацию",
                                       command=self.cancel_sync, style='Danger.TButton')
        self.cancel_button.pack(fill=tk.X, ipady=5, pady=(5, 0))
        self.cancel_button.pack_forget()  # Скрываем кнопку отмены
        
        # Прогресс бар
        progress_frame = ttk.Frame(self.root)
        progress_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.progress = ttk.Progressbar(progress_frame, mode='determinate', maximum=100)
        self.progress.pack(fill=tk.X, side=tk.LEFT, expand=True)
        
        self.progress_label = ttk.Label(progress_frame, text="0%", width=5)
        self.progress_label.pack(side=tk.RIGHT, padx=5)
        
        # Вкладки для отчетов
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Вкладка лога
        log_frame = ttk.Frame(notebook)
        notebook.add(log_frame, text="📋 Лог операций")
        
        self.log = scrolledtext.ScrolledText(log_frame, height=10, state='disabled',
                                            font=('Consolas', 9), wrap=tk.WORD)
        self.log.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Статус соединения в логе
        status_frame = ttk.Frame(log_frame)
        status_frame.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(status_frame, text="Статус соединения:", font=('Arial', 8, 'bold')).pack(side=tk.LEFT)
        ttk.Label(status_frame, textvariable=self.connection_status, font=('Arial', 8),
                 foreground="#FF0000" if "недоступен" in self.connection_status.get() else "#008000").pack(side=tk.LEFT, padx=5)
        ttk.Button(status_frame, text="🔄 Обновить статус", command=self.check_connection_status, width=15).pack(side=tk.RIGHT)
        
        # Вкладка проблемных файлов
        problems_frame = ttk.Frame(notebook)
        notebook.add(problems_frame, text="⚠️ Проблемные файлы")
        
        # Дерево для отображения проблемных файлов
        columns = ('file', 'status', 'details', 'size')
        self.problems_tree = ttk.Treeview(problems_frame, columns=columns, show='headings', selectmode='browse')
        
        self.problems_tree.heading('file', text='Файл')
        self.problems_tree.heading('status', text='Статус')
        self.problems_tree.heading('details', text='Детали')
        self.problems_tree.heading('size', text='Размер')
        
        self.problems_tree.column('file', width=250, anchor=tk.W)
        self.problems_tree.column('status', width=120, anchor=tk.CENTER)
        self.problems_tree.column('details', width=250, anchor=tk.W)
        self.problems_tree.column('size', width=80, anchor=tk.E)
        
        # Вертикальный скроллбар
        scrollbar = ttk.Scrollbar(problems_frame, orient=tk.VERTICAL, command=self.problems_tree.yview)
        self.problems_tree.configure(yscrollcommand=scrollbar.set)
        
        self.problems_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5, padx=(0, 5))
        
        # Стили для дерева
        style = ttk.Style()
        style.configure("Treeview", rowheight=25)
        style.configure("Treeview.Heading", font=('Arial', 9, 'bold'))
        style.configure('Danger.TButton', background='#ff4444', foreground='white')
        
        # Фрейм для действий над проблемными файлами
        actions_frame = ttk.Frame(problems_frame)
        actions_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(actions_frame, text="🔍 Показать в проводнике",
                  command=self.show_file_in_explorer, width=18).pack(side=tk.LEFT, padx=3)
        
        ttk.Button(actions_frame, text="❌ Удалить выбранный файл",
                  command=self.delete_selected_file, width=18).pack(side=tk.LEFT, padx=3)
        
        ttk.Button(actions_frame, text="⬇️ Скачать/Обновить",
                  command=self.download_selected_file, width=18).pack(side=tk.LEFT, padx=3)
        
        # Статистика
        stats_frame = ttk.LabelFrame(self.root, text="Статистика", padding=5)
        stats_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.stats_var = tk.StringVar(value="Ожидание синхронизации...")
        ttk.Label(stats_frame, textvariable=self.stats_var,
                 font=('Arial', 9)).pack(padx=5, pady=2)
    
    def check_connection_status(self):
        """Проверка статуса соединения"""
        self.connection_status.set("⏳ Проверка соединения...")
        
        def check_thread():
            try:
                if ConnectionManager.is_server_available(timeout=3):
                    # Если сервер доступен, выполняем полный тест скорости
                    results = ConnectionManager.test_connection_with_retry()
                    if 'error' in results:
                        self.connection_status.set("🟡 Сервер доступен, но тест скорости неудачен")
                    else:
                        avg_speed = results.get('average_speed_mbps', 0)
                        quality = results.get('connection_quality', 'unknown')
                        self.connection_status.set(f"🟢 Сервер доступен: {avg_speed:.2f} Mbps ({quality})")
                        self.speed_test_results = results
                else:
                    self.connection_status.set("🔴 Сервер недоступен")
            except Exception as e:
                self.connection_status.set(f"🔴 Ошибка проверки: {str(e)}")
        
        threading.Thread(target=check_thread, daemon=True).start()
    
    def get_current_strategy_info(self):
        """Получение информации о текущей стратегии"""
        if self.auto_strategy and self.speed_test_results and 'error' not in self.speed_test_results:
            # Автоматическое определение стратегии
            connection_quality = self.speed_test_results.get('connection_quality', 'medium')
            file_distribution = self.file_distribution or {
                'tiny_files_pct': 80,  # 80% мелких файлов как в примере
                'huge_files_pct': 1    # 1% гигантских файлов
            }
            return DownloadStrategy.get_optimal_strategy(connection_quality, file_distribution)
        else:
            # Ручная стратегия или ошибка соединения
            manual_strategy = self.config_manager.get('Settings', 'manual_strategy', 'balanced_adaptive')
            strategies = DownloadStrategy.get_manual_strategies()
            return strategies.get(manual_strategy, strategies['balanced_adaptive'])
    
    def log_message(self, message, level="info"):
        """Логирование сообщений"""
        # Проверяем, существует ли виджет лога
        if hasattr(self, 'log') and self.log.winfo_exists():
            colors = {
                "info": "#000",
                "success": "#008000",
                "warning": "#FF8C00",
                "error": "#FF0000",
                "debug": "#4169E1"
            }
            
            self.log.config(state='normal')
            self.log.insert(tk.END, message + "\n", level)
            self.log.tag_configure(level, foreground=colors.get(level, "#000"))
            self.log.see(tk.END)
            self.log.config(state='disabled')
            self.root.update()
        else:
            # Если виджет лога еще не создан, выводим в консоль
            print(f"[{level.upper()}] {message}")
    
    def update_file_progress(self, file_info, progress, downloaded, total, extra_info=None):
        """Обновление прогресса для конкретного файла"""
        if hasattr(self, 'progress') and self.progress.winfo_exists():
            self.progress['value'] = progress
            self.progress_label.config(text=f"{progress:.1f}%")
            
            if file_info and extra_info:
                filename = os.path.basename(file_info['relpath'])
                self.log_message(f"  {filename}: {progress:.1f}% ({downloaded/1024/1024:.1f}/{total/1024/1024:.1f}MB) {extra_info}", "info")
            elif file_info:
                filename = os.path.basename(file_info['relpath'])
                self.log_message(f"  {filename}: {progress:.1f}% ({downloaded/1024/1024:.1f}/{total/1024/1024:.1f}MB)", "info")
            
            self.root.update()
    
    def _is_temporary_file(self, filename, filepath):
        """Проверяет, является ли файл временным или частично загруженным"""
        # Основная проверка по расширению .filepart
        if filename.endswith('.filepart'):
            return True
        
        # Проверка по шаблонам имен
        temp_patterns = [
            r'^\.part$',
            r'^\.tmp$',
            r'^\.crdownload$',
            r'^\.part\d+$', 
            r'^\.tmp\d+$'
        ]
        
        for pattern in temp_patterns:
            if re.search(pattern, filename, re.IGNORECASE):
                return True
        
        # Проверка по времени изменения (файлы измененные менее 30 секунд назад)
        try:
            file_stat = os.stat(filepath)
            current_time = time.time()
            if current_time - file_stat.st_mtime < 30:
                # Для больших файлов (>100MB) увеличиваем время ожидания, считая их еще загружающимися
                if file_stat.st_size > 100 * 1024 * 1024:
                    return True
        except Exception:
            pass
        
        return False
    
    def clear_problems_tree(self):
        """Очистка дерева проблемных файлов"""
        for item in self.problems_tree.get_children():
            self.problems_tree.delete(item)
    
    def add_problem_file(self, file_path, status, details, problem_type, file_size=0):
        """Добавление проблемного файла в дерево и список"""
        # Группировка по имени - извлекаем основное имя файла
        file_name = os.path.basename(file_path)
        base_name = re.sub(r'[-_\.]\d+(\.\d+)*', '', file_name.split('.')[0]).lower()
        
        # Форматирование размера
        size_str = f"{file_size/1024/1024:.1f} MB" if file_size > 1024*1024 else f"{file_size/1024:.1f} KB" if file_size > 1024 else f"{file_size} B"
        
        # Добавляем в дерево
        item_id = self.problems_tree.insert('', tk.END, values=(file_path, status, details, size_str))
        
        # Цвета в зависимости от статуса
        color_map = {
            'Отсутствует на сервере': '#FF6B6B',
            'Хеш не совпадает': '#FFA500', 
            'Отсутствует на клиенте': '#4ECDC4'
        }
        
        if status in color_map:
            self.problems_tree.tag_configure(status, background=color_map[status])
            self.problems_tree.item(item_id, tags=(status,))
    
    def get_server_hashes(self):
        """Получение хешей файлов с сервера с автопереподключением"""
        try:
            url = f"{VDS_SERVER_IP}/hashes.json"
            self.log_message(f"🔍 Получение списка файлов с сервера: {url}")
            
            response = ConnectionManager.make_request_with_retry(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            return data['files'], data.get('file_count', 0), data.get('total_size', 0)
        except Exception as e:
            self.log_message(f"❌ Ошибка подключения к серверу: {str(e)}", "error")
            raise
    
    def calculate_file_hash(self, filepath):
        """Вычисление MD5 хеша файла"""
        hash_md5 = hashlib.md5()
        try:
            with open(filepath, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            self.log_message(f"⚠️ Ошибка хеширования {filepath}: {str(e)}", "warning")
            return None
    
    def sync_mods(self):
        """Основной процесс синхронизации с автопереподключением"""
        try:
            self.clear_problems_tree()
            self.log_message("🚀 Начало синхронизации модов...", "info")
            
            # Проверяем соединение перед синхронизацией
            if not ConnectionManager.is_server_available(timeout=5):
                raise ConnectionError("Сервер недоступен. Проверьте соединение и попробуйте снова.")
            
            # Получение текущей стратегии
            current_strategy = self.get_current_strategy_info()
            self.log_message(f"🎯 Используется стратегия: {current_strategy['name']}", "info")
            self.log_message(f"📝 {current_strategy['description']}", "info")
            
            # Создание менеджера загрузки
            self.download_manager = DownloadManager(current_strategy)
            self.download_manager.set_progress_callback(self.update_file_progress)
            self.download_manager.set_error_callback(self.log_message)
            
            # Если есть результаты теста скорости, передаем их менеджеру
            if self.speed_test_results and 'error' not in self.speed_test_results:
                self.download_manager.speed_stats = self.speed_test_results
            
            # Получение данных с сервера
            server_files, total_files_count, total_size_bytes = self.get_server_hashes()
            local_path = self.mods_path.get()
            
            if not local_path:
                raise ValueError("Не выбрана папка для синхронизации")
            
            if not os.path.exists(local_path):
                self.log_message(f"📁 Создание папки: {local_path}", "info")
                os.makedirs(local_path, exist_ok=True)
            
            # Сбор локальных файлов с игнорированием временных файлов
            local_files = {}
            skipped_temp_files = 0
            
            for root, _, files in os.walk(local_path):
                for file in files:
                    # Игнорирование временных файлов
                    if file.endswith('.filepart') or file.startswith('.'):
                        skipped_temp_files += 1
                        continue
                    
                    filepath = os.path.join(root, file)
                    relpath = os.path.relpath(filepath, local_path).replace('\\', '/')
                    
                    # Дополнительная проверка на временные файлы
                    if self._is_temporary_file(file, filepath):
                        skipped_temp_files += 1
                        continue
                    
                    try:
                        file_size = os.path.getsize(filepath)
                        file_mtime = os.path.getmtime(filepath)
                        
                        local_files[relpath] = {
                            'path': filepath,
                            'size': file_size,
                            'mtime': file_mtime
                        }
                    except Exception as e:
                        self.log_message(f"⚠️ Ошибка обработки файла {filepath}: {str(e)}", "warning")
            
            if skipped_temp_files > 0:
                self.log_message(f"⏳ Пропущено временных файлов: {skipped_temp_files}", "info")
                self.log_message("ℹ️ Файлы .filepart (временные файлы WinSCP) будут обработаны после завершения передачи", "info")
            
            # Анализ проблемных файлов
            problem_files = {
                'missing_on_server': [],    # Есть локально, нет на сервере
                'hash_mismatch': [],        # Хеш не совпадает
                'missing_on_client': []     # Есть на сервере, нет локально
            }
            
            missing_file_count = 0
            corrupt_file_count = 0
            new_file_count = 0
            
            # Проверка локальных файлов на сервере (исключая временные)
            for relpath, file_info in local_files.items():
                if relpath not in server_files:
                    missing_file_count += 1
                    self.add_problem_file(relpath, "Отсутствует на сервере", 
                                        f"Файл размером {file_info['size']/1024/1024:.2f} MB существует локально, но отсутствует на сервере",
                                        'missing_on_server', file_info['size'])
                    problem_files['missing_on_server'].append(file_info)
                else:
                    # Проверка целостности файла (хеша)
                    local_hash = self.calculate_file_hash(file_info['path'])
                    server_hash = server_files[relpath].get('hash')
                    
                    if local_hash != server_hash:
                        corrupt_file_count += 1
                        self.add_problem_file(relpath, "Хеш не совпадает", 
                                            f"Локальный: {local_hash[:8]}... Серверный: {server_hash[:8]}...",
                                            'hash_mismatch', file_info['size'])
                        problem_files['hash_mismatch'].append({
                            'relpath': relpath,
                            'local_path': file_info['path'],
                            'size': file_info['size'],
                            'server_hash': server_hash
                        })
            
            # Проверка файлов на сервере локально
            for relpath, server_info in server_files.items():
                local_path_full = os.path.join(local_path, relpath)
                
                if relpath not in local_files:
                    new_file_count += 1
                    self.add_problem_file(relpath, "Отсутствует на клиенте",
                                        f"Файл размером {server_info['size']/1024/1024:.2f} MB существует на сервере, но отсутствует локально",
                                        'missing_on_client', server_info['size'])
                    problem_files['missing_on_client'].append({
                        'relpath': relpath,
                        'local_path': local_path_full,
                        'size': server_info['size'],
                        'hash': server_info['hash']
                    })
            
            # Сбор статистики
            total_problems = missing_file_count + corrupt_file_count + new_file_count
            
            # Обновление статистики в интерфейсе
            self.stats_var.set(f"Обнаружено проблемных файлов: {total_problems}\n"
                             f"Отсутствует на сервере: {missing_file_count}\n"
                             f"Хеш не совпадает: {corrupt_file_count}\n"
                             f"Отсутствует на клиенте: {new_file_count}")
            
            if total_problems > 0:
                self.log_message(f"⚠️ Обнаружено {total_problems} проблемных файлов", "warning")
            else:
                self.log_message("✅ Все файлы в актуальном состоянии!", "success")
            
            # Анализ распределения файлов для оптимизации стратегии
            tiny_count = sum(1 for f in server_files.values() if f.get('size', 0) < 100 * 1024)  # <100KB
            huge_count = sum(1 for f in server_files.values() if f.get('size', 0) >= 10 * 1024 * 1024)  # >10MB
            
            self.file_distribution = {
                'tiny_files_pct': (tiny_count / total_files_count * 100) if total_files_count > 0 else 0,
                'huge_files_pct': (huge_count / total_files_count * 100) if total_files_count > 0 else 0,
                'total_files': total_files_count,
                'total_size_mb': total_size_bytes / 1024 / 1024
            }
            
            self.log_message(f"📈 Распределение файлов: {tiny_count} мелких (<100KB), {huge_count} гигантских (>10MB)", "info")
            
            # Удаление файлов, отсутствующих на сервере
            self.log_message(f"🗑️ Удаление {missing_file_count} файлов, отсутствующих на сервере...", "info")
            
            for file_info in problem_files['missing_on_server']:
                try:
                    if os.path.exists(file_info['path']):
                        os.remove(file_info['path'])
                        self.log_message(f"✅ Удален: {os.path.basename(file_info['path'])}", "info")
                except Exception as e:
                    self.log_message(f"❌ Ошибка удаления {file_info['path']}: {str(e)}", "error")
            
            # Скачивание недостающих и поврежденных файлов
            files_to_download = []
            
            # Добавляем новые файлы с сервера
            for file_info in problem_files['missing_on_client']:
                files_to_download.append(file_info)
            
            # Добавляем файлы с несовпадающими хешами
            for file_info in problem_files['hash_mismatch']:
                files_to_download.append({
                    'relpath': file_info['relpath'],
                    'local_path': file_info['local_path'],
                    'size': file_info['size'],
                    'hash': file_info['server_hash']
                })
            
            if files_to_download:
                self.log_message(f"⬇️ Начало скачивания {len(files_to_download)} файлов...", "info")
                download_result = self.download_manager.download_files(files_to_download, self.file_distribution)
                success_count = sum(1 for r in download_result['results'].values() if r)
                
                self.log_message(f"✅ Успешно обработано: {success_count}/{len(files_to_download)} файлов", "success")
                
                if download_result.get('cancelled'):
                    self.log_message("🛑 Синхронизация отменена пользователем", "warning")
                    return
            
            # Финальная статистика
            self.log_message(f"\n🎉 Синхронизация успешно завершена!", "success")
            messagebox.showinfo("✅ Успех", f"Синхронизация завершена!\n"
                                          f"Обработано файлов: {total_files_count}\n"
                                          f"Общий размер: {total_size_bytes/1024/1024:.1f} MB")
        
        except ConnectionError as e:
            self.log_message(f"🌐 Ошибка соединения: {str(e)}", "error")
            messagebox.showwarning("⚠️ Соединение прервано",
                                  "Соединение с сервером было прервано.\n"
                                  "Попробуйте переподключиться или запустить синхронизацию позже.")
        except Exception as e:
            self.log_message(f"🔥 Критическая ошибка: {str(e)}", "error")
            messagebox.showerror("❌ Ошибка", f"Синхронизация прервана:\n{str(e)}")
        finally:
            self.running = False
            self.sync_button.config(state='normal')
            self.cancel_button.pack_forget()
            self.progress['value'] = 0
            self.progress_label.config(text="0%")
    
    def start_sync(self):
        """Запуск синхронизации"""
        if self.running:
            return
        
        if self.connection_status.get().startswith("🔴"):
            if not messagebox.askyesno("⚠️ Сервер недоступен",
                                     "Сервер недоступен. Вы все равно хотите начать синхронизацию?\n"
                                     "Процесс может завершиться с ошибкой."):
                return
        
        mods_path = self.mods_path.get().strip()
        if not mods_path:
            messagebox.showerror("❌ Ошибка", "Папка для синхронизации не выбрана")
            return
        
        if not os.path.exists(mods_path):
            if not messagebox.askyesno("⚠️ Папка не существует",
                                      f"Папка {mods_path} не существует. Создать её?"):
                return
            try:
                os.makedirs(mods_path)
            except Exception as e:
                messagebox.showerror("❌ Ошибка", f"Не удалось создать папку:\n{str(e)}")
                return
        
        self.running = True
        self.sync_button.config(state='disabled')
        self.cancel_button.pack(fill=tk.X, ipady=5, pady=(5, 0))
        self.progress['value'] = 0
        self.progress_label.config(text="0%")
        
        # Очистка лога перед новой синхронизацией
        self.log.config(state='normal')
        self.log.delete(1.0, tk.END)
        self.log.config(state='disabled')
        
        threading.Thread(target=self.sync_mods, daemon=True).start()
    
    def cancel_sync(self):
        """Отмена текущей синхронизации"""
        if self.running and self.download_manager:
            self.log_message("🛑 Запрошена отмена синхронизации...", "warning")
            self.download_manager.cancel_download()
    
    def show_file_in_explorer(self):
        """Показать файл в проводнике"""
        selected = self.problems_tree.selection()
        if not selected:
            messagebox.showinfo("ℹ️ Информация", "Выберите файл для отображения")
            return
        
        item = self.problems_tree.item(selected[0])
        file_path = item['values'][0]
        full_path = os.path.join(self.mods_path.get(), file_path)
        
        if os.path.exists(full_path):
            os.startfile(os.path.dirname(full_path))
        else:
            messagebox.showwarning("⚠️ Файл не найден", f"Файл не существует:\n{full_path}")
    
    def delete_selected_file(self):
        """Удалить выбранный файл"""
        selected = self.problems_tree.selection()
        if not selected:
            messagebox.showinfo("ℹ️ Информация", "Выберите файл для удаления")
            return
        
        item = self.problems_tree.item(selected[0])
        file_path = item['values'][0]
        full_path = os.path.join(self.mods_path.get(), file_path)
        
        if not os.path.exists(full_path):
            messagebox.showwarning("⚠️ Файл не найден", f"Файл уже удален или не существует:\n{full_path}")
            return
        
        if messagebox.askyesno("❓ Подтверждение", f"Удалить файл?\n{file_path}"):
            try:
                os.remove(full_path)
                self.problems_tree.delete(selected[0])
                self.log_message(f"🗑️ Удален файл: {file_path}", "success")
                messagebox.showinfo("✅ Успех", "Файл успешно удален")
            except Exception as e:
                messagebox.showerror("❌ Ошибка", f"Не удалось удалить файл:\n{str(e)}")
    
    def download_selected_file(self):
        """Скачать/обновить выбранный файл"""
        selected = self.problems_tree.selection()
        if not selected:
            messagebox.showinfo("ℹ️ Информация", "Выберите файл для скачивания/обновления")
            return
        
        item = self.problems_tree.item(selected[0])
        file_path = item['values'][0]
        full_path = os.path.join(self.mods_path.get(), file_path)
        
        try:
            # Проверяем соединение
            if not ConnectionManager.is_server_available(timeout=3):
                raise ConnectionError("Сервер недоступен")
            
            # Создаем директории если их нет
            dir_path = os.path.dirname(full_path)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
            
            # Скачиваем файл
            file_url = f"{VDS_SERVER_IP}/{file_path}"
            self.log_message(f"⬇️ Скачивание: {file_path}", "info")
            
            # Используем текущий метод скачивания
            current_strategy = self.get_current_strategy_info()
            temp_manager = DownloadManager(current_strategy)
            temp_manager.set_progress_callback(self.update_file_progress)
            temp_manager.set_error_callback(self.log_message)
            
            file_info = {
                'relpath': file_path,
                'local_path': full_path,
                'size': 0  # Размер неизвестен для отдельного файла
            }
            
            success = temp_manager._download_file_with_retry(file_url, full_path, file_info, 32768, 30)
            
            if success:
                self.log_message(f"✅ {file_path} успешно скачан/обновлен", "success")
                messagebox.showinfo("✅ Успех", "Файл успешно скачан/обновлен")
                
                # Обновляем статус в дереве
                self.problems_tree.delete(selected[0])
            else:
                raise Exception("Ошибка при скачивании файла")
        
        except ConnectionError as e:
            messagebox.showerror("🌐 Ошибка соединения", f"Сервер недоступен:\n{str(e)}")
        except Exception as e:
            self.log_message(f"❌ Ошибка скачивания {file_path}: {str(e)}", "error")
            messagebox.showerror("❌ Ошибка", f"Не удалось скачать файл:\n{str(e)}")
