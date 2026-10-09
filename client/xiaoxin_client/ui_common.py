import queue
import threading
import tkinter as tk
from tkinter import ttk

from .config import IS_WIN

BRAND = "#1d5bd8"
DARK = "#0e2f73"
BG = "#f3f5f9"
FONT = ("Microsoft YaHei UI", 10) if IS_WIN else ("Noto Sans CJK SC", 10)
FONT_B = (FONT[0], 11, "bold")
FONT_H = (FONT[0], 14, "bold")

_q = queue.Queue()


def ui(fn, *args):
    """从后台线程安全地调度到 Tk 主线程执行"""
    _q.put((fn, args))


def pump(root):
    try:
        while True:
            fn, args = _q.get_nowait()
            try:
                fn(*args)
            except Exception as e:  # noqa
                print("UI error:", e)
    except queue.Empty:
        pass
    root.after(80, pump, root)


def _show_error(e):
    from tkinter import messagebox
    messagebox.showerror("错误", str(e))


def bg(fn, *args, done=None, error=None):
    """后台执行 fn，完成后在主线程回调 done(result)"""
    def run():
        try:
            r = fn(*args)
            if done:
                ui(done, r)
        except Exception as e:  # noqa
            if error:
                ui(error, e)
            else:
                ui(_show_error, e)
    threading.Thread(target=run, daemon=True).start()


def setup_style(root):
    root.configure(bg=BG)
    root.option_add("*Font", FONT)
    s = ttk.Style(root)
    try:
        s.theme_use("clam")
    except tk.TclError:
        pass
    s.configure(".", font=FONT, background=BG)
    s.configure("TFrame", background=BG)
    s.configure("Card.TFrame", background="white")
    s.configure("TLabel", background=BG)
    s.configure("Card.TLabel", background="white")
    s.configure("H.TLabel", font=FONT_H, background=BG, foreground="#1f2d3d")
    s.configure("Muted.TLabel", foreground="#8492a6", background=BG)
    s.configure("Accent.TButton", background=BRAND, foreground="white", padding=(14, 6), borderwidth=0)
    s.map("Accent.TButton", background=[("active", "#3a73e6"), ("disabled", "#a0b4e0")])
    s.configure("TButton", padding=(10, 5))
    from tkinter import font as tkfont
    line = tkfont.Font(root=root, font=FONT).metrics("linespace")
    s.configure("Treeview", rowheight=int(line * 1.5), font=FONT)
    s.configure("Treeview.Heading", font=(FONT[0], 10, "bold"))
    s.configure("TNotebook.Tab", padding=(14, 6))
    s.configure("Horizontal.TProgressbar", background=BRAND, thickness=14)
    return s


def tree_with_scroll(parent, columns, headings, widths=None, show="headings", height=12):
    f = ttk.Frame(parent)
    tv = ttk.Treeview(f, columns=columns, show=show, height=height)
    for i, c in enumerate(columns):
        tv.heading(c, text=headings[i])
        tv.column(c, width=(widths[i] if widths else 120), anchor="w")
    sb = ttk.Scrollbar(f, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=sb.set)
    tv.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    return f, tv


class Sparkline(tk.Canvas):
    """简易折线图：实时显示 CPU/内存/网络/磁盘 曲线"""

    def __init__(self, parent, title, color=BRAND, maxv=100, unit="%", width=220, height=80):
        k = max(float(parent.tk.call("tk", "scaling")) / 1.333, 1.0)  # 按屏幕 DPI 缩放
        width, height = int(width * k), int(height * k)
        super().__init__(parent, width=width, height=height, bg="white", highlightthickness=0)
        self.title, self.color, self.maxv, self.unit = title, color, maxv, unit
        self.data = []
        self.w, self.h = width, height

    def push(self, v):
        self.data = (self.data + [v])[-40:]
        self.redraw()

    def redraw(self):
        self.delete("all")
        mx = self.maxv or max(self.data + [1])
        if self.data:
            pts = []
            for i, v in enumerate(self.data):
                x = 8 + i * (self.w - 16) / 39.0
                y = self.h - 8 - (min(v, mx) / mx) * (self.h - self.h * 0.4)
                pts += [x, y]
            if len(pts) >= 4:
                self.create_line(*pts, fill=self.color, width=2, smooth=True)
        cur = self.data[-1] if self.data else 0
        self.create_text(8, 10, anchor="w", text=self.title, fill="#606266", font=(FONT[0], 9))
        self.create_text(self.w - 8, 10, anchor="e", text="%.1f%s" % (cur, self.unit), fill=self.color, font=(FONT[0], 10, "bold"))
