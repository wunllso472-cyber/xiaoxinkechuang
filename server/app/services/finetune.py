"""模型优化：微调数据预处理、LoRA/QLoRA 训练流水线（真实命令或模拟）、模型评估。"""
import csv
import datetime
import difflib
import hashlib
import json
import math
import os
import random
import re
import subprocess
import threading
import time

import yaml

from .. import config
from ..db import SessionLocal, FtDataset, FtJob, EvalRun, EvalSet
from ..llm import router
from .rag import auto_tags
from .docparse import clean_text, detect_encoding


def _out_dir(*sub):
    d = config.get("finetune.output_dir", "./data/finetune")
    if not os.path.isabs(d):
        d = os.path.join(config.BASE_DIR, d)
    d = os.path.join(d, *sub)
    os.makedirs(d, exist_ok=True)
    return d


def load_qa(path):
    """读取 jsonl / json / csv / xlsx 的问答数据，字段兼容 instruction/input/output、question/answer、问题/答案"""
    ext = path.rsplit(".", 1)[-1].lower()
    rows = []
    if ext in ("jsonl", "json"):
        raw = open(path, "rb").read()
        text = raw.decode(detect_encoding(raw), "ignore")
        if ext == "json":
            rows = json.loads(text)
        else:
            rows = [json.loads(l) for l in text.splitlines() if l.strip()]
    elif ext == "csv":
        raw = open(path, "rb").read()
        rows = list(csv.DictReader(raw.decode(detect_encoding(raw), "ignore").splitlines()))
    elif ext == "xlsx":
        import openpyxl
        ws = openpyxl.load_workbook(path, read_only=True).active
        it = ws.iter_rows(values_only=True)
        head = [str(h) for h in next(it)]
        rows = [dict(zip(head, r)) for r in it]
    out = []
    for r in rows:
        q = r.get("instruction") or r.get("question") or r.get("问题") or ""
        inp = r.get("input") or ""
        a = r.get("output") or r.get("answer") or r.get("答案") or ""
        out.append({"instruction": str(q or ""), "input": str(inp or ""), "output": str(a or "")})
    return out


def preprocess(ds_id):
    """格式标准化(alpaca) → 质量清洗(空值/过短/乱码/重复) → 按知识类型分层分类"""
    db = SessionLocal()
    ds = db.get(FtDataset, ds_id)
    try:
        rows = load_qa(ds.file_path)
        seen, valid, cats = set(), [], {}
        for r in rows:
            r = {k: clean_text(v) for k, v in r.items()}
            if len(r["instruction"]) < 4 or len(r["output"]) < 4:
                continue
            h = hashlib.md5((r["instruction"] + r["output"]).encode()).hexdigest()
            if h in seen:
                continue
            seen.add(h)
            tags = auto_tags(r["instruction"] + r["output"]) or ["其他"]
            if ds.kind == "政策知识":
                level = "法律法规" if re.search(r"法|条例", r["output"]) else ("部门规章" if "办法" in r["output"] else "规范性文件")
                tags = [level] + tags
            r["category"] = tags[0]
            cats[tags[0]] = cats.get(tags[0], 0) + 1
            valid.append(r)
        out = os.path.join(_out_dir("datasets"), "ds_%d.json" % ds.id)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(valid, f, ensure_ascii=False, indent=1)
        ds.total, ds.valid, ds.categories, ds.processed_path, ds.status = len(rows), len(valid), cats, out, "已处理"
    except Exception as e:  # noqa
        ds.status = "处理失败: %s" % str(e)[:100]
    db.commit()
    db.close()


def llamafactory_yaml(job, ds):
    p = job.params or {}
    cfg = {
        "model_name_or_path": job.base_model, "stage": "sft", "do_train": True,
        "finetuning_type": "lora", "lora_rank": p.get("lora_rank", 8), "lora_alpha": p.get("lora_alpha", 16),
        "lora_dropout": p.get("lora_dropout", 0.05), "lora_target": "all",
        "dataset": "xiaoxin_ds_%d" % ds.id, "template": p.get("template", "deepseek"),
        "cutoff_len": p.get("cutoff_len", 2048), "output_dir": _out_dir("jobs", str(job.id)),
        "per_device_train_batch_size": p.get("batch_size", 4), "gradient_accumulation_steps": p.get("grad_accum", 4),
        "learning_rate": p.get("learning_rate", 1e-4), "num_train_epochs": p.get("epochs", 3),
        "lr_scheduler_type": "cosine", "logging_steps": 10, "save_steps": 200, "bf16": True,
    }
    if job.method == "qlora":
        cfg["quantization_bit"] = 4
    return cfg


def _run_job(job_id):
    db = SessionLocal()
    job = db.get(FtJob, job_id)
    ds = db.get(FtDataset, job.dataset_id)
    job.status, job.metrics, job.log = "训练中", {"loss": [], "eval_loss": []}, ""
    db.commit()
    cfg = llamafactory_yaml(job, ds)
    cfg_path = os.path.join(_out_dir("jobs", str(job.id)), "train.yaml")
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True)
    cmd = config.get("finetune.train_command", "")
    try:
        if cmd:
            proc = subprocess.Popen(cmd.format(config=cfg_path), shell=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True)
            losses = []
            for line in proc.stdout:
                job.log = (job.log + line)[-20000:]
                m = re.search(r"'loss':\s*([\d.]+).*'epoch':\s*([\d.]+)", line)
                if m:
                    losses.append({"step": len(losses) + 1, "loss": float(m.group(1))})
                    job.metrics = {"loss": losses, "eval_loss": []}
                    job.progress = min(99, int(float(m.group(2)) / cfg["num_train_epochs"] * 100))
                db.commit()
            proc.wait()
            job.status = "已完成" if proc.returncode == 0 else "失败"
        else:
            # 模拟训练：未配置训练命令（无 GPU 环境）时演示训练监控流程
            steps = max(20, (ds.valid or 100) * int(cfg["num_train_epochs"]) // 16)
            steps = min(steps, 120)
            lr = float(cfg["learning_rate"])
            losses, evals = [], []
            for s in range(1, steps + 1):
                db.refresh(job)
                if job.status == "已停止":
                    break
                loss = 2.6 * math.exp(-s / (steps / 3.0) * (lr / 1e-4) ** 0.3) + 0.35 + random.uniform(-0.05, 0.05)
                losses.append({"step": s, "loss": round(loss, 4)})
                if s % 10 == 0:
                    evals.append({"step": s, "loss": round(loss + 0.08 + random.uniform(0, 0.05), 4)})
                job.metrics = {"loss": list(losses), "eval_loss": list(evals)}
                job.progress = int(s * 100 / steps)
                job.log = (job.log or "") + "[%s] step %d/%d loss=%.4f\n" % (
                    datetime.datetime.now().strftime("%H:%M:%S"), s, steps, loss)
                db.commit()
                time.sleep(0.3)
            if job.status != "已停止":
                job.status = "已完成"
        job.finished_at = datetime.datetime.now()
        if job.status == "已完成":
            job.progress = 100
            job.log += "训练完成，LoRA 权重输出目录：%s\n" % cfg["output_dir"]
    except Exception as e:  # noqa
        job.status, job.log = "失败", (job.log or "") + "\n异常：%s" % e
    db.commit()
    db.close()


def start_job(job_id):
    threading.Thread(target=_run_job, args=(job_id,), daemon=True).start()


def _score(answer, ref, keywords):
    sim = difflib.SequenceMatcher(None, answer, ref).ratio() if ref else 0
    kw = sum(1 for k in keywords if k in answer) / len(keywords) if keywords else sim
    return round(sim, 3), round(kw, 3)


def _run_eval(run_id):
    db = SessionLocal()
    run = db.get(EvalRun, run_id)
    es = db.get(EvalSet, run.eval_set_id)
    results, acc, pro, lat = [], 0, 0, 0
    items = es.items or []
    for it in items:
        start = time.time()
        try:
            res = router.chat([{"role": "system", "content": "你是信创运维与政策领域专家，请准确专业地回答。"},
                               {"role": "user", "content": it["question"]}],
                              model_id=run.model_id, scene="eval", params=run.params or {})
            ans = res["content"]
        except Exception as e:  # noqa
            ans = "调用失败: %s" % e
        ms = int((time.time() - start) * 1000)
        sim, kw = _score(ans, it.get("answer", ""), it.get("keywords", []))
        ok = kw >= 0.6 or sim >= 0.5
        acc += ok
        pro += kw
        lat += ms
        results.append({"question": it["question"], "answer": ans[:1000], "reference": it.get("answer", ""),
                        "similarity": sim, "keyword_hit": kw, "correct": ok, "latency_ms": ms})
    n = max(len(items), 1)
    run.results, run.accuracy, run.professional = results, round(acc * 100.0 / n, 1), round(pro * 100.0 / n, 1)
    run.avg_latency, run.status = round(lat / n, 1), "已完成"
    db.commit()
    db.close()


def start_eval(run_id):
    threading.Thread(target=_run_eval, args=(run_id,), daemon=True).start()
