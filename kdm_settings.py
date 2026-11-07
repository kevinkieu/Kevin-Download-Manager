"""
KDM - Kevin Download Manager
Settings Manager: Load, Save, and Apply User Preferences
"""

import os
import sys
import json
import winsound
from typing import Dict, Any

if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")

DEFAULT_SETTINGS: Dict[str, Any] = {
    "save_dir": os.path.join(os.path.expanduser("~"), "Downloads", "KDM"),
    "auto_subfolders": True,
    "default_connections": 16,
    "close_action": "tray",  # "tray" or "exit"
    "play_sound": True,
    "start_with_windows": False,
    # 1. Hàng đợi & Lập lịch
    "max_active_tasks": 2,           # Số file tải cùng lúc
    "shutdown_when_done": False,     # Tự động tắt máy khi xong
    "scheduler_enabled": False,      # Hẹn giờ tải
    "schedule_start_time": "02:00",  # Giờ bắt đầu
    "schedule_stop_time": "06:00",   # Giờ kết thúc
    # 2. Giới hạn tốc độ
    "speed_limit_enabled": False,    # Bật/Tắt giới hạn tốc độ
    "speed_limit_kbps": 2048,        # Tốc độ tối đa (KB/s)
    # 3. Bắt link Clipboard
    "clipboard_monitor": True,       # Tự động bắt link khi Ctrl+C
    # 6. Proxy & Xác thực
    "proxy_enabled": False,          # Bật Proxy
    "proxy_host": "",
    "proxy_port": 8080,
    "proxy_user": "",
    "proxy_pass": "",
    "auth_user": "",                 # HTTP Basic Auth Username
    "auth_pass": "",                 # HTTP Basic Auth Password
    # 7. Danh sách đuôi tệp tự động bắt link (File Types - Chuẩn IDM)
    "intercept_extensions": (
        "3GP 7Z AAC ACE AIF APK ARJ ASF AVI BIN BZ2 DMG DOC DOCX EPUB EXE "
        "FLAC FLV GZ GZIP IMG ISO LZH M4A M4V MKV MOV MP3 MP4 MPA MPE MPEG "
        "MPG MSI MSU OGG OGV PDF PKG PLJ PPS PPT PPTX QT RA RAR RM RMVB "
        "SEA SIT SITX TAR TIF TIFF TORRENT TS VOB WAV WEBM WMA WMV Z ZIP"
    )
}


class KDMSettings:
    def __init__(self):
        self.data: Dict[str, Any] = DEFAULT_SETTINGS.copy()
        self.load()

    def load(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self.data.update(saved)
            except Exception as e:
                print(f"Error loading settings: {e}")
        # Ensure download directory exists
        os.makedirs(self.get("save_dir"), exist_ok=True)

    def save(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default if default is not None else DEFAULT_SETTINGS.get(key))

    def set(self, key: str, value: Any):
        self.data[key] = value
        self.save()

    def play_complete_sound(self):
        if self.get("play_sound", True):
            try:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass

    def is_startup_enabled(self) -> bool:
        import winreg
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_READ
            )
            val, _ = winreg.QueryValueEx(key, "KevinDownloadManager")
            winreg.CloseKey(key)
            return bool(val)
        except Exception:
            return False

    def apply_startup(self, enable: bool):
        import winreg
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE | winreg.KEY_READ
            )
            if enable:
                if getattr(sys, 'frozen', False):
                    target_cmd = f'"{os.path.abspath(sys.executable)}" --tray'
                else:
                    app_dir = os.path.dirname(os.path.abspath(__file__))
                    run_bat = os.path.join(app_dir, "run_kdm.bat")
                    target_cmd = f'"{run_bat}" --tray'

                winreg.SetValueEx(key, "KevinDownloadManager", 0, winreg.REG_SZ, target_cmd)
            else:
                try:
                    winreg.DeleteValue(key, "KevinDownloadManager")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            print(f"Startup registry error: {e}")

        # Clean up legacy startup bat if it exists
        try:
            startup_dir = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
            bat_file = os.path.join(startup_dir, "KDM_AutoStart.bat")
            if os.path.exists(bat_file):
                os.remove(bat_file)
        except Exception:
            pass
