"""向量化 + 检索增强生成（RAG）。

- 向量化：local（内置字符 n-gram 哈希向量，零依赖）或 api（BGE / m3e 等 OpenAI 兼容 embedding 服务）
- 向量存储：PostgreSQL 表 kb_chunk（向量以 JSON 存储，检索时 numpy 计算余弦相似度；数据量很大时可换 pgvector）
- 检索：语义检索 / 关键词检索(BM25) / 混合检索，相似度阈值、去重合并、重排序
"""
import hashlib
import math
import os
import re
import threading
import time
from collections import Counter

import httpx
import numpy as np

from .. import config
from ..db import SessionLocal, KnowledgeChunk, KnowledgeDoc, ImportLog, RagLog, SystemSetting
from . import docparse

DIM = int(config.get("embedding.dim", 512))


def rag_cfg(key, default=None):
    db = SessionLocal()
    try:
        s = db.get(SystemSetting, "rag")
        if s and s.value and key in s.value:
            return s.value[key]
    finally:
        db.close()
    return config.get("rag." + key, default)


# ---------------- 向量化 ----------------
def _tokens(text):
    text = text.lower()
    words = re.findall(r"[a-z0-9_.]+", text)
    han = re.findall(r"[一-龥]", text)
    grams = [han[i] + han[i + 1] for i in range(len(han) - 1)]
    return words + han + grams


def _local_embed(text):
    v = np.zeros(DIM, dtype=np.float32)
    for tok, cnt in Counter(_tokens(text)).items():
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        v[h % DIM] += (1 if (h >> 8) & 1 else -1) * (1 + math.log(cnt))
    n = np.linalg.norm(v)
    return (v / n).tolist() if n else v.tolist()


def embed(texts):
    if config.get("embedding.provider", "local") == "api":
        r = httpx.post(config.get("embedding.base_url").rstrip("/") + "/embeddings",
                       headers={"Authorization": "Bearer " + (config.get("embedding.api_key") or "")},
                       json={"model": config.get("embedding.model"), "input": texts}, timeout=120)
        r.raise_for_status()
        return [d["embedding"] for d in r.json()["data"]]
    return [_local_embed(t) for t in texts]


# ---------------- 索引缓存 ----------------
_cache = {}
_lock = threading.Lock()


def invalidate(kb_id):
    with _lock:
        _cache.pop(kb_id, None)


def _load_index(kb_id):
    with _lock:
        if kb_id in _cache:
            return _cache[kb_id]
    db = SessionLocal()
    try:
        rows = db.query(KnowledgeChunk.id, KnowledgeChunk.doc_id, KnowledgeChunk.content, KnowledgeChunk.vector) \
            .filter(KnowledgeChunk.kb_id == kb_id).all()
        docs = {d.id: d.filename for d in db.query(KnowledgeDoc).filter(KnowledgeDoc.kb_id == kb_id)}
    finally:
        db.close()
    items = [{"id": r[0], "doc_id": r[1], "content": r[2], "filename": docs.get(r[1], "")} for r in rows]
    mat = np.array([r[3] for r in rows], dtype=np.float32) if rows else np.zeros((0, DIM), dtype=np.float32)
    toks = [Counter(_tokens(i["content"])) for i in items]
    df = Counter()
    for t in toks:
        df.update(t.keys())
    avgdl = (sum(sum(t.values()) for t in toks) / len(toks)) if toks else 1
    idx = {"items": items, "mat": mat, "toks": toks, "df": df, "avgdl": avgdl}
    with _lock:
        _cache[kb_id] = idx
    return idx


def _bm25(idx, query):
    q = set(_tokens(query))
    n = len(idx["items"])
    scores = np.zeros(n, dtype=np.float32)
    for i, tf in enumerate(idx["toks"]):
        dl = sum(tf.values()) or 1
        s = 0.0
        for t in q:
            if t in tf:
                idf = math.log(1 + (n - idx["df"][t] + 0.5) / (idx["df"][t] + 0.5))
                s += idf * tf[t] * 2.2 / (tf[t] + 1.2 * (0.25 + 0.75 * dl / idx["avgdl"]))
        scores[i] = s
    if scores.size and scores.max() > 0:
        scores = scores / scores.max()
    return scores


def search(kb_ids, query, top_k=None, mode=None, threshold=None):
    top_k = top_k or int(rag_cfg("top_k", 5))
    mode = mode or rag_cfg("search_mode", "hybrid")
    threshold = float(threshold if threshold is not None else rag_cfg("score_threshold", 0.05))
    alpha = float(rag_cfg("hybrid_alpha", 0.6))
    if isinstance(kb_ids, int):
        kb_ids = [kb_ids]
    qv = np.array(embed([query])[0], dtype=np.float32)
    results = []
    for kb_id in kb_ids:
        idx = _load_index(kb_id)
        if not idx["items"]:
            continue
        vs = idx["mat"] @ qv if mode != "keyword" else np.zeros(len(idx["items"]))
        ks = _bm25(idx, query) if mode != "vector" else np.zeros(len(idx["items"]))
        if mode == "vector":
            score = vs
        elif mode == "keyword":
            score = ks
        else:
            score = alpha * vs + (1 - alpha) * ks
        order = np.argsort(-score)[: top_k * 3]
        for i in order:
            if score[i] < threshold:
                continue
            it = idx["items"][i]
            results.append(dict(it, kb_id=kb_id, score=round(float(score[i]), 4),
                                vector_score=round(float(vs[i]), 4), keyword_score=round(float(ks[i]), 4)))
    # 融合：去重合并（内容高度重复的片段只保留一个）+ 重排序
    results.sort(key=lambda r: -r["score"])
    merged, seen = [], []
    for r in results:
        sig = set(_tokens(r["content"][:200]))
        if any(len(sig & s) / max(len(sig | s), 1) > 0.8 for s in seen):
            continue
        seen.append(sig)
        merged.append(r)
    q = set(_tokens(query))
    for r in merged:  # 重排序：叠加查询词覆盖率
        cover = len(q & set(_tokens(r["content"]))) / max(len(q), 1)
        r["rerank_score"] = round(r["score"] * 0.7 + cover * 0.3, 4)
    merged.sort(key=lambda r: -r["rerank_score"])
    return merged[:top_k]


def build_prompt(query, hits):
    ctx = "\n\n".join("[%d]（来源：%s）%s" % (i + 1, h["filename"], h["content"]) for i, h in enumerate(hits))
    return ("请根据以下参考资料回答用户问题。若资料中没有相关信息，请如实说明，不要编造。回答时注明引用编号。\n\n"
            "参考资料：\n%s\n\n用户问题：%s" % (ctx, query))


def log_rag(query, kb_id, mode, hits, retrieve_ms, generate_ms=0):
    db = SessionLocal()
    try:
        r = RagLog(query=query[:2000], kb_id=kb_id, mode=mode or rag_cfg("search_mode", "hybrid"),
                   hit_count=len(hits), top_score=hits[0]["score"] if hits else 0,
                   retrieve_ms=retrieve_ms, generate_ms=generate_ms)
        db.add(r)
        db.commit()
        return r.id
    finally:
        db.close()


# ---------------- 知识导入流水线 ----------------
TAG_RULES = {
    "操作系统": ["麒麟", "统信", "uos", "kylin", "操作系统", "内核", "grub", "启动"],
    "办公软件": ["wps", "office", "文档", "表格", "永中"],
    "打印外设": ["打印机", "扫描仪", "驱动", "外设", "打印"],
    "网络": ["网络", "ip", "dns", "网卡", "vpn", "无线", "wifi"],
    "数据库中间件": ["数据库", "达梦", "人大金仓", "中间件", "东方通", "postgres"],
    "安全": ["杀毒", "病毒", "360", "奇安信", "安恒", "漏洞", "安全"],
    "硬件": ["cpu", "内存", "硬盘", "主板", "飞腾", "鲲鹏", "海光", "兆芯", "龙芯"],
    "政策法规": ["政策", "通知", "办法", "规定", "条例", "意见", "法规", "文件"],
}


def auto_tags(text):
    low = text.lower()
    scores = {tag: sum(low.count(k) for k in kws) for tag, kws in TAG_RULES.items()}
    return [t for t, s in sorted(scores.items(), key=lambda x: -x[1]) if s > 0][:3]


def _ilog(db, doc_id, msg, level="INFO"):
    db.add(ImportLog(doc_id=doc_id, level=level, message=msg))
    db.commit()


def process_doc(doc_id):
    """解析 → 清洗 → 切分 → 质量过滤/去重 → 向量化 → 入库；失败自动重试，已完成的分片不重复处理（断点续传）"""
    db = SessionLocal()
    doc = db.get(KnowledgeDoc, doc_id)
    if not doc:
        db.close()
        return
    try:
        doc.status, doc.progress = "处理中", 5
        db.commit()
        _ilog(db, doc.id, "开始解析 %s" % doc.filename)
        parsed = docparse.parse_file(doc.file_path)
        text = docparse.clean_text(parsed["text"])
        doc.progress = 30
        db.commit()
        _ilog(db, doc.id, "解析完成，文本长度 %d，图片 %d" % (len(text), parsed.get("images", 0)))
        chunks = docparse.split_chunks(text, int(rag_cfg("chunk_size", 500)), int(rag_cfg("chunk_overlap", 80)))
        done = db.query(KnowledgeChunk.seq).filter(KnowledgeChunk.doc_id == doc.id).all()
        done_seq = {d[0] for d in done}
        if done_seq:
            _ilog(db, doc.id, "断点续传：已存在 %d 个分片，跳过" % len(done_seq))
        seen, filtered, todo = set(), 0, []
        for i, c in enumerate(chunks):
            h = hashlib.md5(c.encode()).hexdigest()
            if docparse.is_low_quality(c) or h in seen:
                filtered += 1
                continue
            seen.add(h)
            if i not in done_seq:
                todo.append((i, c))
        batch = 32
        for b in range(0, len(todo), batch):
            part = todo[b:b + batch]
            vecs = embed([c for _, c in part])
            for (i, c), v in zip(part, vecs):
                db.add(KnowledgeChunk(kb_id=doc.kb_id, doc_id=doc.id, seq=i, content=c, vector=v))
            doc.progress = 30 + int(65 * (b + len(part)) / max(len(todo), 1))
            db.commit()
        doc.chunk_count = db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == doc.id).count()
        doc.filtered_count = filtered
        if not doc.tags:
            doc.tags = ",".join(auto_tags(text[:20000]))
        doc.status, doc.progress, doc.error = "完成", 100, ""
        db.commit()
        _ilog(db, doc.id, "入库完成：有效分片 %d，过滤无效/重复 %d，标签 %s" % (doc.chunk_count, filtered, doc.tags))
        invalidate(doc.kb_id)
    except Exception as e:  # noqa
        db.rollback()
        doc.retry = (doc.retry or 0) + 1
        doc.status, doc.error = "失败", str(e)[:500]
        db.commit()
        _ilog(db, doc.id, "处理失败(第%d次)：%s" % (doc.retry, e), "ERROR")
        if doc.retry < 3:
            time.sleep(2)
            db.close()
            return process_doc(doc_id)
    finally:
        db.close()


def process_async(doc_id):
    threading.Thread(target=process_doc, args=(doc_id,), daemon=True).start()


def remove_doc_chunks(db, doc):
    db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == doc.id).delete()
    invalidate(doc.kb_id)


def file_md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def ext_of(name):
    return os.path.splitext(name)[1].lstrip(".").lower()
