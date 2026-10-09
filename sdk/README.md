# 小信助手插件 SDK

`xiaoxin_sdk.py` 只依赖 Python 标准库。

## 接入流程

1. 管理员在『工具与插件 → 插件开放平台』创建 API Key 并发给开发者。
2. 开发者实现插件服务（REST / GraphQL / WebSocket 任选），用 SDK 或直接调用接口注册：
   ```python
   from xiaoxin_sdk import XiaoxinClient
   cli = XiaoxinClient("http://小信服务器:8000", "xx-密钥")
   cli.register_plugin("weather", "天气查询", "http://插件地址/", params_schema={"city": "城市"})
   ```
3. 管理员在『工具管理』审核启用后，插件即可在工具调用、链式调度中使用，调用量/成功率/耗时自动纳入『工具性能评估』。

## 接口

| 接口 | 说明 |
|---|---|
| `POST /open/v1/plugins/register` | 注册/更新插件，Header `X-API-Key` |
| `POST /open/v1/tools/{code}/invoke` | 调用已启用工具，Body `{"params": {...}}` |

插件协议：

- **REST**：按配置的方法调用 endpoint，JSON 请求体即参数（GET 时为查询参数），返回 JSON。
- **GraphQL**：POST `{"query": params_schema.query, "variables": params}`。
- **WebSocket**：连接后发送一条 JSON 参数消息，读取一条 JSON 响应。
- 认证：`auth_type=api_key` 时带 `X-API-Key` 头；`bearer` 时带 `Authorization: Bearer`。

## 示例

`example_plugin.py` 演示用 `PluginServer` 把函数发布为插件并自动注册：

```bash
python example_plugin.py --server http://127.0.0.1:8000 --key xx-xxxx --host 本机IP
```
