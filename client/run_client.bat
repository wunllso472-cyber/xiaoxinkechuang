@echo off
REM 源码方式运行客户端（Windows）：pip install psutil
cd /d %~dp0
start "" pythonw -m xiaoxin_client.main
