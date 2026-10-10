import queue
import threading
import tkinter as tk
from tkinter import ttk

from .config import IS_WIN

# Apple 风格配色：浅色侧栏 + 白色内容区 + 系统蓝强调色
BRAND = "#007aff"
BRAND_HOVER = "#268fff"
BRAND_PRESS = "#0062cc"
BG = "#ffffff"          # 内容区
SIDEBAR = "#f2f2f7"     # 侧栏
FILL = "#eeeef0"        # 次要按钮、分段控件
TILE = "#f5f5f7"        # 图表卡片
SEP = "#d9d9de"         # 分隔线
TEXT = "#1d1d1f"
TEXT2 = "#6e6e73"
GREEN, ORANGE, RED = "#34c759", "#ff9500", "#ff3b30"
FONT = ("Microsoft YaHei UI", 10) if IS_WIN else ("Noto Sans CJK SC", 10)
FONT_B = (FONT[0], 11, "bold")
FONT_H = (FONT[0], 14, "bold")
FONT_TITLE = (FONT[0], 20, "bold")

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


def scale(w):
    """屏幕 DPI 缩放系数"""
    return max(float(w.tk.call("tk", "scaling")) / 1.333, 1.0)


def _rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def mix(c1, c2, t):
    """c1 向 c2 混合，t 为 c2 的比例"""
    a, b = _rgb(c1), _rgb(c2)
    return "#%02x%02x%02x" % tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _cover(px, py, x0, y0, x1, y1, r):
    """像素 (px, py) 被圆角矩形覆盖的比例，圆角处 4x4 采样抗锯齿"""
    if px + 1 <= x0 or px >= x1 or py + 1 <= y0 or py >= y1:
        return 0.0
    if (x0 + r <= px and px + 1 <= x1 - r) or (y0 + r <= py and py + 1 <= y1 - r):
        return 1.0
    n = 0
    for i in range(4):
        sx = px + (i + 0.5) / 4
        cx = min(max(sx, x0 + r), x1 - r)
        for j in range(4):
            sy = py + (j + 0.5) / 4
            cy = min(max(sy, y0 + r), y1 - r)
            if (sx - cx) ** 2 + (sy - cy) ** 2 <= r * r:
                n += 1
    return n / 16.0


_images = []  # PhotoImage 需保持引用


def rounded(master, w, h, layers, back=BG):
    """在底色 back 上依次叠加圆角矩形 (x0, y0, x1, y1, r, color)，生成 PhotoImage（不依赖 PIL）"""
    base = _rgb(back)
    shapes = [(x0, y0, x1, y1, r, _rgb(c)) for x0, y0, x1, y1, r, c in layers]
    rows = []
    for y in range(h):
        row = []
        for x in range(w):
            col = base
            for x0, y0, x1, y1, r, c in shapes:
                t = _cover(x, y, x0, y0, x1, y1, r)
                if t:
                    col = c if t == 1.0 else tuple(col[i] + (c[i] - col[i]) * t for i in range(3))
            row.append("#%02x%02x%02x" % tuple(int(round(v)) for v in col))
        rows.append("{" + " ".join(row) + "}")
    img = tk.PhotoImage(master=master, width=w, height=h)
    img.put(" ".join(rows))
    _images.append(img)
    return img


def setup_style(root):
    k = scale(root)

    def px(v):
        return int(round(v * k))

    root.configure(bg=BG)
    root.option_add("*Font", FONT)
    root.option_add("*TCombobox*Listbox.background", BG)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", BRAND)
    root.option_add("*TCombobox*Listbox.selectForeground", "white")
    s = ttk.Style(root)
    try:
        s.theme_use("clam")
    except tk.TclError:
        pass
    s.configure(".", font=FONT, background=BG, foreground=TEXT, bordercolor=BG, lightcolor=BG, darkcolor=BG,
                troughcolor=FILL, focuscolor=BG, selectbackground="#b3d7ff", selectforeground=TEXT, insertcolor=TEXT)
    s.configure("TFrame", background=BG)
    s.configure("Card.TFrame", background=BG)
    s.configure("TLabel", background=BG, foreground=TEXT)
    s.configure("Card.TLabel", background=BG)
    s.configure("H.TLabel", font=FONT_H, background=BG, foreground=TEXT)
    s.configure("Muted.TLabel", foreground=TEXT2, background=BG)

    r = px(7)
    d = 2 * r + 2

    def pill(fill, back=BG, mx=0, border=None):
        w = d + 2 * mx  # mx：两侧留白，九宫格拉伸时边框须小于图片宽度的一半
        layers = [(mx, 0, w - mx, d, r, border or fill)]
        if border:
            layers.append((mx + 1, 1, w - mx - 1, d - 1, r - 1, fill))
        return rounded(root, w, d, layers, back)

    def boxed(name, element, inner):
        s.layout(name, [(element, {"sticky": "nsew", "children": inner})])

    def label(p):
        return [(p + ".padding", {"sticky": "nsew", "children": [(p + ".label", {"sticky": "nsew"})]})]

    # 按钮：圆角填充，主按钮为系统蓝，次要按钮为浅灰，危险操作为红字
    s.element_create("Round.button", "image", pill(FILL), ("disabled", pill("#f5f5f7")), ("pressed", pill("#d4d4d9")),
                     ("active", pill("#e2e2e7")), border=r, padding=0, sticky="nsew")
    s.element_create("Accent.button", "image", pill(BRAND), ("disabled", pill("#b3d7ff")), ("pressed", pill(BRAND_PRESS)),
                     ("active", pill(BRAND_HOVER)), border=r, padding=0, sticky="nsew")
    boxed("TButton", "Round.button", label("Button"))
    boxed("Accent.TButton", "Accent.button", label("Button"))
    s.configure("TButton", padding=(px(14), px(6)), anchor="center", foreground=TEXT, width=-5)
    s.map("TButton", foreground=[("disabled", "#b4b4b9")])
    s.configure("Accent.TButton", foreground="white")
    s.map("Accent.TButton", foreground=[("disabled", "white")])
    s.configure("Danger.TButton", foreground=RED)
    s.map("Danger.TButton", foreground=[("disabled", "#b4b4b9")])

    # 输入框：圆角描边，聚焦时描边变为系统蓝
    s.element_create("Round.field", "image", pill(BG, border="#c7c7cc"), ("focus", pill(BG, border=BRAND)), border=r, padding=0, sticky="nsew")
    boxed("TEntry", "Round.field", [("Entry.padding", {"sticky": "nsew", "children": [("Entry.textarea", {"sticky": "nsew"})]})])
    boxed("TCombobox", "Round.field", [("Combobox.padding", {"sticky": "nsew", "children": [
        ("Combobox.downarrow", {"side": "right", "sticky": "ns"}), ("Combobox.textarea", {"sticky": "nsew"})]})])
    boxed("TSpinbox", "Round.field", [("Spinbox.padding", {"sticky": "nsew", "children": [
        ("null", {"side": "right", "sticky": "", "children": [("Spinbox.uparrow", {"side": "top", "sticky": "e"}),
                                                              ("Spinbox.downarrow", {"side": "bottom", "sticky": "e"})]}),
        ("Spinbox.textarea", {"sticky": "nsew"})]})])
    for n in ("TEntry", "TCombobox", "TSpinbox"):
        s.configure(n, padding=(px(8), px(5)), foreground=TEXT, fieldbackground=BG, background=BG, arrowcolor=TEXT2, arrowsize=px(12))
    s.map("TCombobox", fieldbackground=[("readonly", BG)], selectbackground=[("readonly", BG)], selectforeground=[("readonly", TEXT)])

    # 单选：分段胶囊；侧栏导航：选中项为蓝色圆角条
    s.element_create("Seg.bg", "image", pill(FILL, mx=px(2)), ("selected", pill(BRAND, mx=px(2))), ("active", pill("#e2e2e7", mx=px(2))),
                     border=(r + px(2), r), padding=0, sticky="nsew")
    boxed("TRadiobutton", "Seg.bg", label("Radiobutton"))
    s.configure("TRadiobutton", padding=(px(14), px(5)), anchor="center", foreground=TEXT)
    s.map("TRadiobutton", foreground=[("selected", "white")])
    s.element_create("Nav.bg", "image", pill(SIDEBAR, SIDEBAR), ("selected", pill(BRAND, SIDEBAR)), ("active", pill("#e3e3e8", SIDEBAR)),
                     border=r, padding=0, sticky="nsew")
    boxed("Nav.TRadiobutton", "Nav.bg", label("Radiobutton"))
    s.configure("Nav.TRadiobutton", padding=(px(12), px(8)), anchor="w", background=SIDEBAR, foreground=TEXT, font=(FONT[0], 11))
    s.map("Nav.TRadiobutton", foreground=[("selected", "white")])

    # 勾选项：开关
    sw, sh, gap = px(38), px(22), px(8)

    def knob(x):
        return (x + 2, 2, x + sh - 2, sh - 2, (sh - 4) / 2.0, "#ffffff")

    off = rounded(root, sw + gap, sh, [(0, 0, sw, sh, sh / 2.0, "#d9d9de"), knob(0)])
    on = rounded(root, sw + gap, sh, [(0, 0, sw, sh, sh / 2.0, GREEN), knob(sw - sh)])
    s.element_create("Switch.indicator", "image", off, ("selected", on), sticky="")
    s.layout("TCheckbutton", [("Checkbutton.padding", {"sticky": "nsew", "children": [
        ("Switch.indicator", {"side": "left", "sticky": ""}), ("Checkbutton.label", {"side": "left", "sticky": "nsew"})]})])
    s.configure("TCheckbutton", padding=(0, px(4)), foreground=TEXT)

    # 页签：选中项为浅灰圆角底
    s.element_create("Seg.tab", "image", pill(BG, mx=px(2)), ("selected", pill("#e8e8ed", mx=px(2))), ("active", pill(TILE, mx=px(2))),
                     border=(r + px(2), r), padding=0, sticky="nsew")
    s.layout("TNotebook.Tab", [("Seg.tab", {"sticky": "nsew", "children": [
        ("Notebook.padding", {"side": "top", "sticky": "nsew", "children": [("Notebook.label", {"side": "top", "sticky": ""})]})]})])
    s.configure("TNotebook", borderwidth=0, tabmargins=(0, 0, 0, px(8)))
    s.configure("TNotebook.Tab", padding=(px(16), px(6)), foreground=TEXT2)
    s.map("TNotebook.Tab", foreground=[("selected", TEXT)], expand=[("selected", (0, 0, 0, 0))],
          padding=[("selected", (px(16), px(6)))])

    # 表格：无边框，浅蓝选中行
    from tkinter import font as tkfont
    line = tkfont.Font(root=root, font=FONT).metrics("linespace")
    s.configure("Treeview", rowheight=int(line * 1.7), font=FONT, background=BG, fieldbackground=BG, foreground=TEXT, borderwidth=0)
    s.map("Treeview", background=[("selected", "#dcebff")], foreground=[("selected", TEXT)])
    s.configure("Treeview.Heading", font=(FONT[0], 9), background="#fafafa", foreground=TEXT2, relief="flat", padding=(px(2), px(6)),
                bordercolor="#fafafa", lightcolor="#fafafa", darkcolor="#fafafa")
    s.map("Treeview.Heading", background=[("active", TILE)])

    # 滚动条：细条、无箭头；进度条：细条
    for o in ("Vertical", "Horizontal"):
        s.layout(o + ".TScrollbar", [(o + ".Scrollbar.trough", {"sticky": "ns" if o == "Vertical" else "ew", "children": [
            (o + ".Scrollbar.thumb", {"expand": "1", "sticky": "nsew"})]})])
    s.configure("TScrollbar", troughcolor=BG, background="#c7c7cc", arrowsize=px(9), gripcount=0, borderwidth=0)
    s.map("TScrollbar", background=[("active", "#a1a1a6"), ("disabled", BG)])
    s.configure("Horizontal.TProgressbar", background=BRAND, troughcolor=FILL, thickness=px(6), borderwidth=0,
                bordercolor=FILL, lightcolor=BRAND, darkcolor=BRAND)
    s.configure("Sash", sashthickness=px(10), gripcount=0)
    return s


def tree_with_scroll(parent, columns, headings, widths=None, show="headings", height=12):
    f = tk.Frame(parent, bg=SEP, padx=1, pady=1)  # 细描边
    tv = ttk.Treeview(f, columns=columns, show=show, height=height)
    for i, c in enumerate(columns):
        tv.heading(c, text=headings[i], anchor="w")
        tv.column(c, width=(widths[i] if widths else 120), anchor="w")
    sb = ttk.Scrollbar(f, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=sb.set)
    tv.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    return f, tv


class Sparkline(tk.Canvas):
    """简易折线图：实时显示 CPU/内存/网络/磁盘 曲线（浅灰圆角卡片）"""

    def __init__(self, parent, title, color=BRAND, maxv=100, unit="%", width=160, height=84):
        k = scale(parent)
        width, height = int(width * k), int(height * k)
        super().__init__(parent, width=width, height=height, bg=BG, highlightthickness=0)
        self.title, self.color, self.maxv, self.unit = title, color, maxv, unit
        self.data = []
        self.w, self.h, self.pad = width, height, int(12 * k)
        self.bind("<Configure>", self._resize)  # 宽度随窗口伸缩

    def _resize(self, e):
        self.w = e.width
        self.redraw()

    def push(self, v):
        self.data = (self.data + [v])[-40:]
        self.redraw()

    def redraw(self):
        self.delete("all")
        r, w, h = self.pad, self.w, self.h
        for x, y in ((0, 0), (w - 2 * r, 0), (0, h - 2 * r), (w - 2 * r, h - 2 * r)):
            self.create_oval(x, y, x + 2 * r, y + 2 * r, fill=TILE, outline="")
        self.create_rectangle(r, 0, w - r, h, fill=TILE, outline="")
        self.create_rectangle(0, r, w, h - r, fill=TILE, outline="")
        p, base = self.pad, self.h - self.pad
        mx = self.maxv or max(self.data + [1])
        pts = []
        for i, v in enumerate(self.data):
            pts += [p + i * (self.w - 2 * p) / 39.0, base - (min(v, mx) / mx) * (self.h * 0.45)]
        if len(pts) >= 4:
            self.create_polygon(pts[0], base, *pts, pts[-2], base, fill=mix(TILE, self.color, 0.14), outline="")
            self.create_line(*pts, fill=self.color, width=2, smooth=True)
        cur = self.data[-1] if self.data else 0
        self.create_text(p, p + 2, anchor="w", text=self.title, fill=TEXT2, font=(FONT[0], 9))
        self.create_text(self.w - p, p + 2, anchor="e", text="%.1f%s" % (cur, self.unit), fill=TEXT, font=(FONT[0], 11, "bold"))
