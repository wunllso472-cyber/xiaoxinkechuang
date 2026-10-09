#!/bin/bash
# 小信助手部署验证脚本：逐模块检查服务是否正常（只读检查为主，仅“客户端上报”会写入一条测试终端记录）
# 用法：bash deploy/verify_deploy.sh [服务地址] [管理员账号] [管理员密码]
#   例：bash deploy/verify_deploy.sh http://127.0.0.1:8000 admin admin123
# 依赖：curl、python3（仅用于解析 JSON）
BASE=${1:-http://127.0.0.1:8000}
ADMIN_USER=${2:-admin}
ADMIN_PASS=${3:-admin123}
PASS=0; FAIL=0
PY=$(command -v python3 || command -v python)

OUT=${TMPDIR:-/tmp}/xx_verify.out
BODY=${TMPDIR:-/tmp}/xx_verify_body.json
body() { printf '%s' "$1" > "$BODY"; }   # 请求体写入文件再发送，避免命令行参数编码问题

json() { $PY -c "import sys,json; d=json.load(sys.stdin); print(eval(sys.argv[1]))" "$1" 2>/dev/null; }

check() {  # check 名称 期望状态码 curl参数...
  local name=$1 expect=$2; shift 2
  local code
  code=$(curl -s -o $OUT -w "%{http_code}" --max-time 60 "$@")
  if [ "$code" = "$expect" ]; then
    PASS=$((PASS+1)); printf "  [通过] %-28s HTTP %s\n" "$name" "$code"
  else
    FAIL=$((FAIL+1)); printf "  [失败] %-28s HTTP %s  %s\n" "$name" "$code" "$(head -c 200 $OUT)"
  fi
}

echo "== 1. 基础服务 =="
check "健康检查 /api/health"      200 "$BASE/api/health"
check "接口文档 /api/docs"        200 "$BASE/api/docs"
check "管理端页面 /admin/"        200 "$BASE/admin/"
check "运维H5页面 /h5/"           200 "$BASE/h5/"
check "前端依赖 /vendor"          200 "$BASE/vendor/vue.global.prod.js"

echo "== 2. 账号认证 =="
TOKEN=$(curl -s -X POST "$BASE/api/login" -H "Content-Type: application/json" \
  -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PASS\"}" | json 'd["token"]')
if [ -z "$TOKEN" ]; then
  echo "  [失败] 管理员登录失败，请检查账号密码或数据库初始化，后续检查终止"; exit 1
fi
PASS=$((PASS+1)); echo "  [通过] 管理员登录"
H="Authorization: Bearer $TOKEN"
check "当前用户 /api/me"          200 -H "$H" "$BASE/api/me"
check "用户管理"                  200 -H "$H" "$BASE/api/users"

echo "== 3. 终端接入（客户端接口） =="
check "客户端配置下发"            200 "$BASE/api/client/config"
body '{"device_id":"deploy-verify-0001","hostname":"deploy-verify","user_name":"部署验证","dept":"信息中心","hardware":{"cpu_model":"Phytium FT-2000/4","os_name":"Kylin V10","arch":"aarch64","mem_total":8,"disk_total":256}}'
check "终端上报（测试终端）"      200 -X POST "$BASE/api/client/report" -H "Content-Type: application/json" --data-binary @"$BODY"
check "终端状态查询"              200 "$BASE/api/client/status?device_id=deploy-verify-0001"
check "版本检查"                  200 "$BASE/api/client/version?platform=linux&current=1.0.0"

echo "== 4. 终端监测（管理端） =="
check "全量总览"                  200 -H "$H" "$BASE/api/admin/overview"
check "监测指标"                  200 -H "$H" "$BASE/api/admin/indicators"
check "终端清单"                  200 -H "$H" "$BASE/api/admin/terminals"
check "预警列表"                  200 -H "$H" "$BASE/api/admin/alerts"

echo "== 5. 消息管理 =="
check "消息列表"                  200 -H "$H" "$BASE/api/admin/messages"
check "消息模板"                  200 -H "$H" "$BASE/api/admin/message-templates"

echo "== 6. 智能运维 =="
check "运维工作台"                200 -H "$H" "$BASE/api/ops/workbench"
check "工单池"                    200 -H "$H" "$BASE/api/ops/tickets"
check "案例库"                    200 -H "$H" "$BASE/api/ops/cases"
check "移动端统计（H5接口）"      200 -H "$H" "$BASE/api/mobile/stats"

echo "== 7. 大模型与问答 =="
check "模型列表"                  200 -H "$H" "$BASE/api/admin/models"
check "路由策略"                  200 -H "$H" "$BASE/api/admin/route"
body '{"message":"麒麟系统如何查看IP地址？"}'
check "非流式问答 /api/chat/ask"  200 -X POST -H "$H" -H "Content-Type: application/json" "$BASE/api/chat/ask" --data-binary @"$BODY"
echo "      回答来自模型：$(json 'd.get("model","")' < $OUT)（显示“本地兜底”说明尚未配置可用的大模型 API Key）"

echo "== 8. 知识库（RAG） =="
check "知识库列表"                200 -H "$H" "$BASE/api/kb/bases"
KB_ID=$(json 'd[0]["id"]' < $OUT)
body "{\"kb_ids\":[${KB_ID:-1}],\"query\":\"打印机无法打印\"}"
check "检索测试"                  200 -X POST -H "$H" -H "Content-Type: application/json" "$BASE/api/kb/search" --data-binary @"$BODY"
check "RAG 监控"                  200 -H "$H" "$BASE/api/kb/metrics"

echo "== 9. 合同智审 =="
check "合同列表"                  200 -H "$H" "$BASE/api/contract"
check "规则效果统计"              200 -H "$H" "$BASE/api/contract/stats"
check "审查规则"                  200 -H "$H" "$BASE/api/contract/rules"

echo "== 10. 模型微调与评估 =="
check "微调数据集"                200 -H "$H" "$BASE/api/admin/ft/datasets"
check "微调任务"                  200 -H "$H" "$BASE/api/admin/ft/jobs"
check "评估记录"                  200 -H "$H" "$BASE/api/admin/eval-runs"

echo "== 11. 工具与插件 =="
check "工具列表"                  200 -H "$H" "$BASE/api/admin/tools"
body '{"params":{"expression":"(1+2)*3"}}'
check "内置工具调用（计算器）"    200 -X POST -H "$H" -H "Content-Type: application/json" "$BASE/api/tools/invoke/calculator" --data-binary @"$BODY"
check "工具性能统计"              200 -H "$H" "$BASE/api/tools/metrics"

echo
echo "验证完成：通过 $PASS 项，失败 $FAIL 项"
[ "$FAIL" = "0" ]
