"""智能运维：运维工作台、来电登记、案例检索、工单池、案例库、运维人员移动端工单处置"""
import datetime
import random

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, or_

from ..auth import current_user, require_roles
from ..db import get_db, Ticket, TicketLog, Case, User
from .common import apply_filters, paginate, coerce, crud_router

router = APIRouter(prefix="/api/ops", tags=["智能运维"])
cs_dep = require_roles("cs")
ops_dep = require_roles("ops", "cs")
DEFAULT_HOURS = 48  # 默认反馈期限


def _name(u):
    return u.real_name or u.username


def _log(db, t, action, user, content=""):
    db.add(TicketLog(ticket_id=t.id, action=action, operator=_name(user) if hasattr(user, "username") else str(user),
                     content=content))


def _no():
    return "GD" + datetime.datetime.now().strftime("%Y%m%d%H%M%S") + str(random.randint(10, 99))


def _get(db, tid):
    t = db.get(Ticket, tid)
    if not t:
        raise HTTPException(404, "工单不存在")
    return t


def create_ticket(db, data, user, source="来电"):
    vals = coerce(Ticket, data)
    for k in ("id", "status", "ticket_no"):
        vals.pop(k, None)
    t = Ticket(**vals)
    t.ticket_no, t.source = _no(), source
    t.cs_id = user.id if hasattr(user, "id") else None
    if data.get("status") == "已办结":  # 补录工单，不进入指派流转
        t.status, t.finished_at = "已办结", datetime.datetime.now()
        t.source = "补录" if source == "来电" else source
    elif t.assignee_id:
        a = db.get(User, t.assignee_id)
        t.assignee_name, t.status = _name(a), "待签收"
    else:
        t.status = "待指派"
    t.deadline = t.deadline or datetime.datetime.now() + datetime.timedelta(hours=DEFAULT_HOURS)
    db.add(t)
    db.flush()
    _log(db, t, "登记" if t.status != "已办结" else "补录", user, t.description[:200] if t.description else "")
    if t.status == "待签收":
        _log(db, t, "指派", user, "指派给 " + t.assignee_name)
    db.commit()
    return t


# ---------------- 运维工作台 ----------------
@router.get("/workbench")
def workbench(db=Depends(get_db), user=Depends(ops_dep)):
    counts = dict(db.query(Ticket.status, func.count()).group_by(Ticket.status).all())
    now = datetime.datetime.now()
    warn_assign = db.query(Ticket).filter(Ticket.status == "待指派",
                                          Ticket.created_at < now - datetime.timedelta(minutes=30)).all()
    warn_suspend = db.query(Ticket).filter(Ticket.status == "挂起审核中").all()
    overdue = db.query(Ticket).filter(Ticket.status.in_(["待签收", "处理中"]), Ticket.deadline < now).all()
    todo_q = db.query(Ticket).filter(or_(Ticket.status.in_(["待指派", "挂起审核中"]),
                                         (Ticket.assignee_id == user.id) & Ticket.status.in_(["待签收", "处理中"])))
    trend = []
    for i in range(6, -1, -1):
        d = (now - datetime.timedelta(days=i)).date()
        s = datetime.datetime.combine(d, datetime.time())
        e = s + datetime.timedelta(days=1)
        trend.append({"day": d.strftime("%m-%d"),
                      "created": db.query(Ticket).filter(Ticket.created_at >= s, Ticket.created_at < e).count(),
                      "finished": db.query(Ticket).filter(Ticket.finished_at >= s, Ticket.finished_at < e).count()})
    return {
        "counts": {s: counts.get(s, 0) for s in ["待指派", "待签收", "处理中", "挂起审核中", "待评价", "已办结"]},
        "warnings": [{"type": "待指派超时", "ticket_no": t.ticket_no, "id": t.id, "title": t.title} for t in warn_assign] +
                    [{"type": "待挂起审核", "ticket_no": t.ticket_no, "id": t.id, "title": t.title} for t in warn_suspend] +
                    [{"type": "超期未反馈", "ticket_no": t.ticket_no, "id": t.id, "title": t.title} for t in overdue],
        "todo": [t.to_dict() for t in todo_q.order_by(Ticket.id.desc()).limit(20)],
        "trend": trend,
        "case_pending": db.query(Case).filter(Case.status == "待审核").count(),
    }


# ---------------- 工单池 / 来电登记 ----------------
@router.get("/tickets")
def tickets(request: Request, page: int = 1, page_size: int = 20, db=Depends(get_db), user=Depends(ops_dep)):
    q = apply_filters(Ticket, db.query(Ticket), dict(request.query_params),
                      ("ticket_no", "title", "description", "reporter", "reporter_phone"),
                      ("status", "category", "source", "station", "assignee_id"))
    return paginate(q, page, page_size, Ticket.id.desc())


@router.post("/tickets")
def register(data: dict, db=Depends(get_db), user=Depends(cs_dep)):
    """来电问题登记（状态选“已办结”即为补录工单）"""
    return create_ticket(db, data, user).to_dict()


@router.get("/tickets/{tid}")
def detail(tid: int, db=Depends(get_db), user=Depends(ops_dep)):
    t = _get(db, tid)
    logs = db.query(TicketLog).filter(TicketLog.ticket_id == tid).order_by(TicketLog.id).all()
    return dict(t.to_dict(), logs=[l.to_dict() for l in logs])


@router.post("/tickets/{tid}/assign")
def assign(tid: int, data: dict, db=Depends(get_db), user=Depends(cs_dep)):
    t = _get(db, tid)
    a = db.get(User, int(data["assignee_id"]))
    t.assignee_id, t.assignee_name, t.status = a.id, _name(a), "待签收"
    _log(db, t, "指派", user, "指派给 " + _name(a))
    db.commit()
    return t.to_dict()


@router.post("/tickets/{tid}/suspend-audit")
def suspend_audit(tid: int, data: dict, db=Depends(get_db), user=Depends(cs_dep)):
    """客服审核挂起申请：通过则延长反馈期限"""
    t = _get(db, tid)
    if t.status != "挂起审核中":
        raise HTTPException(400, "工单不在挂起审核状态")
    if data.get("approve"):
        t.deadline = (t.deadline or datetime.datetime.now()) + datetime.timedelta(days=t.suspend_days or 1)
        t.status = "处理中"
        _log(db, t, "挂起审核通过", user, "反馈期限延长至 %s" % t.deadline.strftime("%Y-%m-%d %H:%M"))
    else:
        t.status = "处理中"
        _log(db, t, "挂起审核驳回", user, data.get("comment", ""))
    db.commit()
    return t.to_dict()


@router.post("/tickets/{tid}/close")
def close(tid: int, data: dict, db=Depends(get_db), user=Depends(cs_dep)):
    t = _get(db, tid)
    t.status, t.finished_at = "已办结", datetime.datetime.now()
    _log(db, t, "办结", user, data.get("comment", ""))
    db.commit()
    return t.to_dict()


@router.post("/tickets/{tid}/rate")
def rate(tid: int, data: dict, db=Depends(get_db), user=Depends(current_user)):
    """用户评价（客服可代录）"""
    t = _get(db, tid)
    t.rating, t.rating_comment = int(data.get("rating", 5)), data.get("comment", "")
    t.status, t.finished_at = "已办结", datetime.datetime.now()
    _log(db, t, "评价", user, "%s星 %s" % (t.rating, t.rating_comment))
    db.commit()
    return t.to_dict()


@router.post("/tickets/{tid}/to-case")
def to_case(tid: int, data: dict, db=Depends(get_db), user=Depends(ops_dep)):
    """将典型工单上报为案例，待市保障中心审核"""
    t = _get(db, tid)
    c = Case(title=data.get("title") or t.title, category=t.category, question=t.description,
             answer=data.get("answer") or t.solution or t.feedback, source_ticket_id=t.id,
             reporter=_name(user), station=user.station, status="待审核")
    db.add(c)
    db.commit()
    return c.to_dict()


# ---------------- 案例库 ----------------
case_router = crud_router(Case, "/api/ops/cases", ops_dep, ("title", "question", "answer"),
                          ("status", "category", "station", "quality"))


@router.post("/cases/{cid}/audit")
def audit_case(cid: int, data: dict, db=Depends(get_db), user=Depends(require_roles())):
    c = db.get(Case, cid)
    c.status = "已通过" if data.get("approve") else "已驳回"
    c.audit_comment = data.get("comment", "")
    if "quality" in data:
        c.quality = bool(data["quality"])
    db.commit()
    return c.to_dict()


@router.get("/case-search")
def case_search(keyword: str = "", category: str = "", quality: int = 0, db=Depends(get_db), user=Depends(ops_dep)):
    """案例检索（仅已审核通过的案例），高质量案例优先"""
    q = db.query(Case).filter(Case.status == "已通过")
    if category:
        q = q.filter(Case.category == category)
    if quality:
        q = q.filter(Case.quality == True)  # noqa: E712
    if keyword:
        for w in keyword.split():
            like = "%%%s%%" % w
            q = q.filter(or_(Case.title.ilike(like), Case.question.ilike(like), Case.answer.ilike(like)))
    rows = q.order_by(Case.quality.desc(), Case.view_count.desc()).limit(30).all()
    return [r.to_dict() for r in rows]


@router.post("/cases/{cid}/view")
def view_case(cid: int, db=Depends(get_db), user=Depends(ops_dep)):
    c = db.get(Case, cid)
    c.view_count = (c.view_count or 0) + 1
    db.commit()
    return c.to_dict()


# ---------------- 运维人员移动端 ----------------
m = APIRouter(prefix="/api/mobile", tags=["运维移动端"])


@m.get("/tickets")
def my_tickets(tab: str = "todo", keyword: str = "", db=Depends(get_db), user=Depends(current_user)):
    """我的工单：todo 待办 / done 已办 / all 全部"""
    q = db.query(Ticket).filter(Ticket.assignee_id == user.id)
    if tab == "todo":
        q = q.filter(Ticket.status.in_(["待签收", "处理中", "挂起审核中"]))
    elif tab == "done":
        q = q.filter(Ticket.status.in_(["待评价", "已办结"]))
    if keyword:
        q = q.filter(or_(Ticket.title.ilike("%" + keyword + "%"), Ticket.ticket_no.ilike("%" + keyword + "%")))
    return [t.to_dict() for t in q.order_by(Ticket.id.desc()).limit(100)]


@m.get("/stats")
def my_stats(db=Depends(get_db), user=Depends(current_user)):
    base = db.query(Ticket).filter(Ticket.assignee_id == user.id)
    return {"to_sign": base.filter(Ticket.status == "待签收").count(),
            "processing": base.filter(Ticket.status == "处理中").count(),
            "suspending": base.filter(Ticket.status == "挂起审核中").count(),
            "done": base.filter(Ticket.status.in_(["待评价", "已办结"])).count()}


def _mine(db, tid, user, status=None):
    t = _get(db, tid)
    if t.assignee_id != user.id and user.role != "admin":
        raise HTTPException(403, "非本人工单")
    if status and t.status not in status:
        raise HTTPException(400, "当前状态(%s)不允许该操作" % t.status)
    return t


@m.post("/tickets/{tid}/sign")
def sign(tid: int, db=Depends(get_db), user=Depends(current_user)):
    t = _mine(db, tid, user, ["待签收"])
    t.status = "处理中"
    _log(db, t, "签收", user)
    db.commit()
    return t.to_dict()


@m.post("/tickets/{tid}/transfer")
def transfer(tid: int, data: dict, db=Depends(get_db), user=Depends(current_user)):
    """转派给本保障站其他运维人员或纳管的供应商/厂商运维人员"""
    t = _mine(db, tid, user, ["待签收", "处理中"])
    a = db.get(User, int(data["assignee_id"]))
    if a.station != user.station:
        raise HTTPException(400, "只能转派给本保障站人员")
    t.assignee_id, t.assignee_name, t.status = a.id, _name(a), "待签收"
    _log(db, t, "转派", user, "转派给 %s%s，原因：%s" % (_name(a), "(" + a.company + ")" if a.company else "",
                                                     data.get("reason", "")))
    db.commit()
    return t.to_dict()


@m.post("/tickets/{tid}/suspend")
def suspend(tid: int, data: dict, db=Depends(get_db), user=Depends(current_user)):
    t = _mine(db, tid, user, ["处理中"])
    t.status, t.suspend_reason, t.suspend_days = "挂起审核中", data.get("reason", ""), int(data.get("days", 1))
    _log(db, t, "申请挂起", user, "原因：%s，延期 %s 天" % (t.suspend_reason, t.suspend_days))
    db.commit()
    return t.to_dict()


@m.put("/tickets/{tid}/info")
def supplement_info(tid: int, data: dict, db=Depends(get_db), user=Depends(current_user)):
    """反馈前核验/补充工单基础信息"""
    t = _mine(db, tid, user, ["处理中", "待签收"])
    changed = []
    for k in ("title", "description", "category", "reporter", "reporter_phone", "dept", "address", "device_info"):
        if k in data and data[k] != getattr(t, k):
            changed.append(k)
            setattr(t, k, data[k])
    _log(db, t, "信息补充", user, "修改字段：" + ",".join(changed) if changed else "核验无误")
    db.commit()
    return t.to_dict()


@m.post("/tickets/{tid}/feedback")
def feedback(tid: int, data: dict, db=Depends(get_db), user=Depends(current_user)):
    t = _mine(db, tid, user, ["处理中"])
    t.solution, t.feedback, t.status = data.get("solution", ""), data.get("feedback", ""), "待评价"
    _log(db, t, "反馈", user, t.solution)
    db.commit()
    return t.to_dict()


@m.post("/tickets/supplement")
def supplement(data: dict, db=Depends(get_db), user=Depends(current_user)):
    """运维人员补录已解决但未登记的工单"""
    data = dict(data, assignee_id=user.id)
    t = create_ticket(db, dict(data, status="已办结"), user, source="移动补录")
    t.assignee_name, t.station = _name(user), user.station
    t.solution, t.feedback = data.get("solution", ""), data.get("feedback", "")
    db.commit()
    return t.to_dict()


@m.get("/colleagues")
def colleagues(db=Depends(get_db), user=Depends(current_user)):
    us = db.query(User).filter(User.station == user.station, User.role == "ops", User.id != user.id,
                               User.enabled == True).all()  # noqa: E712
    return [{"id": u.id, "name": _name(u), "company": u.company or "本站"} for u in us]
