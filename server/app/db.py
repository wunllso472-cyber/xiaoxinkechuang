import datetime
import json

from sqlalchemy import create_engine, Column, Integer, String, Text, Float, Boolean, DateTime, JSON, Date
from sqlalchemy.orm import declarative_base, sessionmaker

from . import config

_url = config.get("database.url")
_kwargs = {"echo": config.get("database.echo", False), "pool_pre_ping": True}
if _url.startswith("sqlite"):
    _kwargs["connect_args"] = {"check_same_thread": False}
else:
    _kwargs["pool_size"] = config.get("database.pool_size", 10)

engine = create_engine(_url, **_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class _Base:
    def to_dict(self, exclude=()):
        d = {}
        for c in self.__table__.columns:
            if c.name in exclude:
                continue
            v = getattr(self, c.name)
            if isinstance(v, (datetime.datetime, datetime.date)):
                v = v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime.datetime) else v.isoformat()
            d[c.name] = v
        return d


Base = declarative_base(cls=_Base)
now = datetime.datetime.now


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def C(t, **kw):
    return Column(t, **kw)


# ============ 系统 / 用户 ============
class User(Base):
    __tablename__ = "sys_user"
    id = C(Integer, primary_key=True)
    username = C(String(64), unique=True, index=True)
    password_hash = C(String(256))
    real_name = C(String(64))
    role = C(String(16), default="user")  # admin 管理员 / cs 客服 / ops 运维 / user 普通用户
    station = C(String(64), default="市保障中心")  # 所属保障站
    company = C(String(64), default="")  # 供应商/厂商
    phone = C(String(32), default="")
    enabled = C(Boolean, default=True)
    created_at = C(DateTime, default=now)


class SystemSetting(Base):
    __tablename__ = "sys_setting"
    key = C(String(64), primary_key=True)
    value = C(JSON)
    description = C(String(256), default="")


# ============ 终端 ============
class Terminal(Base):
    __tablename__ = "terminal"
    id = C(Integer, primary_key=True)
    device_id = C(String(64), unique=True, index=True)
    hostname = C(String(128))
    user_name = C(String(64), default="")
    dept = C(String(128), default="")
    ip = C(String(64), default="")
    mac = C(String(64), default="")
    os_name = C(String(128), default="")
    os_version = C(String(128), default="")
    arch = C(String(32), default="")
    cpu_model = C(String(256), default="")
    cpu_vendor = C(String(64), default="")
    cpu_cores = C(Integer, default=0)
    mem_total = C(Float, default=0)  # GB
    disk_total = C(Float, default=0)  # GB
    disk_model = C(String(256), default="")
    brand = C(String(128), default="")
    model = C(String(128), default="")
    serial = C(String(128), default="")
    is_xinchuang = C(Boolean, default=False)
    dual_system = C(Boolean, default=False)
    is_cloud_desktop = C(Boolean, default=False)
    cloud_server = C(String(128), default="")
    client_version = C(String(32), default="")
    cpu_usage = C(Float, default=0)
    mem_usage = C(Float, default=0)
    disk_usage = C(Float, default=0)
    status = C(String(16), default="online")
    boot_time = C(DateTime)
    hw_snapshot = C(JSON)
    first_seen = C(DateTime, default=now)
    last_seen = C(DateTime, default=now)


class HardwareChange(Base):
    __tablename__ = "terminal_hw_change"
    id = C(Integer, primary_key=True)
    device_id = C(String(64), index=True)
    component = C(String(64))
    old_value = C(Text)
    new_value = C(Text)
    confirmed = C(Boolean, default=False)
    created_at = C(DateTime, default=now)


class RunRecord(Base):
    __tablename__ = "terminal_run_record"
    id = C(Integer, primary_key=True)
    device_id = C(String(64), index=True)
    kind = C(String(32), index=True)  # boot / shutdown / app_installed / app_usage / usb / printer
    content = C(JSON)
    created_at = C(DateTime, default=now, index=True)


class LoadRecord(Base):
    __tablename__ = "terminal_load_record"
    id = C(Integer, primary_key=True)
    device_id = C(String(64), index=True)
    cpu = C(Float)
    mem = C(Float)
    disk = C(Float)
    created_at = C(DateTime, default=now, index=True)


class ActiveDay(Base):
    __tablename__ = "terminal_active_day"
    id = C(Integer, primary_key=True)
    device_id = C(String(64), index=True)
    day = C(Date, index=True)
    online_minutes = C(Integer, default=0)


class CloudServer(Base):
    __tablename__ = "cloud_server"
    id = C(Integer, primary_key=True)
    name = C(String(128))
    ip = C(String(64))
    spec = C(String(256), default="")
    location = C(String(128), default="")
    remark = C(String(256), default="")


class AlertRule(Base):
    __tablename__ = "alert_rule"
    id = C(Integer, primary_key=True)
    name = C(String(128))
    metric = C(String(32))  # cpu_usage/mem_usage/disk_usage/offline_days/dual_system/usb/hw_change/blacklist_app/non_xinchuang
    operator = C(String(8), default=">")
    threshold = C(String(256), default="")
    level = C(String(8), default="中")
    enabled = C(Boolean, default=True)
    description = C(String(256), default="")


class Alert(Base):
    __tablename__ = "alert"
    id = C(Integer, primary_key=True)
    device_id = C(String(64), index=True)
    rule_id = C(Integer)
    rule_name = C(String(128))
    level = C(String(8))
    content = C(Text)
    status = C(String(16), default="未处理")
    created_at = C(DateTime, default=now, index=True)


# ============ 客户端管理 ============
class ClientVersion(Base):
    __tablename__ = "client_version"
    id = C(Integer, primary_key=True)
    version = C(String(32))
    platform = C(String(16))  # windows / linux
    arch = C(String(16), default="all")
    file_path = C(String(512), default="")
    changelog = C(Text, default="")
    force_update = C(Boolean, default=False)
    status = C(String(16), default="已发布")  # 草稿/灰度/已发布/已下线
    created_at = C(DateTime, default=now)


class Software(Base):
    __tablename__ = "software"
    id = C(Integer, primary_key=True)
    name = C(String(128))
    version = C(String(32), default="")
    category = C(String(64), default="办公")
    platform = C(String(16), default="linux")
    description = C(Text, default="")
    file_path = C(String(512), default="")
    size = C(Integer, default=0)
    created_at = C(DateTime, default=now)


class DictItem(Base):
    __tablename__ = "dict_item"
    id = C(Integer, primary_key=True)
    dict_type = C(String(32))  # cpu / brand / model / os / disk
    raw_value = C(String(256))
    std_value = C(String(256))
    extra = C(String(256), default="")  # 如：是否信创
    remark = C(String(256), default="")


class ClientConfig(Base):
    __tablename__ = "client_config"
    key = C(String(64), primary_key=True)
    name = C(String(128))
    value = C(String(256))
    trigger = C(String(16), default="interval")  # startup / interval / manual
    description = C(String(256), default="")


# ============ 消息 ============
class MessageTemplate(Base):
    __tablename__ = "message_template"
    id = C(Integer, primary_key=True)
    name = C(String(128))
    title = C(String(256), default="")
    content = C(Text)
    created_at = C(DateTime, default=now)


class Message(Base):
    __tablename__ = "message"
    id = C(Integer, primary_key=True)
    title = C(String(256))
    content = C(Text)
    scope_type = C(String(16), default="all")  # all / dept / device
    scope_value = C(String(512), default="")
    send_type = C(String(16), default="now")  # now / timed
    send_time = C(DateTime)
    status = C(String(16), default="待发送")  # 草稿/待发送/已发送
    target_count = C(Integer, default=0)
    read_count = C(Integer, default=0)
    creator = C(String(64), default="")
    created_at = C(DateTime, default=now)
    sent_at = C(DateTime)


class MessageReceipt(Base):
    __tablename__ = "message_receipt"
    id = C(Integer, primary_key=True)
    message_id = C(Integer, index=True)
    device_id = C(String(64), index=True)
    delivered_at = C(DateTime)
    read_at = C(DateTime)


# ============ 智能运维 ============
class Ticket(Base):
    __tablename__ = "ops_ticket"
    id = C(Integer, primary_key=True)
    ticket_no = C(String(32), unique=True)
    title = C(String(256))
    description = C(Text, default="")
    category = C(String(64), default="其他")
    reporter = C(String(64), default="")
    reporter_phone = C(String(32), default="")
    dept = C(String(128), default="")
    address = C(String(256), default="")
    device_info = C(String(256), default="")
    source = C(String(16), default="来电")  # 来电/补录/移动补录/智能问答
    # 待指派 / 待签收 / 处理中 / 挂起审核中 / 已挂起 / 待评价 / 已办结
    status = C(String(16), default="待指派", index=True)
    station = C(String(64), default="市保障中心")
    cs_id = C(Integer)
    assignee_id = C(Integer, index=True)
    assignee_name = C(String(64), default="")
    deadline = C(DateTime)
    suspend_reason = C(Text, default="")
    suspend_days = C(Integer, default=0)
    solution = C(Text, default="")
    feedback = C(Text, default="")
    rating = C(Integer)
    rating_comment = C(String(256), default="")
    created_at = C(DateTime, default=now)
    updated_at = C(DateTime, default=now, onupdate=now)
    finished_at = C(DateTime)


class TicketLog(Base):
    __tablename__ = "ops_ticket_log"
    id = C(Integer, primary_key=True)
    ticket_id = C(Integer, index=True)
    action = C(String(32))
    operator = C(String(64))
    content = C(Text, default="")
    created_at = C(DateTime, default=now)


class Case(Base):
    __tablename__ = "ops_case"
    id = C(Integer, primary_key=True)
    title = C(String(256))
    category = C(String(64), default="其他")
    question = C(Text)
    answer = C(Text)
    status = C(String(16), default="待审核")  # 待审核/已通过/已驳回
    quality = C(Boolean, default=False)  # 高质量案例
    source_ticket_id = C(Integer)
    reporter = C(String(64), default="")
    station = C(String(64), default="")
    audit_comment = C(String(256), default="")
    view_count = C(Integer, default=0)
    created_at = C(DateTime, default=now)


# ============ 大模型 ============
class LLMModel(Base):
    __tablename__ = "llm_model"
    id = C(Integer, primary_key=True)
    name = C(String(128))
    provider = C(String(32), default="deepseek")
    base_url = C(String(512), default="")
    api_key = C(String(512), default="")
    model = C(String(128), default="")
    temperature = C(Float, default=0.7)
    top_p = C(Float, default=0.95)
    max_tokens = C(Integer, default=2048)
    timeout = C(Integer, default=60)
    priority = C(Integer, default=10)
    weight = C(Integer, default=1)
    scene = C(String(128), default="")  # 适用业务场景，逗号分隔：chat,kb,contract,ops
    version = C(String(32), default="v1")
    gray_percent = C(Integer, default=100)  # 灰度比例 0-100
    enabled = C(Boolean, default=True)
    is_default = C(Boolean, default=False)
    extra = C(JSON)  # 其他透传参数，如 {"frequency_penalty":0}
    health = C(String(16), default="未知")
    last_check = C(DateTime)
    created_at = C(DateTime, default=now)


class LLMCallLog(Base):
    __tablename__ = "llm_call_log"
    id = C(Integer, primary_key=True)
    model_id = C(Integer, index=True)
    model_name = C(String(128))
    scene = C(String(32), default="chat")
    latency_ms = C(Integer)
    success = C(Boolean)
    error = C(Text, default="")
    prompt_tokens = C(Integer, default=0)
    completion_tokens = C(Integer, default=0)
    fallback = C(Boolean, default=False)
    created_at = C(DateTime, default=now, index=True)


class ChatSession(Base):
    __tablename__ = "chat_session"
    id = C(String(64), primary_key=True)
    user = C(String(64), default="")
    device_id = C(String(64), default="")
    title = C(String(256), default="新会话")
    mode = C(String(16), default="chat")  # chat / kb
    model_id = C(Integer)
    kb_id = C(Integer)
    intent = C(String(64), default="")
    slots = C(JSON)
    summary = C(Text, default="")
    expired = C(Boolean, default=False)
    created_at = C(DateTime, default=now)
    last_active = C(DateTime, default=now)


class ChatMessage(Base):
    __tablename__ = "chat_message"
    id = C(Integer, primary_key=True)
    session_id = C(String(64), index=True)
    role = C(String(16))
    content = C(Text)
    model_name = C(String(128), default="")
    refs = C(JSON)
    created_at = C(DateTime, default=now)


class Intent(Base):
    __tablename__ = "chat_intent"
    id = C(Integer, primary_key=True)
    name = C(String(64))
    keywords = C(String(256), default="")  # 触发关键词，逗号分隔
    description = C(String(256), default="")
    slots = C(JSON)  # [{"name":"device","label":"设备类型","required":true,"pattern":""}]
    action = C(String(32), default="none")  # none / create_ticket
    enabled = C(Boolean, default=True)


# ============ 知识库 ============
class KnowledgeBase(Base):
    __tablename__ = "kb"
    id = C(Integer, primary_key=True)
    name = C(String(128))
    description = C(String(512), default="")
    owner = C(String(64), default="public")  # public 或 device_id（个人私有）
    created_at = C(DateTime, default=now)


class KnowledgeDoc(Base):
    __tablename__ = "kb_doc"
    id = C(Integer, primary_key=True)
    kb_id = C(Integer, index=True)
    filename = C(String(256))
    file_path = C(String(512))
    file_type = C(String(16))
    size = C(Integer, default=0)
    md5 = C(String(64), index=True)
    version = C(Integer, default=1)
    parent_id = C(Integer)  # 历史版本指向的最新文档
    is_latest = C(Boolean, default=True)
    tags = C(String(256), default="")
    tag_checked = C(Boolean, default=False)
    status = C(String(16), default="待处理")
    progress = C(Integer, default=0)
    chunk_count = C(Integer, default=0)
    filtered_count = C(Integer, default=0)
    retry = C(Integer, default=0)
    error = C(Text, default="")
    created_at = C(DateTime, default=now)


class ImportLog(Base):
    __tablename__ = "kb_import_log"
    id = C(Integer, primary_key=True)
    doc_id = C(Integer, index=True)
    level = C(String(8), default="INFO")
    message = C(Text)
    created_at = C(DateTime, default=now)


class KnowledgeChunk(Base):
    __tablename__ = "kb_chunk"
    id = C(Integer, primary_key=True)
    kb_id = C(Integer, index=True)
    doc_id = C(Integer, index=True)
    seq = C(Integer)
    content = C(Text)
    vector = C(JSON)
    created_at = C(DateTime, default=now)


class RagLog(Base):
    __tablename__ = "kb_rag_log"
    id = C(Integer, primary_key=True)
    query = C(Text)
    kb_id = C(Integer)
    mode = C(String(16))
    hit_count = C(Integer)
    top_score = C(Float)
    retrieve_ms = C(Integer)
    generate_ms = C(Integer, default=0)
    feedback = C(Integer, default=0)  # 1 有用 / -1 无用
    created_at = C(DateTime, default=now, index=True)


# ============ 模型优化 ============
class FtDataset(Base):
    __tablename__ = "ft_dataset"
    id = C(Integer, primary_key=True)
    name = C(String(128))
    kind = C(String(16), default="运维知识")  # 运维知识 / 政策知识
    file_path = C(String(512))
    total = C(Integer, default=0)
    valid = C(Integer, default=0)
    categories = C(JSON)
    processed_path = C(String(512), default="")
    status = C(String(16), default="未处理")
    created_at = C(DateTime, default=now)


class FtJob(Base):
    __tablename__ = "ft_job"
    id = C(Integer, primary_key=True)
    name = C(String(128))
    dataset_id = C(Integer)
    base_model = C(String(128))
    method = C(String(16), default="lora")
    params = C(JSON)
    status = C(String(16), default="待运行")
    progress = C(Integer, default=0)
    metrics = C(JSON)
    log = C(Text, default="")
    created_at = C(DateTime, default=now)
    finished_at = C(DateTime)


class EvalSet(Base):
    __tablename__ = "eval_set"
    id = C(Integer, primary_key=True)
    name = C(String(128))
    items = C(JSON)  # [{"question":..,"answer":..,"keywords":[..]}]
    created_at = C(DateTime, default=now)


class EvalRun(Base):
    __tablename__ = "eval_run"
    id = C(Integer, primary_key=True)
    eval_set_id = C(Integer)
    model_id = C(Integer)
    model_name = C(String(128))
    params = C(JSON)
    accuracy = C(Float, default=0)
    professional = C(Float, default=0)
    avg_latency = C(Float, default=0)
    results = C(JSON)
    status = C(String(16), default="运行中")
    created_at = C(DateTime, default=now)


# ============ 合同智审 ============
class ContractTemplate(Base):
    __tablename__ = "contract_template"
    id = C(Integer, primary_key=True)
    name = C(String(128))
    category = C(String(64), default="采购合同")
    industry = C(String(64), default="通用")
    clauses = C(JSON)  # [{"name":"合同金额","required":true,"keywords":["金额","价款"]}]
    content = C(Text, default="")
    created_at = C(DateTime, default=now)


class ReviewRule(Base):
    __tablename__ = "review_rule"
    id = C(Integer, primary_key=True)
    code = C(String(32))
    name = C(String(128))
    category = C(String(32), default="要素完整性")
    # keyword_required / keyword_forbidden / regex_required / regex_forbidden / amount_max / amount_min / element_required / llm
    rule_type = C(String(32))
    params = C(JSON)
    level = C(String(8), default="中")
    enabled = C(Boolean, default=True)
    version = C(Integer, default=1)
    hit_count = C(Integer, default=0)
    false_positive = C(Integer, default=0)
    description = C(String(256), default="")


class Contract(Base):
    __tablename__ = "contract"
    id = C(Integer, primary_key=True)
    filename = C(String(256))
    file_path = C(String(512))
    file_type = C(String(16))
    uploader = C(String(64), default="")
    text = C(Text, default="")
    structure = C(JSON)
    elements = C(JSON)
    diff = C(JSON)
    review = C(JSON)
    risk_level = C(String(8), default="")
    status = C(String(16), default="待审查")
    template_id = C(Integer)
    duration_ms = C(Integer, default=0)
    created_at = C(DateTime, default=now)


# ============ 工具与插件 ============
class Tool(Base):
    __tablename__ = "tool"
    id = C(Integer, primary_key=True)
    code = C(String(64), unique=True)
    name = C(String(128))
    kind = C(String(16), default="plugin")  # builtin / plugin
    description = C(String(512), default="")
    protocol = C(String(16), default="rest")  # builtin / rest / graphql / websocket
    endpoint = C(String(512), default="")
    method = C(String(8), default="POST")
    auth_type = C(String(16), default="none")  # none / api_key / bearer
    auth_value = C(String(512), default="")
    params_schema = C(JSON)
    timeout = C(Integer, default=30)
    enabled = C(Boolean, default=True)
    provider = C(String(128), default="")
    created_at = C(DateTime, default=now)


class ToolCallLog(Base):
    __tablename__ = "tool_call_log"
    id = C(Integer, primary_key=True)
    tool_code = C(String(64), index=True)
    success = C(Boolean)
    latency_ms = C(Integer)
    error = C(Text, default="")
    created_at = C(DateTime, default=now, index=True)


def init_db():
    Base.metadata.create_all(engine)


def jdump(o):
    return json.dumps(o, ensure_ascii=False)
