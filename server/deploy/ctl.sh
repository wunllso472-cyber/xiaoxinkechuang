#!/bin/bash
# 小信助手服务端启停脚本（无 root 权限部署时代替 systemd，见部署手册 3.5）
# 用法：./ctl.sh start|stop|restart|status|log        端口默认 8000，可用 PORT=8010 ./ctl.sh start 指定
# 放在程序目录（含 app/、venv/、config.yaml）或其下的 deploy/ 中均可
cd "$(dirname "$0")"
[ -d app ] || cd ..
PORT=${PORT:-8000}
PID_FILE=run.pid
LOG=logs/server.log
mkdir -p logs
running() { [ -f $PID_FILE ] && kill -0 "$(cat $PID_FILE)" 2>/dev/null; }
case "$1" in
  start)
    if running; then echo "已在运行，PID $(cat $PID_FILE)"; exit 0; fi
    # 必须单进程（--workers 1）：会话中止标记、检索缓存、定时任务都在进程内存中
    PYTHONUNBUFFERED=1 nohup venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 >> $LOG 2>&1 &
    echo $! > $PID_FILE
    for i in $(seq 1 60); do
      curl -sf http://127.0.0.1:$PORT/api/health >/dev/null && { echo "启动成功，PID $(cat $PID_FILE)，端口 $PORT"; exit 0; }
      running || { echo "启动失败，见 $LOG"; tail -30 $LOG; exit 1; }
      sleep 1
    done
    echo "60 秒内未就绪，见 $LOG"; exit 1 ;;
  stop)
    if running; then
      kill "$(cat $PID_FILE)"
      for i in $(seq 1 15); do running || break; sleep 1; done
      running && kill -9 "$(cat $PID_FILE)"
      echo "已停止"
    else
      echo "未运行"
    fi
    rm -f $PID_FILE ;;
  restart) "$0" stop; "$0" start ;;
  status)
    if running; then echo "运行中，PID $(cat $PID_FILE)"; curl -s http://127.0.0.1:$PORT/api/health; echo; else echo "未运行"; exit 1; fi ;;
  log) tail -f $LOG ;;
  *) echo "用法：$0 start|stop|restart|status|log"; exit 2 ;;
esac
