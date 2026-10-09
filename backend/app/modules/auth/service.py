"""鉴权业务：登录/刷新/登出/me。"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.common.audit import record as audit
from app.core import response as R
from app.core.config import settings
from app.core.exceptions import BizException
from app.core.redis import get_redis
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.modules.admin.models import LoginLog, UserPref
from app.modules.auth.models import User

FAIL_KEY = "login_fail:{username}"
FAIL_LIMIT = 5
FAIL_WINDOW_SEC = 15 * 60


def _fail_guard(username: str) -> None:
    r = get_redis()
    n = int(r.get(FAIL_KEY.format(username=username)) or 0)
    if n >= FAIL_LIMIT:
        raise BizException(R.AUTH_LOCKED, http_status=401)


def _record_fail(username: str) -> None:
    r = get_redis()
    key = FAIL_KEY.format(username=username)
    n = r.incr(key)
    if n == 1:
        r.expire(key, FAIL_WINDOW_SEC)


def _clear_fail(username: str) -> None:
    get_redis().delete(FAIL_KEY.format(username=username))


def _login_log(db: Session, username: str, success: int, reason: str = "", ip: str = "", ua: str = "") -> None:
    """登录日志（sys_login_log）：成功/失败都留痕。"""
    db.add(LoginLog(username=username, success=success, reason=reason, ip=ip or "", ua=(ua or "")[:255]))


def login(db: Session, username: str, password: str, ip: str = "", ua: str = "") -> dict:
    _fail_guard(username)
    user: User | None = db.query(User).filter(User.username == username, User.deleted == 0).first()
    ok = bool(user) and verify_password(password, user.password_hash)
    if ok and user.status == "enabled":
        _clear_fail(username)
        user.last_login_at = datetime.now()
        perms = user.perm_codes
        roles = user.role_codes
        access = create_access_token(user.id, roles, perms)
        refresh, jti = create_refresh_token(user.id)
        get_redis().setex(f"refresh:{jti}", 60 * 60 * 24 * settings.refresh_token_expire_days, str(user.id))
        audit(db, user_id=user.id, module="auth", action="login", detail={"username": username}, ip=ip)
        _login_log(db, username, 1, ip=ip, ua=ua)
        db.commit()
        return {
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "Bearer",
            "user": _user_out(db, user),
        }

    if user and user.status in ("disabled", "locked"):
        audit(
            db,
            user_id=user.id,
            module="auth",
            action="login_denied",
            detail={"reason": user.status},
            ip=ip,
        )
        _login_log(db, username, 0, reason=user.status, ip=ip, ua=ua)
        db.commit()
        raise BizException(R.AUTH_FORBIDDEN, http_status=401)

    _record_fail(username)
    audit(
        db,
        user_id=None,
        module="auth",
        action="login_failed",
        detail={"username": username},
        ip=ip,
    )
    _login_log(db, username, 0, reason="用户名或密码错误", ip=ip, ua=ua)
    db.commit()
    raise BizException(R.AUTH_UNAUTHORIZED, "用户名或密码错误", http_status=401)


def refresh(db: Session, refresh_token: str) -> dict:
    try:
        payload = decode_token(refresh_token, "refresh")
    except Exception:
        raise BizException(R.AUTH_UNAUTHORIZED, http_status=401) from None
    jti = payload["jti"]
    r = get_redis()
    if not r.get(f"refresh:{jti}"):  # 已吊销/过期
        raise BizException(R.AUTH_UNAUTHORIZED, http_status=401) from None
    user = db.get(User, int(payload["sub"]))
    if not user or user.deleted or user.status != "enabled":
        raise BizException(R.AUTH_UNAUTHORIZED, http_status=401) from None
    access = create_access_token(user.id, user.role_codes, user.perm_codes)
    # 旋转：吊销旧 refresh，签发新 refresh（旧 token 立即失效）
    new_refresh, new_jti = create_refresh_token(user.id)
    r.delete(f"refresh:{jti}")
    r.setex(f"refresh:{new_jti}", 60 * 60 * 24 * settings.refresh_token_expire_days, str(user.id))
    return {
        "access_token": access,
        "refresh_token": new_refresh,
        "token_type": "Bearer",
        "user": _user_out(db, user),
    }


def logout(db: Session, refresh_token: str | None, user: User) -> None:
    if refresh_token:
        try:
            payload = decode_token(refresh_token, "refresh")
            get_redis().delete(f"refresh:{payload['jti']}")
        except Exception:
            pass
    audit(db, user_id=user.id, module="auth", action="logout")
    db.commit()


def _prefs(db: Session, user_id: int) -> dict[str, str]:
    rows = db.query(UserPref).filter(UserPref.user_id == user_id, UserPref.deleted == 0).all()
    return {r.pref_key: r.pref_value for r in rows}


def _user_out(db: Session, user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "name": user.name,
        "dept_id": user.dept_id,
        "dept_name": user.dept_name,
        "email": user.email,
        "mobile": user.mobile,
        "roles": user.role_codes,
        "perms": user.perm_codes,
        "prefs": _prefs(db, user.id),
    }


def me(db: Session, user: User) -> dict:
    from app.modules.admin.service import menu_tree_for_user

    data = _user_out(db, user)
    data["menus"] = menu_tree_for_user(db, user)
    return data


def change_password(db: Session, user: User, old: str, new: str) -> None:
    if not verify_password(old, user.password_hash):
        raise BizException(R.AUTH_OLD_PASSWORD_WRONG)
    from app.core.security import hash_password

    if len(new) < 8:
        raise BizException(R.GENERIC_PARAM, "新密码至少 8 位")
    user.password_hash = hash_password(new)
    audit(db, user_id=user.id, module="auth", action="change_password")
    db.commit()
