"""终端配件信息采集与运行负载采集（Linux：Ubuntu/麒麟/统信；Windows）"""
import glob
import json
import os
import platform
import re
import socket
import subprocess
import uuid

import psutil

from .config import IS_WIN

CREATE_NO_WINDOW = 0x08000000 if IS_WIN else 0


def run(cmd, timeout=20, shell=False):
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, shell=shell, creationflags=CREATE_NO_WINDOW)
        out = r.stdout
        for enc in ("utf-8", "gbk"):
            try:
                return out.decode(enc)
            except UnicodeDecodeError:
                continue
        return out.decode("utf-8", "ignore")
    except (OSError, subprocess.SubprocessError):
        return ""


def ps_json(script):
    """Windows：执行 PowerShell 并解析 JSON"""
    out = run(["powershell", "-NoProfile", "-Command", script + " | ConvertTo-Json -Compress"], timeout=40)
    try:
        d = json.loads(out) if out.strip() else []
        return d if isinstance(d, list) else [d]
    except ValueError:
        return []


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except OSError:
        return ""


# ---------------- Linux ----------------
def _linux_cpu():
    model, vendor = "", ""
    info = _read("/proc/cpuinfo")
    for key in ("model name", "Model Name", "Hardware", "cpu model"):
        m = re.search(r"^%s\s*:\s*(.+)$" % key, info, re.M)
        if m:
            model = m.group(1).strip()
            break
    ls = run(["lscpu"])
    if not model:
        m = re.search(r"Model name:\s*(.+)", ls)
        model = m.group(1).strip() if m else ""
    m = re.search(r"Vendor ID:\s*(.+)", ls)
    vendor = m.group(1).strip() if m else ""
    # 飞腾/鲲鹏的 ARM 实现者代码
    impl = re.search(r"CPU implementer\s*:\s*(0x[0-9a-f]+)", info)
    if impl:
        vendor = vendor or {"0x70": "Phytium", "0x48": "HiSilicon Kunpeng", "0x41": "ARM"}.get(impl.group(1), impl.group(1))
    if not model and vendor:
        model = vendor
    return model, vendor


def _linux_os():
    d = {}
    for line in _read("/etc/os-release").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d[k] = v.strip('"')
    return d.get("NAME", platform.system()), d.get("VERSION", platform.release())


def _linux_disk():
    out = run(["lsblk", "-d", "-n", "-o", "NAME,MODEL,TYPE"])
    models = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1] == "disk" and not parts[0].startswith(("loop", "ram", "zram")):
            models.append(" ".join(parts[1:-1]) or parts[0])
    return ", ".join(models)


def _linux_dual_system():
    for cfg in glob.glob("/boot/grub*/grub.cfg") + glob.glob("/boot/efi/EFI/*/grub.cfg"):
        if re.search(r"menuentry\s+['\"]?.*Windows", _read(cfg), re.I):
            return True
    if os.path.isdir("/boot/efi/EFI/Microsoft"):
        return True
    out = run(["lsblk", "-n", "-o", "FSTYPE"])
    return "ntfs" in out and os.path.exists("/boot/efi/EFI/Microsoft/Boot")


# ---------------- Windows ----------------
def _win_info():
    d = {}
    cpu = ps_json("Get-CimInstance Win32_Processor | Select-Object Name,Manufacturer")
    if cpu:
        d["cpu_model"], d["cpu_vendor"] = (cpu[0].get("Name") or "").strip(), cpu[0].get("Manufacturer") or ""
    cs = ps_json("Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model")
    if cs:
        d["brand"], d["model"] = cs[0].get("Manufacturer") or "", cs[0].get("Model") or ""
    bios = ps_json("Get-CimInstance Win32_BIOS | Select-Object SerialNumber")
    if bios:
        d["serial"] = bios[0].get("SerialNumber") or ""
    disks = ps_json("Get-CimInstance Win32_DiskDrive | Select-Object Model")
    d["disk_model"] = ", ".join((x.get("Model") or "") for x in disks)
    os_ = ps_json("Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version")
    if os_:
        d["os_name"], d["os_version"] = os_[0].get("Caption") or "Windows", os_[0].get("Version") or ""
    # 双系统：存在 Linux 文件系统分区（GPT 类型 GUID 或 MBR 0x83）
    parts = ps_json("Get-Partition | Select-Object GptType,MbrType")
    d["dual_system"] = any((p.get("GptType") or "").lower() == "{0fc63daf-8483-4772-8e79-3d69d8477de4}" or p.get("MbrType") == 131
                           for p in parts)
    return d


def _mac_ip():
    ip = ""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except OSError:
        pass
    mac = ""
    for name, addrs in psutil.net_if_addrs().items():
        if any(a.family == socket.AF_INET and a.address == ip for a in addrs):
            for a in addrs:
                if a.family == psutil.AF_LINK:
                    mac = a.address.replace("-", ":").lower()
    if not mac:
        mac = ":".join(re.findall("..", "%012x" % uuid.getnode()))
    return mac, ip


def disk_total_gb():
    total = 0
    seen = set()
    for p in psutil.disk_partitions(all=False):
        if p.device in seen or "loop" in p.device or p.fstype in ("squashfs", "tmpfs"):
            continue
        seen.add(p.device)
        try:
            total += psutil.disk_usage(p.mountpoint).total
        except OSError:
            pass
    return round(total / 1024 ** 3, 1)


def collect_hardware():
    mac, ip = _mac_ip()
    d = {
        "cpu_cores": psutil.cpu_count(logical=True),
        "mem_total": round(psutil.virtual_memory().total / 1024 ** 3, 1),
        "disk_total": disk_total_gb(),
        "arch": platform.machine(),
        "mac": mac,
        "ip": ip,
        "hostname": socket.gethostname(),
    }
    if IS_WIN:
        d.update(_win_info())
    else:
        d["cpu_model"], d["cpu_vendor"] = _linux_cpu()
        d["os_name"], d["os_version"] = _linux_os()
        d["brand"] = _read("/sys/class/dmi/id/sys_vendor")
        d["model"] = _read("/sys/class/dmi/id/product_name")
        d["serial"] = _read("/sys/class/dmi/id/product_serial") or _read("/sys/class/dmi/id/board_serial")
        d["disk_model"] = _linux_disk()
        d["dual_system"] = _linux_dual_system()
        d["kernel"] = platform.release()
    return d


def collect_load():
    root = "C:\\" if IS_WIN else "/"
    return {"cpu": psutil.cpu_percent(interval=0.5), "mem": psutil.virtual_memory().percent,
            "disk": psutil.disk_usage(root).percent}


HW_LABELS = {"cpu_model": "CPU", "cpu_cores": "CPU核数", "mem_total": "内存(GB)", "disk_total": "硬盘容量(GB)",
             "disk_model": "硬盘型号", "os_name": "操作系统", "os_version": "系统版本", "brand": "品牌", "model": "型号",
             "serial": "序列号", "mac": "网卡MAC", "ip": "IP地址", "arch": "架构", "hostname": "主机名"}


def diff_hardware(old, new):
    """本地对比历史配件信息"""
    changes = []
    for k in ("cpu_model", "mem_total", "disk_total", "disk_model", "brand", "model", "serial", "mac"):
        if old.get(k) not in (None, "") and new.get(k) not in (None, "") and str(old[k]) != str(new[k]):
            if k in ("mem_total", "disk_total") and abs(float(old[k]) - float(new[k])) < max(1.0, float(old[k]) * 0.05):
                continue
            changes.append((HW_LABELS[k], old[k], new[k]))
    return changes
