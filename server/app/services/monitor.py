"""终端监测：数据字典标准化、配件更换检测、监测指标测算、预警规则评估。"""
import datetime

from ..db import (Terminal, HardwareChange, DictItem, AlertRule, Alert, ActiveDay, SystemSetting, RunRecord)

XC_CPU = ["phytium", "飞腾", "kunpeng", "鲲鹏", "hisilicon", "hygon", "海光", "zhaoxin", "兆芯", "loongson", "龙芯", "sw", "申威"]
XC_OS = ["kylin", "麒麟", "uos", "统信", "uniontech", "deepin", "openeuler", "欧拉", "nfs", "中科方德"]
HW_FIELDS = {"cpu_model": "CPU", "mem_total": "内存(GB)", "disk_total": "硬盘容量(GB)", "disk_model": "硬盘型号",
             "os_name": "操作系统", "brand": "品牌", "model": "型号", "serial": "序列号", "mac": "网卡MAC"}


def normalize(db, dict_type, raw):
    """型号数据字典：采集的非规范文本 → 规范名称（包含匹配）"""
    if not raw:
        return raw, None
    low = raw.lower()
    items = db.query(DictItem).filter(DictItem.dict_type == dict_type).all()
    for it in sorted(items, key=lambda x: -len(x.raw_value or "")):  # 最长（最精确）的原始值优先
        if it.raw_value and it.raw_value.lower() in low:
            return it.std_value, it
    return raw, None


def is_xinchuang(cpu, os_name, cpu_dict=None):
    if cpu_dict is not None and cpu_dict.extra:
        return "信创" in cpu_dict.extra and any(k in (os_name or "").lower() for k in XC_OS)
    c, o = (cpu or "").lower(), (os_name or "").lower()
    return any(k in c for k in XC_CPU) and any(k in o for k in XC_OS)


def upsert_terminal(db, data):
    """处理客户端上报的配件与负载信息，返回 (terminal, changes)"""
    dev = data["device_id"]
    t = db.query(Terminal).filter(Terminal.device_id == dev).first()
    is_new = t is None
    if is_new:
        t = Terminal(device_id=dev, first_seen=datetime.datetime.now())
        db.add(t)
    hw = data.get("hardware") or {}
    cpu_std, cpu_item = normalize(db, "cpu", hw.get("cpu_model", ""))
    brand_std, _ = normalize(db, "brand", hw.get("brand", ""))
    model_std, _ = normalize(db, "model", hw.get("model", ""))
    os_std, _ = normalize(db, "os", hw.get("os_name", ""))
    new_vals = {
        "cpu_model": cpu_std, "mem_total": hw.get("mem_total", 0), "disk_total": hw.get("disk_total", 0),
        "disk_model": hw.get("disk_model", ""), "os_name": os_std, "brand": brand_std, "model": model_std,
        "serial": hw.get("serial", ""), "mac": hw.get("mac", ""),
    }
    changes = []
    if not is_new and hw:
        for f, label in HW_FIELDS.items():
            old, new = getattr(t, f), new_vals.get(f)
            if new in (None, "") or old in (None, ""):
                continue
            if isinstance(new, (int, float)) and isinstance(old, (int, float)):
                if abs(float(old) - float(new)) < max(1.0, float(old) * 0.05):
                    continue
            elif str(old) == str(new):
                continue
            changes.append(HardwareChange(device_id=dev, component=label, old_value=str(old), new_value=str(new)))
        for c in changes:
            db.add(c)
    if hw:
        for k, v in new_vals.items():
            setattr(t, k, v)
        t.cpu_vendor = hw.get("cpu_vendor", "")
        t.cpu_cores = hw.get("cpu_cores", 0)
        t.os_version = hw.get("os_version", "")
        t.arch = hw.get("arch", "")
        t.hw_snapshot = hw
        t.is_xinchuang = is_xinchuang(cpu_std + " " + t.cpu_vendor, os_std, cpu_item)
        t.dual_system = bool(hw.get("dual_system"))
    for k in ("hostname", "user_name", "dept", "ip", "client_version", "is_cloud_desktop", "cloud_server"):
        if data.get(k) is not None:
            setattr(t, k, data[k])
    load = data.get("load") or {}
    if load:
        t.cpu_usage, t.mem_usage, t.disk_usage = load.get("cpu", 0), load.get("mem", 0), load.get("disk", 0)
    if data.get("boot_time"):
        t.boot_time = datetime.datetime.fromtimestamp(data["boot_time"])
    t.status = "online"
    t.last_seen = datetime.datetime.now()
    mark_active(db, dev)
    db.flush()
    return t, changes


def mark_active(db, dev, minutes=0):
    today = datetime.date.today()
    a = db.query(ActiveDay).filter(ActiveDay.device_id == dev, ActiveDay.day == today).first()
    if not a:
        db.add(ActiveDay(device_id=dev, day=today, online_minutes=minutes))
    else:
        a.online_minutes = (a.online_minutes or 0) + minutes


# ---------------- 指标测算 ----------------
def _get_setting(db, key, default):
    s = db.get(SystemSetting, key)
    return s.value if s and s.value is not None else default


def compute_indicators(db, dept=None):
    q = db.query(Terminal)
    if dept:
        q = q.filter(Terminal.dept == dept)
    ts = q.all()
    total = len(ts)
    planned = _get_setting(db, "planned_terminals", {}).get(dept or "_all", 0) or total
    week_ago = datetime.datetime.now() - datetime.timedelta(days=7)
    xc = sum(1 for t in ts if t.is_xinchuang)
    active = sum(1 for t in ts if t.last_seen and t.last_seen >= week_ago)
    users = {}
    for t in ts:
        if t.user_name:
            users.setdefault(t.user_name, set()).add(bool(t.is_xinchuang))
    dual_track = sum(1 for v in users.values() if len(v) == 2)
    dual_sys = sum(1 for t in ts if t.dual_system)
    pct = lambda a, b: round(a * 100.0 / b, 2) if b else 0.0  # noqa: E731
    th = _get_setting(db, "indicator_thresholds", {"接入率": 90, "替代完成率": 80, "活跃率": 70, "双轨率": 20, "违规双系统数": 0})
    ind = {
        "终端总数": total, "应接入数": planned, "信创终端数": xc, "活跃终端数": active,
        "接入率": pct(total, planned), "替代完成率": pct(xc, total), "双轨率": pct(dual_track, len(users)),
        "活跃率": pct(active, total), "违规双系统数": dual_sys,
    }
    warnings = []
    for k in ("接入率", "替代完成率", "活跃率"):
        if ind[k] < th.get(k, 0):
            warnings.append({"indicator": k, "value": ind[k], "threshold": th[k], "message": "%s低于%s%%" % (k, th[k])})
    if ind["双轨率"] > th.get("双轨率", 100):
        warnings.append({"indicator": "双轨率", "value": ind["双轨率"], "threshold": th["双轨率"], "message": "双轨率偏高"})
    if dual_sys > th.get("违规双系统数", 0):
        warnings.append({"indicator": "违规双系统数", "value": dual_sys, "threshold": th.get("违规双系统数", 0),
                         "message": "存在违规双系统终端 %d 台" % dual_sys})
    ind["预警"] = warnings
    return ind


# ---------------- 预警规则 ----------------
def _cmp(v, op, th):
    try:
        th = float(th)
        v = float(v)
    except (TypeError, ValueError):
        return False
    return {">": v > th, ">=": v >= th, "<": v < th, "<=": v <= th, "=": v == th}.get(op, False)


def _add_alert(db, t, rule, content):
    recent = datetime.datetime.now() - datetime.timedelta(hours=6)
    dup = db.query(Alert).filter(Alert.device_id == t.device_id, Alert.rule_id == rule.id,
                                 Alert.status == "未处理", Alert.created_at >= recent).first()
    if not dup:
        db.add(Alert(device_id=t.device_id, rule_id=rule.id, rule_name=rule.name, level=rule.level,
                     content="[%s/%s] %s" % (t.hostname, t.user_name, content)))


def evaluate_alerts(db, t, changes=(), run_records=None):
    rules = db.query(AlertRule).filter(AlertRule.enabled == True).all()  # noqa: E712
    for r in rules:
        m = r.metric
        if m in ("cpu_usage", "mem_usage", "disk_usage"):
            v = getattr(t, m) or 0
            if _cmp(v, r.operator, r.threshold):
                _add_alert(db, t, r, "%s=%.1f%%，触发阈值 %s%s" % (r.name, v, r.operator, r.threshold))
        elif m == "dual_system" and t.dual_system:
            _add_alert(db, t, r, "检测到违规双系统")
        elif m == "non_xinchuang" and not t.is_xinchuang:
            _add_alert(db, t, r, "非信创终端：%s / %s" % (t.cpu_model, t.os_name))
        elif m == "hw_change" and changes:
            _add_alert(db, t, r, "配件更换：" + "；".join("%s %s→%s" % (c.component, c.old_value, c.new_value) for c in changes))
        elif m == "usb" and run_records:
            for rec in run_records:
                if rec.get("kind") == "usb":
                    _add_alert(db, t, r, "U盘使用：%s" % (rec.get("content") or {}).get("device", ""))
                    break
        elif m == "blacklist_app" and run_records:
            black = [x.strip().lower() for x in (r.threshold or "").split(",") if x.strip()]
            for rec in run_records:
                if rec.get("kind") in ("app_usage", "app_installed"):
                    names = [str(n).lower() for n in (rec.get("content") or {}).get("apps", [])]
                    hit = [b for b in black if any(b in n for n in names)]
                    if hit:
                        _add_alert(db, t, r, "使用违规软件：%s" % ",".join(hit))
                        break


def check_offline(db):
    """定时任务：标记离线终端，评估离线天数规则"""
    now = datetime.datetime.now()
    for t in db.query(Terminal).filter(Terminal.status == "online").all():
        if t.last_seen and (now - t.last_seen).total_seconds() > 600:
            t.status = "offline"
    for r in db.query(AlertRule).filter(AlertRule.enabled == True, AlertRule.metric == "offline_days").all():  # noqa
        try:
            days = float(r.threshold)
        except ValueError:
            continue
        for t in db.query(Terminal).filter(Terminal.last_seen < now - datetime.timedelta(days=days)).all():
            _add_alert(db, t, r, "终端已离线超过 %s 天" % r.threshold)
    db.commit()


def activity_stats(db, period="day", n=14):
    """按日/按周统计活跃终端数与活跃率"""
    total = db.query(Terminal).count() or 1
    today = datetime.date.today()
    out = []
    if period == "week":
        start = today - datetime.timedelta(days=today.weekday())
        for i in range(n - 1, -1, -1):
            s = start - datetime.timedelta(weeks=i)
            e = s + datetime.timedelta(days=6)
            cnt = db.query(ActiveDay.device_id).filter(ActiveDay.day >= s, ActiveDay.day <= e).distinct().count()
            out.append({"label": s.strftime("%m-%d") + "周", "active": cnt, "rate": round(cnt * 100.0 / total, 1)})
    else:
        for i in range(n - 1, -1, -1):
            d = today - datetime.timedelta(days=i)
            cnt = db.query(ActiveDay.device_id).filter(ActiveDay.day == d).distinct().count()
            out.append({"label": d.strftime("%m-%d"), "active": cnt, "rate": round(cnt * 100.0 / total, 1)})
    return {"total": total, "series": out}


def save_run_records(db, dev, records):
    for rec in records or []:
        db.add(RunRecord(device_id=dev, kind=rec.get("kind", "other"), content=rec.get("content")))
