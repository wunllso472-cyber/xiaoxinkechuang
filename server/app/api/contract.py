"""合同智审：上传(PDF/OFD/Word/Excel/PPT)、解析、要素提取、模板差异、规则审查"""
import os
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import FileResponse
from sqlalchemy import func

from ..auth import admin_only
from ..db import get_db, SessionLocal, Contract, ContractTemplate, ReviewRule
from ..services import contract as cs, docparse
from .client import actor
from .common import save_upload, paginate, apply_filters, crud_router

router = APIRouter(prefix="/api/contract", tags=["合同智审"])
ALLOW = {"pdf", "ofd", "docx", "xlsx", "pptx", "txt", "png", "jpg", "jpeg"}

template_router = crud_router(ContractTemplate, "/api/contract/templates", admin_only, ("name", "category"),
                              ("category", "industry"))
rule_router = crud_router(ReviewRule, "/api/contract/rules", admin_only, ("name", "code", "description"),
                          ("category", "rule_type", "level", "enabled"))


def analyze(cid, use_llm=False):
    db = SessionLocal()
    c = db.get(Contract, cid)
    t0 = time.time()
    try:
        c.status = "解析中"
        db.commit()
        parsed = docparse.parse_file(c.file_path)
        text = docparse.clean_text(parsed["text"])
        clauses = cs.split_clauses(text)
        c.text = text
        c.structure = {"clauses": clauses, "tables": parsed["tables"][:10], "images": parsed.get("images", 0),
                       "blocks": len(parsed["blocks"])}
        elements = cs.extract_elements(text)
        if use_llm:
            for k, v in cs.llm_extract(text).items():
                key = {"合同金额": "合同金额(小写)", "争议解决": "争议解决/管辖地"}.get(k, k)
                if v and not elements.get(key):
                    elements[key] = v
        c.elements = {"elements": elements, "entities": cs.extract_entities(text)}
        tpl = db.get(ContractTemplate, c.template_id) if c.template_id else db.query(ContractTemplate).first()
        if tpl:
            c.template_id = tpl.id
            c.diff = {"template": tpl.name, "items": cs.compare_template(text, clauses, tpl)}
        rules = db.query(ReviewRule).filter(ReviewRule.enabled == True).all()  # noqa: E712
        if not use_llm:
            rules = [r for r in rules if r.rule_type != "llm"]
        items, risk = cs.review(text, elements, rules)
        for it in items:
            if not it["passed"]:
                r = db.get(ReviewRule, it["rule_id"])
                r.hit_count = (r.hit_count or 0) + 1
        c.review = {"items": items, "failed": sum(1 for i in items if not i["passed"]), "total": len(items)}
        c.risk_level, c.status = risk, "已完成"
    except Exception as e:  # noqa
        c.status, c.review = "失败", {"error": str(e)}
    c.duration_ms = int((time.time() - t0) * 1000)
    db.commit()
    db.close()


@router.post("/upload")
def upload(file: UploadFile = File(...), template_id: int = Form(0), use_llm: int = Form(0),
           db=Depends(get_db), who=Depends(actor)):
    path, name, ext, size = save_upload(file, "contract", ALLOW, 100)
    c = Contract(filename=name, file_path=path, file_type=ext, uploader=who.name, template_id=template_id or None)
    db.add(c)
    db.commit()
    threading.Thread(target=analyze, args=(c.id, bool(use_llm)), daemon=True).start()
    return c.to_dict(exclude=("text",))


@router.get("")
def list_contracts(request: Request, page: int = 1, page_size: int = 20, db=Depends(get_db), who=Depends(actor)):
    q = db.query(Contract)
    if not who.user:
        q = q.filter(Contract.uploader == who.name)
    q = apply_filters(Contract, q, dict(request.query_params), ("filename", "uploader"), ("risk_level", "status"))
    res = paginate(q, page, page_size, Contract.id.desc())
    for i in res["items"]:
        for k in ("text", "structure", "elements", "diff"):
            i.pop(k, None)
        i["failed"] = (i.pop("review") or {}).get("failed")
    return res


@router.get("/stats")
def stats(db=Depends(get_db), user=Depends(admin_only)):
    """规则效果监控：命中率、误报率；审核效率"""
    total = db.query(Contract).filter(Contract.status == "已完成").count() or 1
    rules = [{"code": r.code, "name": r.name, "hit": r.hit_count or 0, "hit_rate": round((r.hit_count or 0) * 100.0 / total, 1),
              "false_positive": r.false_positive or 0,
              "fp_rate": round((r.false_positive or 0) * 100.0 / r.hit_count, 1) if r.hit_count else 0}
             for r in db.query(ReviewRule).order_by(ReviewRule.code)]
    avg = db.query(func.avg(Contract.duration_ms)).scalar() or 0
    risk = dict(db.query(Contract.risk_level, func.count()).group_by(Contract.risk_level).all())
    return {"contracts": total, "avg_ms": int(avg), "risk": risk, "rules": rules}


@router.get("/{cid}")
def detail(cid: int, db=Depends(get_db), who=Depends(actor)):
    c = db.get(Contract, cid)
    if not c:
        raise HTTPException(404, "合同不存在")
    return c.to_dict()


@router.get("/{cid}/file")
def file(cid: int, db=Depends(get_db), who=Depends(actor)):
    c = db.get(Contract, cid)
    return FileResponse(c.file_path, filename=c.filename)


@router.post("/{cid}/reanalyze")
def reanalyze(cid: int, data: dict, db=Depends(get_db), who=Depends(actor)):
    c = db.get(Contract, cid)
    if data.get("template_id"):
        c.template_id = int(data["template_id"])
        db.commit()
    threading.Thread(target=analyze, args=(cid, bool(data.get("use_llm"))), daemon=True).start()
    return {"ok": True}


@router.post("/{cid}/false-positive")
def false_positive(cid: int, data: dict, db=Depends(get_db), who=Depends(actor)):
    """标记误报，用于规则误报率统计"""
    r = db.get(ReviewRule, int(data["rule_id"]))
    r.false_positive = (r.false_positive or 0) + 1
    c = db.get(Contract, cid)
    rv = dict(c.review or {})
    for it in rv.get("items", []):
        if it["rule_id"] == r.id:
            it["false_positive"] = True
    c.review = rv
    db.commit()
    return {"ok": True}


@router.delete("/{cid}")
def delete(cid: int, db=Depends(get_db), user=Depends(admin_only)):
    c = db.get(Contract, cid)
    if c:
        if os.path.exists(c.file_path):
            os.remove(c.file_path)
        db.delete(c)
        db.commit()
    return {"ok": True}


# ---------------- 规则导入导出/版本 ----------------
rules_extra = APIRouter(prefix="/api/contract-rules", tags=["合同智审"])


@rules_extra.get("/export")
def export_rules(db=Depends(get_db), user=Depends(admin_only)):
    return [r.to_dict(exclude=("id", "hit_count", "false_positive")) for r in db.query(ReviewRule).order_by(ReviewRule.code)]


@rules_extra.post("/import")
def import_rules(data: dict, db=Depends(get_db), user=Depends(admin_only)):
    n = 0
    for it in data.get("rules", []):
        r = db.query(ReviewRule).filter(ReviewRule.code == it.get("code")).first()
        if r:
            for k in ("name", "category", "rule_type", "params", "level", "enabled", "description"):
                if k in it:
                    setattr(r, k, it[k])
            r.version = (r.version or 1) + 1
        else:
            db.add(ReviewRule(**{k: v for k, v in it.items() if hasattr(ReviewRule, k) and k != "id"}))
        n += 1
    db.commit()
    return {"imported": n}


@rules_extra.post("/test")
def test_rule(data: dict, user=Depends(admin_only)):
    """规则编辑器即时测试"""
    class R:
        pass
    r = R()
    r.rule_type, r.params = data["rule_type"], data.get("params") or {}
    text = data.get("text", "")
    ok, msg = cs.run_rule(r, text, cs.extract_elements(text))
    return {"passed": ok, "message": msg}
