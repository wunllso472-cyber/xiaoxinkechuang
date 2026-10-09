#!/bin/bash
# 小信助手服务端一键部署脚本 —— CentOS 7 / 8 / Stream 8 / Stream 9（aarch64：鲲鹏/飞腾；x86_64：海光/兆芯 同样适用）
# 用法（root 执行）：
#   DB_PASS='强密码' bash deploy/install_centos_arm.sh                   在线安装，本机 PostgreSQL
#   OFFLINE=1 DB_PASS='强密码' bash deploy/install_centos_arm.sh         使用 deploy/wheels 离线依赖包
#   DB_HOST=10.0.0.5 DB_PASS='强密码' bash deploy/install_centos_arm.sh  使用已建好库的独立数据库服务器
# 可重复执行：已有的数据库、用户、config.yaml 和业务数据都会保留
set -e

APP_DIR=/opt/xiaoxin
SRC_DIR=$(cd "$(dirname "$0")/.." && pwd)
DB_HOST=${DB_HOST:-127.0.0.1}
DB_PORT=${DB_PORT:-5432}
DB_NAME=${DB_NAME:-xiaoxin}
DB_USER=${DB_USER:-xiaoxin}
DB_PASS=${DB_PASS:-xiaoxin123}
PORT=${PORT:-8000}
PG_VERSION=${PG_VERSION:-}          # 指定后从 PostgreSQL 官方源安装该版本，如 13 / 15 / 16
SEED_DEMO=${SEED_DEMO:-0}           # 1 = 写入演示数据（仅测试环境）
PIP_INDEX=${PIP_INDEX:-https://mirrors.aliyun.com/pypi/simple/}

[ "$(id -u)" = "0" ] || { echo "请使用 root 执行"; exit 1; }
EL=$(rpm -E %{rhel} 2>/dev/null || echo 0)
ARCH=$(uname -m)
echo "==> 架构：$ARCH，系统：$(cat /etc/redhat-release 2>/dev/null || echo unknown)"
[ "$DB_PASS" = "xiaoxin123" ] && echo "!!! 警告：正在使用默认数据库密码 xiaoxin123，生产环境请通过 DB_PASS 指定强密码"
PKG=yum; command -v dnf >/dev/null 2>&1 && PKG=dnf

# ---------- 1. Python 3.8+ ----------
PY=""
find_py() {
  for p in python3.11 python3.9 python3.8 /opt/rh/rh-python38/root/usr/bin/python3 python3; do
    if command -v $p >/dev/null 2>&1 && $p -c 'import sys; exit(0 if sys.version_info >= (3,8) else 1)' 2>/dev/null; then
      PY=$(command -v $p); return 0
    fi
  done
  return 1
}
if ! find_py; then
  echo "==> 安装 Python"
  if [ "$EL" -ge 8 ]; then
    $PKG install -y python39 python39-devel || $PKG install -y python3.11 python3.11-devel
  else
    # CentOS 7：通过 SCL 安装 rh-python38
    yum install -y centos-release-scl && yum install -y rh-python38 rh-python38-python-devel
  fi
  find_py || { echo "未能安装 Python 3.8+，请手动安装后重试"; exit 1; }
fi
echo "==> 使用 Python：$PY ($($PY --version 2>&1))"

# ---------- 2. PostgreSQL（仅本机数据库）----------
PG_SVC=postgresql
if [ "$DB_HOST" = "127.0.0.1" ] || [ "$DB_HOST" = "localhost" ]; then
  # 识别已安装的 PostgreSQL：官方源版本（/usr/pgsql-N）优先，其次系统自带
  detect_pg() {
    local d
    if [ -n "$PG_VERSION" ]; then d=/usr/pgsql-$PG_VERSION; else d=$(ls -d /usr/pgsql-* 2>/dev/null | sort -t- -k2 -n | tail -1); fi
    if [ -n "$d" ] && [ -x "$d/bin/postgres" ]; then
      PG_MAJOR=${d#/usr/pgsql-}; PG_BIN=$d/bin; PG_SVC=postgresql-$PG_MAJOR
      PGDATA=/var/lib/pgsql/$PG_MAJOR/data; PG_SETUP="$PG_BIN/postgresql-$PG_MAJOR-setup initdb"
      return 0
    fi
    if [ -x /usr/bin/postgres ] && [ -z "$PG_VERSION" ]; then
      PG_BIN=/usr/bin; PG_SVC=postgresql; PGDATA=/var/lib/pgsql/data
      PG_MAJOR=$(/usr/bin/postgres --version | sed -E 's/.* ([0-9]+)(\.[0-9]+)?.*/\1/')
      PG_SETUP="postgresql-setup --initdb"; [ "$EL" -lt 8 ] && PG_SETUP="postgresql-setup initdb"
      return 0
    fi
    return 1
  }
  install_pgdg() {
    echo "==> 从 PostgreSQL 官方源安装 PostgreSQL $1"
    rpm -q pgdg-redhat-repo >/dev/null 2>&1 || \
      $PKG install -y "https://download.postgresql.org/pub/repos/yum/reporpms/EL-$EL-$ARCH/pgdg-redhat-repo-latest.noarch.rpm"
    [ "$EL" -ge 8 ] && dnf -qy module disable postgresql || true
    $PKG install -y postgresql$1-server postgresql$1-contrib
  }
  if ! detect_pg; then
    if [ -n "$PG_VERSION" ]; then
      install_pgdg "$PG_VERSION"
    elif [ "$EL" -ge 8 ]; then
      echo "==> 安装系统自带 PostgreSQL"
      # CentOS 8 默认模块流为 10，可用时切到 13
      [ "$EL" = "8" ] && dnf -qy module enable postgresql:13 2>/dev/null || true
      dnf install -y postgresql-server postgresql-contrib
    else
      # CentOS 7 自带 9.2 过旧，改用官方源 13
      install_pgdg 13
    fi
    detect_pg || { echo "PostgreSQL 安装失败，请参照部署手册 2.1 手动安装"; exit 1; }
  fi
  echo "==> PostgreSQL $PG_MAJOR（服务 $PG_SVC，数据目录 $PGDATA）"
  if [ "$PG_MAJOR" -lt 10 ] 2>/dev/null; then
    echo "PostgreSQL 版本低于 10，请设置 PG_VERSION=13 从官方源安装新版本"; exit 1
  fi
  if [ ! -f "$PGDATA/PG_VERSION" ]; then
    echo "==> 初始化数据目录"
    PGSETUP_INITDB_OPTIONS="--encoding=UTF8 --locale=C" $PG_SETUP
  fi
  # 本机 TCP 连接使用密码认证（md5 同时兼容 scram-sha-256 存储的密码）
  cp -n $PGDATA/pg_hba.conf $PGDATA/pg_hba.conf.orig
  sed -i -E 's/^(host\s+all\s+all\s+127\.0\.0\.1\/32\s+)\S+/\1md5/; s/^(host\s+all\s+all\s+::1\/128\s+)\S+/\1md5/' $PGDATA/pg_hba.conf
  systemctl enable $PG_SVC && systemctl restart $PG_SVC
  echo "==> 创建数据库用户和数据库"
  (cd /tmp && runuser -u postgres -- $PG_BIN/psql -q -v ON_ERROR_STOP=1 -v db_user="$DB_USER" -v db_pass="$DB_PASS" \
     -v db_name="$DB_NAME" -f - ) < "$SRC_DIR"/deploy/sql/00_create_db.sql
else
  echo "==> 使用独立数据库服务器 $DB_HOST:$DB_PORT（需已按部署手册 2.3 创建用户和数据库）"
fi

# ---------- 3. 应用 ----------
echo "==> 部署应用到 $APP_DIR"
mkdir -p $APP_DIR
rm -rf $APP_DIR/app
cp -r "$SRC_DIR"/app "$SRC_DIR"/requirements.txt $APP_DIR/
# 只复制示例知识和微调样例；源码中的 dev.db、uploads 等开发测试数据不带到服务器
mkdir -p $APP_DIR/data/uploads
cp -f "$SRC_DIR"/data/sample_kb.md $APP_DIR/data/
cp -rf "$SRC_DIR"/data/finetune_samples $APP_DIR/data/
[ -f $APP_DIR/config.yaml ] || cp "$SRC_DIR"/config.yaml $APP_DIR/
[ -x $APP_DIR/venv/bin/python ] || $PY -m venv $APP_DIR/venv
if [ "$OFFLINE" = "1" ]; then
  $APP_DIR/venv/bin/pip install --no-index --find-links "$SRC_DIR"/deploy/wheels -r $APP_DIR/requirements.txt
else
  $APP_DIR/venv/bin/pip install -U pip -i $PIP_INDEX
  $APP_DIR/venv/bin/pip install -r $APP_DIR/requirements.txt -i $PIP_INDEX
fi

# 写入数据库连接串（密码自动做 URL 编码）、演示数据开关；secret_key 仍为默认值时替换为随机值
DB_USER="$DB_USER" DB_PASS="$DB_PASS" DB_HOST="$DB_HOST" DB_PORT="$DB_PORT" DB_NAME="$DB_NAME" SEED_DEMO="$SEED_DEMO" \
$APP_DIR/venv/bin/python - $APP_DIR/config.yaml <<'PYEOF'
import os, re, secrets, sys
from urllib.parse import quote
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
e = os.environ
url = "postgresql+psycopg2://%s:%s@%s:%s/%s" % (quote(e["DB_USER"], safe=""), quote(e["DB_PASS"], safe=""),
                                                e["DB_HOST"], e["DB_PORT"], e["DB_NAME"])
s = re.sub(r'(?m)^(\s*url:\s*)"[^"\n]*"', lambda m: m.group(1) + '"%s"' % url, s, count=1)
s = re.sub(r'(?m)^(\s*seed_demo:\s*)\S+', lambda m: m.group(1) + ("true" if e["SEED_DEMO"] == "1" else "false"), s, count=1)
s = re.sub(r'(?m)^(\s*secret_key:\s*)"please-change-me-xiaoxin-2025"',
           lambda m: m.group(1) + '"%s"' % secrets.token_hex(24), s, count=1)
open(p, "w", encoding="utf-8").write(s)
PYEOF
chmod 600 $APP_DIR/config.yaml

id xiaoxin >/dev/null 2>&1 || useradd -r -s /sbin/nologin -d $APP_DIR xiaoxin
chown -R xiaoxin:xiaoxin $APP_DIR

# ---------- 4. 初始化数据库：建表 + 基础数据（已有数据的表自动跳过）----------
echo "==> 初始化数据库"
(cd $APP_DIR && runuser -u xiaoxin -- $APP_DIR/venv/bin/python -m app.init_data)

# ---------- 5. 系统服务 ----------
sed -e "s#__PORT__#$PORT#" -e "s#postgresql.service#$PG_SVC.service#g" "$SRC_DIR"/deploy/xiaoxin.service \
  > /etc/systemd/system/xiaoxin.service
systemctl daemon-reload && systemctl enable xiaoxin && systemctl restart xiaoxin

if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active firewalld >/dev/null 2>&1; then
  firewall-cmd --permanent --add-port=$PORT/tcp && firewall-cmd --reload
fi
for i in $(seq 1 30); do curl -sf http://127.0.0.1:$PORT/api/health >/dev/null && break; sleep 1; done
curl -s http://127.0.0.1:$PORT/api/health && echo || { echo "服务未就绪，请查看：journalctl -u xiaoxin -n 100"; exit 1; }
echo "==> 部署完成"
echo "    管理端：http://<服务器IP>:$PORT/admin/   默认账号 admin / admin123（请立即修改）"
echo "    运维H5：http://<服务器IP>:$PORT/h5/"
echo "    配置文件：$APP_DIR/config.yaml    日志：journalctl -u xiaoxin -f"
echo "    下一步：bash deploy/verify_deploy.sh http://127.0.0.1:$PORT admin admin123"
