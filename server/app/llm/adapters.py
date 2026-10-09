"""模型适配器：将统一请求格式转换为各厂商 API 调用，并将响应解析为统一格式。

统一请求:  messages=[{"role":"system|user|assistant","content":"..."}], params={temperature, top_p, max_tokens, ...}
统一响应:  {"content": str, "usage": {"prompt_tokens": int, "completion_tokens": int}}
流式输出:  逐段 yield 文本
"""
import json

import httpx


class LLMError(Exception):
    pass


class BaseAdapter:
    def __init__(self, m):
        self.m = m  # LLMModel ORM 对象或同结构对象

    def build_params(self, override=None):
        p = {
            "temperature": self.m.temperature,
            "top_p": self.m.top_p,
            "max_tokens": self.m.max_tokens,
        }
        if self.m.extra:
            p.update(self.m.extra)
        if override:
            p.update({k: v for k, v in override.items() if v is not None})
        return p

    def chat(self, messages, params=None):
        raise NotImplementedError

    def stream(self, messages, params=None):
        raise NotImplementedError


class OpenAICompatibleAdapter(BaseAdapter):
    """OpenAI 兼容协议（DeepSeek、通义千问兼容模式、vLLM/Xinference 部署的星辰等均适用）"""

    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self.m.api_key:
            h["Authorization"] = "Bearer " + self.m.api_key
        return h

    def _url(self):
        return self.m.base_url.rstrip("/") + "/chat/completions"

    def _body(self, messages, params, stream):
        body = {"model": self.m.model, "messages": self.convert_messages(messages), "stream": stream}
        body.update(self.build_params(params))
        return body

    def convert_messages(self, messages):
        return messages

    def parse_response(self, data):
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise LLMError("响应格式无法解析: %s" % str(data)[:300])
        usage = data.get("usage") or {}
        return {"content": content, "usage": {"prompt_tokens": usage.get("prompt_tokens", 0),
                                               "completion_tokens": usage.get("completion_tokens", 0)}}

    def chat(self, messages, params=None):
        if not self.m.base_url:
            raise LLMError("未配置 base_url")
        try:
            r = httpx.post(self._url(), headers=self._headers(), json=self._body(messages, params, False),
                           timeout=self.m.timeout or 60)
        except httpx.HTTPError as e:
            raise LLMError("请求失败: %s" % e)
        if r.status_code != 200:
            raise LLMError("HTTP %s: %s" % (r.status_code, r.text[:300]))
        return self.parse_response(r.json())

    def stream(self, messages, params=None):
        if not self.m.base_url:
            raise LLMError("未配置 base_url")
        try:
            with httpx.stream("POST", self._url(), headers=self._headers(),
                              json=self._body(messages, params, True), timeout=self.m.timeout or 60) as r:
                if r.status_code != 200:
                    r.read()
                    raise LLMError("HTTP %s: %s" % (r.status_code, r.text[:300]))
                for line in r.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0].get("delta", {})
                    except (ValueError, KeyError, IndexError):
                        continue
                    # deepseek-reasoner 的思考过程不输出给用户
                    if delta.get("content"):
                        yield delta["content"]
        except httpx.HTTPError as e:
            raise LLMError("请求失败: %s" % e)


class DeepSeekAdapter(OpenAICompatibleAdapter):
    def build_params(self, override=None):
        p = super().build_params(override)
        if "reasoner" in (self.m.model or ""):
            # deepseek-reasoner 不支持 temperature/top_p
            p.pop("temperature", None)
            p.pop("top_p", None)
        return p


class QwenAdapter(OpenAICompatibleAdapter):
    pass


class TeleChatAdapter(OpenAICompatibleAdapter):
    """星辰大模型：私有化部署通常提供 OpenAI 兼容接口；如为自有协议在此改写 _url/_body/parse_response"""

    def convert_messages(self, messages):
        # 部分星辰版本不支持 system 角色，转换为首条 user 消息
        out = []
        for msg in messages:
            if msg["role"] == "system":
                out.append({"role": "user", "content": "[系统设定]" + msg["content"]})
                out.append({"role": "assistant", "content": "好的。"})
            else:
                out.append(msg)
        return out


class MockAdapter(BaseAdapter):
    """未配置真实模型时的本地兜底，保证系统可离线演示"""

    def _answer(self, messages):
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        sys = "\n".join(m["content"] for m in messages if m["role"] == "system")
        if "JSON" in sys or "json" in user[:200]:
            return "{}"
        if "参考资料" in user or "参考资料" in sys:
            body = user.split("参考资料：", 1)[-1].split("\n\n用户问题：", 1)[0]
            first = body.split("\n\n[2]", 1)[0].strip()  # 只展示最相关的一条资料
            return ("【本地兜底模型】知识库中最相关的资料如下：\n" + first[:600] +
                    "\n\n（当前未接入大模型，仅展示检索结果；配置 DeepSeek API Key 后将生成完整回答）")
        return ("【本地兜底模型】已收到您的问题：「%s」。当前大模型服务未配置或暂不可用，"
                "请管理员在『模型管理』中检查 DeepSeek 等模型的 API Key 与地址。" % user[-200:])

    def chat(self, messages, params=None):
        text = self._answer(messages)
        return {"content": text, "usage": {"prompt_tokens": 0, "completion_tokens": len(text)}}

    def stream(self, messages, params=None):
        text = self._answer(messages)
        for i in range(0, len(text), 6):
            yield text[i:i + 6]


ADAPTERS = {
    "deepseek": DeepSeekAdapter,
    "openai": OpenAICompatibleAdapter,
    "qwen": QwenAdapter,
    "telechat": TeleChatAdapter,
    "mock": MockAdapter,
}


def get_adapter(m):
    return ADAPTERS.get(m.provider, OpenAICompatibleAdapter)(m)
