import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import config, scheduler
from .db import init_db
from .seed import seed
from .api import system, client, terminal, message, ops, llm, kb, contract, tools

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="小信助手智能体服务端", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(Exception)
async def on_error(request: Request, exc: Exception):
    logging.exception("未处理异常: %s", exc)
    return JSONResponse({"detail": "服务器内部错误：%s" % exc}, status_code=500)


# 注意：带固定子路径的 CRUD 路由需先于 /{id} 动态路由注册
for r in [
    system.router, system.users_router,
    client.router,
    terminal.router, terminal.cloud_server_router, terminal.alert_rule_router, terminal.version_router,
    terminal.software_router, terminal.dict_router, terminal.client_config_router,
    message.template_router, message.router,
    ops.router, ops.case_router, ops.m,
    llm.router, llm.model_router, llm.intent_router, llm.eval_set_router,
    kb.router,
    contract.template_router, contract.rule_router, contract.rules_extra, contract.router,
    tools.router, tools.tool_router, tools.open_router,
]:
    app.include_router(r)

STATIC = os.path.join(os.path.dirname(__file__), "static")
app.mount("/admin", StaticFiles(directory=os.path.join(STATIC, "admin"), html=True), name="admin")
app.mount("/h5", StaticFiles(directory=os.path.join(STATIC, "h5"), html=True), name="h5")
app.mount("/vendor", StaticFiles(directory=os.path.join(STATIC, "vendor")), name="vendor")


@app.get("/")
def index():
    return RedirectResponse("/admin/")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.on_event("startup")
def startup():
    init_db()
    seed()
    scheduler.start()
    logging.info("小信助手服务端已启动，数据库：%s", config.get("database.url").split("@")[-1])
