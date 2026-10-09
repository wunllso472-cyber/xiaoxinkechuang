"""智能问答 + 模型管理 + 模型优化"""
import datetime
import json
import re
import threading
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy import func, case

from .. import config
from ..auth import admin_only
from ..db import (get_db, SessionLocal, LLMModel, LLMCallLog, SystemSetting, ChatSession, ChatMessage, Intent,
                  FtDataset, FtJob, EvalSet, EvalRun, KnowledgeBase)
from ..llm import router as llm
from ..services import rag, finetune
from .client import actor
from .common import crud_router, save_upload, paginate

router = APIRouter(prefix="/api", tags=["智能问答/模型"])

# ======================= 模型管理 =======================
model_router = crud_router(LLMModel, "/api/admin/models", admin_only, ("name", "model", "provider"),
                           ("provider", "enabled"), hidden=("api_key",))


@router.get("/models/available")
def available_models(db=Depends(get_db), who=Depends(actor)):
    """供客户端/前端选择的模型列表（不含密钥）"""
    ms = db.query(LLMModel).filter(LLMModel.enabled == True).order_by(LLMModel.priority).all()  # noqa: E712
    return [{"id": m.id, "name": m.name, "provider": m.provider, "is_default": m.is_default} for m in ms]


@router.get("/admin/route")
def get_route(db=Depends(get_db), user=Depends(admin_only)):
    s = db.get(SystemSetting, "route_strategy")
    return {"strategy": s.value if s else "priority",
            "options": [{"value": "priority", "label": "优先级 + 自动降级"}, {"value": "round_robin", "label": "轮询"},
                        {"value": "weighted", "label": "加权随机"}, {"value": "scene", "label": "按业务场景"}]}


@router.put("/admin/route")
def set_route(data: dict, db=Depends(get_db), user=Depends(admin_only)):
    s = db.get(SystemSetting, "route_strategy") or SystemSetting(key="route_strategy")
    s.value = data["strategy"]
    db.merge(s)
    db.commit()
    return {"ok": True}


@router.post("/admin/models/{mid}/health")
def model_health(mid: int, db=Depends(get_db), user=Depends(admin_only)):
    m = db.get(LLMModel, mid)
    r = llm.health_check(m)
    m.health, m.last_check = ("健康" if r["ok"] else "异常"), datetime.datetime.now()
    db.commit()
    return r


@router.post("/admin/models/{mid}/test")
def model_test(mid: int, data: dict, user=Depends(admin_only)):
    start = time.time()
    try:
        r = llm.chat([{"role": "user", "content": data.get("prompt", "你好")}], model_id=mid, params=data.get("params"))
        return {"ok": True, "content": r["content"], "model": r["model"], "ms": int((time.time() - start) * 1000)}
    except Exception as e:  # noqa
        return {"ok": False, "error": str(e)}


@router.post("/admin/models/{mid}/publish")
def model_publish(mid: int, data: dict, db=Depends(get_db), user=Depends(admin_only)):
    """版本管理/灰度发布：设置版本号与灰度比例；全量发布时设为默认模型"""
    m = db.get(LLMModel, mid)
    m.version = data.get("version", m.version)
    m.gray_percent = int(data.get("gray_percent", 100))
    if m.gray_percent >= 100 and data.get("set_default"):
        db.query(LLMModel).update({"is_default": False})
        m.is_default = True
    db.commit()
    return m.to_dict(exclude=("api_key",))


@router.get("/admin/models-metrics")
def model_metrics(days: int = 7, db=Depends(get_db), user=Depends(admin_only)):
    """模型性能监控：调用量、成功率、平均响应时间、降级次数、趋势"""
    since = datetime.datetime.now() - datetime.timedelta(days=days)
    rows = db.query(LLMCallLog.model_name, func.count(), func.avg(LLMCallLog.latency_ms),
                    func.sum(case((LLMCallLog.success == True, 1), else_=0)), func.sum(case((LLMCallLog.fallback == True, 1), else_=0)),  # noqa: E712
                   
                    func.sum(LLMCallLog.completion_tokens)) \
        .filter(LLMCallLog.created_at >= since).group_by(LLMCallLog.model_name).all()
    models = [{"model": r[0], "calls": r[1], "avg_ms": int(r[2] or 0),
               "success_rate": round((r[3] or 0) * 100.0 / r[1], 1) if r[1] else 0,
               "fallback": int(r[4] or 0), "tokens": int(r[5] or 0)} for r in rows]
    trend = []
    for i in range(days - 1, -1, -1):
        d = (datetime.datetime.now() - datetime.timedelta(days=i)).date()
        s = datetime.datetime.combine(d, datetime.time())
        q = db.query(func.count(), func.avg(LLMCallLog.latency_ms)).filter(
            LLMCallLog.created_at >= s, LLMCallLog.created_at < s + datetime.timedelta(days=1)).first()
        trend.append({"day": d.strftime("%m-%d"), "calls": q[0], "avg_ms": int(q[1] or 0)})
    errors = [l.to_dict() for l in db.query(LLMCallLog).filter(LLMCallLog.success == False)  # noqa: E712
              .order_by(LLMCallLog.id.desc()).limit(20)]
    return {"models": models, "trend": trend, "errors": errors}


# ======================= 意图/槽位 =======================
intent_router = crud_router(Intent, "/api/admin/intents", admin_only, ("name", "keywords"))

# ======================= 多轮问答 =======================
_stop_flags = {}


def _session_cfg(db, key, default):
    s = db.get(SystemSetting, "chat")
    if s and s.value and key in s.value:
        return s.value[key]
    return config.get("llm." + key, default)


def _owner_filter(q, who):
    return q.filter(ChatSession.user == who.key)


@router.post("/chat/sessions")
def new_session(data: dict, db=Depends(get_db), who=Depends(actor)):
    s = ChatSession(id=uuid.uuid4().hex, user=who.key, device_id=who.device_id, mode=data.get("mode", "chat"),
                    model_id=data.get("model_id"), kb_id=data.get("kb_id"), slots={})
    db.add(s)
    db.commit()
    return s.to_dict()


@router.get("/chat/sessions")
def list_sessions(db=Depends(get_db), who=Depends(actor)):
    rows = _owner_filter(db.query(ChatSession), who).filter(ChatSession.expired == False) \
        .order_by(ChatSession.last_active.desc()).limit(50).all()  # noqa: E712
    return [r.to_dict() for r in rows]


@router.get("/chat/sessions/{sid}")
def get_session(sid: str, db=Depends(get_db), who=Depends(actor)):
    s = db.get(ChatSession, sid)
    if not s or s.user != who.key:
        raise HTTPException(404, "会话不存在")
    msgs = db.query(ChatMessage).filter(ChatMessage.session_id == sid).order_by(ChatMessage.id).all()
    return dict(s.to_dict(), messages=[m.to_dict() for m in msgs])


@router.delete("/chat/sessions/{sid}")
def del_session(sid: str, db=Depends(get_db), who=Depends(actor)):
    s = db.get(ChatSession, sid)
    if s and s.user == who.key:
        s.expired = True
        db.commit()
    return {"ok": True}


@router.post("/chat/stop/{sid}")
def stop(sid: str, who=Depends(actor)):
    """暂停/中止当前生成任务"""
    _stop_flags[sid] = True
    return {"ok": True}


def _extract_slots(intent, text, current):
    slots = dict(current or {})
    for sd in intent.slots or []:
        if slots.get(sd["name"]):
            continue
        if sd.get("pattern"):
            m = re.search(sd["pattern"], text)
            if m:
                slots[sd["name"]] = m.group(1) if m.groups() else m.group(0)
    missing = [sd for sd in intent.slots or [] if sd.get("required", True) and not slots.get(sd["name"])]
    if missing:
        desc = "；".join("%s(%s)" % (sd["name"], sd.get("label", sd["name"])) for sd in intent.slots)
        try:
            r = llm.chat([{"role": "system", "content": "你是信息抽取器，只输出JSON对象，没有提到的字段不要输出。"},
                          {"role": "user", "content": "需要的字段：%s\n已知：%s\n用户说：%s\n请抽取字段值，输出JSON。" % (
                              desc, json.dumps(slots, ensure_ascii=False), text)}],
                         scene="slot", params={"temperature": 0})
            m = re.search(r"\{.*\}", r["content"], re.S)
            if m:
                for k, v in json.loads(m.group(0)).items():
                    if v and any(sd["name"] == k for sd in intent.slots):
                        slots[k] = str(v)
        except Exception:  # noqa
            pass
        # 兜底：若上一轮在追问某个槽位，直接把用户回答填入
        asking = (current or {}).get("_asking")
        if asking and not slots.get(asking) and len(text) < 100:
            slots[asking] = text.strip()
    return slots


def _do_action(db, intent, slots, who):
    if intent.action == "create_ticket":
        from .ops import create_ticket
        from ..db import User
        data = {"title": slots.get("title") or "%s故障报修" % slots.get("device", ""),
                "description": slots.get("problem", "") or json.dumps(slots, ensure_ascii=False),
                "reporter": slots.get("contact") or who.name, "reporter_phone": slots.get("phone", ""),
                "address": slots.get("address", ""), "device_info": slots.get("device", ""), "category": "智能报修"}
        op = who.user or db.query(User).filter(User.role == "admin").first()
        t = create_ticket(db, data, op, source="智能问答")
        return "已为您创建报修工单，单号：%s，运维人员将尽快联系您。" % t.ticket_no
    return "已收集完全部信息：" + "，".join("%s=%s" % (k, v) for k, v in slots.items() if not k.startswith("_"))


def _state_tracking(db, s, text, who):
    """状态跟踪/槽位填充：返回需要直接回复的文本，None 表示走普通问答"""
    intents = db.query(Intent).filter(Intent.enabled == True).all()  # noqa: E712
    intent = None
    if s.intent:
        intent = next((i for i in intents if i.name == s.intent), None)
        if text.strip() in ("取消", "算了", "退出"):
            s.intent, s.slots = "", {}
            return "好的，已取消“%s”。" % intent.name if intent else "已取消。"
    if not intent:
        for i in intents:
            if any(k and k in text for k in (i.keywords or "").split(",")):
                intent = i
                s.intent, s.slots = i.name, {}
                break
    if not intent:
        return None
    slots = _extract_slots(intent, text, s.slots)
    missing = [sd for sd in intent.slots or [] if sd.get("required", True) and not slots.get(sd["name"])]
    if missing:
        slots["_asking"] = missing[0]["name"]
        s.slots = slots
        got = "，".join("%s：%s" % (sd.get("label", sd["name"]), slots[sd["name"]])
                       for sd in intent.slots if slots.get(sd["name"]))
        return ("【%s】%s请提供%s。（回复“取消”可退出）" % (intent.name, ("已记录 " + got + "。") if got else "",
                                                 missing[0].get("label", missing[0]["name"])))
    slots.pop("_asking", None)
    s.intent, s.slots = "", {}
    return _do_action(db, intent, slots, who)


def _history(db, s):
    rounds = int(_session_cfg(db, "context_window_rounds", 6))
    msgs = db.query(ChatMessage).filter(ChatMessage.session_id == s.id).order_by(ChatMessage.id.desc()).all()
    msgs = list(reversed(msgs))
    keep = msgs[-rounds * 2:] if rounds > 0 else []
    older = msgs[:-rounds * 2] if rounds > 0 else msgs
    if older and _session_cfg(db, "context_strategy", "window") == "summary":
        try:
            text = "\n".join("%s：%s" % ("用户" if m.role == "user" else "助手", m.content[:500]) for m in older[-20:])
            r = llm.chat([{"role": "user", "content": "请将以下对话压缩为200字以内的摘要，保留关键信息：\n" + text}],
                         scene="summary")
            s.summary = r["content"]
        except Exception:  # noqa
            pass
    return [{"role": m.role, "content": m.content} for m in keep]


SYSTEM_PROMPT = ("你是“小信助手”，中国电信浙江公司的信创终端智能助手，擅长信创终端（麒麟/统信操作系统、飞腾/鲲鹏/海光/兆芯CPU）"
                 "的使用、运维故障排查、政策咨询。回答要准确、简洁、专业。")


@router.post("/chat/send")
def send(data: dict, who=Depends(actor)):
    """流式问答（SSE）。mode=chat 普通多轮问答；mode=kb 本地知识问答(RAG)"""
    text = (data.get("message") or "").strip()
    if not text:
        raise HTTPException(400, "消息不能为空")
    db = SessionLocal()
    sid = data.get("session_id")
    s = db.get(ChatSession, sid) if sid else None
    if s and (s.user != who.key or s.expired):
        s = None
    if not s:
        s = ChatSession(id=uuid.uuid4().hex, user=who.key, device_id=who.device_id, slots={},
                        mode=data.get("mode", "chat"), title=text[:30])
        db.add(s)
    if s.title == "新会话":
        s.title = text[:30]
    s.mode = data.get("mode") or s.mode
    s.model_id = data.get("model_id") or s.model_id
    s.last_active = datetime.datetime.now()
    history = _history(db, s)
    db.add(ChatMessage(session_id=s.id, role="user", content=text))
    db.commit()
    _stop_flags.pop(s.id, None)

    direct = _state_tracking(db, s, text, who) if s.mode == "chat" else None
    db.commit()
    refs, prompt_msgs, rag_ms = [], None, 0
    if direct is None:
        user_content = text
        if s.mode == "kb":
            kb_ids = data.get("kb_ids") or ([s.kb_id] if s.kb_id else None)
            if not kb_ids:
                kb_ids = [k.id for k in db.query(KnowledgeBase).filter(
                    KnowledgeBase.owner.in_(["public", who.device_id or who.key])).all()]
            t0 = time.time()
            hits = rag.search(kb_ids, text) if kb_ids else []
            rag_ms = int((time.time() - t0) * 1000)
            refs = [{"file": h["filename"], "score": h["rerank_score"], "content": h["content"][:200]} for h in hits]
            user_content = rag.build_prompt(text, hits) if hits else text + "\n（知识库中未检索到相关资料，请基于通用知识回答并说明）"
            rag.log_rag(text, kb_ids[0] if kb_ids else None, None, hits, rag_ms)
        sys_prompt = SYSTEM_PROMPT + (("\n此前对话摘要：" + s.summary) if s.summary else "")
        prompt_msgs = [{"role": "system", "content": sys_prompt}] + history + [{"role": "user", "content": user_content}]
    sess_id, model_id, user_key = s.id, s.model_id, who.key
    db.close()

    def gen():
        meta = {}
        yield "data: %s\n\n" % json.dumps({"type": "meta", "session_id": sess_id, "refs": refs}, ensure_ascii=False)
        out = []
        if direct is not None:
            out.append(direct)
            yield "data: %s\n\n" % json.dumps({"type": "delta", "text": direct}, ensure_ascii=False)
        else:
            stream = llm.stream(prompt_msgs, model_id=model_id, scene="kb" if refs else "chat",
                                params=data.get("params"), user_key=user_key, meta=meta)
            try:
                for piece in stream:
                    if _stop_flags.get(sess_id):
                        out.append("\n[已停止生成]")
                        yield "data: %s\n\n" % json.dumps({"type": "delta", "text": "\n[已停止生成]"}, ensure_ascii=False)
                        break
                    out.append(piece)
                    yield "data: %s\n\n" % json.dumps({"type": "delta", "text": piece}, ensure_ascii=False)
            finally:
                stream.close()
        d2 = SessionLocal()
        d2.add(ChatMessage(session_id=sess_id, role="assistant", content="".join(out),
                           model_name=meta.get("model", "状态跟踪" if direct else ""), refs=refs))
        d2.commit()
        d2.close()
        _stop_flags.pop(sess_id, None)
        yield "data: %s\n\n" % json.dumps({"type": "done", "model": meta.get("model", "")}, ensure_ascii=False)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.post("/chat/ask")
def ask(data: dict, who=Depends(actor)):
    """非流式问答（第三方/简单调用）"""
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + (data.get("history") or []) + \
           [{"role": "user", "content": data["message"]}]
    return llm.chat(msgs, model_id=data.get("model_id"), params=data.get("params"), user_key=who.key)


@router.get("/admin/chat/sessions")
def admin_sessions(page: int = 1, page_size: int = 20, keyword: str = "", db=Depends(get_db), user=Depends(admin_only)):
    q = db.query(ChatSession)
    if keyword:
        q = q.filter(ChatSession.title.ilike("%" + keyword + "%"))
    return paginate(q, page, page_size, ChatSession.last_active.desc())


def expire_sessions():
    db = SessionLocal()
    try:
        minutes = int(_session_cfg(db, "session_timeout_minutes", 60))
        db.query(ChatSession).filter(ChatSession.expired == False,  # noqa: E712
                                     ChatSession.last_active < datetime.datetime.now() - datetime.timedelta(minutes=minutes)) \
            .update({"expired": True}, synchronize_session=False)
        db.commit()
    finally:
        db.close()


# ======================= 模型优化：微调 / 评估 / 参数调整 =======================
@router.get("/admin/ft/datasets")
def ds_list(db=Depends(get_db), user=Depends(admin_only)):
    return [d.to_dict() for d in db.query(FtDataset).order_by(FtDataset.id.desc())]


@router.post("/admin/ft/datasets")
def ds_upload(name: str = Form(...), kind: str = Form("运维知识"), file: UploadFile = File(...),
              db=Depends(get_db), user=Depends(admin_only)):
    path, fname, ext, size = save_upload(file, "finetune", {"jsonl", "json", "csv", "xlsx"})
    d = FtDataset(name=name, kind=kind, file_path=path)
    db.add(d)
    db.commit()
    threading.Thread(target=finetune.preprocess, args=(d.id,), daemon=True).start()
    return d.to_dict()


@router.post("/admin/ft/datasets/{did}/preprocess")
def ds_preprocess(did: int, user=Depends(admin_only)):
    finetune.preprocess(did)
    return {"ok": True}


@router.delete("/admin/ft/datasets/{did}")
def ds_delete(did: int, db=Depends(get_db), user=Depends(admin_only)):
    d = db.get(FtDataset, did)
    if d:
        db.delete(d)
        db.commit()
    return {"ok": True}


@router.get("/admin/ft/jobs")
def job_list(db=Depends(get_db), user=Depends(admin_only)):
    out = []
    for j in db.query(FtJob).order_by(FtJob.id.desc()):
        d = j.to_dict()
        d.pop("log")
        loss = (j.metrics or {}).get("loss") or []
        d["final_loss"] = loss[-1]["loss"] if loss else None
        out.append(d)
    return out


@router.get("/admin/ft/jobs/{jid}")
def job_detail(jid: int, db=Depends(get_db), user=Depends(admin_only)):
    j = db.get(FtJob, jid)
    d = j.to_dict()
    ds = db.get(FtDataset, j.dataset_id)
    if ds:
        d["train_config"] = finetune.llamafactory_yaml(j, ds)
    return d


@router.post("/admin/ft/jobs")
def job_create(data: dict, db=Depends(get_db), user=Depends(admin_only)):
    ds = db.get(FtDataset, int(data["dataset_id"]))
    if not ds or ds.status != "已处理":
        raise HTTPException(400, "数据集未完成预处理")
    j = FtJob(name=data.get("name") or "微调任务", dataset_id=ds.id, base_model=data.get("base_model", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"),
              method=data.get("method", "lora"), params=data.get("params") or {})
    db.add(j)
    db.commit()
    finetune.start_job(j.id)
    return j.to_dict()


@router.post("/admin/ft/jobs/{jid}/stop")
def job_stop(jid: int, db=Depends(get_db), user=Depends(admin_only)):
    j = db.get(FtJob, jid)
    j.status = "已停止"
    db.commit()
    return {"ok": True}


@router.post("/admin/ft/jobs/{jid}/retrain")
def job_retrain(jid: int, data: dict, db=Depends(get_db), user=Depends(admin_only)):
    """参数调整：基于原任务修改超参数后重新微调验证"""
    old = db.get(FtJob, jid)
    params = dict(old.params or {})
    params.update(data.get("params") or {})
    j = FtJob(name="%s-调参v%d" % (old.name.split("-调参")[0], db.query(FtJob).count() + 1), dataset_id=old.dataset_id,
              base_model=old.base_model, method=data.get("method", old.method), params=params)
    db.add(j)
    db.commit()
    finetune.start_job(j.id)
    return j.to_dict()


eval_set_router = crud_router(EvalSet, "/api/admin/eval-sets", admin_only, ("name",))


@router.get("/admin/eval-runs")
def eval_runs(db=Depends(get_db), user=Depends(admin_only)):
    out = []
    for r in db.query(EvalRun).order_by(EvalRun.id.desc()).limit(100):
        d = r.to_dict()
        d.pop("results")
        out.append(d)
    return out


@router.get("/admin/eval-runs/{rid}")
def eval_run_detail(rid: int, db=Depends(get_db), user=Depends(admin_only)):
    return db.get(EvalRun, rid).to_dict()


@router.post("/admin/eval-runs")
def eval_start(data: dict, db=Depends(get_db), user=Depends(admin_only)):
    m = db.get(LLMModel, int(data["model_id"]))
    r = EvalRun(eval_set_id=int(data["eval_set_id"]), model_id=m.id, model_name=m.name, params=data.get("params") or {})
    db.add(r)
    db.commit()
    finetune.start_eval(r.id)
    return r.to_dict()
