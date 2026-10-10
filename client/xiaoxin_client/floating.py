"""桌面悬浮助手：置顶可拖动的小图标，单击快速唤醒智能问答，右键菜单"""
import tkinter as tk

from .config import IS_WIN
from .ui_common import BRAND

BASE_SIZE = 64


class FloatingBall(tk.Toplevel):
    def __init__(self, master, on_click, menu_items):
        super().__init__(master)
        SIZE = int(BASE_SIZE * max(float(self.tk.call("tk", "scaling")) / 1.333, 1.0))  # 按 DPI 缩放
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        key = "#010203"
        if IS_WIN:
            self.configure(bg=key)
            self.attributes("-transparentcolor", key)
        else:
            try:
                self.attributes("-alpha", 0.92)
                self.attributes("-type", "dock")  # 部分 Linux 窗口管理器下不出现在任务栏
            except tk.TclError:
                pass
            key = "#ffffff"
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry("%dx%d+%d+%d" % (SIZE, SIZE, sw - SIZE - 30, sh // 2))
        c = tk.Canvas(self, width=SIZE, height=SIZE, bg=key, highlightthickness=0)
        c.pack()
        c.create_oval(3, 3, SIZE - 3, SIZE - 3, fill=BRAND, outline="#ffffff", width=3)
        c.create_text(SIZE // 2, SIZE * 0.42, text="小信", fill="white", font=("Microsoft YaHei UI" if IS_WIN else "Noto Sans CJK SC", -SIZE // 4, "bold"))
        c.create_text(SIZE // 2, SIZE * 0.7, text="助手", fill="#d6e9ff", font=("Microsoft YaHei UI" if IS_WIN else "Noto Sans CJK SC", -SIZE // 6))
        self.dot = c.create_oval(SIZE * 0.72, SIZE * 0.06, SIZE * 0.9, SIZE * 0.24, fill="#ff3b30", outline="white", state="hidden")
        self.c = c
        self.on_click = on_click
        self.menu = tk.Menu(self, tearoff=0)
        for label, fn in menu_items:
            if label == "-":
                self.menu.add_separator()
            else:
                self.menu.add_command(label=label, command=fn)
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._drag)
        c.bind("<ButtonRelease-1>", self._release)
        c.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))
        self._moved = False

    def _press(self, e):
        self._dx, self._dy, self._moved = e.x, e.y, False

    def _drag(self, e):
        self._moved = True
        self.geometry("+%d+%d" % (e.x_root - self._dx, e.y_root - self._dy))

    def _release(self, e):
        if not self._moved:
            self.on_click()

    def notify(self, on=True):
        self.c.itemconfig(self.dot, state="normal" if on else "hidden")
