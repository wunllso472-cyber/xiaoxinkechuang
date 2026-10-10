import os
import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.environ.get("XX_CONFIG", os.path.join(BASE_DIR, "config.yaml"))


def _load():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if os.environ.get("XX_DATABASE_URL"):
        cfg.setdefault("database", {})["url"] = os.environ["XX_DATABASE_URL"]
    if os.environ.get("XX_DB_SCHEMA"):
        cfg.setdefault("database", {})["schema"] = os.environ["XX_DB_SCHEMA"]
    if os.environ.get("XX_SECRET_KEY"):
        cfg.setdefault("server", {})["secret_key"] = os.environ["XX_SECRET_KEY"]
    if os.environ.get("XX_LLM_API_KEY"):
        for m in cfg.get("llm", {}).get("default_models", []):
            if m.get("provider") == "deepseek":
                m["api_key"] = os.environ["XX_LLM_API_KEY"]
    return cfg


settings = _load()


def get(path, default=None):
    """按 'a.b.c' 读取配置"""
    cur = settings
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def upload_dir(sub=""):
    d = get("server.upload_dir", "./data/uploads")
    if not os.path.isabs(d):
        d = os.path.join(BASE_DIR, d)
    d = os.path.join(d, sub) if sub else d
    os.makedirs(d, exist_ok=True)
    return d
