@echo off
REM 本地开发启动（需先安装 PostgreSQL 并按 config.yaml 创建数据库；临时体验可用 SQLite：set XX_DATABASE_URL=sqlite:///./data/dev.db）
cd /d %~dp0
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
