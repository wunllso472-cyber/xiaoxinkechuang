"""通用工具：分页查询、字段类型转换、通用 CRUD 路由工厂、文件保存。"""
import datetime
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, Request
from sqlalchemy import or_, DateTime, Date, Integer, Float, Boolean

from .. import config
from ..db import get_db


def coerce(model, data):
    out = {}
    cols = {c.name: c for c in model.__table__.columns}
    for k, v in data.items():
        if k not in cols or k == "id" and v in (None, ""):
            continue
        t = cols[k].type
        if v == "" and not isinstance(t, (Boolean,)) and k != "id" and not hasattr(t, "length"):
            v = None
        if v is not None:
            if isinstance(t, DateTime) and isinstance(v, str):
                v = datetime.datetime.fromisoformat(v.replace("T", " ").replace("Z", "")[:19])
            elif isinstance(t, Date) and isinstance(v, str):
                v = datetime.date.fromisoformat(v[:10])
            elif isinstance(t, Integer) and not isinstance(v, bool):
                v = int(v)
            elif isinstance(t, Float):
                v = float(v)
            elif isinstance(t, Boolean):
                v = v in (True, 1, "1", "true", "True", "是")
        out[k] = v
    return out


def paginate(q, page=1, page_size=20, order=None):
    total = q.count()
    if order is not None:
        q = q.order_by(order)
    rows = q.offset((max(page, 1) - 1) * page_size).limit(page_size).all()
    return {"total": total, "items": [r.to_dict() for r in rows]}


def apply_filters(model, q, params, search_fields=(), filter_fields=()):
    kw = params.get("keyword")
    if kw and search_fields:
        q = q.filter(or_(*[getattr(model, f).ilike("%%%s%%" % kw) for f in search_fields]))
    for f in filter_fields:
        v = params.get(f)
        if v not in (None, ""):
            col = getattr(model, f)
            if isinstance(col.type, Boolean):
                v = v in ("1", "true", "True")
            q = q.filter(col == v)
    if params.get("start") and hasattr(model, "created_at"):
        q = q.filter(model.created_at >= params["start"])
    if params.get("end") and hasattr(model, "created_at"):
        q = q.filter(model.created_at <= params["end"] + " 23:59:59")
    return q


def crud_router(model, prefix, dep, search_fields=(), filter_fields=(), hidden=(), before_save=None, tags=None):
    """为简单实体生成 列表/详情/新增/修改/删除 接口"""
    r = APIRouter(prefix=prefix, tags=tags or [prefix])
    pk = list(model.__table__.primary_key.columns)[0]

    @r.get("")
    def list_items(request: Request, page: int = 1, page_size: int = 20, db=Depends(get_db), user=Depends(dep)):
        q = apply_filters(model, db.query(model), dict(request.query_params), search_fields, filter_fields)
        res = paginate(q, page, page_size, pk.desc())
        if hidden:
            for it in res["items"]:
                for h in hidden:
                    if it.get(h):
                        it[h] = "******"
        return res

    @r.get("/{item_id}")
    def get_item(item_id: str, db=Depends(get_db), user=Depends(dep)):
        obj = db.get(model, int(item_id) if isinstance(pk.type, Integer) else item_id)
        if not obj:
            raise HTTPException(404, "记录不存在")
        return obj.to_dict()

    @r.post("")
    def create_item(data: dict, db=Depends(get_db), user=Depends(dep)):
        data.pop("id", None) if isinstance(pk.type, Integer) else None
        vals = coerce(model, data)
        if before_save:
            vals = before_save(db, None, vals, user) or vals
        obj = model(**vals)
        db.add(obj)
        db.commit()
        return obj.to_dict()

    @r.put("/{item_id}")
    def update_item(item_id: str, data: dict, db=Depends(get_db), user=Depends(dep)):
        obj = db.get(model, int(item_id) if isinstance(pk.type, Integer) else item_id)
        if not obj:
            raise HTTPException(404, "记录不存在")
        vals = coerce(model, data)
        for h in hidden:
            if vals.get(h) == "******":
                vals.pop(h)
        if before_save:
            vals = before_save(db, obj, vals, user) or vals
        for k, v in vals.items():
            if k != pk.name:
                setattr(obj, k, v)
        db.commit()
        return obj.to_dict()

    @r.delete("/{item_id}")
    def delete_item(item_id: str, db=Depends(get_db), user=Depends(dep)):
        obj = db.get(model, int(item_id) if isinstance(pk.type, Integer) else item_id)
        if obj:
            db.delete(obj)
            db.commit()
        return {"ok": True}

    return r


def save_upload(file: UploadFile, sub, allow=None, max_mb=200):
    name = os.path.basename(file.filename or "file")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if allow and ext not in allow:
        raise HTTPException(400, "不支持的文件格式：%s，仅支持 %s" % (ext, "/".join(sorted(allow))))
    path = os.path.join(config.upload_dir(sub), "%s_%s" % (uuid.uuid4().hex[:8], name))
    size = 0
    with open(path, "wb") as f:
        while True:
            chunk = file.file.read(1 << 20)
            if not chunk:
                break
            size += len(chunk)
            if size > max_mb * 1024 * 1024:
                f.close()
                os.remove(path)
                raise HTTPException(400, "文件超过 %dMB" % max_mb)
            f.write(chunk)
    return path, name, ext, size
