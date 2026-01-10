import tkinter as tk
from tkinter import ttk
import urllib3
from requests.exceptions import RequestException, ConnectionError, Timeout
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

VDS_SERVER_IP = "http://147.45.184.36:8000"  # ЗАМЕНИТЕ НА ВАШ РЕАЛЬНЫЙ IP И ПОРТ
CONFIG_FILE = "modsync_config.ini"
def main():
    root = tk.Tk()
    
    # Настройка стилей
    style = ttk.Style()
    style.configure('Accent.TButton', font=('Arial', 10, 'bold'))
    style.configure('Danger.TButton', background='#ff4444', foreground='white')
    
    app = ModSyncApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()