"""终端运行数据采集：开关机、已安装应用、应用使用、U盘使用、打印机使用"""
import os
import re
import time

import psutil

from .config import IS_WIN
from .sysinfo import run, ps_json

_seen_usb = set()
_seen_print = set()


def installed_apps():
    if IS_WIN:
        apps = ps_json(r"Get-ItemProperty HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*,"
                       r"HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\* -ErrorAction SilentlyContinue"
                       r" | Where-Object DisplayName | Select-Object DisplayName")
        return sorted({a.get("DisplayName") for a in apps if a.get("DisplayName")})
    out = run(["dpkg-query", "-W", "-f=${Package}\\n"], timeout=60)
    if not out:
        out = run(["rpm", "-qa", "--qf", "%{NAME}\\n"], timeout=60)
    # 仅保留带桌面入口的应用，避免上报海量系统库
    desktop = set()
    for d in ("/usr/share/applications", os.path.expanduser("~/.local/share/applications"), "/opt/apps"):
        if os.path.isdir(d):
            for root, _, fns in os.walk(d):
                for fn in fns:
                    if fn.endswith(".desktop"):
                        desktop.add(fn[:-8])
    return sorted(desktop) or sorted(out.split())[:500]


def running_apps():
    names = set()
    try:
        me = psutil.Process().username()
    except psutil.Error:
        me = None
    for p in psutil.process_iter(["name", "username"]):
        try:
            if p.info["username"] == me and p.info["name"]:
                names.add(p.info["name"])
        except psutil.Error:
            pass
    return sorted(names)


def usb_devices():
    """当前插入的 U 盘/移动存储"""
    devs = []
    if IS_WIN:
        for d in ps_json("Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=2' | Select-Object DeviceID,VolumeName,Size"):
            devs.append("%s %s" % (d.get("DeviceID"), d.get("VolumeName") or ""))
    else:
        for p in os.listdir("/dev/disk/by-id") if os.path.isdir("/dev/disk/by-id") else []:
            if p.startswith("usb-") and not re.search(r"-part\d+$", p):
                devs.append(p[4:])
    return devs


def printer_jobs():
    jobs = []
    if IS_WIN:
        for j in ps_json("Get-Printer | ForEach-Object { Get-PrintJob -PrinterName $_.Name -ErrorAction SilentlyContinue } "
                         "| Select-Object Id,PrinterName,DocumentName,SubmittedTime"):
            jobs.append("%s|%s|%s" % (j.get("PrinterName"), j.get("Id"), j.get("DocumentName")))
    else:
        out = run(["lpstat", "-W", "all", "-o"], timeout=10)
        jobs = [l.split()[0] + "|" + " ".join(l.split()[1:3]) for l in out.splitlines() if l.strip()]
    return jobs


def printers():
    if IS_WIN:
        return [p.get("Name") for p in ps_json("Get-Printer | Select-Object Name")]
    return re.findall(r"^printer (\S+)", run(["lpstat", "-p"], timeout=10), re.M)


def boot_records():
    recs = [{"kind": "boot", "content": {"time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(psutil.boot_time()))}}]
    if not IS_WIN:
        out = run(["last", "-x", "-n", "20", "shutdown", "reboot"], timeout=10)
        for line in out.splitlines():
            if line.startswith("shutdown"):
                recs.append({"kind": "shutdown", "content": {"raw": line.strip()}})
    else:
        evs = ps_json("Get-WinEvent -FilterHashtable @{LogName='System';Id=6006,6005} -MaxEvents 10 -ErrorAction SilentlyContinue"
                      " | Select-Object Id,@{n='t';e={$_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')}}")
        for e in evs:
            recs.append({"kind": "shutdown" if e.get("Id") == 6006 else "boot", "content": {"time": e.get("t")}})
    return recs


def collect(first=False):
    recs = []
    if first:
        recs += boot_records()
        recs.append({"kind": "app_installed", "content": {"apps": installed_apps()[:800]}})
    recs.append({"kind": "app_usage", "content": {"apps": running_apps()[:300]}})
    for d in usb_devices():
        if d not in _seen_usb:
            _seen_usb.add(d)
            recs.append({"kind": "usb", "content": {"device": d, "action": "插入"}})
    for j in printer_jobs():
        if j not in _seen_print:
            _seen_print.add(j)
            recs.append({"kind": "printer", "content": {"job": j}})
    if first:
        recs.append({"kind": "printer", "content": {"printers": printers()}})
    return recs
