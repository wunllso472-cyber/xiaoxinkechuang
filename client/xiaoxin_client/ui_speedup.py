"""一键提速：垃圾清理 / 内存加速 / 大文件检索"""
import os
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox

import psutil

from . import cleaner, procmgr, bigfile
from .cleaner import fmt_size
from .config import IS_WIN
from .ui_common import bg, ui, tree_with_scroll, Sparkline, FONT_B


class JunkFrame(ttk.Frame):
    """垃圾清理：树状分类、详情窗口、扫描/清理进度条"""

    def __init__(self, parent):
        super().__init__(parent, padding=10)
        top = ttk.Frame(self)
        top.pack(fill="x")
        self.scan_btn = ttk.Button(top, text="一键扫描", style="Accent.TButton", command=self.scan)
        self.scan_btn.pack(side="left")
        self.clean_btn = ttk.Button(top, text="一键清理", command=self.clean, state="disabled")
        self.clean_btn.pack(side="left", padx=8)
        self.summary = ttk.Label(top, text="扫描系统缓存、日志、临时文件、APT 包缓存、Bash 历史、应用缓存等", style="Muted.TLabel")
        self.summary.pack(side="left", padx=8)
        self.pb = ttk.Progressbar(self, mode="determinate")
        self.pb.pack(fill="x", pady=8)
        self.ptext = ttk.Label(self, text="", style="Muted.TLabel")
        self.ptext.pack(anchor="w")
        f, self.tv = tree_with_scroll(self, ("size", "count", "admin"), ("大小", "文件数", "需授权"), [120, 90, 70], show="tree headings", height=16)
        self.tv.heading("#0", text="垃圾分类（勾选：双击切换）")
        self.tv.column("#0", width=380)
        f.pack(fill="both", expand=True)
        self.tv.bind("<Double-1>", self.toggle)
        self.tv.bind("<Button-3>", self.detail)
        ttk.Label(self, text="提示：双击勾选/取消；右键查看该类别的具体文件详情", style="Muted.TLabel").pack(anchor="w", pady=4)
        self.result = {}
        self.checked = set()

    def _progress(self, i, n, text):
        ui(self._set_progress, i, n, text)

    def _set_progress(self, i, n, text):
        self.pb["maximum"] = n or 1
        self.pb["value"] = i
        self.ptext.config(text=text[:120])

    def scan(self):
        self.scan_btn.config(state="disabled")
        self.tv.delete(*self.tv.get_children())
        bg(cleaner.scan, self._progress, done=self._scanned)

    def _scanned(self, result):
        self.result = result
        self.checked = set()
        total = 0
        for cat, items in result.items():
            cs = sum(d["size"] for d in items.values())
            cn = sum(len(d["files"]) for d in items.values())
            pid = self.tv.insert("", "end", text="☑ " + cat, values=(fmt_size(cs), cn, ""), open=True)
            for item, d in items.items():
                iid = self.tv.insert(pid, "end", text="☑ " + item, values=(fmt_size(d["size"]), len(d["files"]), "是" if d["admin"] else ""))
                if d["files"]:
                    self.checked.add(iid)
                else:
                    self.tv.item(iid, text="☐ " + item)
            total += cs
        self.summary.config(text="共发现垃圾 %s，可清理" % fmt_size(total))
        self.scan_btn.config(state="normal")
        self.clean_btn.config(state="normal")

    def toggle(self, e):
        iid = self.tv.focus()
        if not iid:
            return
        parent = self.tv.parent(iid) or iid
        kids = self.tv.get_children(iid) or (iid,)
        on = not all(k in self.checked for k in kids)
        for k in kids:
            (self.checked.add if on else self.checked.discard)(k)
            self.tv.item(k, text=("☑ " if on else "☐ ") + self.tv.item(k, "text")[2:])
        allon = all(k in self.checked for k in self.tv.get_children(parent))
        self.tv.item(parent, text=("☑ " if allon else "☐ ") + self.tv.item(parent, "text")[2:])

    def _data(self, iid):
        parent = self.tv.parent(iid)
        if not parent:
            return None
        cat = self.tv.item(parent, "text")[2:]
        item = self.tv.item(iid, "text")[2:]
        return cat, item, self.result[cat][item]

    def detail(self, e):
        iid = self.tv.identify_row(e.y)
        d = self._data(iid) if iid else None
        if not d:
            return
        win = tk.Toplevel(self)
        win.title("详细信息 - %s / %s" % (d[0], d[1]))
        win.geometry("760x420")
        f, tv = tree_with_scroll(win, ("path", "size"), ("文件", "大小"), [600, 100])
        f.pack(fill="both", expand=True, padx=8, pady=8)
        for p, s in sorted(d[2]["files"], key=lambda x: -x[1])[:3000]:
            tv.insert("", "end", values=(p, fmt_size(s)))

    def clean(self):
        sel = [self._data(i) for i in self.checked]
        sel = [s for s in sel if s and s[2]["files"]]
        if not sel:
            return messagebox.showinfo("提示", "没有勾选可清理的项")
        if any(s[0] == "Bash 历史记录" for s in sel) and not messagebox.askyesno("确认", "将清空 Bash 历史记录，是否继续？"):
            return
        self.clean_btn.config(state="disabled")
        bg(cleaner.clean, sel, self._progress, done=self._cleaned)

    def _cleaned(self, r):
        count, freed, failed = r
        messagebox.showinfo("清理完成", "已清理 %d 项，释放空间 %s%s" % (count, fmt_size(freed), "\n%d 项因权限不足未清理" % failed if failed else ""))
        self.scan()


class ProcessFrame(ttk.Frame):
    """内存加速：进程可视化排序 + 一键优化闲置进程"""

    def __init__(self, parent):
        super().__init__(parent, padding=10)
        charts = ttk.Frame(self)
        charts.pack(fill="x")
        self.sp = {"cpu": Sparkline(charts, "CPU", "#1d5bd8"), "mem": Sparkline(charts, "内存", "#29a37a"),
                   "net": Sparkline(charts, "网络", "#e6a23c", maxv=0, unit="KB/s"), "disk": Sparkline(charts, "磁盘IO", "#d9534f", maxv=0, unit="KB/s")}
        for s in self.sp.values():
            s.pack(side="left", padx=4)
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=8)
        ttk.Label(bar, text="排序：").pack(side="left")
        self.sort = tk.StringVar(value="cpu")
        for k, t in (("cpu", "CPU"), ("mem", "内存"), ("net", "网络连接"), ("disk", "磁盘IO")):
            ttk.Radiobutton(bar, text=t, value=k, variable=self.sort, command=self.render).pack(side="left")
        ttk.Button(bar, text="刷新", command=self.refresh).pack(side="left", padx=8)
        ttk.Button(bar, text="一键优化闲置进程", style="Accent.TButton", command=self.optimize).pack(side="left")
        ttk.Button(bar, text="结束选中进程", command=self.kill_sel).pack(side="left", padx=8)
        self.info = ttk.Label(bar, text="", style="Muted.TLabel")
        self.info.pack(side="left")
        f, self.tv = tree_with_scroll(self, ("pid", "name", "user", "cpu", "mem", "disk", "net"),
                                      ("PID", "进程名", "用户", "CPU%", "内存MB", "磁盘KB/s", "网络连接"), [70, 220, 100, 70, 90, 90, 80], height=16)
        f.pack(fill="both", expand=True)
        self.rows = []
        self.prev = None
        self.after(500, self.tick)
        self.refresh()

    def tick(self):
        if self.winfo_exists():
            u = procmgr.system_usage()
            if self.prev:
                self.sp["net"].push((u["net_bytes"] - self.prev["net_bytes"]) / 1024 / 2)
                self.sp["disk"].push((u["disk_bytes"] - self.prev["disk_bytes"]) / 1024 / 2)
            self.prev = u
            self.sp["cpu"].push(u["cpu"])
            self.sp["mem"].push(u["mem"])
            self.after(2000, self.tick)

    def refresh(self):
        bg(procmgr.snapshot, done=self._loaded)

    def _loaded(self, rows):
        self.rows = rows
        self.render()

    def render(self):
        self.tv.delete(*self.tv.get_children())
        k = self.sort.get()
        for r in sorted(self.rows, key=lambda r: -r[k])[:300]:
            self.tv.insert("", "end", iid=str(r["pid"]), values=(r["pid"], r["name"], r["user"], r["cpu"], r["mem"], r["disk"], r["net"]))
        vm = psutil.virtual_memory()
        self.info.config(text="进程 %d 个 · 内存已用 %.1f/%.1fGB" % (len(self.rows), vm.used / 1024 ** 3, vm.total / 1024 ** 3))

    def optimize(self):
        idle = procmgr.find_idle(self.rows)
        if not idle:
            return messagebox.showinfo("内存加速", "未发现可优化的闲置进程")
        # 在列表中高亮候选进程；选择“否”后可调整选中项，再点“结束选中进程”
        self.tv.selection_set([str(r["pid"]) for r in idle if self.tv.exists(str(r["pid"]))])
        names = "\n".join("%s (PID %d, %.0fMB)" % (r["name"], r["pid"], r["mem"]) for r in idle[:20])
        if messagebox.askyesno("一键优化", "发现 %d 个闲置进程（长时间无CPU、无网络、无磁盘活动），共占用 %.0fMB：\n\n%s\n\n"
                               "是否全部结束？选择“否”可在列表中调整选中项后点“结束选中进程”。"
                               % (len(idle), sum(r["mem"] for r in idle), names)):
            ok, freed = procmgr.kill([r["pid"] for r in idle])
            messagebox.showinfo("内存加速", "已优化 %d 个进程，释放内存约 %.0fMB" % (ok, freed))
            self.refresh()

    def kill_sel(self):
        pids = [int(i) for i in self.tv.selection()]
        if pids and messagebox.askyesno("确认", "结束选中的 %d 个进程？" % len(pids)):
            procmgr.kill(pids)
            self.refresh()


class BigFileFrame(ttk.Frame):
    """大文件检索：扫描进度、文件名、大小、更新时间、统计；勾选/全部清理"""

    def __init__(self, parent):
        super().__init__(parent, padding=10)
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        ttk.Label(bar, text="扫描路径：").pack(side="left")
        self.path = tk.StringVar(value=";".join(bigfile.roots()) if IS_WIN else os.path.expanduser("~"))
        ttk.Entry(bar, textvariable=self.path, width=28).pack(side="left")
        ttk.Label(bar, text=" 大于(MB)：").pack(side="left")
        self.min_mb = tk.IntVar(value=100)
        ttk.Spinbox(bar, from_=10, to=10240, textvariable=self.min_mb, width=6).pack(side="left")
        self.btn = ttk.Button(bar, text="开始扫描", style="Accent.TButton", command=self.scan)
        self.btn.pack(side="left", padx=8)
        ttk.Button(bar, text="停止", command=lambda: setattr(self, "stopping", True)).pack(side="left")
        ttk.Button(bar, text="全选", command=lambda: self.tv.selection_set(self.tv.get_children())).pack(side="left", padx=(16, 4))
        ttk.Button(bar, text="删除选中", command=self.delete).pack(side="left")
        ttk.Button(bar, text="打开所在目录", command=self.open_dir).pack(side="left", padx=4)
        self.pb = ttk.Progressbar(self, mode="indeterminate")
        self.pb.pack(fill="x", pady=8)
        self.ptext = ttk.Label(self, text="", style="Muted.TLabel")
        self.ptext.pack(anchor="w")
        f, self.tv = tree_with_scroll(self, ("name", "size", "mtime", "path"), ("文件名", "大小", "更新时间", "路径"), [200, 90, 140, 480], height=15)
        f.pack(fill="both", expand=True)
        self.stat = ttk.Label(self, text="", font=FONT_B)
        self.stat.pack(anchor="w", pady=4)
        self.found = []
        self.stopping = False

    def scan(self):
        self.tv.delete(*self.tv.get_children())
        self.found = []
        self.stopping = False
        self.btn.config(state="disabled")
        self.pb.start(12)
        paths = [p for p in self.path.get().split(";") if p.strip()]
        bg(bigfile.scan, paths, self.min_mb.get(), lambda n, p, t: ui(self._prog, n, p, t),
           lambda info: ui(self._add, info), lambda: self.stopping, done=self._done)

    def _prog(self, n, p, t):
        self.ptext.config(text="已扫描 %d 个文件，用时 %.0fs，当前：%s" % (n, t, p[-100:]))

    def _add(self, info):
        self.found.append(info)
        self.tv.insert("", "end", iid=info["path"], values=(info["name"], fmt_size(info["size"]), info["mtime"], info["path"]))
        self._stat()

    def _stat(self):
        by_ext = {}
        for f in self.found:
            by_ext[f["ext"]] = by_ext.get(f["ext"], 0) + f["size"]
        top = "、".join("%s %s" % (k, fmt_size(v)) for k, v in sorted(by_ext.items(), key=lambda x: -x[1])[:5])
        self.stat.config(text="共 %d 个大文件，合计 %s　　按类型：%s" % (len(self.found), fmt_size(sum(f["size"] for f in self.found)), top))

    def _done(self, r):
        self.pb.stop()
        self.btn.config(state="normal")
        # 按大小排序
        items = sorted(self.found, key=lambda f: -f["size"])
        self.tv.delete(*self.tv.get_children())
        for i in items:
            self.tv.insert("", "end", iid=i["path"], values=(i["name"], fmt_size(i["size"]), i["mtime"], i["path"]))

    def delete(self):
        sel = list(self.tv.selection())
        if not sel:
            return messagebox.showinfo("提示", "请先选择文件（可点“全选”）")
        if not messagebox.askyesno("确认删除", "将永久删除 %d 个文件，是否继续？" % len(sel)):
            return
        ok, freed, failed = bigfile.delete(sel)
        for p in sel:
            if not os.path.exists(p):
                self.tv.delete(p)
        self.found = [f for f in self.found if os.path.exists(f["path"])]
        self._stat()
        messagebox.showinfo("删除完成", "已删除 %d 个文件，释放 %s%s" % (ok, fmt_size(freed), "\n失败：\n" + "\n".join(failed[:5]) if failed else ""))

    def open_dir(self):
        sel = self.tv.selection()
        if sel:
            d = os.path.dirname(sel[0])
            if IS_WIN:
                os.startfile(d)  # noqa
            else:
                subprocess.Popen(["xdg-open", d])
