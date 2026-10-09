"""工具与插件：内置工具使用、工具调度(链式调用)、工具性能评估、第三方插件接入"""
import datetime
import hashlib
import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Header
from sqlalchemy import func, case

from ..auth import admin_only
from ..db import get_db, Tool, ToolCallLog, SystemSetting
from ..services import tools as ts
from .client import actor
from .common import crud_router, save_upload

router = APIRouter(prefix="/api/tools", tags=["工具与插件"])
tool_router = crud_router(Tool, "/api/admin/tools", admin_only, ("name", "code", "description"),
                          ("kind", "protocol", "enabled"), hidden=("auth_value",))


@router.get("")
def list_tools(db=Depends(get_db), who=Depends(actor)):
    return [t.to_dict(exclude=("auth_value",)) for t in db.query(Tool).filter(Tool.enabled == True)]  # noqa: E712


@router.post("/upload")
def upload_file(file: UploadFile = File(...), who=Depends(actor)):
    """为图片识别等工具上传文件，返回服务器路径"""
    path, name, ext, size = save_upload(file, "tools", None, 50)
    return {"path": path, "name": name, "size": size}


@router.post("/invoke/{code}")
def invoke(code: str, data: dict, who=Depends(actor)):
    try:
        return {"ok": True, "result": ts.invoke(code, data.get("params") or {}, data.get("timeout"))}
    except Exception as e:  # noqa
        return {"ok": False, "error": str(e)}


@router.post("/chain")
def chain(data: dict, who=Depends(actor)):
    """链式调用：{"steps":[{"tool":"ocr","params":{"path":".."}},{"tool":"summary","params":{"text":"${steps.0.text}"}}]}"""
    return {"trace": ts.run_chain(data.get("steps", []), data.get("stop_on_error", True))}


@router.get("/metrics")
def metrics(days: int = 7, db=Depends(get_db), user=Depends(admin_only)):
    """工具性能评估：响应时间、成功率、调用量、P95、并发(峰值每分钟调用)、异常告警"""
    since = datetime.datetime.now() - datetime.timedelta(days=days)
    rows = db.query(ToolCallLog.tool_code, func.count(), func.avg(ToolCallLog.latency_ms),
                    func.sum(case((ToolCallLog.success == True, 1), else_=0)), func.max(ToolCallLog.latency_ms)) \
        .filter(ToolCallLog.created_at >= since).group_by(ToolCallLog.tool_code).all()  # noqa: E712
    names = {t.code: t.name for t in db.query(Tool)}
    tools, alerts = [], []
    for code, cnt, avg, ok, mx in rows:
        lat = sorted(r[0] for r in db.query(ToolCallLog.latency_ms).filter(
            ToolCallLog.tool_code == code, ToolCallLog.created_at >= since))
        p95 = lat[int(len(lat) * 0.95) - 1] if lat else 0
        rate = round((ok or 0) * 100.0 / cnt, 1) if cnt else 0
        tools.append({"code": code, "name": names.get(code, code), "calls": cnt, "avg_ms": int(avg or 0),
                      "p95_ms": p95, "max_ms": mx, "success_rate": rate})
        if rate < 90:
            alerts.append("工具【%s】成功率 %.1f%% 低于 90%%" % (names.get(code, code), rate))
        if p95 > 5000:
            alerts.append("工具【%s】P95 响应 %dms 超过 5s" % (names.get(code, code), p95))
    trend = []
    for i in range(days - 1, -1, -1):
        d = (datetime.datetime.now() - datetime.timedelta(days=i)).date()
        s = datetime.datetime.combine(d, datetime.time())
        r = db.query(func.count(), func.avg(ToolCallLog.latency_ms)).filter(
            ToolCallLog.created_at >= s, ToolCallLog.created_at < s + datetime.timedelta(days=1)).first()
        trend.append({"day": d.strftime("%m-%d"), "calls": r[0], "avg_ms": int(r[1] or 0)})
    errors = [e.to_dict() for e in db.query(ToolCallLog).filter(ToolCallLog.success == False)  # noqa: E712
              .order_by(ToolCallLog.id.desc()).limit(20)]
    try:
        import psutil
        res = {"cpu": psutil.cpu_percent(interval=0.2), "mem": psutil.virtual_memory().percent}
    except ImportError:
        res = {}
    return {"tools": tools, "trend": trend, "alerts": alerts, "errors": errors, "resource": res}


# ---------------- 开放平台：第三方插件自助注册 ----------------
open_router = APIRouter(prefix="/open/v1", tags=["开放平台"])


def _check_key(db, key):
    s = db.get(SystemSetting, "open_api_keys")
    keys = (s.value or []) if s else []
    if not key or hashlib.sha256(key.encode()).hexdigest() not in [k.get("hash") for k in keys]:
        raise HTTPException(401, "无效的 API Key")


@open_router.post("/plugins/register")
def register_plugin(data: dict, x_api_key: str = Header(default=""), db=Depends(get_db)):
    """第三方开发者通过 API Key 注册工具（协议：rest / graphql / websocket）"""
    _check_key(db, x_api_key)
    if data.get("protocol", "rest") not in ("rest", "graphql", "websocket"):
        raise HTTPException(400, "protocol 仅支持 rest/graphql/websocket")
    t = db.query(Tool).filter(Tool.code == data["code"]).first() or Tool(code=data["code"], kind="plugin")
    for k in ("name", "description", "protocol", "endpoint", "method", "auth_type", "auth_value", "params_schema",
              "timeout", "provider"):
        if k in data:
            setattr(t, k, data[k])
    t.enabled = False  # 注册后需管理员审核启用
    db.merge(t)
    db.commit()
    return {"ok": True, "message": "注册成功，待管理员审核启用"}


@open_router.post("/tools/{code}/invoke")
def open_invoke(code: str, data: dict, x_api_key: str = Header(default=""), db=Depends(get_db)):
    _check_key(db, x_api_key)
    try:
        return {"ok": True, "result": ts.invoke(code, data.get("params") or {})}
    except Exception as e:  # noqa
        return {"ok": False, "error": str(e)}


@router.post("/api-keys")
def create_key(data: dict, db=Depends(get_db), user=Depends(admin_only)):
    key = "xx-" + os.urandom(16).hex()
    s = db.get(SystemSetting, "open_api_keys") or SystemSetting(key="open_api_keys", value=[])
    s.value = list(s.value or []) + [{"name": data.get("name", "第三方"), "hash": hashlib.sha256(key.encode()).hexdigest(),
                                     "prefix": key[:8], "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}]
    db.merge(s)
    db.commit()
    return {"key": key, "message": "请妥善保存，密钥只显示一次"}


@router.get("/api-keys")
def list_keys(db=Depends(get_db), user=Depends(admin_only)):
    s = db.get(SystemSetting, "open_api_keys")
    return [{k: v for k, v in it.items() if k != "hash"} for it in ((s.value or []) if s else [])]


@router.delete("/api-keys/{prefix}")
def delete_key(prefix: str, db=Depends(get_db), user=Depends(admin_only)):
    s = db.get(SystemSetting, "open_api_keys")
    if s:
        s.value = [k for k in (s.value or []) if k["prefix"] != prefix]
        db.commit()
    return {"ok": True}
