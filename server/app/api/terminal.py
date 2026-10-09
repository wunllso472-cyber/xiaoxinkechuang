"""管理端：终端资源管理、终端运行监测、客户端管理"""
import datetime

from fastapi import APIRouter, Depends, Request, UploadFile, File
from sqlalchemy import func

from ..auth import current_user, admin_only
from ..db import (get_db, Terminal, HardwareChange, RunRecord, LoadRecord, Alert, AlertRule, CloudServer,
                  ClientVersion, Software, DictItem, ClientConfig)
from ..services import monitor
from .common import crud_router, apply_filters, paginate, save_upload

router = APIRouter(prefix="/api/admin", tags=["终端管理"])

T_FILTERS = ("dept", "status", "is_xinchuang", "dual_system", "is_cloud_desktop", "os_name", "cpu_model", "brand",
             "cloud_server", "arch")


@router.get("/terminals")
def terminals(request: Request, page: int = 1, page_size: int = 20, db=Depends(get_db), user=Depends(current_user)):
    """终端资源清单：多维查询（部门/状态/信创/双系统/云桌面/操作系统/CPU/品牌/关键字）"""
    q = apply_filters(Terminal, db.query(Terminal), dict(request.query_params),
                      ("hostname", "user_name", "ip", "device_id", "serial", "mac"), T_FILTERS)
    res = paginate(q, page, page_size, Terminal.last_seen.desc())
    for it in res["items"]:
        it.pop("hw_snapshot", None)
    return res


@router.get("/terminals/options")
def terminal_options(db=Depends(get_db), user=Depends(current_user)):
    def distinct(col):
        return [r[0] for r in db.query(col).distinct().all() if r[0]]
    return {"dept": distinct(Terminal.dept), "os_name": distinct(Terminal.os_name),
            "cpu_model": distinct(Terminal.cpu_model), "brand": distinct(Terminal.brand),
            "cloud_server": distinct(Terminal.cloud_server)}


@router.get("/terminals/{tid}")
def terminal_detail(tid: int, db=Depends(get_db), user=Depends(current_user)):
    t = db.get(Terminal, tid)
    loads = db.query(LoadRecord).filter(LoadRecord.device_id == t.device_id).order_by(LoadRecord.id.desc()).limit(60).all()
    return {"terminal": t.to_dict(),
            "changes": [c.to_dict() for c in db.query(HardwareChange).filter(HardwareChange.device_id == t.device_id)
                        .order_by(HardwareChange.id.desc()).limit(50)],
            "alerts": [a.to_dict() for a in db.query(Alert).filter(Alert.device_id == t.device_id)
                       .order_by(Alert.id.desc()).limit(50)],
            "records": [r.to_dict() for r in db.query(RunRecord).filter(RunRecord.device_id == t.device_id)
                        .order_by(RunRecord.id.desc()).limit(50)],
            "loads": [l.to_dict() for l in reversed(loads)]}


@router.put("/terminals/{tid}")
def terminal_update(tid: int, data: dict, db=Depends(get_db), user=Depends(admin_only)):
    t = db.get(Terminal, tid)
    for k in ("user_name", "dept", "is_cloud_desktop", "cloud_server"):
        if k in data:
            setattr(t, k, data[k])
    db.commit()
    return {"ok": True}


@router.delete("/terminals/{tid}")
def terminal_delete(tid: int, db=Depends(get_db), user=Depends(admin_only)):
    t = db.get(Terminal, tid)
    if t:
        db.delete(t)
        db.commit()
    return {"ok": True}


@router.get("/cloud-desktops")
def cloud_desktops(keyword: str = "", server: str = "", db=Depends(get_db), user=Depends(current_user)):
    """云桌面资源清单：服务端 → 用户端 一对多"""
    servers = {s.name: s.to_dict() for s in db.query(CloudServer).all()}
    q = db.query(Terminal).filter(Terminal.is_cloud_desktop == True)  # noqa: E712
    if server:
        q = q.filter(Terminal.cloud_server == server)
    if keyword:
        like = "%%%s%%" % keyword
        q = q.filter((Terminal.hostname.ilike(like)) | (Terminal.user_name.ilike(like)) | (Terminal.ip.ilike(like)))
    groups = {}
    for t in q.all():
        key = t.cloud_server or "未知服务端"
        g = groups.setdefault(key, dict(servers.get(key, {"name": key, "ip": "", "spec": ""}), clients=[]))
        g["clients"].append({k: v for k, v in t.to_dict().items() if k != "hw_snapshot"})
    for name, s in servers.items():
        if name not in groups and not keyword and not server:
            groups[name] = dict(s, clients=[])
    out = list(groups.values())
    for g in out:
        g["client_count"] = len(g["clients"])
        g["online_count"] = sum(1 for c in g["clients"] if c["status"] == "online")
    return out


cloud_server_router = crud_router(CloudServer, "/api/admin/cloud-servers", admin_only, ("name", "ip"))


@router.get("/overview")
def overview(db=Depends(get_db), user=Depends(current_user)):
    """终端数据全量展示"""
    total = db.query(Terminal).count()
    online = db.query(Terminal).filter(Terminal.status == "online").count()

    def group(col):
        return [{"name": r[0] or "未知", "value": r[1]} for r in db.query(col, func.count()).group_by(col).all()]
    today = datetime.datetime.now().replace(hour=0, minute=0, second=0)
    return {
        "total": total, "online": online, "offline": total - online,
        "xinchuang": db.query(Terminal).filter(Terminal.is_xinchuang == True).count(),  # noqa: E712
        "cloud_desktop": db.query(Terminal).filter(Terminal.is_cloud_desktop == True).count(),  # noqa: E712
        "alerts_today": db.query(Alert).filter(Alert.created_at >= today).count(),
        "alerts_open": db.query(Alert).filter(Alert.status == "未处理").count(),
        "by_os": group(Terminal.os_name), "by_cpu": group(Terminal.cpu_model), "by_dept": group(Terminal.dept),
        "by_brand": group(Terminal.brand), "by_version": group(Terminal.client_version),
        "load_top": [{"hostname": t.hostname, "cpu": t.cpu_usage, "mem": t.mem_usage, "disk": t.disk_usage}
                     for t in db.query(Terminal).filter(Terminal.status == "online").order_by(Terminal.cpu_usage.desc()).limit(10)],
    }


@router.get("/indicators")
def indicators(dept: str = "", db=Depends(get_db), user=Depends(current_user)):
    """监测指标：接入率、替代完成率、双轨率、活跃率、违规双系统"""
    overall = monitor.compute_indicators(db)
    by_dept = []
    for (d,) in db.query(Terminal.dept).distinct().all():
        if d:
            by_dept.append(dict(monitor.compute_indicators(db, d), dept=d))
    abnormal = [t.to_dict(exclude=("hw_snapshot",)) for t in db.query(Terminal).filter(
        (Terminal.dual_system == True) | (Terminal.is_xinchuang == False)).limit(200)]  # noqa: E712
    return {"overall": monitor.compute_indicators(db, dept) if dept else overall, "by_dept": by_dept,
            "abnormal_terminals": abnormal}


@router.get("/hw-changes")
def hw_changes(request: Request, page: int = 1, page_size: int = 20, db=Depends(get_db), user=Depends(current_user)):
    q = apply_filters(HardwareChange, db.query(HardwareChange), dict(request.query_params),
                      ("device_id", "component"), ("confirmed",))
    res = paginate(q, page, page_size, HardwareChange.id.desc())
    names = {t.device_id: t for t in db.query(Terminal).filter(
        Terminal.device_id.in_([i["device_id"] for i in res["items"]]))}
    for i in res["items"]:
        t = names.get(i["device_id"])
        i["hostname"], i["user_name"] = (t.hostname, t.user_name) if t else ("", "")
    return res


@router.post("/hw-changes/{cid}/confirm")
def confirm_change(cid: int, db=Depends(get_db), user=Depends(current_user)):
    c = db.get(HardwareChange, cid)
    c.confirmed = True
    db.commit()
    return {"ok": True}


@router.get("/alerts")
def alerts(request: Request, page: int = 1, page_size: int = 20, db=Depends(get_db), user=Depends(current_user)):
    q = apply_filters(Alert, db.query(Alert), dict(request.query_params), ("content", "device_id"),
                      ("status", "level", "rule_name"))
    return paginate(q, page, page_size, Alert.id.desc())


@router.post("/alerts/handle")
def handle_alerts(data: dict, db=Depends(get_db), user=Depends(current_user)):
    db.query(Alert).filter(Alert.id.in_(data.get("ids", []))).update({"status": "已处理"}, synchronize_session=False)
    db.commit()
    return {"ok": True}


alert_rule_router = crud_router(AlertRule, "/api/admin/alert-rules", admin_only, ("name",), ("metric", "enabled"))


@router.get("/activity")
def activity(period: str = "day", n: int = 14, db=Depends(get_db), user=Depends(current_user)):
    """终端运行情况：按日/按周活跃度"""
    return monitor.activity_stats(db, period, n)


@router.get("/run-records")
def records(request: Request, page: int = 1, page_size: int = 20, db=Depends(get_db), user=Depends(current_user)):
    q = apply_filters(RunRecord, db.query(RunRecord), dict(request.query_params), ("device_id",), ("kind", "device_id"))
    res = paginate(q, page, page_size, RunRecord.id.desc())
    devs = {t.device_id: t for t in db.query(Terminal).filter(
        Terminal.device_id.in_([i["device_id"] for i in res["items"]]))}
    for i in res["items"]:
        t = devs.get(i["device_id"])
        i["hostname"] = t.hostname if t else ""
        i["user_name"] = t.user_name if t else ""
    return res


@router.get("/run-records/stats")
def record_stats(days: int = 7, db=Depends(get_db), user=Depends(current_user)):
    since = datetime.datetime.now() - datetime.timedelta(days=days)
    rows = db.query(RunRecord.kind, func.count()).filter(RunRecord.created_at >= since).group_by(RunRecord.kind).all()
    apps = {}
    for r in db.query(RunRecord).filter(RunRecord.kind == "app_usage", RunRecord.created_at >= since).limit(2000):
        for a in (r.content or {}).get("apps", []):
            apps[a] = apps.get(a, 0) + 1
    return {"by_kind": [{"name": k, "value": v} for k, v in rows],
            "top_apps": sorted([{"name": k, "value": v} for k, v in apps.items()], key=lambda x: -x["value"])[:15]}


# ---------------- 客户端管理 ----------------
version_router = crud_router(ClientVersion, "/api/admin/versions", admin_only, ("version", "changelog"), ("platform", "status"))
software_router = crud_router(Software, "/api/admin/software", admin_only, ("name", "description"), ("platform", "category"))
dict_router = crud_router(DictItem, "/api/admin/dicts", admin_only, ("raw_value", "std_value"), ("dict_type",))
client_config_router = crud_router(ClientConfig, "/api/admin/client-config", admin_only, ("name", "key"))


@router.post("/upload/{kind}/{item_id}")
def upload_package(kind: str, item_id: int, file: UploadFile = File(...), db=Depends(get_db), user=Depends(admin_only)):
    """为版本或装机软件上传安装包"""
    model = ClientVersion if kind == "version" else Software
    obj = db.get(model, item_id)
    path, name, ext, size = save_upload(file, "packages", max_mb=2048)
    obj.file_path = path
    if kind == "software":
        obj.size = size
    db.commit()
    return obj.to_dict()


@router.post("/dicts/apply")
def dict_apply(db=Depends(get_db), user=Depends(admin_only)):
    """按数据字典重新标准化已采集的终端数据"""
    n = 0
    for t in db.query(Terminal).all():
        hw = t.hw_snapshot or {}
        cpu, item = monitor.normalize(db, "cpu", hw.get("cpu_model", t.cpu_model))
        t.cpu_model = cpu
        t.brand = monitor.normalize(db, "brand", hw.get("brand", t.brand))[0]
        t.model = monitor.normalize(db, "model", hw.get("model", t.model))[0]
        t.os_name = monitor.normalize(db, "os", hw.get("os_name", t.os_name))[0]
        t.is_xinchuang = monitor.is_xinchuang(cpu + " " + (t.cpu_vendor or ""), t.os_name, item)
        n += 1
    db.commit()
    return {"updated": n}
