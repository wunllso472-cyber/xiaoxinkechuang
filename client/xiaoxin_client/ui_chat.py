"""智能问答（多模型切换/多轮/本地知识问答/暂停）与合同智审"""
import os
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from . import api
from .ui_common import bg, ui, tree_with_scroll, scale, FONT, BRAND, BG, SEP, TEXT, TEXT2


class ChatFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=10)
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        ttk.Label(bar, text="模型", style="Muted.TLabel").pack(side="left", padx=(0, 6))
        self.model_var = tk.StringVar(value="自动路由")
        self.model_cb = ttk.Combobox(bar, textvariable=self.model_var, state="readonly", width=22)
        self.model_cb.pack(side="left")
        self.mode = tk.StringVar(value="chat")
        ttk.Radiobutton(bar, text="智能问答", value="chat", variable=self.mode).pack(side="left", padx=(12, 0))
        ttk.Radiobutton(bar, text="本地知识问答", value="kb", variable=self.mode).pack(side="left")
        ttk.Button(bar, text="上传私有文档", command=self.upload_doc).pack(side="left", padx=8)
        ttk.Button(bar, text="新会话", command=self.new_session).pack(side="right")
        k = scale(self)
        box = tk.Frame(self, bg=SEP, padx=1, pady=1)
        box.pack(fill="both", expand=True, pady=12)
        self.text = tk.Text(box, wrap="word", bg=BG, fg=TEXT, relief="flat", bd=0, highlightthickness=0, padx=int(14 * k), pady=int(12 * k),
                            state="disabled", height=20, cursor="arrow")
        self.text.pack(fill="both", expand=True)
        # 气泡：用户为系统蓝靠右，助手为浅灰靠左
        self.text.tag_config("user", justify="right", spacing1=int(4 * k), spacing3=int(4 * k))
        self.wrap = int(460 * k)
        self.text.tag_config("bot", foreground=TEXT, background="#e9e9eb", lmargin1=int(12 * k), lmargin2=int(12 * k), rmargin=int(160 * k),
                             spacing1=int(7 * k), spacing3=int(7 * k), rmargincolor=BG)
        self.text.tag_config("meta", foreground=TEXT2, font=(FONT[0], 9), lmargin1=int(4 * k))
        bottom = ttk.Frame(self)
        bottom.pack(fill="x")
        ibox = tk.Frame(bottom, bg="#c7c7cc", padx=1, pady=1)
        ibox.pack(side="left", fill="x", expand=True)
        self.input = tk.Text(ibox, height=3, wrap="word", relief="flat", bd=0, highlightthickness=0, bg=BG, fg=TEXT, insertbackground=TEXT,
                             padx=int(10 * k), pady=int(8 * k))
        self.input.pack(fill="x", expand=True)
        self.input.bind("<FocusIn>", lambda e: ibox.config(bg=BRAND))
        self.input.bind("<FocusOut>", lambda e: ibox.config(bg="#c7c7cc"))
        self.input.bind("<Return>", self._enter)
        self.send_btn = ttk.Button(bottom, text="发送", style="Accent.TButton", command=self.send)
        self.send_btn.pack(side="left", padx=8, fill="y")
        self.stop_btn = ttk.Button(bottom, text="暂停", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", fill="y")
        self.models = []
        self.session_id = ""
        self.stopping = False
        self.busy = False
        self.private_kb = None
        self._append("bot", "您好，我是小信助手，可以为您解答信创终端使用、故障排查和政策问题。\n也可以说“我的电脑坏了需要报修”，我会帮您登记报修工单。")
        self.load_models()

    def load_models(self):
        bg(lambda: api.get("/api/models/available"), done=self._models, error=lambda e: None)

    def _models(self, ms):
        self.models = ms
        self.model_cb["values"] = ["自动路由"] + [m["name"] for m in ms]

    def _append(self, tag, text):
        self.text.config(state="normal")
        if tag == "user":  # 用户气泡贴合文字宽度，靠右
            k, start = scale(self), self.text.index("end-1c")
            self.text.window_create("end", window=tk.Label(self.text, text=text, bg=BRAND, fg="white", justify="left", wraplength=self.wrap,
                                                           padx=int(12 * k), pady=int(7 * k)))
            self.text.insert("end", "\n")
            self.text.tag_add(tag, start, "end-1c")
        else:
            self.text.insert("end", text + "\n", tag)
        self.text.insert("end", "\n")
        self.text.config(state="disabled")
        self.text.see("end")

    def _enter(self, e):
        if not (e.state & 0x1):  # Shift+Enter 换行
            self.send()
            return "break"

    def new_session(self):
        self.session_id = ""
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.config(state="disabled")

    def send(self, text=None):
        text = (text or self.input.get("1.0", "end")).strip()
        if not text or self.busy:
            return
        self.input.delete("1.0", "end")
        self._append("user", text)
        model_id = next((m["id"] for m in self.models if m["name"] == self.model_var.get()), None)
        self.busy, self.stopping = True, False
        self.send_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.text.config(state="normal")
        self.text.insert("end", "", "bot")
        self.mark = self.text.index("end-1c")
        self.text.config(state="disabled")
        body = {"message": text, "session_id": self.session_id, "model_id": model_id, "mode": self.mode.get()}
        threading.Thread(target=api.stream, args=("/api/chat/send", body, lambda e: ui(self._on_event, e), lambda: self.stopping),
                         daemon=True).start()

    def _on_event(self, e):
        t = e.get("type")
        self.text.config(state="normal")
        if t == "meta":
            self.session_id = e["session_id"]
            self.refs = e.get("refs") or []
        elif t == "delta":
            self.text.insert("end", e["text"], "bot")
        elif t == "done":
            self.text.insert("end", "\n", "bot")
            meta = "  —— %s" % (e.get("model") or "")
            if getattr(self, "refs", None):
                meta += "  参考：" + "；".join("%s" % r["file"] for r in self.refs[:3])
            self.text.insert("end", meta + "\n\n", "meta")
        elif t == "error":
            self.text.insert("end", "\n[错误] %s\n\n" % e.get("text"), "meta")
        elif t == "end":
            if self.stopping:
                self.text.insert("end", "\n[已暂停]\n\n", "meta")
            self.busy = False
            self.send_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
        self.text.config(state="disabled")
        self.text.see("end")

    def stop(self):
        """暂停当前任务：通知服务端停止生成并断开流"""
        if self.session_id:
            bg(lambda: api.post("/api/chat/stop/" + self.session_id), error=lambda e: None)
        self.stopping = True

    def upload_doc(self):
        path = filedialog.askopenfilename(title="选择私有文档", filetypes=[("文档", "*.pdf *.docx *.txt *.md *.xlsx *.pptx *.ofd"), ("全部", "*.*")])
        if not path:
            return

        def do():
            if not self.private_kb:
                kbs = [k for k in api.get("/api/kb/bases") if k["owner"] != "public"]
                self.private_kb = kbs[0]["id"] if kbs else api.post("/api/kb/bases", {"name": "我的私有文档", "private": True})["id"]
            r = api.upload("/api/kb/bases/%d/docs" % self.private_kb, path, field_name="files")
            for _ in range(60):
                prog = [d for d in api.get("/api/kb/import-progress", {"kb_id": self.private_kb})]
                if not prog:
                    break
                time.sleep(1)
            return r
        self._append("meta", "正在上传并解析 %s …" % os.path.basename(path))
        bg(do, done=lambda r: (self._append("meta", "文档已入库：%s。请切换到“本地知识问答”提问。" % r[0]["status"]), self.mode.set("kb")))


class ContractFrame(ttk.Frame):
    """合同智审：上传 PDF/OFD 采购合同，展示要素提取、合规研判和预警"""

    def __init__(self, parent):
        super().__init__(parent, padding=10)
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        ttk.Button(bar, text="上传合同（PDF/OFD）", style="Accent.TButton", command=self.upload).pack(side="left")
        self.use_llm = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="大模型增强", variable=self.use_llm).pack(side="left", padx=8)
        ttk.Button(bar, text="刷新列表", command=self.load).pack(side="left")
        self.status = ttk.Label(bar, text="", style="Muted.TLabel")
        self.status.pack(side="left", padx=8)
        pw = ttk.PanedWindow(self, orient="horizontal")
        pw.pack(fill="both", expand=True, pady=12)
        lf, self.list = tree_with_scroll(pw, ("name", "risk", "status"), ("合同", "风险", "状态"), [200, 50, 70])
        self.list.bind("<<TreeviewSelect>>", self.show)
        pw.add(lf, weight=1)
        right = ttk.Notebook(pw)
        pw.add(right, weight=3)
        f1, self.review = tree_with_scroll(right, ("rule", "level", "result", "msg"), ("审查规则", "级别", "结果", "预警提醒"), [180, 50, 70, 360])
        self.review.tag_configure("bad", background="#ffebe9")
        right.add(f1, text="合规性研判")
        f2, self.elements = tree_with_scroll(right, ("k", "v"), ("要素", "提取结果"), [160, 500])
        right.add(f2, text="要素提取")
        f3, self.diff = tree_with_scroll(right, ("c", "s", "m"), ("模板条款", "比对结果", "合同对应条款"), [160, 160, 300])
        right.add(f3, text="差异提示")
        self.load()

    def load(self):
        bg(lambda: api.get("/api/contract", {"page_size": 50}), done=self._list, error=lambda e: self.status.config(text=str(e)))

    def _list(self, r):
        self.list.delete(*self.list.get_children())
        for c in r["items"]:
            self.list.insert("", "end", iid=str(c["id"]), values=(c["filename"], c["risk_level"] or "-", c["status"]))
        if any(c["status"] in ("待审查", "解析中") for c in r["items"]):
            self.after(2000, self.load)

    def upload(self):
        path = filedialog.askopenfilename(title="选择采购合同", filetypes=[("合同文件", "*.pdf *.ofd *.docx"), ("全部", "*.*")])
        if path:
            self.status.config(text="上传中…")
            bg(api.upload, "/api/contract/upload", path, {"use_llm": int(self.use_llm.get())},
               done=lambda r: (self.status.config(text="已上传，正在审查"), self.load()))

    def show(self, e=None):
        sel = self.list.selection()
        if sel:
            bg(lambda: api.get("/api/contract/" + sel[0]), done=self._detail)

    def _detail(self, c):
        for tv in (self.review, self.elements, self.diff):
            tv.delete(*tv.get_children())
        rv = c.get("review") or {}
        if rv.get("error"):
            return messagebox.showerror("解析失败", rv["error"])
        for it in sorted(rv.get("items", []), key=lambda x: x["passed"]):
            self.review.insert("", "end", values=(it["name"], it["level"], "合规" if it["passed"] else "不合规", it["message"]),
                               tags=() if it["passed"] else ("bad",))
        for k, v in ((c.get("elements") or {}).get("elements") or {}).items():
            self.elements.insert("", "end", values=(k, v or "未识别"))
        for d in (c.get("diff") or {}).get("items", []):
            self.diff.insert("", "end", values=(d["clause"], d["status"], d["matched_title"]))
        self.status.config(text="综合风险：%s，不合规 %s 项" % (c.get("risk_level"), rv.get("failed", 0)))
