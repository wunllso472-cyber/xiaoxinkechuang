"""工具与插件：内置工具、第三方插件(REST/GraphQL/WebSocket)调用、链式调度、性能日志。"""
import ast
import concurrent.futures
import datetime
import json
import operator
import re
import time

import httpx

from ..db import SessionLocal, Tool, ToolCallLog
from . import docparse

_pool = concurrent.futures.ThreadPoolExecutor(max_workers=8)


# ---------------- 内置工具 ----------------
def t_ocr(params):
    path = params.get("path")
    if not path:
        raise ValueError("缺少参数 path")
    text = docparse.ocr_image(path)
    return {"text": text, "confidence": 0.9 if text else 0.0,
            "note": "" if text else "未配置 OCR 引擎(config.yaml -> ocr)"}


def t_image_analyze(params):
    """图片基础分析：尺寸、格式、主色调、是否疑似图表/文档（基于颜色分布的启发式）"""
    from PIL import Image
    img = Image.open(params["path"])
    w, h = img.size
    small = img.convert("RGB").resize((64, 64))
    colors = small.getcolors(64 * 64) or []
    colors.sort(key=lambda c: -c[0])
    top = ["#%02x%02x%02x" % c[1] for c in colors[:5]]
    white_ratio = sum(c[0] for c in colors if min(c[1]) > 230) / 4096.0
    kind = "文档/截图" if white_ratio > 0.6 else ("图表" if len(colors) < 200 else "照片/场景")
    return {"width": w, "height": h, "format": img.format, "mode": img.mode, "main_colors": top,
            "scene": kind, "confidence": round(0.5 + abs(white_ratio - 0.5), 2)}


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod, ast.USub: operator.neg}


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("不支持的表达式")


def t_calculator(params):
    return {"result": _eval(ast.parse(str(params.get("expression", "0")), mode="eval").body)}


def t_datetime(params):
    n = datetime.datetime.now()
    return {"now": n.strftime("%Y-%m-%d %H:%M:%S"), "weekday": "一二三四五六日"[n.weekday()]}


def t_kb_search(params):
    from . import rag
    hits = rag.search([int(x) for x in str(params.get("kb_id", "1")).split(",")], params.get("query", ""),
                      int(params.get("top_k", 3)))
    return {"hits": [{"content": h["content"][:300], "score": h["score"], "file": h["filename"]} for h in hits]}


def t_doc_parse(params):
    r = docparse.parse_file(params["path"])
    return {"text": r["text"][:5000], "blocks": len(r["blocks"]), "tables": len(r["tables"])}


def t_summary(params):
    from ..llm import router
    res = router.chat([{"role": "user", "content": "请用100字以内总结：\n" + str(params.get("text", ""))[:6000]}],
                      scene="tool")
    return {"summary": res["content"]}


BUILTIN = {
    "ocr": ("OCR文字识别", t_ocr, {"path": "图片路径"}),
    "image_analyze": ("图片场景/图表分析", t_image_analyze, {"path": "图片路径"}),
    "calculator": ("计算器", t_calculator, {"expression": "算式"}),
    "datetime": ("当前时间", t_datetime, {}),
    "kb_search": ("知识库检索", t_kb_search, {"kb_id": "知识库ID", "query": "问题", "top_k": 3}),
    "doc_parse": ("文档解析", t_doc_parse, {"path": "文件路径"}),
    "summary": ("文本摘要(大模型)", t_summary, {"text": "文本"}),
}


# ---------------- 插件调用 ----------------
def _auth_headers(tool):
    if tool.auth_type == "api_key":
        return {"X-API-Key": tool.auth_value or ""}
    if tool.auth_type == "bearer":
        return {"Authorization": "Bearer " + (tool.auth_value or "")}
    return {}


def _call_plugin(tool, params):
    h = _auth_headers(tool)
    if tool.protocol == "rest":
        if (tool.method or "POST").upper() == "GET":
            r = httpx.get(tool.endpoint, params=params, headers=h, timeout=tool.timeout)
        else:
            r = httpx.request(tool.method.upper(), tool.endpoint, json=params, headers=h, timeout=tool.timeout)
        r.raise_for_status()
        try:
            return r.json()
        except ValueError:
            return {"text": r.text}
    if tool.protocol == "graphql":
        q = (tool.params_schema or {}).get("query") or params.pop("query", "")
        r = httpx.post(tool.endpoint, json={"query": q, "variables": params}, headers=h, timeout=tool.timeout)
        r.raise_for_status()
        return r.json()
    if tool.protocol == "websocket":
        from websockets.sync.client import connect
        with connect(tool.endpoint, additional_headers=h, open_timeout=tool.timeout) as ws:
            ws.send(json.dumps(params, ensure_ascii=False))
            msg = ws.recv(timeout=tool.timeout)
        try:
            return json.loads(msg)
        except ValueError:
            return {"text": msg}
    raise ValueError("不支持的协议: %s" % tool.protocol)


def invoke(code, params, timeout=None):
    db = SessionLocal()
    try:
        tool = db.query(Tool).filter(Tool.code == code).first()
    finally:
        db.close()
    if not tool or not tool.enabled:
        raise ValueError("工具不存在或未启用: %s" % code)
    params = dict(params or {})
    timeout = timeout or tool.timeout or 30
    start = time.time()
    try:
        if tool.kind == "builtin":
            fn = BUILTIN[code][1]
            fut = _pool.submit(fn, params)
        else:
            fut = _pool.submit(_call_plugin, tool, params)
        result = fut.result(timeout=timeout)
        _log(code, True, start)
        return result
    except concurrent.futures.TimeoutError:
        _log(code, False, start, "超时(%ss)" % timeout)
        raise ValueError("工具调用超时(%ss)" % timeout)
    except Exception as e:  # noqa
        _log(code, False, start, e)
        raise


def _log(code, ok, start, err=""):
    db = SessionLocal()
    try:
        db.add(ToolCallLog(tool_code=code, success=ok, latency_ms=int((time.time() - start) * 1000), error=str(err)[:500]))
        db.commit()
    finally:
        db.close()


def _render(v, ctx):
    """参数模板：${steps.0.text} 引用前序步骤输出"""
    if isinstance(v, str):
        def rep(m):
            cur = ctx
            for k in m.group(1).split("."):
                cur = cur[int(k)] if isinstance(cur, list) else cur.get(k, "")
            return cur if isinstance(cur, str) else json.dumps(cur, ensure_ascii=False)
        return re.sub(r"\$\{([\w.]+)\}", rep, v)
    if isinstance(v, dict):
        return {k: _render(x, ctx) for k, x in v.items()}
    return v


def run_chain(steps, stop_on_error=True):
    """链式调用：steps=[{"tool":"ocr","params":{...},"timeout":10}, {"tool":"summary","params":{"text":"${steps.0.text}"}}]"""
    ctx = {"steps": []}
    trace = []
    for i, s in enumerate(steps):
        params = _render(s.get("params", {}), ctx)
        start = time.time()
        try:
            out = invoke(s["tool"], params, s.get("timeout"))
            ctx["steps"].append(out)
            trace.append({"step": i, "tool": s["tool"], "ok": True, "output": out,
                          "ms": int((time.time() - start) * 1000)})
        except Exception as e:  # noqa
            ctx["steps"].append({})
            trace.append({"step": i, "tool": s["tool"], "ok": False, "error": str(e),
                          "ms": int((time.time() - start) * 1000)})
            if stop_on_error:
                break
    return trace
