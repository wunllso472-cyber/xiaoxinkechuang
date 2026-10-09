"""一键提速：垃圾文件扫描与清理（按分类树状展示）"""
import os
import re
import shutil
import subprocess
import time

from .config import IS_WIN
from .sysinfo import run

HOME = os.path.expanduser("~")


def _walk_files(root, pattern=None, min_age_sec=0, max_files=20000):
    out = []
    if not os.path.exists(root):
        return out
    now = time.time()
    if os.path.isfile(root):
        try:
            st = os.stat(root)
            out.append((root, st.st_size))
        except OSError:
            pass
        return out
    for dp, dns, fns in os.walk(root, onerror=lambda e: None):
        for fn in fns:
            if pattern and not re.search(pattern, fn):
                continue
            p = os.path.join(dp, fn)
            try:
                st = os.lstat(p)
            except OSError:
                continue
            if min_age_sec and now - st.st_mtime < min_age_sec:
                continue
            out.append((p, st.st_size))
            if len(out) >= max_files:
                return out
    return out


def _writable(p):
    return os.access(os.path.dirname(p) or p, os.W_OK)


def categories():
    """返回 [(分类, 子项名, 扫描函数, 是否需要管理员权限)]"""
    if IS_WIN:
        tmp = os.environ.get("TEMP", os.path.join(HOME, "AppData", "Local", "Temp"))
        local = os.environ.get("LOCALAPPDATA", os.path.join(HOME, "AppData", "Local"))
        win = os.environ.get("WINDIR", r"C:\Windows")
        return [
            ("系统临时文件", "用户临时目录 %TEMP%", lambda: _walk_files(tmp, min_age_sec=3600), False),
            ("系统临时文件", "Windows\\Temp", lambda: _walk_files(os.path.join(win, "Temp"), min_age_sec=3600), True),
            ("日志文件", "Windows 日志(*.log)", lambda: _walk_files(os.path.join(win, "Logs"), r"\.log$"), True),
            ("日志文件", "Windows 更新缓存", lambda: _walk_files(os.path.join(win, "SoftwareDistribution", "Download")), True),
            ("系统缓存", "预读取 Prefetch", lambda: _walk_files(os.path.join(win, "Prefetch")), True),
            ("系统缓存", "缩略图缓存", lambda: _walk_files(os.path.join(local, "Microsoft", "Windows", "Explorer"), r"^thumbcache")),
            ("应用程序缓存", "Edge 浏览器缓存", lambda: _walk_files(os.path.join(local, "Microsoft", "Edge", "User Data", "Default", "Cache"))),
            ("应用程序缓存", "Chrome 浏览器缓存", lambda: _walk_files(os.path.join(local, "Google", "Chrome", "User Data", "Default", "Cache"))),
            ("应用程序缓存", "崩溃转储", lambda: _walk_files(os.path.join(local, "CrashDumps"))),
        ]
    return [
        ("APT 包管理器", "已下载软件包缓存(clean)", lambda: _walk_files("/var/cache/apt/archives", r"\.deb$"), True),
        ("APT 包管理器", "过期软件包(autoclean)", _apt_autoclean, True),
        ("APT 包管理器", "无用依赖包(autoremove)", _apt_autoremove, True),
        ("APT 包管理器", "软件包列表", lambda: _walk_files("/var/lib/apt/lists", r"_(Packages|Sources|Translation)"), True),
        ("Bash 历史记录", "~/.bash_history", lambda: _walk_files(os.path.join(HOME, ".bash_history")), False),
        ("系统临时文件", "/tmp", lambda: _walk_files("/tmp", min_age_sec=86400), False),
        ("系统临时文件", "/var/tmp", lambda: _walk_files("/var/tmp", min_age_sec=86400), False),
        ("日志文件", "/var/log 历史日志", lambda: _walk_files("/var/log", r"(\.\d+|\.gz|\.old)$"), True),
        ("日志文件", "~/.xsession-errors", lambda: _walk_files(os.path.join(HOME, ".xsession-errors")) + _walk_files(os.path.join(HOME, ".xsession-errors.old")), False),
        ("应用程序缓存", "~/.cache", lambda: _walk_files(os.path.join(HOME, ".cache")), False),
        ("应用程序缓存", "/var/cache", lambda: [x for x in _walk_files("/var/cache") if "/apt/" not in x[0]], True),
        ("应用程序缓存", "回收站", lambda: _walk_files(os.path.join(HOME, ".local", "share", "Trash")), False),
    ]


def _apt_autoremove():
    out = run(["apt-get", "-s", "autoremove"], timeout=60)
    pkgs = re.findall(r"^Remv (\S+)", out, re.M)
    return [("[软件包] " + p, 0) for p in pkgs]


def _apt_autoclean():
    out = run(["apt-get", "-s", "autoclean"], timeout=60)
    names = re.findall(r"^Del (\S+) (\S+)", out, re.M)
    return [("[过期包] %s %s" % n, 0) for n in names]


def scan(progress=None, stop=None):
    """返回 {分类: {子项: {"files":[(path,size)], "size":n, "admin":bool}}}"""
    cats = categories()
    result = {}
    for i, (cat, item, fn, *rest) in enumerate(cats):
        admin = rest[0] if rest else False
        if stop and stop():
            break
        if progress:
            progress(i, len(cats), "%s / %s" % (cat, item))
        try:
            files = fn()
        except Exception:  # noqa
            files = []
        result.setdefault(cat, {})[item] = {"files": files, "size": sum(s for _, s in files), "admin": admin}
    if progress:
        progress(len(cats), len(cats), "扫描完成")
    return result


def _sudo(cmd):
    """Linux 下需要提权的操作用 pkexec（图形化授权）"""
    if os.geteuid() == 0:
        return subprocess.run(cmd, capture_output=True)
    if shutil.which("pkexec"):
        return subprocess.run(["pkexec"] + cmd, capture_output=True)
    return subprocess.run(["sudo", "-n"] + cmd, capture_output=True)


def clean(selected, progress=None):
    """selected: [(分类, 子项, 数据)]；返回 (清理文件数, 释放字节, 失败数)"""
    count, freed, failed = 0, 0, 0
    total = sum(len(d["files"]) or 1 for _, _, d in selected) or 1
    done = 0
    for cat, item, data in selected:
        if not IS_WIN and cat == "APT 包管理器":
            sub = {"已下载软件包缓存(clean)": "clean", "过期软件包(autoclean)": "autoclean", "无用依赖包(autoremove)": "autoremove"}.get(item)
            if sub:
                r = _sudo(["apt-get", "-y", sub])
                if r.returncode == 0:
                    count += len(data["files"])
                    freed += data["size"]
                else:
                    failed += 1
            elif item == "软件包列表":
                r = _sudo(["sh", "-c", "rm -rf /var/lib/apt/lists/*"])
                if r.returncode == 0:
                    freed += data["size"]
            done += len(data["files"]) or 1
            if progress:
                progress(done, total, item)
            continue
        if item == "~/.bash_history":
            try:
                open(os.path.join(HOME, ".bash_history"), "w").close()
                count += 1
                freed += data["size"]
            except OSError:
                failed += 1
            continue
        need_sudo = []
        for path, size in data["files"]:
            done += 1
            try:
                os.remove(path)
                count += 1
                freed += size
            except OSError:
                need_sudo.append((path, size))
            if progress and done % 50 == 0:
                progress(done, total, path)
        if need_sudo and not IS_WIN and data.get("admin"):
            r = _sudo(["rm", "-f"] + [p for p, _ in need_sudo[:2000]])
            if r.returncode == 0:
                count += len(need_sudo)
                freed += sum(s for _, s in need_sudo)
                need_sudo = []
        failed += len(need_sudo)
    if progress:
        progress(total, total, "清理完成")
    return count, freed, failed


def fmt_size(b):
    for u in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return "%.1f%s" % (b, u)
        b /= 1024.0
    return "%.1fTB" % b
