"""接口冒烟测试：python tests/smoke_test.py http://127.0.0.1:8000"""
import io
import json
import sys
import time
import zipfile

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
c = httpx.Client(base_url=BASE, timeout=60)
fails = []


def check(name, r, expect=200):
    ok = r.status_code == expect
    print(("OK  " if ok else "FAIL"), name, r.status_code, "" if ok else r.text[:300])
    if not ok:
        fails.append(name)
    try:
        return r.json()
    except ValueError:
        return r.text


tok = check("登录", c.post("/api/login", json={"username": "admin", "password": "admin123"}))["token"]
H = {"Authorization": "Bearer " + tok}
D = {"X-Device-Id": "test-dev-1"}

# ---- 客户端上报 ----
hw = {"cpu_model": "Phytium FT-2000/4", "cpu_vendor": "Phytium", "cpu_cores": 4, "mem_total": 8, "disk_total": 256,
      "os_name": "Kylin V10", "arch": "aarch64", "brand": "GreatWall", "serial": "SN1", "dual_system": False}
r = check("终端上报", c.post("/api/client/report", json={"device_id": "test-dev-1", "hostname": "T1", "user_name": "测试",
                                                       "dept": "信息中心", "hardware": hw, "load": {"cpu": 95, "mem": 50, "disk": 40}}))
assert r["is_xinchuang"], r
hw2 = dict(hw, mem_total=16)
r = check("配件更换上报", c.post("/api/client/report", json={"device_id": "test-dev-1", "hardware": hw2}))
assert r["changes"], r
check("心跳", c.post("/api/client/heartbeat", json={"device_id": "test-dev-1", "load": {"cpu": 10}, "minutes": 5}))
check("运行数据", c.post("/api/client/run-records", json={"device_id": "test-dev-1", "records": [
    {"kind": "boot", "content": {"time": "2025-01-01 08:00"}}, {"kind": "usb", "content": {"device": "Kingston"}},
    {"kind": "app_usage", "content": {"apps": ["wps", "thunder"]}}]}))
check("客户端状态", c.get("/api/client/status", params={"device_id": "test-dev-1"}))
check("客户端配置", c.get("/api/client/config"))

# ---- 管理端终端 ----
check("终端清单", c.get("/api/admin/terminals", params={"is_xinchuang": "true", "keyword": "T"}, headers=H))
check("全量展示", c.get("/api/admin/overview", headers=H))
ind = check("监测指标", c.get("/api/admin/indicators", headers=H))
print("    指标:", {k: v for k, v in ind["overall"].items() if k != "预警"})
check("云桌面", c.get("/api/admin/cloud-desktops", headers=H))
check("配件变更", c.get("/api/admin/hw-changes", headers=H))
al = check("预警", c.get("/api/admin/alerts", headers=H))
print("    预警数:", al["total"])
check("活跃度-周", c.get("/api/admin/activity", params={"period": "week"}, headers=H))
check("运行数据统计", c.get("/api/admin/run-records/stats", headers=H))
check("字典重算", c.post("/api/admin/dicts/apply", headers=H))
v = check("新增版本", c.post("/api/admin/versions", json={"version": "1.2.0", "platform": "linux", "changelog": "x"}, headers=H))
check("版本检查", c.get("/api/client/version", params={"platform": "linux", "current": "1.0.0"}))

# ---- 消息 ----
m = check("新建即时消息", c.post("/api/admin/messages", json={"title": "测试", "content": "hello", "scope_type": "all",
                                                           "send_type": "now"}, headers=H))
msgs = check("客户端拉取消息", c.get("/api/client/messages", params={"device_id": "test-dev-1"}))
check("消息已读", c.post("/api/client/messages/%d/read" % m["id"], json={"device_id": "test-dev-1"}))
check("定时消息", c.post("/api/admin/messages", json={"title": "定时", "content": "x", "send_type": "timed",
                                                    "send_time": "2020-01-01 00:00:00"}, headers=H))
check("消息列表", c.get("/api/admin/messages", headers=H))

# ---- 运维工单 ----
t = check("来电登记", c.post("/api/ops/tickets", json={"title": "电脑蓝屏", "description": "开机蓝屏", "reporter": "张三"}, headers=H))
staff = check("人员", c.get("/api/staff", params={"role": "ops"}, headers=H))
ops_id = [s for s in staff if s["name"] == "运维张工"][0]["id"]
check("指派", c.post("/api/ops/tickets/%d/assign" % t["id"], json={"assignee_id": ops_id}, headers=H))
otok = check("运维登录", c.post("/api/login", json={"username": "yunwei1", "password": "123456"}))["token"]
OH = {"Authorization": "Bearer " + otok}
check("我的工单", c.get("/api/mobile/tickets", params={"tab": "todo"}, headers=OH))
check("签收", c.post("/api/mobile/tickets/%d/sign" % t["id"], headers=OH))
check("挂起申请", c.post("/api/mobile/tickets/%d/suspend" % t["id"], json={"reason": "等配件", "days": 2}, headers=OH))
check("挂起审核", c.post("/api/ops/tickets/%d/suspend-audit" % t["id"], json={"approve": True}, headers=H))
check("信息补充", c.put("/api/mobile/tickets/%d/info" % t["id"], json={"address": "3楼"}, headers=OH))
check("反馈", c.post("/api/mobile/tickets/%d/feedback" % t["id"], json={"solution": "重装驱动"}, headers=OH))
check("评价", c.post("/api/ops/tickets/%d/rate" % t["id"], json={"rating": 5}, headers=H))
check("上报案例", c.post("/api/ops/tickets/%d/to-case" % t["id"], json={}, headers=OH))
mt = check("移动新增工单", c.post("/api/mobile/tickets", json={"title": "现场报修", "category": "网络", "reporter": "李四"}, headers=OH))
assert mt["status"] == "处理中" and mt["source"] == "移动登记" and mt["assignee_name"], mt
check("移动新增工单反馈", c.post("/api/mobile/tickets/%d/feedback" % mt["id"], json={"solution": "重插网线"}, headers=OH))
mp = check("移动新增工单（转工单池）", c.post("/api/mobile/tickets", json={"title": "现场报修2", "self_handle": False}, headers=OH))
assert mp["status"] == "待指派" and not mp["assignee_id"], mp
check("移动补录", c.post("/api/mobile/tickets/supplement", json={"title": "补录单", "solution": "已处理"}, headers=OH))
check("工单详情", c.get("/api/ops/tickets/%d" % t["id"], headers=H))
check("工作台", c.get("/api/ops/workbench", headers=H))
check("案例检索", c.get("/api/ops/case-search", params={"keyword": "打印"}, headers=H))
check("案例库", c.get("/api/ops/cases", headers=H))

# ---- 模型 / 问答 ----
check("模型列表", c.get("/api/admin/models", headers=H))
check("可用模型", c.get("/api/models/available", headers=D))
check("路由策略", c.put("/api/admin/route", json={"strategy": "priority"}, headers=H))
with c.stream("POST", "/api/chat/send", json={"message": "你好，介绍一下麒麟系统"}, headers=D) as r:
    body = r.read().decode()
print("OK  " if "done" in body else "FAIL", "流式问答", body[:200].replace("\n", " "))
sid = json.loads(body.split("\n")[0][5:])["session_id"]
for msg in ["我的电脑坏了，需要报修", "电脑", "开机蓝屏", "3楼301", "13812345678"]:
    with c.stream("POST", "/api/chat/send", json={"message": msg, "session_id": sid}, headers=D) as r:
        out = "".join(json.loads(l[5:]).get("text", "") for l in r.read().decode().split("\n") if l.startswith("data:"))
    print("    槽位对话>", msg, "=>", out[:80])
assert "工单" in out, "槽位填充未创建工单"
check("会话详情", c.get("/api/chat/sessions/" + sid, headers=D))
check("模型监控", c.get("/api/admin/models-metrics", headers=H))

# ---- 知识库 ----
kbs = check("知识库列表", c.get("/api/kb/bases", headers=H))
files = {"files": ("测试.txt", "鲲鹏服务器部署 PostgreSQL 数据库时需要使用 aarch64 版本安装包。".encode("utf-8"), "text/plain")}
check("上传文档", c.post("/api/kb/bases/%d/docs" % kbs[0]["id"], files=files, headers=H))
time.sleep(2)
check("文档列表", c.get("/api/kb/bases/%d/docs" % kbs[0]["id"], headers=H))
s = check("检索测试", c.post("/api/kb/search", json={"kb_ids": [kbs[0]["id"]], "query": "打印机无法打印"}, headers=H))
print("    命中:", [(h["filename"], h["score"]) for h in s["hits"][:3]])
with c.stream("POST", "/api/chat/send", json={"message": "鲲鹏部署PostgreSQL用什么安装包", "mode": "kb"}, headers=H) as r:
    body = r.read().decode()
print("OK  " if "refs" in body else "FAIL", "知识问答", body[:150].replace("\n", " "))
check("RAG监控", c.get("/api/kb/metrics", headers=H))
check("检索评估", c.post("/api/kb/evaluate", json={"kb_ids": [kbs[0]["id"]], "cases": [{"query": "打印机", "expected": "CUPS"}]}, headers=H))

# ---- 合同 ----
contract_text = """信创终端采购合同
合同编号：HT-2025-001
甲方（采购人）：某某市大数据中心
乙方（供应商）：某某科技有限公司
第一条 采购内容
采购飞腾D2000台式计算机100台，预装银河麒麟操作系统，终端单价 15000 元。
第二条 合同金额
合同总金额：¥1,500,000.00元（大写：人民币壹佰伍拾万元整）。
第三条 付款方式
付款方式：验收合格后30日内支付全部款项，乙方开具发票。
第四条 交付与验收
交货期限：合同签订后30日内，交货地点：甲方指定地点。
第五条 违约责任
任何一方违约应承担违约金，违约金为合同金额的5%。
第六条 争议解决
因本合同产生的争议，提交甲方所在地人民法院诉讼解决。
第七条 合同生效
本合同自双方签字盖章之日起生效。签订日期：2025年3月1日
"""
r = check("合同上传", c.post("/api/contract/upload", files={"file": ("合同.txt", contract_text.encode("utf-8"), "text/plain")}, headers=H))
time.sleep(2)
d = check("合同结果", c.get("/api/contract/%d" % r["id"], headers=H))
print("    状态:", d["status"], "风险:", d["risk_level"], "要素:", {k: v for k, v in list(d["elements"]["elements"].items())[:6]})
print("    未通过:", [i["name"] for i in d["review"]["items"] if not i["passed"]])
# OFD 解析
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("OFD.xml", "<ofd:OFD xmlns:ofd='http://www.ofdspec.org/2016'/>")
    z.writestr("Doc_0/Pages/Page_0/Content.xml", "<ofd:Page xmlns:ofd='http://www.ofdspec.org/2016'><ofd:Content><ofd:Layer>"
               "<ofd:TextObject Boundary='0 10 100 5'><ofd:TextCode>甲方：测试单位</ofd:TextCode></ofd:TextObject>"
               "<ofd:TextObject Boundary='0 20 100 5'><ofd:TextCode>乙方：测试公司</ofd:TextCode></ofd:TextObject>"
               "</ofd:Layer></ofd:Content></ofd:Page>")
r = check("OFD合同上传", c.post("/api/contract/upload", files={"file": ("合同.ofd", buf.getvalue(), "application/ofd")}, headers=H))
time.sleep(2)
d = check("OFD结果", c.get("/api/contract/%d" % r["id"], headers=H))
print("    OFD要素:", d["elements"]["elements"]["甲方"], d["elements"]["elements"]["乙方"])
check("规则统计", c.get("/api/contract/stats", headers=H))
check("规则测试", c.post("/api/contract-rules/test", json={"rule_type": "keyword_required", "params": {"keywords": ["违约"]}, "text": "无"}, headers=H))

# ---- 工具 ----
check("计算器", c.post("/api/tools/invoke/calculator", json={"params": {"expression": "(1+2)*3"}}, headers=H))
tr = check("链式调用", c.post("/api/tools/chain", json={"steps": [{"tool": "datetime"}, {"tool": "calculator", "params": {"expression": "2**10"}}]}, headers=H))
check("工具监控", c.get("/api/tools/metrics", headers=H))
key = check("创建APIKey", c.post("/api/tools/api-keys", json={"name": "测试"}, headers=H))["key"]
check("插件注册", c.post("/open/v1/plugins/register", json={"code": "weather", "name": "天气", "endpoint": "http://x/y"}, headers={"X-API-Key": key}))

# ---- 微调 / 评估 ----
jsonl = "\n".join(json.dumps({"instruction": "问题%d：麒麟系统如何重启网络" % i, "output": "执行 systemctl restart NetworkManager 命令%d" % i}, ensure_ascii=False) for i in range(30))
ds = check("上传数据集", c.post("/api/admin/ft/datasets", data={"name": "运维QA", "kind": "运维知识"}, files={"file": ("a.jsonl", jsonl.encode(), "application/json")}, headers=H))
time.sleep(1.5)
dss = check("数据集列表", c.get("/api/admin/ft/datasets", headers=H))
print("    数据集:", dss[0]["status"], dss[0]["valid"], dss[0]["categories"])
j = check("创建微调", c.post("/api/admin/ft/jobs", json={"dataset_id": ds["id"], "params": {"epochs": 1}}, headers=H))
time.sleep(2)
check("微调详情", c.get("/api/admin/ft/jobs/%d" % j["id"], headers=H))
check("停止微调", c.post("/api/admin/ft/jobs/%d/stop" % j["id"], headers=H))
check("评估", c.post("/api/admin/eval-runs", json={"eval_set_id": 1, "model_id": 5}, headers=H))

print("\n失败项:", fails or "无")
sys.exit(1 if fails else 0)
