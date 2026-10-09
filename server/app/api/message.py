"""消息管理：消息列表、新建消息任务、消息模板、定时发送"""
import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth import require_roles
from ..db import get_db, Message, MessageTemplate, MessageReceipt, Terminal, SessionLocal
from .common import crud_router, apply_filters, paginate, coerce

router = APIRouter(prefix="/api/admin/messages", tags=["消息管理"])
dep = require_roles("cs")

template_router = crud_router(MessageTemplate, "/api/admin/message-templates", dep, ("name", "content"))


def targets(db, m):
    q = db.query(Terminal.device_id)
    vals = [v.strip() for v in (m.scope_value or "").replace("，", ",").split(",") if v.strip()]
    if m.scope_type == "dept" and vals:
        q = q.filter(Terminal.dept.in_(vals))
    elif m.scope_type == "device" and vals:
        q = q.filter((Terminal.device_id.in_(vals)) | (Terminal.hostname.in_(vals)))
    return [r[0] for r in q.all()]


def send_message(db, m):
    devs = targets(db, m)
    for d in devs:
        db.add(MessageReceipt(message_id=m.id, device_id=d))
    m.status, m.sent_at, m.target_count = "已发送", datetime.datetime.now(), len(devs)
    db.commit()


def send_due_messages():
    """定时任务：到点发送"""
    db = SessionLocal()
    try:
        for m in db.query(Message).filter(Message.status == "待发送", Message.send_type == "timed",
                                          Message.send_time <= datetime.datetime.now()).all():
            send_message(db, m)
    finally:
        db.close()


@router.get("")
def list_messages(request: Request, page: int = 1, page_size: int = 20, db=Depends(get_db), user=Depends(dep)):
    q = apply_filters(Message, db.query(Message), dict(request.query_params), ("title", "content"), ("status", "scope_type"))
    return paginate(q, page, page_size, Message.id.desc())


@router.post("")
def create_message(data: dict, db=Depends(get_db), user=Depends(dep)):
    """新建消息任务：可基于模板二次编辑；即时发送 / 定时发送 / 存草稿"""
    if data.get("template_id") and not data.get("content"):
        t = db.get(MessageTemplate, int(data["template_id"]))
        data.setdefault("title", t.title or t.name)
        data["content"] = t.content
    vals = coerce(Message, data)
    vals.pop("id", None)
    m = Message(**vals)
    m.creator = user.real_name or user.username
    if data.get("draft"):
        m.status = "草稿"
    elif m.send_type == "timed":
        if not m.send_time:
            raise HTTPException(400, "定时发送需设置发送时间")
        m.status = "待发送"
    db.add(m)
    db.commit()
    if m.status == "待发送" and m.send_type == "now":
        send_message(db, m)
    return m.to_dict()


@router.put("/{mid}")
def update_message(mid: int, data: dict, db=Depends(get_db), user=Depends(dep)):
    m = db.get(Message, mid)
    if m.status == "已发送":
        allowed = {"title", "content"}  # 已发送消息仅允许修订内容
        data = {k: v for k, v in data.items() if k in allowed}
    for k, v in coerce(Message, data).items():
        if k != "id":
            setattr(m, k, v)
    if m.status == "草稿" and data.get("publish"):
        m.status = "待发送"
    db.commit()
    if m.status == "待发送" and m.send_type == "now":
        send_message(db, m)
    return m.to_dict()


@router.post("/{mid}/send")
def send_now(mid: int, db=Depends(get_db), user=Depends(dep)):
    m = db.get(Message, mid)
    if m.status == "已发送":
        raise HTTPException(400, "消息已发送")
    send_message(db, m)
    return m.to_dict()


@router.delete("/{mid}")
def delete_message(mid: int, db=Depends(get_db), user=Depends(dep)):
    db.query(MessageReceipt).filter(MessageReceipt.message_id == mid).delete()
    m = db.get(Message, mid)
    if m:
        db.delete(m)
    db.commit()
    return {"ok": True}


@router.get("/{mid}/receipts")
def receipts(mid: int, db=Depends(get_db), user=Depends(dep)):
    rows = db.query(MessageReceipt, Terminal).outerjoin(Terminal, Terminal.device_id == MessageReceipt.device_id) \
        .filter(MessageReceipt.message_id == mid).all()
    return [{"device_id": r.device_id, "hostname": t.hostname if t else "", "user_name": t.user_name if t else "",
             "delivered_at": r.to_dict()["delivered_at"], "read_at": r.to_dict()["read_at"]} for r, t in rows]
