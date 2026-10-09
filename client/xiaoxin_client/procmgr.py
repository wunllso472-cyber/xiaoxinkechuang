"""内存加速：进程可视化（CPU/内存/网络/磁盘排序）与闲置进程一键优化"""
import os
import time

import psutil

from .config import IS_WIN

# 不允许结束的关键进程
PROTECTED = {
    "systemd", "init", "kthreadd", "Xorg", "Xwayland", "gnome-shell", "ukui-session", "dde-desktop", "dde-dock", "kwin_x11",
    "sshd", "dbus-daemon", "NetworkManager", "pulseaudio", "pipewire", "lightdm", "gdm", "sddm", "python", "python3",
    "System", "System Idle Process", "Registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe",
    "lsass.exe", "svchost.exe", "explorer.exe", "dwm.exe", "fontdrvhost.exe", "sihost.exe", "ctfmon.exe", "MsMpEng.exe",
    "xiaoxin", "XiaoxinAssistant.exe",
    # 用户正在使用的前台应用（浏览器、办公、通讯、终端），不作为闲置进程处理
    "msedge.exe", "chrome.exe", "firefox.exe", "360se.exe", "QQBrowser.exe", "WINWORD.EXE", "EXCEL.EXE", "POWERPNT.EXE",
    "wps.exe", "et.exe", "wpp.exe", "WeChat.exe", "QQ.exe", "DingTalk.exe", "WindowsTerminal.exe", "cmd.exe", "powershell.exe",
    "chrome", "chromium", "firefox", "firefox-esr", "microsoft-edge", "wps", "et", "wpp", "wpsoffice", "deepin-terminal",
    "gnome-terminal-server", "mate-terminal", "bash", "zsh",
    # 安全软件
    "360tray.exe", "360sd.exe", "ZhuDongFangYu.exe", "QAXEntClient.exe", "QAXTray.exe", "360safe.exe",
    # 输入法与 WebView 宿主
    "msedgewebview2.exe", "fcitx", "fcitx5", "ibus-daemon", "ibus-x11", "sogoupinyin-service", "sogouImeService.exe", "TabTip.exe",
}
SYSTEM_DIRS = [os.environ.get("WINDIR", r"C:\Windows").lower()] if IS_WIN else ["/usr/libexec", "/usr/lib/systemd"]
_prev_io = {}


def snapshot():
    """采集进程列表：cpu%、内存MB、磁盘IO速率KB/s、网络连接数"""
    procs = list(psutil.process_iter(["pid", "name", "username", "memory_info", "create_time", "status"]))
    for p in procs:
        try:
            p.cpu_percent(None)
        except (psutil.Error, OSError):
            pass
    time.sleep(0.8)
    now = time.time()
    conns = {}
    try:
        for c in psutil.net_connections(kind="inet"):
            if c.pid:
                conns[c.pid] = conns.get(c.pid, 0) + 1
    except (psutil.AccessDenied, OSError):
        pass
    rows = []
    me = os.getpid()
    for p in procs:
        try:
            info = p.info
            io_rate = 0.0
            try:
                io = p.io_counters()
                total = io.read_bytes + io.write_bytes
                prev = _prev_io.get(p.pid)
                if prev:
                    io_rate = (total - prev[0]) / max(now - prev[1], 0.1) / 1024
                _prev_io[p.pid] = (total, now)
            except (psutil.Error, OSError, AttributeError):
                pass
            rows.append({
                "pid": info["pid"], "name": info["name"] or "", "user": (info["username"] or "").split("\\")[-1],
                "cpu": round(p.cpu_percent(None) / (psutil.cpu_count() or 1), 1),
                "mem": round((info["memory_info"].rss if info["memory_info"] else 0) / 1024 / 1024, 1),
                "disk": round(max(io_rate, 0), 1), "net": conns.get(info["pid"], 0),
                "uptime": int(now - (info["create_time"] or now)), "status": info["status"], "self": info["pid"] == me,
            })
        except (psutil.Error, OSError):
            continue
    return rows


def system_usage():
    root = "C:\\" if IS_WIN else "/"
    net = psutil.net_io_counters()
    disk = psutil.disk_io_counters()
    return {"cpu": psutil.cpu_percent(None), "mem": psutil.virtual_memory().percent, "disk": psutil.disk_usage(root).percent,
            "net_bytes": net.bytes_sent + net.bytes_recv, "disk_bytes": (disk.read_bytes + disk.write_bytes) if disk else 0}


def find_idle(rows, cpu_threshold=0.5, min_mem_mb=30, min_uptime=600):
    """闲置进程：当前用户、非关键进程、长时间运行、CPU 低、无网络连接且占用一定内存"""
    try:
        me = psutil.Process().username().split("\\")[-1]
    except psutil.Error:
        me = ""
    out = []
    for r in rows:
        if r["self"] or r["name"] in PROTECTED or r["user"] != me:
            continue
        try:  # 操作系统自带组件（开始菜单、搜索、输入法宿主等）不处理
            exe = (psutil.Process(r["pid"]).exe() or "").lower()
        except (psutil.Error, OSError):
            continue
        if any(exe.startswith(d) for d in SYSTEM_DIRS):
            continue
        if r["cpu"] <= cpu_threshold and r["mem"] >= min_mem_mb and r["uptime"] >= min_uptime and r["net"] == 0 \
                and r["disk"] < 1 and r["status"] in ("sleeping", "idle", "stopped", "running"):
            out.append(r)
    return sorted(out, key=lambda r: -r["mem"])


def kill(pids):
    ok, freed = 0, 0.0
    for pid in pids:
        try:
            p = psutil.Process(pid)
            if p.name() in PROTECTED:
                continue
            freed += p.memory_info().rss / 1024 / 1024
            p.terminate()
            ok += 1
        except psutil.Error:
            pass
    return ok, round(freed, 1)
