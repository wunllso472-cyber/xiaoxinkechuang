"""示例：开发一个“设备保修查询”插件并注册到小信助手

1. 管理端『工具与插件 → 插件开放平台』创建 API Key
2. python example_plugin.py --server http://小信服务器:8000 --key xx-xxxx --host 本机IP
3. 管理端『工具管理』启用 warranty 插件，即可在工具调用测试 / 链式调度中使用
"""
import argparse
import threading
import time

from xiaoxin_sdk import XiaoxinClient, PluginServer

WARRANTY = {"SN001": "2027-06-30", "SN002": "2025-12-31"}


def warranty(serial="", **_):
    exp = WARRANTY.get(serial)
    if not exp:
        return {"serial": serial, "found": False}
    return {"serial": serial, "found": True, "expire": exp, "in_warranty": exp >= time.strftime("%Y-%m-%d")}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:8000")
    ap.add_argument("--key", required=True, help="开放平台 API Key")
    ap.add_argument("--host", default="127.0.0.1", help="小信服务器可访问到的本机地址")
    ap.add_argument("--port", type=int, default=9001)
    a = ap.parse_args()
    threading.Thread(target=PluginServer(warranty, port=a.port, api_key="plugin-secret").serve, daemon=True).start()
    cli = XiaoxinClient(a.server, a.key)
    print(cli.register_plugin("warranty", "设备保修查询", "http://%s:%d/" % (a.host, a.port),
                              description="按序列号查询终端保修期", params_schema={"serial": "设备序列号"},
                              auth_type="api_key", auth_value="plugin-secret", provider="示例厂商"))
    print("插件运行中，Ctrl+C 退出")
    while True:
        time.sleep(3600)
