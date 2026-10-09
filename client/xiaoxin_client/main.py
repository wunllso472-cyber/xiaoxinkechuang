"""小信助手桌面客户端入口"""
import logging
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox

if __package__ in (None, ""):  # 支持 python main.py 与 PyInstaller 直接运行
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "xiaoxin_client"

from xiaoxin_client.config import cfg, APP_NAME, VERSION, DATA_DIR  # noqa: E402
from xiaoxin_client.agent import Agent  # noqa: E402
from xiaoxin_client.floating import FloatingBall  # noqa: E402
from xiaoxin_client.ui_common import setup_style, pump, ui, DARK, FONT, FONT_B  # noqa: E402
from xiaoxin_client.ui_speedup import JunkFrame, ProcessFrame, BigFileFrame  # noqa: E402
from xiaoxin_client.ui_chat import ChatFrame, ContractFrame  # noqa: E402
from xiaoxin_client.ui_misc import DeviceFrame, MessageFrame, SoftwareFrame, SettingsFrame  # noqa: E402

logging.basicConfig(filename=os.path.join(DATA_DIR, "client.log"), level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

NAV = [("speedup", "一键提速"), ("device", "设备监测"), ("chat", "智能问答"), ("contract", "合同智审"),
       ("message", "消息中心"), ("software", "软件中心"), ("settings", "设置")]


class App:
    def __init__(self):
        if sys.platform == "win32":
            try:  # 高分屏下避免界面模糊
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except (AttributeError, OSError):
                pass
        self.root = tk.Tk()
        self.root.title("%s v%s" % (APP_NAME, VERSION))
        k = self.k = max(float(self.root.tk.call("tk", "scaling")) / 1.333, 1.0)  # 屏幕 DPI 缩放系数
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry("%dx%d" % (min(int(1100 * k), int(sw * 0.95)), min(int(720 * k), int(sh * 0.9))))
        self.root.minsize(min(int(960 * k), sw), min(int(620 * k), sh))
        setup_style(self.root)
        self.agent = Agent(on_messages=lambda m: ui(self.on_messages, m), on_hw_change=lambda c: ui(self.on_hw_change, c),
                           on_status=lambda t: ui(self.status.config, {"text": t}), on_update=lambda r: ui(self.on_update, r))
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        self.ball = None
        if cfg.get("floating", True):
            self.ball = FloatingBall(self.root, self.quick_chat, [
                ("智能问答", self.quick_chat), ("一键提速", lambda: self.show("speedup")), ("设备监测", lambda: self.show("device")),
                ("消息中心", lambda: self.show("message")), ("-", None), ("打开主界面", lambda: self.show(self.current)),
                ("退出小信助手", self.quit)])
        self.agent.start()
        pump(self.root)

    def _build(self):
        side = tk.Frame(self.root, bg=DARK, width=int(170 * self.k))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Label(side, text="小信助手", bg=DARK, fg="white", font=(FONT[0], 16, "bold"), pady=18).pack(fill="x")
        self.nav_btns = {}
        for key, label in NAV:
            b = tk.Label(side, text="  " + label, bg=DARK, fg="#c9d3ea", anchor="w", font=(FONT[0], 11), pady=10, cursor="hand2")
            b.pack(fill="x")
            b.bind("<Button-1>", lambda e, k=key: self.show(k))
            self.nav_btns[key] = b
        self.status = tk.Label(side, text="连接中…", bg=DARK, fg="#8fa3c8", font=(FONT[0], 9), wraplength=int(150 * self.k), justify="left")
        self.status.pack(side="bottom", fill="x", pady=10, padx=8)
        self.body = ttk.Frame(self.root)
        self.body.pack(side="left", fill="both", expand=True)
        self.pages = {}
        self.current = None
        self.show("speedup")

    def _make(self, key):
        if key == "speedup":
            nb = ttk.Notebook(self.body)
            nb.add(JunkFrame(nb), text="垃圾清理")
            nb.add(ProcessFrame(nb), text="内存加速")
            nb.add(BigFileFrame(nb), text="大文件检索")
            return nb
        return {"device": lambda: DeviceFrame(self.body, self.agent), "chat": lambda: ChatFrame(self.body),
                "contract": lambda: ContractFrame(self.body), "message": lambda: MessageFrame(self.body),
                "software": lambda: SoftwareFrame(self.body), "settings": lambda: SettingsFrame(self.body)}[key]()

    def show(self, key):
        self.root.deiconify()
        self.root.lift()
        if self.current:
            self.pages[self.current].pack_forget()
            self.nav_btns[self.current].config(bg=DARK, fg="#c9d3ea")
        if key not in self.pages:
            self.pages[key] = self._make(key)
        self.pages[key].pack(fill="both", expand=True, padx=8, pady=8)
        self.nav_btns[key].config(bg="#1d5bd8", fg="white")
        self.current = key
        if key == "message" and self.ball:
            self.ball.notify(False)
            self.pages[key].load()

    def quick_chat(self):
        self.show("chat")
        self.pages["chat"].input.focus_set()

    def hide(self):
        if self.ball:
            self.root.withdraw()  # 关闭主窗口后保留悬浮助手
        else:
            self.quit()

    def quit(self):
        self.agent.stop()
        self.root.destroy()

    def on_messages(self, msgs):
        if self.ball:
            self.ball.notify(True)
        m = msgs[0]
        win = tk.Toplevel(self.root)
        win.title("小信助手 - 新消息")
        win.attributes("-topmost", True)
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        k = self.k
        win.geometry("%dx%d+%d+%d" % (340 * k, 180 * k, sw - 360 * k, sh - 240 * k))
        win.configure(bg="white")
        tk.Label(win, text=m["title"], bg="white", font=FONT_B, anchor="w").pack(fill="x", padx=12, pady=(12, 4))
        tk.Label(win, text=m["content"][:120], bg="white", wraplength=int(310 * k), justify="left", anchor="w").pack(fill="x", padx=12)
        ttk.Button(win, text="查看（共%d条未读）" % len(msgs), command=lambda: (win.destroy(), self.show("message"))).pack(pady=10)
        win.after(15000, lambda: win.winfo_exists() and win.destroy())

    def on_hw_change(self, changes):
        messagebox.showwarning("配件更换提醒", "检测到本机配件发生变化：\n\n" + "\n".join(
            "%s：%s → %s" % (c["component"], c["old"], c["new"]) for c in changes) + "\n\n已同步上报管理后台。")

    def on_update(self, r):
        if messagebox.askyesno("版本更新", "发现新版本 %s：\n%s\n\n是否立即下载？" % (r["latest"], r.get("changelog", ""))):
            import webbrowser
            webbrowser.open(cfg["server"].rstrip("/") + r["url"])

    def run(self):
        self.root.mainloop()


def main():
    App().run()


if __name__ == "__main__":
    main()
