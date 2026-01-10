#!/usr/bin/env python3
"""
Minecraft Mod Sync Client
GUI-клиент для синхронизации модов с сервером
"""

import tkinter as tk
from tkinter import ttk
import sys
import os

# Добавляем путь к shared для импортов
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from modsync.client.ui.main_window import ModSyncApp


def main():
    """Точка входа в клиентское приложение"""
    root = tk.Tk()
    
    # Настройка стилей
    style = ttk.Style()
    style.configure('Accent.TButton', font=('Arial', 10, 'bold'))
    style.configure('Danger.TButton', background='#ff4444', foreground='white')
    
    app = ModSyncApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()