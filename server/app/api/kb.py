"""信创知识库管理：知识导入、版本、标签、预处理、RAG 检索与检索质量监控"""
import datetime
import os
import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from sqlalchemy import func

from .. import config
from ..auth import admin_only
from ..db import get_db, KnowledgeBase, KnowledgeDoc, KnowledgeChunk, ImportLog, RagLog, SystemSetting
from ..services import rag, docparse
from .client import actor
from .common import save_upload, paginate, apply_filters

router = APIRouter(prefix="/api/kb", tags=["知识库"])


@router.get("/bases")
def bases(db=Depends(get_db), who=Depends(actor)):
    q = db.query(KnowledgeBase)
    if not (who.user and who.user.role == "admin"):
        q = q.filter(KnowledgeBase.owner.in_(["public", who.device_id or who.key]))
    out = []
    for k in q.order_by(KnowledgeBase.id).all():
        d = k.to_dict()
        d["doc_count"] = db.query(KnowledgeDoc).filter(KnowledgeDoc.kb_id == k.id, KnowledgeDoc.is_latest == True).count()  # noqa
        d["chunk_count"] = db.query(KnowledgeChunk).filter(KnowledgeChunk.kb_id == k.id).count()
        out.append(d)
    return out


@router.post("/bases")
def create_base(data: dict, db=Depends(get_db), who=Depends(actor)):
    owner = "public" if (who.user and who.user.role == "admin" and not data.get("private")) else (who.device_id or who.key)
    k = KnowledgeBase(name=data["name"], description=data.get("description", ""), owner=owner)
    db.add(k)
    db.commit()
    return k.to_dict()


@router.put("/bases/{kid}")
def update_base(kid: int, data: dict, db=Depends(get_db), user=Depends(admin_only)):
    k = db.get(KnowledgeBase, kid)
    k.name, k.description = data.get("name", k.name), data.get("description", k.description)
    db.commit()
    return k.to_dict()


@router.delete("/bases/{kid}")
def delete_base(kid: int, db=Depends(get_db), user=Depends(admin_only)):
    db.query(KnowledgeChunk).filter(KnowledgeChunk.kb_id == kid).delete()
    db.query(KnowledgeDoc).filter(KnowledgeDoc.kb_id == kid).delete()
    k = db.get(KnowledgeBase, kid)
    if k:
        db.delete(k)
    db.commit()
    rag.invalidate(kid)
    return {"ok": True}


def _check_kb(db, kid, who):
    k = db.get(KnowledgeBase, kid)
    if not k:
        raise HTTPException(404, "知识库不存在")
    if k.owner == "public" and not (who.user and who.user.role == "admin"):
        raise HTTPException(403, "公共知识库仅管理员可维护")
    if k.owner != "public" and k.owner not in (who.device_id, who.key) and not (who.user and who.user.role == "admin"):
        raise HTTPException(403, "无权限")
    return k


@router.post("/bases/{kid}/docs")
def upload_docs(kid: int, files: List[UploadFile] = File(...), tags: str = Form(""), db=Depends(get_db),
                who=Depends(actor)):
    """批量导入：MD5 冲突检测（重复文件跳过）；同名文件自动生成新版本并保留历史版本"""
    _check_kb(db, kid, who)
    result = []
    for f in files:
        path, name, ext, size = save_upload(f, "kb", docparse.SUPPORTED)
        md5 = rag.file_md5(path)
        dup = db.query(KnowledgeDoc).filter(KnowledgeDoc.kb_id == kid, KnowledgeDoc.md5 == md5).first()
        if dup:
            os.remove(path)
            result.append({"filename": name, "status": "冲突：内容与已有文档《%s》v%d 相同，已跳过" % (dup.filename, dup.version)})
            continue
        old = db.query(KnowledgeDoc).filter(KnowledgeDoc.kb_id == kid, KnowledgeDoc.filename == name,
                                            KnowledgeDoc.is_latest == True).first()  # noqa: E712
        version = 1
        if old:  # 增量更新：旧版本下线，新版本入库
            old.is_latest = False
            rag.remove_doc_chunks(db, old)
            version = old.version + 1
        d = KnowledgeDoc(kb_id=kid, filename=name, file_path=path, file_type=ext, size=size, md5=md5,
                         version=version, tags=tags, parent_id=old.id if old else None)
        db.add(d)
        db.commit()
        if old:
            db.add(ImportLog(doc_id=d.id, message="检测到同名文档，生成新版本 v%d（历史版本 #%d 已下线）" % (version, old.id)))
            db.commit()
        rag.process_async(d.id)
        result.append({"filename": name, "id": d.id, "version": version, "status": "已加入处理队列"})
    return result


@router.get("/bases/{kid}/docs")
def docs(kid: int, request: Request, page: int = 1, page_size: int = 20, history: int = 0, db=Depends(get_db),
         who=Depends(actor)):
    q = db.query(KnowledgeDoc).filter(KnowledgeDoc.kb_id == kid)
    if not history:
        q = q.filter(KnowledgeDoc.is_latest == True)  # noqa: E712
    q = apply_filters(KnowledgeDoc, q, dict(request.query_params), ("filename", "tags"), ("status", "file_type"))
    return paginate(q, page, page_size, KnowledgeDoc.id.desc())


@router.get("/docs/{did}/versions")
def versions(did: int, db=Depends(get_db), who=Depends(actor)):
    d = db.get(KnowledgeDoc, did)
    rows = db.query(KnowledgeDoc).filter(KnowledgeDoc.kb_id == d.kb_id, KnowledgeDoc.filename == d.filename) \
        .order_by(KnowledgeDoc.version.desc()).all()
    return [r.to_dict() for r in rows]


@router.post("/docs/{did}/rollback")
def rollback(did: int, db=Depends(get_db), user=Depends(admin_only)):
    """历史版本追溯：将指定历史版本恢复为当前版本"""
    d = db.get(KnowledgeDoc, did)
    for o in db.query(KnowledgeDoc).filter(KnowledgeDoc.kb_id == d.kb_id, KnowledgeDoc.filename == d.filename,
                                           KnowledgeDoc.is_latest == True):  # noqa: E712
        o.is_latest = False
        rag.remove_doc_chunks(db, o)
    d.is_latest = True
    d.status = "待处理"
    db.add(ImportLog(doc_id=d.id, message="回滚到 v%d" % d.version))
    db.commit()
    rag.process_async(d.id)
    return {"ok": True}


@router.get("/docs/{did}/logs")
def logs(did: int, db=Depends(get_db), who=Depends(actor)):
    return [l.to_dict() for l in db.query(ImportLog).filter(ImportLog.doc_id == did).order_by(ImportLog.id)]


@router.get("/docs/{did}/chunks")
def chunks(did: int, db=Depends(get_db), who=Depends(actor)):
    return [{"seq": c.seq, "content": c.content} for c in
            db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == did).order_by(KnowledgeChunk.seq).limit(200)]


@router.post("/docs/{did}/retry")
def retry(did: int, db=Depends(get_db), who=Depends(actor)):
    """错误重试 / 断点续传"""
    d = db.get(KnowledgeDoc, did)
    d.retry, d.status = 0, "待处理"
    db.commit()
    rag.process_async(did)
    return {"ok": True}


@router.put("/docs/{did}/tags")
def set_tags(did: int, data: dict, db=Depends(get_db), user=Depends(admin_only)):
    """人工校验分类标签"""
    d = db.get(KnowledgeDoc, did)
    d.tags, d.tag_checked = data.get("tags", ""), True
    db.commit()
    return d.to_dict()


@router.delete("/docs/{did}")
def delete_doc(did: int, db=Depends(get_db), who=Depends(actor)):
    d = db.get(KnowledgeDoc, did)
    if d:
        _check_kb(db, d.kb_id, who)
        rag.remove_doc_chunks(db, d)
        db.delete(d)
        db.commit()
    return {"ok": True}


@router.get("/import-progress")
def import_progress(kb_id: int = 0, db=Depends(get_db), who=Depends(actor)):
    q = db.query(KnowledgeDoc).filter(KnowledgeDoc.status.in_(["待处理", "处理中", "失败"]))
    if kb_id:
        q = q.filter(KnowledgeDoc.kb_id == kb_id)
    return [{"id": d.id, "filename": d.filename, "status": d.status, "progress": d.progress, "error": d.error}
            for d in q.all()]


# ---------------- 检索 ----------------
@router.post("/search")
def search(data: dict, who=Depends(actor)):
    """检索测试：可指定 mode(vector/keyword/hybrid)、top_k、threshold"""
    t0 = time.time()
    hits = rag.search(data.get("kb_ids") or [1], data["query"], data.get("top_k"), data.get("mode"), data.get("threshold"))
    ms = int((time.time() - t0) * 1000)
    rag.log_rag(data["query"], (data.get("kb_ids") or [1])[0], data.get("mode"), hits, ms)
    return {"ms": ms, "hits": hits}


@router.get("/settings")
def get_settings(db=Depends(get_db), who=Depends(actor)):
    keys = ("chunk_size", "chunk_overlap", "top_k", "score_threshold", "search_mode", "hybrid_alpha")
    return {k: rag.rag_cfg(k) for k in keys}


@router.put("/settings")
def put_settings(data: dict, db=Depends(get_db), user=Depends(admin_only)):
    """相似度阈值动态调整等检索参数，即时生效"""
    s = db.get(SystemSetting, "rag") or SystemSetting(key="rag", value={})
    v = dict(s.value or {})
    v.update(data)
    s.value = v
    db.merge(s)
    db.commit()
    return v


@router.post("/feedback/{log_id}")
def rag_feedback(log_id: int, data: dict, db=Depends(get_db), who=Depends(actor)):
    r = db.get(RagLog, log_id)
    if r:
        r.feedback = int(data.get("value", 0))
        db.commit()
    return {"ok": True}


@router.post("/evaluate")
def evaluate(data: dict, user=Depends(admin_only)):
    """检索质量评估：cases=[{"query":..,"expected":"期望命中的文件名或关键词"}]，计算召回率/精确率"""
    kb_ids = data.get("kb_ids") or [1]
    res, recall_hit, precision_sum = [], 0, 0.0
    for c in data.get("cases", []):
        hits = rag.search(kb_ids, c["query"], data.get("top_k"), data.get("mode"))
        exp = c.get("expected", "")
        rel = [h for h in hits if exp and (exp in h["filename"] or exp in h["content"])]
        recall_hit += 1 if rel else 0
        precision_sum += len(rel) / len(hits) if hits else 0
        res.append({"query": c["query"], "hits": len(hits), "relevant": len(rel)})
    n = max(len(data.get("cases", [])), 1)
    return {"recall": round(recall_hit * 100.0 / n, 1), "precision": round(precision_sum * 100.0 / n, 1), "details": res}


@router.get("/metrics")
def metrics(days: int = 7, db=Depends(get_db), user=Depends(admin_only)):
    """RAG 链路监控：检索耗时、命中数、最高相似度、用户反馈"""
    since = datetime.datetime.now() - datetime.timedelta(days=days)
    q = db.query(RagLog).filter(RagLog.created_at >= since)
    agg = q.with_entities(func.count(), func.avg(RagLog.retrieve_ms), func.avg(RagLog.top_score),
                          func.avg(RagLog.hit_count)).first()
    zero = q.filter(RagLog.hit_count == 0).count()
    up = q.filter(RagLog.feedback == 1).count()
    down = q.filter(RagLog.feedback == -1).count()
    trend = []
    for i in range(days - 1, -1, -1):
        d = (datetime.datetime.now() - datetime.timedelta(days=i)).date()
        s = datetime.datetime.combine(d, datetime.time())
        r = db.query(func.count(), func.avg(RagLog.retrieve_ms), func.avg(RagLog.top_score)).filter(
            RagLog.created_at >= s, RagLog.created_at < s + datetime.timedelta(days=1)).first()
        trend.append({"day": d.strftime("%m-%d"), "count": r[0], "avg_ms": round(r[1] or 0, 1),
                      "avg_score": round(r[2] or 0, 3)})
    recent = [r.to_dict() for r in q.order_by(RagLog.id.desc()).limit(20)]
    return {"count": agg[0], "avg_ms": round(agg[1] or 0, 1), "avg_top_score": round(agg[2] or 0, 3),
            "avg_hits": round(agg[3] or 0, 1), "zero_hit_rate": round(zero * 100.0 / agg[0], 1) if agg[0] else 0,
            "satisfaction": round(up * 100.0 / (up + down), 1) if (up + down) else None,
            "trend": trend, "recent": recent, "embedding": config.get("embedding.provider")}
