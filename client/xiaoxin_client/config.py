import json
import os
import platform
import sys
import uuid

APP_NAME = "小信助手"
VERSION = "1.0.0"
IS_WIN = platform.system() == "Windows"

if os.environ.get("XX_DATA_DIR"):
    DATA_DIR = os.environ["XX_DATA_DIR"]
elif IS_WIN:
    DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "XiaoxinAssistant")
else:
    DATA_DIR = os.path.join(os.path.expanduser("~"), ".xiaoxin")
os.makedirs(DATA_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

DEFAULTS = {
    "server": "http://127.0.0.1:8000",
    "client_key": "",
    "user_name": "",
    "dept": "",
    "is_cloud_desktop": False,
    "cloud_server": "",
    "floating": True,
    "device_id": "",
}


def _machine_id():
    for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(p) as f:
                v = f.read().strip()
                if v:
                    return v
        except OSError:
            pass
    if IS_WIN:
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                               winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
            return winreg.QueryValueEx(k, "MachineGuid")[0]
        except OSError:
            pass
    return uuid.uuid4().hex


def load():
    cfg = dict(DEFAULTS)
    # 安装目录下的 config.json 作为默认值（便于批量部署时预置服务器地址）
    install_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for p in (os.path.join(install_dir, "config.json"), CONFIG_FILE):
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    cfg.update(json.load(f))
            except (OSError, ValueError):
                pass
    if os.environ.get("XX_SERVER"):
        cfg["server"] = os.environ["XX_SERVER"]
    if not cfg.get("device_id"):
        cfg["device_id"] = _machine_id()
        save(cfg)
    return cfg


def save(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


cfg = load()
