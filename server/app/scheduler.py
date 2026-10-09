"""后台定时任务：定时消息发送、会话超时销毁、离线检测与预警"""
import logging
import threading
import time

from .db import SessionLocal
from .services import monitor

log = logging.getLogger("scheduler")


def _loop():
    from .api.message import send_due_messages
    from .api.llm import expire_sessions
    tick = 0
    while True:
        try:
            send_due_messages()
            if tick % 5 == 0:
                expire_sessions()
                db = SessionLocal()
                try:
                    monitor.check_offline(db)
                finally:
                    db.close()
        except Exception as e:  # noqa
            log.exception("定时任务异常: %s", e)
        tick += 1
        time.sleep(30)


def start():
    threading.Thread(target=_loop, daemon=True, name="xx-scheduler").start()
