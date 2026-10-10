"""与服务端通信（仅依赖标准库 urllib）"""
import json
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .config import cfg


class ApiError(Exception):
    pass


def _headers(extra=None):
    h = {"X-Device-Id": cfg["device_id"], "X-Client-Key": cfg.get("client_key", "")}
    h.update(extra or {})
    return h


def _url(path, params=None):
    u = cfg["server"].rstrip("/") + path
    if params:
        u += "?" + urllib.parse.urlencode(params)
    return u


def request(method, path, body=None, params=None, timeout=30):
    data = None
    headers = _headers()
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(_url(path, params), data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read()).get("detail")
        except Exception:  # noqa
            detail = str(e)
        raise ApiError(detail)
    except (urllib.error.URLError, OSError) as e:
        raise ApiError("无法连接服务器：%s" % e)
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def get(path, params=None, timeout=30):
    return request("GET", path, params=params, timeout=timeout)


def post(path, body=None, timeout=30):
    return request("POST", path, body or {}, timeout=timeout)


def delete(path):
    return request("DELETE", path)


def upload(path, file_path, fields=None, field_name="file", timeout=300):
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in (fields or {}).items():
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (boundary, k, v)).encode("utf-8"))
    name = os.path.basename(file_path)
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    with open(file_path, "rb") as f:
        content = f.read()
    parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
                  % (boundary, field_name, name, ctype)).encode("utf-8") + content + b"\r\n")
    parts.append(("--%s--\r\n" % boundary).encode())
    headers = _headers({"Content-Type": "multipart/form-data; boundary=" + boundary})
    req = urllib.request.Request(_url(path), data=b"".join(parts), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise ApiError(e.read().decode("utf-8", "ignore")[:300])
    except (urllib.error.URLError, OSError) as e:
        raise ApiError("无法连接服务器：%s" % e)


def stream(path, body, on_event, stop_flag=None):
    """SSE 流式读取；stop_flag() 返回 True 时中断"""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(_url(path), data=data, headers=_headers({"Content-Type": "application/json"}), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            for line in r:
                if stop_flag and stop_flag():
                    break
                line = line.decode("utf-8", "ignore").strip()
                if line.startswith("data:"):
                    try:
                        on_event(json.loads(line[5:]))
                    except ValueError:
                        pass
    except Exception as e:  # noqa
        on_event({"type": "error", "text": str(e)})
    on_event({"type": "end"})


def download(path, dest, on_progress=None):
    """下载到 dest；on_progress(已下载字节, 总字节) 的总字节未知时为 0。先写临时文件，完整下载后才改名"""
    req = urllib.request.Request(_url(path), headers=_headers())
    part = dest + ".part"
    try:
        with urllib.request.urlopen(req, timeout=600) as r, open(part, "wb") as f:
            total, got = int(r.headers.get("Content-Length") or 0), 0
            while True:
                b = r.read(256 << 10)
                if not b:
                    break
                f.write(b)
                got += len(b)
                if on_progress:
                    on_progress(got, total)
        if total and got < total:
            raise ApiError("下载中断：仅收到 %d / %d 字节" % (got, total))
        os.replace(part, dest)
    except urllib.error.HTTPError as e:
        raise ApiError("服务器返回 %s" % e.code)
    except (urllib.error.URLError, OSError) as e:
        raise ApiError("%s" % getattr(e, "reason", e))
    finally:
        if os.path.exists(part):
            os.remove(part)
    return dest
