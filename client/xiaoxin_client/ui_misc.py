"""设备监测 / 消息中心 / 软件中心 / 设置"""
import os
import subprocess
import tempfile
import tkinter as tk
from tkinter import ttk, messagebox

from . import api, sysinfo, config
from .cleaner import fmt_size
from .config import cfg, IS_WIN, VERSION
from .ui_common import bg, tree_with_scroll, scale, FONT_B, BG, SEP, TEXT, GREEN, RED


class DeviceFrame(ttk.Frame):
    """探针监测：本机配件信息、更换状态提醒、合规/预警"""

    def __init__(self, parent, agent):
        super().__init__(parent, padding=10)
        self.agent = agent
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        ttk.Button(bar, text="重新采集并上报", style="Accent.TButton", command=self.collect).pack(side="left")
        self.badge = ttk.Label(bar, text="", font=FONT_B)
        self.badge.pack(side="left", padx=12)
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, pady=12)
        f1, self.hw = tree_with_scroll(nb, ("k", "v"), ("配件", "参数"), [160, 560], height=14)
        nb.add(f1, text="配件信息")
        f2, self.changes = tree_with_scroll(nb, ("c", "o", "n", "t"), ("配件", "原配件", "新配件", "发现时间"), [120, 220, 220, 150])
        nb.add(f2, text="配件更换记录")
        f3, self.alerts = tree_with_scroll(nb, ("r", "l", "c", "t"), ("预警规则", "级别", "内容", "时间"), [120, 50, 420, 150])
        nb.add(f3, text="违规/异常预警")
        self.load()

    def collect(self):
        bg(self.agent.report_hardware, done=lambda r: (self.load(), messagebox.showinfo("采集完成", "配件信息已上报%s" % (
            "，检测到 %d 项配件变更" % len(r["changes"]) if r.get("changes") else ""))))

    def load(self):
        hw = self.agent.hardware or sysinfo.collect_hardware()
        self.hw.delete(*self.hw.get_children())
        for k, label in sysinfo.HW_LABELS.items():
            self.hw.insert("", "end", values=(label, hw.get(k, "")))
        self.hw.insert("", "end", values=("双系统检测", "检测到双系统（违规）" if hw.get("dual_system") else "正常"))
        bg(lambda: api.get("/api/client/status", {"device_id": cfg["device_id"]}), done=self._status, error=lambda e: None)

    def _status(self, s):
        t = s["terminal"]
        self.badge.config(text=("✔ 信创终端" if t["is_xinchuang"] else "非信创终端") + ("　⚠ 违规双系统" if t["dual_system"] else ""),
                          foreground=GREEN if t["is_xinchuang"] and not t["dual_system"] else RED)
        self.changes.delete(*self.changes.get_children())
        for c in s["changes"]:
            self.changes.insert("", "end", values=(c["component"], c["old_value"], c["new_value"], c["created_at"]))
        self.alerts.delete(*self.alerts.get_children())
        for a in s["alerts"]:
            self.alerts.insert("", "end", values=(a["rule_name"], a["level"], a["content"], a["created_at"]))


class MessageFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=10)
        ttk.Button(self, text="刷新", command=self.load).pack(anchor="w")
        f, self.tv = tree_with_scroll(self, ("t", "time", "r"), ("消息", "发送时间", "状态"), [400, 150, 60])
        f.pack(fill="both", expand=True, pady=12)
        self.tv.bind("<<TreeviewSelect>>", self.show)
        box = tk.Frame(self, bg=SEP, padx=1, pady=1)
        box.pack(fill="x")
        self.body = tk.Text(box, height=8, wrap="word", bg=BG, fg=TEXT, relief="flat", bd=0, highlightthickness=0, padx=14, pady=12)
        self.body.pack(fill="x")
        self.msgs = {}
        self.load()

    def load(self):
        bg(lambda: api.get("/api/client/messages", {"device_id": cfg["device_id"], "all": 1}), done=self._loaded, error=lambda e: None)

    def _loaded(self, msgs):
        self.tv.delete(*self.tv.get_children())
        self.msgs = {str(m["id"]): m for m in msgs}
        for m in msgs:
            self.tv.insert("", "end", iid=str(m["id"]), values=(m["title"], m["sent_at"], "已读" if m["read"] else "未读"))

    def show(self, e=None):
        sel = self.tv.selection()
        if not sel:
            return
        m = self.msgs[sel[0]]
        self.body.delete("1.0", "end")
        self.body.insert("end", m["title"] + "\n\n" + m["content"])
        if not m["read"]:
            bg(lambda: api.post("/api/client/messages/%s/read" % m["id"], {"device_id": cfg["device_id"]}), error=lambda e: None)
            m["read"] = True
            self.tv.set(sel[0], "r", "已读")


class SoftwareFrame(ttk.Frame):
    """装机软件中心：管理员发布的常用软件安装包"""

    def __init__(self, parent):
        super().__init__(parent, padding=10)
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        ttk.Button(bar, text="刷新", command=self.load).pack(side="left")
        ttk.Button(bar, text="下载并安装", style="Accent.TButton", command=self.install).pack(side="left", padx=8)
        f, self.tv = tree_with_scroll(self, ("n", "v", "c", "s", "d"), ("软件", "版本", "分类", "大小", "说明"), [160, 80, 80, 80, 360])
        f.pack(fill="both", expand=True, pady=12)
        self.items = {}
        self.load()

    def load(self):
        bg(lambda: api.get("/api/client/software", {"platform": "windows" if IS_WIN else "linux"}), done=self._loaded, error=lambda e: None)

    def _loaded(self, rows):
        self.tv.delete(*self.tv.get_children())
        self.items = {str(r["id"]): r for r in rows}
        for r in rows:
            self.tv.insert("", "end", iid=str(r["id"]), values=(r["name"], r["version"], r["category"], fmt_size(r["size"]), r["description"]))

    def install(self):
        sel = self.tv.selection()
        if not sel:
            return
        s = self.items[sel[0]]
        if not s["url"]:
            return messagebox.showinfo("提示", "该软件暂无安装包")
        ext = os.path.splitext(s["file_path"])[1]
        dest = os.path.join(tempfile.gettempdir(), "%s-%s%s" % (s["name"], s["version"], ext))

        def done(path):
            if IS_WIN:
                os.startfile(path)  # noqa
            elif path.endswith(".deb"):
                subprocess.Popen(["pkexec", "apt-get", "install", "-y", path])
            else:
                subprocess.Popen(["xdg-open", path])
        bg(api.download, s["url"], dest, done=done)


class SettingsFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=10)
        k = scale(self)
        self.vars = {}
        rows = [("server", "服务器地址"), ("client_key", "客户端接入密钥"), ("user_name", "使用人"), ("dept", "部门"),
                ("cloud_server", "云桌面服务端名称")]
        for i, (key, label) in enumerate(rows):
            ttk.Label(self, text=label, style="Muted.TLabel").grid(row=i, column=0, sticky="w", pady=int(7 * k), padx=(0, int(16 * k)))
            v = tk.StringVar(value=cfg.get(key, ""))
            ttk.Entry(self, textvariable=v, width=48).grid(row=i, column=1, sticky="w", pady=int(5 * k))
            self.vars[key] = v
        self.cloud = tk.BooleanVar(value=cfg.get("is_cloud_desktop", False))
        ttk.Checkbutton(self, text="本机为云桌面用户端", variable=self.cloud).grid(row=len(rows), column=1, sticky="w", pady=(int(10 * k), 0))
        self.floating = tk.BooleanVar(value=cfg.get("floating", True))
        ttk.Checkbutton(self, text="显示桌面悬浮助手", variable=self.floating).grid(row=len(rows) + 1, column=1, sticky="w")
        ttk.Button(self, text="保存", style="Accent.TButton", command=self.save).grid(row=len(rows) + 2, column=1, sticky="w", pady=int(18 * k))
        ttk.Label(self, text="设备ID：%s\n客户端版本：%s\n配置文件：%s" % (cfg["device_id"], VERSION, config.CONFIG_FILE),
                  style="Muted.TLabel").grid(row=len(rows) + 3, column=0, columnspan=2, sticky="w")

    def save(self):
        for k, v in self.vars.items():
            cfg[k] = v.get().strip()
        cfg["is_cloud_desktop"] = self.cloud.get()
        cfg["floating"] = self.floating.get()
        config.save(cfg)
        messagebox.showinfo("设置", "已保存，下次上报时生效")
