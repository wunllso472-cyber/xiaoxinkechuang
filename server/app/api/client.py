"""桌面客户端接口（以设备 ID 标识，无需登录）"""
import datetime
import os

from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import FileResponse

from ..auth import parse_token
from ..db import (get_db, Terminal, HardwareChange, Alert, ClientConfig, Message, MessageReceipt, ClientVersion,
                  Software, SessionLocal, User, SystemSetting)
from ..services import monitor

router = APIRouter(prefix="/api/client", tags=["客户端"])


class Actor:
    def __init__(self, user=None, device_id=""):
        self.user = user
        self.device_id = device_id

    @property
    def key(self):
        return ("u%s" % self.user.id) if self.user else ("d:" + self.device_id)

    @property
    def name(self):
        return (self.user.real_name or self.user.username) if self.user else self.device_id


def actor(authorization: str = Header(default=""), x_device_id: str = Header(default=""),
          x_client_key: str = Header(default="")):
    """登录用户(管理端/H5) 或 已注册设备(桌面客户端) 均可调用"""
    token = authorization.replace("Bearer ", "").strip()
    if token:
        p = parse_token(token)
        if p:
            db = SessionLocal()
            try:
                u = db.get(User, p["uid"])
            finally:
                db.close()
            if u:
                return Actor(user=u)
    if x_device_id:
        db = SessionLocal()
        try:
            s = db.get(SystemSetting, "client_key")
            if s and s.value and s.value != x_client_key:
                raise HTTPException(401, "客户端密钥错误")
        finally:
            db.close()
        return Actor(device_id=x_device_id)
    raise HTTPException(401, "未登录")


def _config(db):
    return {c.key: {"value": c.value, "trigger": c.trigger, "name": c.name} for c in db.query(ClientConfig).all()}


@router.post("/report")
def report(data: dict, db=Depends(get_db)):
    """上报终端配件信息 + 运行负载；返回配件变更、下发配置"""
    if not data.get("device_id"):
        raise HTTPException(400, "缺少 device_id")
    t, changes = monitor.upsert_terminal(db, data)
    monitor.evaluate_alerts(db, t, changes)
    db.commit()
    return {"ok": True, "is_xinchuang": t.is_xinchuang,
            "changes": [{"component": c.component, "old": c.old_value, "new": c.new_value} for c in changes],
            "config": _config(db)}


@router.post("/heartbeat")
def heartbeat(data: dict, db=Depends(get_db)):
    t = db.query(Terminal).filter(Terminal.device_id == data.get("device_id")).first()
    if not t:
        return {"ok": False, "need_report": True}
    load = data.get("load") or {}
    t.cpu_usage, t.mem_usage, t.disk_usage = load.get("cpu", t.cpu_usage), load.get("mem", t.mem_usage), load.get("disk", t.disk_usage)
    t.status, t.last_seen = "online", datetime.datetime.now()
    from ..db import LoadRecord
    db.add(LoadRecord(device_id=t.device_id, cpu=t.cpu_usage, mem=t.mem_usage, disk=t.disk_usage))
    monitor.mark_active(db, t.device_id, int(data.get("minutes", 0)))
    monitor.evaluate_alerts(db, t)
    db.commit()
    unread = db.query(MessageReceipt).filter(MessageReceipt.device_id == t.device_id,
                                             MessageReceipt.read_at == None).count()  # noqa: E711
    return {"ok": True, "unread_messages": unread}


@router.post("/run-records")
def run_records(data: dict, db=Depends(get_db)):
    """上报运行数据：开关机、已装应用、应用使用、U盘、打印机"""
    dev = data.get("device_id")
    recs = data.get("records") or []
    monitor.save_run_records(db, dev, recs)
    t = db.query(Terminal).filter(Terminal.device_id == dev).first()
    if t:
        monitor.evaluate_alerts(db, t, run_records=recs)
    db.commit()
    return {"ok": True, "count": len(recs)}


@router.get("/config")
def get_config(db=Depends(get_db)):
    return _config(db)


@router.get("/status")
def status(device_id: str, db=Depends(get_db)):
    t = db.query(Terminal).filter(Terminal.device_id == device_id).first()
    if not t:
        raise HTTPException(404, "终端未注册")
    changes = db.query(HardwareChange).filter(HardwareChange.device_id == device_id) \
        .order_by(HardwareChange.id.desc()).limit(20).all()
    alerts = db.query(Alert).filter(Alert.device_id == device_id).order_by(Alert.id.desc()).limit(20).all()
    return {"terminal": t.to_dict(exclude=("hw_snapshot",)), "changes": [c.to_dict() for c in changes],
            "alerts": [a.to_dict() for a in alerts]}


@router.get("/messages")
def messages(device_id: str, all: int = 0, db=Depends(get_db)):
    q = db.query(MessageReceipt).filter(MessageReceipt.device_id == device_id)
    if not all:
        q = q.filter(MessageReceipt.read_at == None)  # noqa: E711
    out = []
    for r in q.order_by(MessageReceipt.id.desc()).limit(50).all():
        m = db.get(Message, r.message_id)
        if not m:
            continue
        if not r.delivered_at:
            r.delivered_at = datetime.datetime.now()
        out.append({"id": m.id, "title": m.title, "content": m.content, "sent_at": m.sent_at.strftime("%Y-%m-%d %H:%M") if m.sent_at else "",
                    "read": r.read_at is not None})
    db.commit()
    return out


@router.post("/messages/{mid}/read")
def read_message(mid: int, data: dict, db=Depends(get_db)):
    r = db.query(MessageReceipt).filter(MessageReceipt.message_id == mid,
                                        MessageReceipt.device_id == data.get("device_id")).first()
    if r and not r.read_at:
        r.read_at = datetime.datetime.now()
        m = db.get(Message, mid)
        if m:
            m.read_count = (m.read_count or 0) + 1
        db.commit()
    return {"ok": True}


def _vtuple(v):
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0,)


@router.get("/version")
def check_version(platform: str, current: str = "0", arch: str = "", db=Depends(get_db)):
    vs = db.query(ClientVersion).filter(ClientVersion.platform == platform,
                                        ClientVersion.status == "已发布").all()
    vs = [v for v in vs if v.arch in ("all", "", arch)]
    if not vs:
        return {"update": False}
    latest = max(vs, key=lambda v: _vtuple(v.version))
    if _vtuple(latest.version) <= _vtuple(current):
        return {"update": False, "latest": latest.version}
    return {"update": True, "latest": latest.version, "changelog": latest.changelog, "force": latest.force_update,
            "url": "/api/client/download/version/%d" % latest.id if latest.file_path else ""}


@router.get("/software")
def software(platform: str = "", db=Depends(get_db)):
    q = db.query(Software)
    if platform:
        q = q.filter(Software.platform.in_([platform, "all"]))
    return [dict(s.to_dict(), url="/api/client/download/software/%d" % s.id if s.file_path else "") for s in q.all()]


@router.get("/download/{kind}/{item_id}")
def download(kind: str, item_id: int, db=Depends(get_db)):
    obj = db.get(ClientVersion if kind == "version" else Software, item_id)
    if not obj or not obj.file_path or not os.path.exists(obj.file_path):
        raise HTTPException(404, "文件不存在")
    path = obj.file_path
    db.close()  # 大文件传输可能持续很久，先归还数据库连接，否则并发下载会占满连接池
    return FileResponse(path, filename=os.path.basename(path).split("_", 1)[-1])
