"""首次启动初始化基础数据（仅在表为空时写入）"""
import datetime
import os
import random

from . import config
from .auth import hash_password
from .db import (SessionLocal, User, LLMModel, SystemSetting, ClientConfig, AlertRule, DictItem, Intent, KnowledgeBase,
                 KnowledgeDoc, ReviewRule, ContractTemplate, Tool, MessageTemplate, CloudServer, EvalSet, Terminal,
                 Ticket, Case, ActiveDay)
from .services import contract as cs, tools as ts, rag


def _empty(db, model):
    return db.query(model).first() is None


def seed():
    db = SessionLocal()
    try:
        if _empty(db, User):
            for u, n, r, st, comp in [("admin", "系统管理员", "admin", "市保障中心", ""),
                                      ("kefu", "客服小王", "cs", "市保障中心", ""),
                                      ("yunwei1", "运维张工", "ops", "市保障中心", ""),
                                      ("yunwei2", "运维李工", "ops", "市保障中心", ""),
                                      ("changshang", "厂商赵工", "ops", "市保障中心", "某信创厂商"),
                                      ("xqyunwei", "区县运维陈工", "ops", "西湖区保障站", "")]:
                db.add(User(username=u, real_name=n, role=r, station=st, company=comp,
                            password_hash=hash_password("admin123" if u == "admin" else "123456")))

        if _empty(db, LLMModel):
            for m in config.get("llm.default_models", []):
                db.add(LLMModel(**{k: v for k, v in m.items() if hasattr(LLMModel, k)}))

        defaults = {
            "route_strategy": config.get("llm.route_strategy", "priority"),
            "chat": {"session_timeout_minutes": config.get("llm.session_timeout_minutes", 60),
                     "context_window_rounds": config.get("llm.context_window_rounds", 6),
                     "context_strategy": config.get("llm.context_strategy", "window")},
            "planned_terminals": {"_all": 0},
            "indicator_thresholds": {"接入率": 90, "替代完成率": 80, "活跃率": 70, "双轨率": 20, "违规双系统数": 0},
            "client_key": "",
            "open_api_keys": [],
        }
        for k, v in defaults.items():
            if not db.get(SystemSetting, k):
                db.add(SystemSetting(key=k, value=v))

        if _empty(db, ClientConfig):
            for key, name, val, trig, desc in [
                ("dual_system_check", "双系统监测进程", "0", "startup", "客户端启动时执行"),
                ("hardware_collect", "配件信息采集", "3600", "interval", "间隔秒数"),
                ("load_collect", "运行负载采集(心跳)", "300", "interval", "间隔秒数"),
                ("run_data_collect", "运行数据采集(应用/U盘/打印)", "1800", "interval", "间隔秒数"),
                ("message_poll", "消息拉取", "120", "interval", "间隔秒数"),
                ("version_check", "版本检查", "0", "startup", "客户端启动时执行"),
                ("idle_process_cpu", "闲置进程判定CPU阈值(%)", "0.5", "manual", "进程优化使用"),
                ("big_file_mb", "大文件阈值(MB)", "100", "manual", "大文件检索使用"),
            ]:
                db.add(ClientConfig(key=key, name=name, value=val, trigger=trig, description=desc))

        if _empty(db, AlertRule):
            for name, metric, op, th, lv in [
                ("CPU使用率过高", "cpu_usage", ">", "90", "中"), ("内存使用率过高", "mem_usage", ">", "90", "中"),
                ("磁盘空间不足", "disk_usage", ">", "90", "高"), ("违规双系统", "dual_system", "=", "1", "高"),
                ("长期离线", "offline_days", ">", "7", "低"), ("配件更换", "hw_change", "=", "1", "中"),
                ("U盘使用", "usb", "=", "1", "低"), ("违规软件", "blacklist_app", "in", "迅雷,thunder,steam,qq游戏", "中"),
                ("非信创终端", "non_xinchuang", "=", "1", "低")]:
                db.add(AlertRule(name=name, metric=metric, operator=op, threshold=th, level=lv,
                                 enabled=metric not in ("non_xinchuang", "usb")))

        if _empty(db, DictItem):
            for t, raw, std, extra in [
                ("cpu", "Phytium", "飞腾", "信创"), ("cpu", "FT-2000", "飞腾FT-2000/4", "信创"),
                ("cpu", "D2000", "飞腾D2000", "信创"), ("cpu", "Kunpeng", "鲲鹏", "信创"),
                ("cpu", "HUAWEI Kunpeng 920", "鲲鹏920", "信创"), ("cpu", "Hygon", "海光", "信创"),
                ("cpu", "ZHAOXIN", "兆芯", "信创"), ("cpu", "KX-6000", "兆芯KX-6000", "信创"),
                ("cpu", "Loongson", "龙芯", "信创"), ("cpu", "Intel", "Intel", "非信创"), ("cpu", "AMD", "AMD", "非信创"),
                ("os", "Kylin", "银河麒麟", "信创"), ("os", "UOS", "统信UOS", "信创"), ("os", "UnionTech", "统信UOS", "信创"),
                ("os", "Ubuntu", "Ubuntu", "非信创"), ("os", "Windows", "Windows", "非信创"),
                ("brand", "LENOVO", "联想", ""), ("brand", "Huawei", "华为", ""), ("brand", "TsingHua Tongfang", "清华同方", ""),
                ("brand", "GreatWall", "长城", ""), ("brand", "Inspur", "浪潮", "")]:
                db.add(DictItem(dict_type=t, raw_value=raw, std_value=std, extra=extra))

        if _empty(db, Intent):
            db.add(Intent(name="故障报修", keywords="报修,坏了,故障,打不开,无法开机,蓝屏,黑屏",
                          description="收集报修信息后自动创建运维工单", action="create_ticket",
                          slots=[{"name": "device", "label": "故障设备类型（电脑/打印机/网络等）", "required": True},
                                 {"name": "problem", "label": "故障现象描述", "required": True},
                                 {"name": "address", "label": "所在地点（楼层/房间）", "required": True},
                                 {"name": "phone", "label": "联系电话", "required": True, "pattern": r"(1[3-9]\d{9})"}]))
            db.add(Intent(name="会议室预订", keywords="订会议室,预订会议室", action="none", enabled=False,
                          slots=[{"name": "time", "label": "时间", "required": True},
                                 {"name": "people", "label": "人数", "required": True},
                                 {"name": "preference", "label": "偏好(投影/视频)", "required": False}]))

        if _empty(db, ReviewRule):
            for code, name, cat, rt, params, lv in cs.DEFAULT_RULES:
                db.add(ReviewRule(code=code, name=name, category=cat, rule_type=rt, params=params, level=lv))
        if _empty(db, ContractTemplate):
            db.add(ContractTemplate(name="信创终端采购合同标准模板", category="采购合同", industry="政企",
                                    clauses=cs.DEFAULT_TEMPLATE_CLAUSES))

        if _empty(db, Tool):
            for code, (name, fn, schema) in ts.BUILTIN.items():
                db.add(Tool(code=code, name=name, kind="builtin", protocol="builtin", params_schema=schema,
                            description=name, provider="小信助手"))

        if _empty(db, MessageTemplate):
            db.add(MessageTemplate(name="系统升级通知", title="小信助手升级通知",
                                   content="尊敬的用户：小信助手将于{时间}升级至新版本，届时请保持终端开机联网。"))
            db.add(MessageTemplate(name="安全提醒", title="终端安全提醒", content="请勿在信创终端上安装未经授权的软件，禁止使用双系统。"))
        if _empty(db, CloudServer):
            db.add(CloudServer(name="云桌面服务器-01", ip="10.10.1.11", spec="鲲鹏920 64核/256G", location="机房A"))
            db.add(CloudServer(name="云桌面服务器-02", ip="10.10.1.12", spec="飞腾S2500 64核/256G", location="机房A"))
        if _empty(db, EvalSet):
            db.add(EvalSet(name="信创运维基础测试集", items=[
                {"question": "银河麒麟系统如何查看系统版本？", "answer": "使用 cat /etc/os-release 或 nkvers 命令查看",
                 "keywords": ["os-release", "nkvers"]},
                {"question": "统信UOS下打印机无法打印一般如何排查？", "answer": "检查CUPS服务、驱动、连接与打印队列",
                 "keywords": ["CUPS", "驱动", "队列"]},
                {"question": "飞腾CPU属于什么架构？", "answer": "ARM架构（ARMv8）", "keywords": ["ARM"]}]))
        db.commit()

        if _empty(db, KnowledgeBase):
            kb = KnowledgeBase(name="信创运维知识库", description="信创终端运维知识、常见故障解决方案", owner="public")
            db.add(kb)
            db.commit()
            db.add(KnowledgeBase(name="信创政策知识库", description="信创相关政策法规", owner="public"))
            db.commit()
            sample = os.path.join(config.BASE_DIR, "data", "sample_kb.md")
            if os.path.exists(sample):
                d = KnowledgeDoc(kb_id=kb.id, filename="信创终端常见问题.md", file_path=sample, file_type="md",
                                 size=os.path.getsize(sample), md5=rag.file_md5(sample))
                db.add(d)
                db.commit()
                rag.process_doc(d.id)

        if config.get("server.seed_demo", True) and _empty(db, Terminal):
            _demo(db)
    finally:
        db.close()


def _demo(db):
    """演示数据：若干终端、工单、案例"""
    now = datetime.datetime.now()
    depts = ["办公室", "财务部", "信息中心", "市场部"]
    specs = [("飞腾D2000", "Phytium", "银河麒麟", True), ("鲲鹏920", "HUAWEI", "统信UOS", True),
             ("兆芯KX-6000", "Zhaoxin", "统信UOS", True), ("Intel Core i5-10400", "Intel", "Windows", False)]
    for i in range(12):
        cpu, vendor, os_name, xc = specs[i % 4]
        t = Terminal(device_id="demo-%03d" % i, hostname="PC-%03d" % i, user_name="用户%d" % (i % 9), dept=depts[i % 4],
                     ip="10.20.0.%d" % (10 + i), os_name=os_name, cpu_model=cpu, cpu_vendor=vendor, cpu_cores=8,
                     mem_total=16, disk_total=512, brand="长城" if xc else "联想", model="TD120" if xc else "M720",
                     is_xinchuang=xc, dual_system=(i == 5), is_cloud_desktop=(i >= 9),
                     cloud_server="云桌面服务器-01" if i >= 9 else "", client_version="1.0.0",
                     cpu_usage=random.randint(5, 95), mem_usage=random.randint(20, 92), disk_usage=random.randint(30, 95),
                     status="online" if i % 5 else "offline", last_seen=now - datetime.timedelta(days=0 if i % 5 else 9),
                     arch="aarch64" if vendor in ("Phytium", "HUAWEI") else "x86_64")
        db.add(t)
        for d in range(14):
            if random.random() < 0.7:
                db.add(ActiveDay(device_id=t.device_id, day=(now - datetime.timedelta(days=d)).date(), online_minutes=300))
    ops = db.query(User).filter(User.username == "yunwei1").first()
    for i, (title, st) in enumerate([("打印机无法打印", "待指派"), ("WPS 打开文档崩溃", "待签收"), ("麒麟系统无法连接网络", "处理中"),
                                     ("U盘无法识别", "待评价"), ("显示器黑屏", "已办结")]):
        db.add(Ticket(ticket_no="GD%s%02d" % (now.strftime("%Y%m%d"), i), title=title, description=title + "，请尽快处理",
                      category="终端故障", reporter="用户%d" % i, reporter_phone="1380000000%d" % i, dept=depts[i % 4],
                      status=st, assignee_id=ops.id if st != "待指派" else None,
                      assignee_name=ops.real_name if st != "待指派" else "",
                      deadline=now + datetime.timedelta(hours=48), created_at=now - datetime.timedelta(hours=i * 5),
                      finished_at=now if st == "已办结" else None))
    db.add(Case(title="麒麟系统打印机脱机", category="打印外设", question="打印机显示脱机无法打印",
                answer="1. 检查 cups 服务：systemctl restart cups；2. 删除并重新添加打印机；3. 确认驱动为厂商信创版本。",
                status="已通过", quality=True, reporter="运维张工", station="市保障中心"))
    db.add(Case(title="统信UOS 无线网卡无法识别", category="网络", question="笔记本无线网络列表为空",
                answer="确认网卡型号，安装对应驱动包，执行 sudo modprobe 加载驱动后重启 NetworkManager。",
                status="待审核", reporter="区县运维陈工", station="西湖区保障站"))
    db.commit()
