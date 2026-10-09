import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Depends, Header, HTTPException

from . import config
from .db import SessionLocal, User

SECRET = config.get("server.secret_key", "xiaoxin").encode()
EXPIRE = int(config.get("server.token_expire_hours", 24)) * 3600


def hash_password(pwd):
    salt = os.urandom(8).hex()
    h = hashlib.pbkdf2_hmac("sha256", pwd.encode(), salt.encode(), 100000).hex()
    return "%s$%s" % (salt, h)


def verify_password(pwd, stored):
    try:
        salt, h = stored.split("$", 1)
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(h, hashlib.pbkdf2_hmac("sha256", pwd.encode(), salt.encode(), 100000).hex())


def create_token(user):
    payload = {"uid": user.id, "role": user.role, "exp": int(time.time()) + EXPIRE}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = hmac.new(SECRET, body.encode(), hashlib.sha256).hexdigest()
    return body + "." + sig


def parse_token(token):
    try:
        body, sig = token.split(".", 1)
        if not hmac.compare_digest(sig, hmac.new(SECRET, body.encode(), hashlib.sha256).hexdigest()):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if payload["exp"] < time.time():
            return None
        return payload
    except Exception:
        return None


def current_user(authorization: str = Header(default="")):
    token = authorization.replace("Bearer ", "").strip()
    payload = parse_token(token) if token else None
    if not payload:
        raise HTTPException(401, "未登录或登录已过期")
    db = SessionLocal()
    try:
        user = db.get(User, payload["uid"])
    finally:
        db.close()
    if not user or not user.enabled:
        raise HTTPException(401, "用户不存在或已禁用")
    return user


def require_roles(*roles):
    def dep(user=Depends(current_user)):
        if user.role != "admin" and user.role not in roles:
            raise HTTPException(403, "无权限")
        return user
    return dep


admin_only = require_roles("admin")
