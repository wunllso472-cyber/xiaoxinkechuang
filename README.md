# 小信助手智能体

信创终端智能助手：桌面客户端 + 管理端 + 运维移动端（H5）+ 信创垂域大模型能力底座。

```
xiaoxinkechuang/
├── server/                     服务端（FastAPI + PostgreSQL / 人大金仓，部署于 CentOS，ARM 与 x86 通用）
│   ├── app/
│   │   ├── api/                接口：客户端、终端、消息、运维、问答/模型、知识库、合同、工具插件
│   │   ├── llm/                大模型统一调用接口：适配器 + 路由/降级
│   │   ├── services/           文档解析、RAG、合同审查、终端监测、工具调度、微调评估
│   │   └── static/             管理端(admin)、运维移动端(h5)、前端依赖(vendor，离线可用)
│   ├── config.yaml             配置（数据库、大模型参数、向量、OCR、微调）
│   ├── deploy/                 CentOS 一键部署、systemd、无 root 启停脚本(ctl.sh)、离线依赖下载、部署验证脚本
│   ├── Dockerfile / docker-compose.yml
│   └── tests/smoke_test.py     接口冒烟测试
├── client/                     桌面客户端（Python + Tkinter，Ubuntu/麒麟/统信/Windows）
│   ├── xiaoxin_client/         一键提速、探针监测、悬浮助手、智能问答、合同智审、消息、软件中心
│   ├── build_linux.sh          打包 .deb
│   └── build_windows.bat       打包 exe
├── sdk/                        第三方插件 SDK 与示例
└── docs/                       需求规格、系统设计、数据库设计、用户操作手册、技术架构、部署手册等
```

## 快速体验（开发机）

```bash
# 服务端（需要 PostgreSQL；创建库 xiaoxin / 用户 xiaoxin / 密码 xiaoxin123，或修改 config.yaml）
cd server
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000
# 临时无 PostgreSQL 时可用 SQLite 体验：XX_DATABASE_URL=sqlite:///./data/dev.db
# 人大金仓（KingbaseES）：连接串同样用 postgresql+psycopg2://，并且必须配置 database.schema（或 XX_DB_SCHEMA），见部署手册 2.8

# 客户端
cd client
pip install psutil
python -m xiaoxin_client.main        # 默认连接 http://127.0.0.1:8000（见 client/config.json）

# 冒烟测试
python server/tests/smoke_test.py http://127.0.0.1:8000
```

- 管理端 http://127.0.0.1:8000/admin/ （admin / admin123）
- 运维 H5 http://127.0.0.1:8000/h5/ （yunwei1 / 123456）
- 接口文档 http://127.0.0.1:8000/api/docs

## 大模型

在管理端『模型管理 → 模型接入与配置』填写 DeepSeek 的 API Key 即可，参数（地址、模型、temperature、top_p、max_tokens、超时、优先级、灰度、扩展参数）均可配置，详见 [docs/大模型配置说明.md](docs/大模型配置说明.md)。未配置时由“本地兜底”模型返回提示，系统其余功能可正常使用。

## 文档

- [需求功能对照表](docs/需求功能对照表.md) —— 价格清单中每一项功能对应的实现位置
- [需求规格说明书](docs/需求规格说明书.md)
- [系统设计说明书](docs/系统设计说明书.md)
- [数据库设计说明书](docs/数据库设计说明书.md)
- [用户操作手册](docs/用户操作手册.md)
- [技术架构说明](docs/技术架构说明.md)
- [系统安装部署手册](docs/部署手册.md) —— CentOS + PostgreSQL / 人大金仓，一键 / 离线 / 手动 / 无 root 权限部署（已在 CentOS 7 + KingbaseES V8R6 上验证），数据库初始化（`python -m app.init_data` 或 `server/deploy/sql/` 脚本）及初始化数据清单，各模块验证（`server/deploy/verify_deploy.sh`）
- [大模型配置说明](docs/大模型配置说明.md)
- [信创适配说明](docs/信创适配说明.md)
- [插件 SDK](sdk/README.md)

## 账号与角色

| 账号 | 角色 | 说明 |
|---|---|---|
| admin / admin123 | 管理员 | 全部功能 |
| kefu / 123456 | 客服 | 消息、来电登记、工单指派与挂起审核、案例 |
| yunwei1、yunwei2 / 123456 | 运维 | 市保障中心运维，H5 处理工单 |
| changshang / 123456 | 运维（厂商） | 纳管的厂商运维人员，可被转派 |
| xqyunwei / 123456 | 运维 | 区县保障站，上报案例 |
