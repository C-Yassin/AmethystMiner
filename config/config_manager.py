import os
import json
from PyQt6.QtCore import QStandardPaths

is_flatpak_env = 'FLATPAK_ID' in os.environ or os.path.exists('/.flatpak-info')
base_config = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericConfigLocation)

CONFIG_DIR = os.path.join(base_config, "amethyst_miner")
os.makedirs(CONFIG_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")
MINER_DIR = "/app/bin" if is_flatpak_env else os.path.join(CONFIG_DIR, "bin")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUI_DIR = os.path.join(BASE_DIR, "gui")
CORE_DIR = os.path.join(BASE_DIR, "core")
app_id = "io.github.C_Yassin.AmethystMiner"

def get_icon_path(name):
    return os.path.join(GUI_DIR, name)

def load_config():
    defaults = {
        "worker_name": "LinuxRig-01",
        "wallet": "",
        "pool": "pool.supportxmr.com:3333",
        "threads": max(1, os.cpu_count() - 1) if os.cpu_count() else 1,
        "priority": 2,
        "idle_enabled": False,
        "enable_msr": False,
        "idle_minutes": 5,
        "schedule_enabled": False,
        "schedule_start": "22:00",
        "schedule_stop": "08:00",
        "autostart_enabled": True,
        "already_seen_message": True
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                defaults.update(json.load(f))
        except Exception:
            pass
    return defaults

def save_config(data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)
