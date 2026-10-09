"""小信助手 第三方工具/插件 SDK（仅依赖 Python 标准库）

两部分：
1. XiaoxinClient —— 调用小信助手开放平台：注册插件、调用工具
2. PluginServer  —— 快速把一个 Python 函数发布为符合规范的 REST 插件

插件规范：
- 小信助手以 POST JSON 调用插件 endpoint，请求体即工具参数（如 {"city": "杭州"}）
- 插件返回 JSON 对象；出错时返回 HTTP 4xx/5xx 和 {"error": "..."}
- 认证：auth_type=api_key 时请求头带 X-API-Key；bearer 时带 Authorization: Bearer <token>
"""
import json
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class XiaoxinClient:
    def __init__(self, server, api_key):
        self.server = server.rstrip("/")
        self.api_key = api_key

    def _post(self, path, body):
        req = urllib.request.Request(self.server + path, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "X-API-Key": self.api_key}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())

    def register_plugin(self, code, name, endpoint, protocol="rest", method="POST", description="",
                        params_schema=None, auth_type="none", auth_value="", timeout=30, provider=""):
        """注册（或更新）插件，注册后需管理员在管理端『工具管理』中启用"""
        return self._post("/open/v1/plugins/register", {
            "code": code, "name": name, "endpoint": endpoint, "protocol": protocol, "method": method,
            "description": description, "params_schema": params_schema or {}, "auth_type": auth_type,
            "auth_value": auth_value, "timeout": timeout, "provider": provider})

    def invoke(self, code, **params):
        """调用小信助手中已启用的工具（内置工具或插件）"""
        return self._post("/open/v1/tools/%s/invoke" % code, {"params": params})


class PluginServer:
    """把函数发布为 REST 插件：

        def weather(city): return {"city": city, "weather": "晴"}
        PluginServer(weather, port=9001, api_key="secret").serve()
    """

    def __init__(self, func, host="0.0.0.0", port=9001, api_key=""):
        self.func, self.host, self.port, self.api_key = func, host, port, api_key

    def serve(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, code, obj):
                data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                if outer.api_key and self.headers.get("X-API-Key") != outer.api_key:
                    return self._send(401, {"error": "unauthorized"})
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    params = json.loads(self.rfile.read(n) or b"{}")
                    self._send(200, outer.func(**params))
                except TypeError as e:
                    self._send(400, {"error": "参数错误: %s" % e})
                except Exception as e:  # noqa
                    self._send(500, {"error": str(e)})

            def log_message(self, *args):
                pass

        print("插件服务已启动: http://%s:%d/" % (self.host, self.port))
        ThreadingHTTPServer((self.host, self.port), Handler).serve_forever()
