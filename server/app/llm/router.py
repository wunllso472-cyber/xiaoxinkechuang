"""统一模型调用接口 + 路由策略 + 自动降级。

每次调用都从数据库读取模型配置，因此管理端增删改模型后立即生效，无需重启服务。
"""
import hashlib
import itertools
import random
import time

from ..db import SessionLocal, LLMModel, LLMCallLog, SystemSetting
from .adapters import get_adapter, LLMError

_rr = itertools.count()
CLOUD_PROVIDERS = ("deepseek", "qwen")  # 必须配置 API Key 的云端模型


def _setting(db, key, default):
    s = db.get(SystemSetting, key)
    return s.value if s and s.value is not None else default


def candidate_models(db, model_id=None, scene="chat", user_key=""):
    """返回按路由策略排好序的候选模型列表（第一个为首选，其余为降级备用）"""
    models = db.query(LLMModel).filter(LLMModel.enabled == True).all()  # noqa: E712
    # 跳过未完成配置的模型（云端模型未填 API Key、或未填地址），避免每次请求都等待失败
    models = [m for m in models if m.provider == "mock" or
              (m.base_url and (m.api_key or m.provider not in CLOUD_PROVIDERS))]
    # 灰度发布：按用户哈希决定是否命中灰度版本
    bucket = int(hashlib.md5((user_key or "anon").encode()).hexdigest(), 16) % 100
    models = [m for m in models if (m.gray_percent if m.gray_percent is not None else 100) > bucket]
    if not models:
        return []
    strategy = _setting(db, "route_strategy", "priority")
    models.sort(key=lambda m: (not m.is_default, m.priority))
    if strategy == "round_robin":
        k = next(_rr) % len(models)
        models = models[k:] + models[:k]
    elif strategy == "weighted":
        first = random.choices(models, weights=[max(m.weight or 1, 1) for m in models])[0]
        models = [first] + [m for m in models if m is not first]
    elif strategy == "scene":
        hit = [m for m in models if scene in (m.scene or "").split(",")]
        models = hit + [m for m in models if m not in hit]
    # mock 永远放最后兜底
    models.sort(key=lambda m: m.provider == "mock")
    if model_id:
        chosen = [m for m in models if m.id == int(model_id)]
        models = chosen + [m for m in models if m.id != int(model_id)]
    return models


def _log(model, scene, start, ok, err="", usage=None, fallback=False):
    db = SessionLocal()
    try:
        usage = usage or {}
        db.add(LLMCallLog(model_id=model.id, model_name=model.name, scene=scene,
                          latency_ms=int((time.time() - start) * 1000), success=ok, error=str(err)[:1000],
                          prompt_tokens=usage.get("prompt_tokens", 0),
                          completion_tokens=usage.get("completion_tokens", 0), fallback=fallback))
        db.commit()
    finally:
        db.close()


def chat(messages, model_id=None, scene="chat", params=None, user_key=""):
    """同步调用，返回 {"content","model","model_id"}；首选失败自动降级到备用模型"""
    db = SessionLocal()
    try:
        models = candidate_models(db, model_id, scene, user_key)
    finally:
        db.close()
    if not models:
        raise LLMError("没有可用的模型，请在模型管理中启用模型")
    errors = []
    for i, m in enumerate(models):
        start = time.time()
        try:
            res = get_adapter(m).chat(messages, params)
            _log(m, scene, start, True, usage=res["usage"], fallback=i > 0)
            return {"content": res["content"], "model": m.name, "model_id": m.id, "fallback_errors": errors}
        except Exception as e:  # noqa
            _log(m, scene, start, False, e, fallback=i > 0)
            errors.append("%s: %s" % (m.name, e))
    raise LLMError("所有模型调用失败: " + "; ".join(errors))


def stream(messages, model_id=None, scene="chat", params=None, user_key="", meta=None):
    """流式调用。首个分片产出前失败则降级；meta 字典回填实际使用的模型名"""
    db = SessionLocal()
    try:
        models = candidate_models(db, model_id, scene, user_key)
    finally:
        db.close()
    if not models:
        yield "没有可用的模型，请在模型管理中启用模型"
        return
    errors = []
    for i, m in enumerate(models):
        start = time.time()
        started = False
        size = 0
        try:
            for piece in get_adapter(m).stream(messages, params):
                if not started and meta is not None:
                    meta["model"] = m.name
                    meta["model_id"] = m.id
                started = True
                size += len(piece)
                yield piece
            _log(m, scene, start, True, usage={"completion_tokens": size}, fallback=i > 0)
            return
        except GeneratorExit:
            _log(m, scene, start, True, "用户中止", usage={"completion_tokens": size}, fallback=i > 0)
            raise
        except Exception as e:  # noqa
            _log(m, scene, start, False, e, fallback=i > 0)
            errors.append("%s: %s" % (m.name, e))
            if started:
                yield "\n[模型输出中断: %s]" % e
                return
    yield "所有模型调用失败: " + "; ".join(errors)


def health_check(m):
    start = time.time()
    try:
        res = get_adapter(m).chat([{"role": "user", "content": "你好，请回复OK"}], {"max_tokens": 16})
        return {"ok": True, "latency_ms": int((time.time() - start) * 1000), "reply": res["content"][:100]}
    except Exception as e:  # noqa
        return {"ok": False, "latency_ms": int((time.time() - start) * 1000), "error": str(e)[:300]}
