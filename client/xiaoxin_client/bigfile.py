"""大文件检索：扫描大于阈值(默认100MB)的文件"""
import os
import time

import psutil

from .config import IS_WIN

SKIP_LINUX = ("/proc", "/sys", "/dev", "/run", "/snap", "/var/lib/docker", "/boot")
SKIP_WIN = ("\\Windows\\WinSxS", "\\System Volume Information", "\\$Recycle.Bin", "\\Windows\\Installer")


def roots():
    if IS_WIN:
        return [p.mountpoint for p in psutil.disk_partitions() if "fixed" in p.opts or p.fstype == "NTFS"] or ["C:\\"]
    return ["/"]


def scan(paths, min_mb=100, on_progress=None, on_found=None, stop=None):
    """逐目录遍历；on_progress(已扫描文件数, 当前路径)；on_found(信息字典)"""
    limit = min_mb * 1024 * 1024
    scanned = 0
    found = []
    t0 = time.time()
    for root in paths:
        for dp, dns, fns in os.walk(root, onerror=lambda e: None):
            if stop and stop():
                return found, scanned
            if IS_WIN:
                if any(s.lower() in dp.lower() for s in SKIP_WIN):
                    dns[:] = []
                    continue
            elif dp.startswith(SKIP_LINUX) and dp != "/":
                dns[:] = []
                continue
            for fn in fns:
                scanned += 1
                p = os.path.join(dp, fn)
                try:
                    st = os.lstat(p)
                except OSError:
                    continue
                if st.st_size >= limit and os.path.isfile(p):
                    info = {"path": p, "name": fn, "size": st.st_size,
                            "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
                            "ext": os.path.splitext(fn)[1].lower() or "无"}
                    found.append(info)
                    if on_found:
                        on_found(info)
                if on_progress and scanned % 500 == 0:
                    on_progress(scanned, p, time.time() - t0)
    if on_progress:
        on_progress(scanned, "扫描完成", time.time() - t0)
    return found, scanned


def delete(paths):
    ok, freed, failed = 0, 0, []
    for p in paths:
        try:
            size = os.path.getsize(p)
            os.remove(p)
            ok += 1
            freed += size
        except OSError as e:
            failed.append("%s: %s" % (p, e))
    return ok, freed, failed
