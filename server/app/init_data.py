"""数据库初始化工具（不启动服务即可建表、写入初始数据、检查结果、导出 SQL 脚本）

用法（在服务端目录 /opt/xiaoxin 下执行）：
  python -m app.init_data                    建表 + 写入基础数据（与服务首次启动的逻辑相同，可重复执行）
  python -m app.init_data --demo             同时写入演示数据（终端/工单/案例，仅测试环境）
  python -m app.init_data --check            只检查：数据库连接、表数量、各表记录数
  python -m app.init_data --export-sql DIR   导出 PostgreSQL 脚本：01_schema.sql（建表）、02_init_data.sql（基础数据）
"""
import argparse
import datetime
import json
import os
import sys
import tempfile

# 导出的基础数据不含知识库：知识库和示例文档由服务首次启动时创建并导入（需要读取 data/sample_kb.md）
KB_TABLES = {"kb", "kb_doc", "kb_chunk", "kb_import_log", "kb_rag_log"}


def _run_init(demo):
    from . import config
    from .db import init_db
    from .seed import seed
    config.settings.setdefault("server", {})["seed_demo"] = bool(demo)
    print("==> 数据库：%s" % config.get("database.url").split("@")[-1])
    init_db()
    print("==> 表结构已就绪")
    seed()
    print("==> 初始数据已写入（已有数据的表自动跳过）")


def _check():
    from sqlalchemy import inspect, text
    from . import config
    from .db import SCHEMA, Base, engine
    print("==> 数据库：%s%s" % (config.get("database.url").split("@")[-1], "，schema：" + SCHEMA if SCHEMA else ""))
    prefix = '"%s".' % SCHEMA if SCHEMA else ""
    with engine.connect() as conn:
        if engine.dialect.name == "postgresql":
            print("    版本：%s" % conn.execute(text("SELECT version()")).scalar())
        existing = set(inspect(conn).get_table_names(schema=SCHEMA))
        expected = [t.name for t in Base.metadata.sorted_tables]
        missing = [t for t in expected if t not in existing]
        print("    表数量：%d / %d%s" % (len(expected) - len(missing), len(expected),
                                       "" if not missing else "，缺少：" + ", ".join(missing)))
        print("\n    %-22s %s" % ("表名", "记录数"))
        for t in expected:
            if t in existing:
                print("    %-24s %d" % (t, conn.execute(text('SELECT count(*) FROM %s"%s"' % (prefix, t))).scalar()))
        if "sys_user" in existing:
            users = conn.execute(text("SELECT username, role, enabled FROM %ssys_user ORDER BY id" % prefix)).fetchall()
            print("\n    用户：" + "，".join("%s(%s%s)" % (u, r, "" if e else "，已禁用") for u, r, e in users))
    return 0 if not missing else 1


def _literal(v, is_json=False):
    if v is None:
        return "NULL"
    if isinstance(v, bool) and not is_json:
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)) and not is_json:
        return repr(v)
    if isinstance(v, (datetime.datetime, datetime.date)):
        return "now()"
    if is_json or isinstance(v, (dict, list)):
        v = json.dumps(v, ensure_ascii=False)
    return "'%s'" % str(v).replace("'", "''")


def _export_sql(out_dir):
    """在临时 SQLite 中执行一遍初始化，再按 PostgreSQL 方言导出建表语句和基础数据"""
    tmp = os.path.join(tempfile.mkdtemp(prefix="xiaoxin_export_"), "export.db")
    os.environ["XX_DATABASE_URL"] = "sqlite:///" + tmp.replace("\\", "/")
    from sqlalchemy import JSON, Integer, select
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateIndex, CreateTable
    from . import config
    from .db import Base, engine
    # 导出的模型配置中不能带 API Key
    for m in config.get("llm.default_models", []):
        m["api_key"] = ""
    _run_init(demo=False)

    os.makedirs(out_dir, exist_ok=True)
    dialect = postgresql.dialect()
    q = dialect.identifier_preparer.quote
    tables = Base.metadata.sorted_tables
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = ["-- 小信助手智能体：PostgreSQL 建表脚本（%d 张表）" % len(tables),
             "-- 由 python -m app.init_data --export-sql 生成于 %s，请勿手工修改" % stamp,
             "-- 执行：psql -h 127.0.0.1 -U xiaoxin -d xiaoxin -v ON_ERROR_STOP=1 -f 01_schema.sql",
             "-- 可重复执行：已存在的表和索引自动跳过", "", "BEGIN;", ""]
    for t in tables:
        lines.append(str(CreateTable(t, if_not_exists=True).compile(dialect=dialect)).strip() + ";")
        for idx in sorted(t.indexes, key=lambda i: i.name):
            lines.append(str(CreateIndex(idx, if_not_exists=True).compile(dialect=dialect)).strip() + ";")
        lines.append("")
    lines += ["COMMIT;", ""]
    with open(os.path.join(out_dir, "01_schema.sql"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))

    lines = ["-- 小信助手智能体：PostgreSQL 基础数据脚本（不含演示数据和知识库）",
             "-- 由 python -m app.init_data --export-sql 生成于 %s，请勿手工修改" % stamp,
             "-- 执行：psql -h 127.0.0.1 -U xiaoxin -d xiaoxin -v ON_ERROR_STOP=1 -f 02_init_data.sql",
             "-- 仅用于空库：sys_user 已有数据时脚本报错退出，不会写入任何数据",
             "-- 知识库（信创运维知识库 + 示例文档、信创政策知识库）由服务首次启动时自动创建并导入",
             "", "BEGIN;", "",
             "DO $$ BEGIN",
             "  IF EXISTS (SELECT 1 FROM sys_user) THEN",
             "    RAISE EXCEPTION '数据库中已有用户数据，基础数据脚本只能在空库上执行';",
             "  END IF;",
             "END $$;", ""]
    total = 0
    with engine.connect() as conn:
        for t in tables:
            if t.name in KB_TABLES:
                continue
            rows = conn.execute(select(t)).mappings().all()
            if not rows:
                continue
            cols = list(t.columns)
            names = ", ".join(q(c.name) for c in cols)
            lines.append("-- %s（%d 条）" % (t.name, len(rows)))
            for r in rows:
                lines.append("INSERT INTO %s (%s) VALUES (%s);" % (
                    q(t.name), names, ", ".join(_literal(r[c.name], isinstance(c.type, JSON)) for c in cols)))
            pk = list(t.primary_key.columns)
            if len(pk) == 1 and isinstance(pk[0].type, Integer):
                lines.append("SELECT setval(pg_get_serial_sequence('%s', '%s'), (SELECT max(%s) FROM %s));"
                             % (t.name, pk[0].name, pk[0].name, t.name))
            lines.append("")
            total += len(rows)
    lines += ["COMMIT;", ""]
    with open(os.path.join(out_dir, "02_init_data.sql"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    engine.dispose()
    print("==> 已导出到 %s：01_schema.sql（%d 张表）、02_init_data.sql（%d 条记录）" % (out_dir, len(tables), total))


def main():
    p = argparse.ArgumentParser(prog="python -m app.init_data", description="小信助手数据库初始化工具")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--demo", action="store_true", help="同时写入演示数据（仅测试环境）")
    g.add_argument("--check", action="store_true", help="只检查数据库，不写入")
    g.add_argument("--export-sql", metavar="DIR", help="导出 PostgreSQL 建表和基础数据脚本")
    a = p.parse_args()
    if a.export_sql:
        _export_sql(os.path.abspath(a.export_sql))
        return 0
    if a.check:
        return _check()
    _run_init(a.demo)
    return _check()


if __name__ == "__main__":
    sys.exit(main())
