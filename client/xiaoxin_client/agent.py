"""后台代理：按服务端下发的配置周期执行 配件采集/负载心跳/运行数据采集/消息拉取/版本检查/双系统监测"""
import json
import logging
import os
import platform
import threading
import time

from . import api, collector, sysinfo
from .config import cfg, DATA_DIR, VERSION, IS_WIN

log = logging.getLogger("agent")
HW_CACHE = os.path.join(DATA_DIR, "hw_cache.json")

DEFAULT_INTERVALS = {"hardware_collect": 3600, "load_collect": 300, "run_data_collect": 1800, "message_poll": 120}


class Agent:
    def __init__(self, on_messages=None, on_hw_change=None, on_status=None, on_update=None):
        self.on_messages = on_messages
        self.on_hw_change = on_hw_change
        self.on_status = on_status
        self.on_update = on_update
        self.server_cfg = {}
        self.last = {}
        self.hardware = {}
        self.online = False
        self.is_xinchuang = None
        self._stop = False
        self._first_run = True

    def interval(self, key):
        c = self.server_cfg.get(key)
        try:
            return max(int(float(c["value"])), 30) if c and c.get("trigger") == "interval" else DEFAULT_INTERVALS[key]
        except (ValueError, KeyError):
            return DEFAULT_INTERVALS[key]

    def _status(self, text):
        if self.on_status:
            self.on_status(text)

    def report_hardware(self):
        hw = sysinfo.collect_hardware()
        self.hardware = hw
        # 本地对比历史配件信息
        old = {}
        if os.path.exists(HW_CACHE):
            try:
                old = json.load(open(HW_CACHE, encoding="utf-8"))
            except ValueError:
                pass
        local_changes = sysinfo.diff_hardware(old, hw) if old else []
        json.dump(hw, open(HW_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
        body = {"device_id": cfg["device_id"], "hostname": hw.get("hostname"), "ip": hw.get("ip"),
                "user_name": cfg.get("user_name") or os.environ.get("USER") or os.environ.get("USERNAME", ""),
                "dept": cfg.get("dept", ""), "client_version": VERSION, "is_cloud_desktop": cfg.get("is_cloud_desktop", False),
                "cloud_server": cfg.get("cloud_server", ""), "hardware": hw, "load": sysinfo.collect_load(),
                "boot_time": __import__("psutil").boot_time()}
        r = api.post("/api/client/report", body)
        self.server_cfg = r.get("config", {})
        self.is_xinchuang = r.get("is_xinchuang")
        changes = r.get("changes") or [{"component": c[0], "old": c[1], "new": c[2]} for c in local_changes]
        if changes and self.on_hw_change:
            self.on_hw_change(changes)
        return r

    def heartbeat(self):
        r = api.post("/api/client/heartbeat", {"device_id": cfg["device_id"], "load": sysinfo.collect_load(),
                                               "minutes": self.interval("load_collect") // 60})
        if r.get("need_report"):
            self.report_hardware()

    def run_data(self):
        recs = collector.collect(first=self._first_run)
        if recs:
            api.post("/api/client/run-records", {"device_id": cfg["device_id"], "records": recs}, timeout=60)

    def poll_messages(self):
        msgs = api.get("/api/client/messages", {"device_id": cfg["device_id"]})
        if msgs and self.on_messages:
            self.on_messages(msgs)

    def check_version(self):
        r = api.get("/api/client/version", {"platform": "windows" if IS_WIN else "linux", "current": VERSION,
                                            "arch": platform.machine().lower()})
        if r.get("update") and self.on_update:
            self.on_update(r)

    def _due(self, key, interval):
        return time.time() - self.last.get(key, 0) >= interval

    def loop(self):
        while not self._stop:
            try:
                if self._first_run or self._due("hardware", self.interval("hardware_collect")):
                    self.report_hardware()  # 含双系统监测（客户端启动时执行）
                    self.last["hardware"] = self.last["load"] = time.time()
                    if self._first_run:
                        self.check_version()
                if self._due("load", self.interval("load_collect")):
                    self.heartbeat()
                    self.last["load"] = time.time()
                if self._first_run or self._due("run", self.interval("run_data_collect")):
                    self.run_data()
                    self.last["run"] = time.time()
                if self._due("msg", self.interval("message_poll")):
                    self.poll_messages()
                    self.last["msg"] = time.time()
                self._first_run = False
                if not self.online:
                    self.online = True
                    self._status("已连接服务器")
            except api.ApiError as e:
                self.online = False
                self._status("离线：%s" % e)
                time.sleep(30)
            except Exception as e:  # noqa
                log.exception("agent error")
                self._status("采集异常：%s" % e)
            time.sleep(10)

    def start(self):
        threading.Thread(target=self.loop, daemon=True, name="xx-agent").start()

    def stop(self):
        self._stop = True
        try:
            api.post("/api/client/run-records", {"device_id": cfg["device_id"], "records": [
                {"kind": "shutdown", "content": {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "by": "客户端退出"}}]}, timeout=3)
        except api.ApiError:
            pass
