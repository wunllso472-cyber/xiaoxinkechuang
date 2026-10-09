from fastapi import APIRouter, Depends, HTTPException

from ..auth import hash_password, verify_password, create_token, current_user, admin_only
from ..db import get_db, User, SystemSetting
from .common import crud_router

router = APIRouter(prefix="/api", tags=["系统"])


@router.post("/login")
def login(data: dict, db=Depends(get_db)):
    u = db.query(User).filter(User.username == data.get("username")).first()
    if not u or not u.enabled or not verify_password(data.get("password", ""), u.password_hash):
        raise HTTPException(400, "用户名或密码错误")
    return {"token": create_token(u), "user": u.to_dict(exclude=("password_hash",))}


@router.get("/me")
def me(user=Depends(current_user)):
    return user.to_dict(exclude=("password_hash",))


@router.post("/me/password")
def change_password(data: dict, db=Depends(get_db), user=Depends(current_user)):
    u = db.get(User, user.id)
    if not verify_password(data.get("old", ""), u.password_hash):
        raise HTTPException(400, "原密码错误")
    u.password_hash = hash_password(data["new"])
    db.commit()
    return {"ok": True}


def _user_save(db, obj, vals, user):
    pwd = vals.pop("password_hash", None)
    if pwd and pwd != "******":
        vals["password_hash"] = hash_password(pwd)
    elif obj is None:
        vals["password_hash"] = hash_password("123456")
    return vals


users_router = crud_router(User, "/api/users", admin_only, search_fields=("username", "real_name"),
                           filter_fields=("role", "station"), hidden=("password_hash",), before_save=_user_save)


@router.get("/staff")
def staff(role: str = "", station: str = "", db=Depends(get_db), user=Depends(current_user)):
    """人员下拉（指派/转派用）"""
    q = db.query(User).filter(User.enabled == True)  # noqa: E712
    if role:
        q = q.filter(User.role.in_(role.split(",")))
    if station:
        q = q.filter(User.station == station)
    return [{"id": u.id, "name": u.real_name or u.username, "role": u.role, "station": u.station,
             "company": u.company} for u in q.all()]


@router.get("/settings/{key}")
def get_setting(key: str, db=Depends(get_db), user=Depends(current_user)):
    s = db.get(SystemSetting, key)
    return {"key": key, "value": s.value if s else None}


@router.put("/settings/{key}")
def set_setting(key: str, data: dict, db=Depends(get_db), user=Depends(admin_only)):
    s = db.get(SystemSetting, key)
    if not s:
        s = SystemSetting(key=key)
        db.add(s)
    s.value = data.get("value")
    db.commit()
    return {"ok": True}
