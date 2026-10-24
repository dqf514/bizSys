"""鉴权业务：登录/刷新/登出/me。"""

import re
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit import record as audit
from app.core import response as R
from app.core.config import settings
from app.core.exceptions import BizException
from app.core.redis import get_redis
from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_step_up_token,
    decode_token,
    verify_password,
)
from app.modules.admin.models import Dept, LoginLog, UserDept, UserPref
from app.modules.auth.models import User, UserBankAccount, UserEmergencyContact

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
        "avatar_url": avatar_url(user),
        "roles": user.role_codes,
        "perms": user.perm_codes,
        "prefs": _prefs(db, user.id),
    }


def me(db: Session, user: User) -> dict:
    from app.modules.admin.service import all_menu_paths, menu_tree_for_user

    data = _user_out(db, user)
    data["menus"] = menu_tree_for_user(db, user)
    data["allMenuPaths"] = all_menu_paths(db)
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


# ---------------- 批次B 个人档案 / 二次验证 ----------------

STEP_UP_EXPIRE_SEC = 5 * 60
AVATAR_ALLOWED_EXT = {"jpg", "jpeg", "png", "webp"}
AVATAR_MAX_BYTES = 5 * 1024 * 1024
AVATAR_CONTENT_TYPES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
# 邮箱作为后期邮箱验证码登录标识预留：格式 + 全库唯一（排除本人、含软删不看——与 username 唯一策略一致仅看未删）
EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")
MOBILE_RE = re.compile(r"^[\d+\- ]{5,20}$")


def avatar_url(user: User) -> str:
    """头像访问 URL（公开端点，同 /public/logo：<img> 无法带 Authorization）；v 参数防缓存。"""
    if not user.avatar:
        return ""
    ts = int(user.update_time.timestamp()) if user.update_time else 0
    return f"/api/v1/auth/avatar/{user.id}?v={ts}"


def step_up(db: Session, user: User, password: str, method: str, ip: str = "") -> dict:
    """密码重验 → 短时 step-up token。method 预留 sms/email（短信/邮箱验证码接入后复用本通道）。"""
    if method != "password":
        raise BizException(R.GENERIC_PARAM, "暂不支持的验证方式")
    if not verify_password(password, user.password_hash):
        audit(db, user_id=user.id, module="auth", action="step_up_failed", ip=ip)
        db.commit()
        raise BizException(R.AUTH_OLD_PASSWORD_WRONG, "密码错误")
    token = create_step_up_token(user.id, minutes=STEP_UP_EXPIRE_SEC // 60)
    audit(db, user_id=user.id, module="auth", action="step_up", ip=ip)
    db.commit()
    return {"stepUpToken": token, "expiresIn": STEP_UP_EXPIRE_SEC}


def verify_step_up(user: User, token: str) -> None:
    """敏感接口前置校验：token 有效且属于本人，否则 403/20007。"""
    ok = False
    if token:
        try:
            payload = decode_token(token, "step_up")
            ok = int(payload.get("sub", 0)) == user.id
        except Exception:
            ok = False
    if not ok:
        raise BizException(R.AUTH_STEP_UP_REQUIRED, http_status=403)


def _direct_leader(db: Session, user: User) -> str:
    """直接领导：从主部门负责人沿部门链向上取（本部门无负责人查父部门）；链上都没有返回空串。"""
    dept_id = user.dept_id
    seen: set[int] = set()
    while dept_id and dept_id not in seen:
        seen.add(dept_id)
        leader_membership = db.scalars(
            select(UserDept).where(
                UserDept.dept_id == dept_id, UserDept.is_leader == 1, UserDept.deleted == 0
            )
        ).first()
        if leader_membership and leader_membership.user_id != user.id:
            leader = db.get(User, leader_membership.user_id)
            if leader and not leader.deleted:
                return leader.name or leader.username
        dept = db.get(Dept, dept_id)
        dept_id = dept.parent_id if dept and not dept.deleted else None
    return ""


def get_profile(db: Session, user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "name": user.name,
        "mobile": user.mobile,
        "email": user.email,
        "employeeNo": user.employee_no,
        "hireDate": user.hire_date.isoformat() if user.hire_date else "",
        "jobLevel": user.job_level,
        "avatarUrl": avatar_url(user),
        "deptName": user.dept_name,
        "leaderName": _direct_leader(db, user),
        "roles": user.role_codes,
    }


def update_profile(db: Session, user: User, mobile: str, email: str, step_up_token: str) -> dict:
    """电话/邮箱变更：任一变化都要求 step-up；邮箱格式 + 唯一性校验。"""
    changed = [f for f, v in (("mobile", mobile), ("email", email)) if v != getattr(user, f)]
    if changed:
        verify_step_up(user, step_up_token)
    if email and not EMAIL_RE.match(email):
        raise BizException(R.GENERIC_PARAM, "邮箱格式不正确")
    if mobile and not MOBILE_RE.match(mobile):
        raise BizException(R.GENERIC_PARAM, "电话格式不正确")
    if email and db.scalar(select(User.id).where(User.email == email, User.deleted == 0, User.id != user.id)):
        raise BizException(R.AUTH_EMAIL_EXISTS)
    user.mobile = mobile
    user.email = email
    if changed:
        audit(db, user_id=user.id, module="auth", action="profile_contact_change", detail={"fields": changed})
    db.commit()
    return get_profile(db, user)


def _image_magic_ok(ext: str, data: bytes) -> bool:
    """魔数校验：防改扩展名伪装图片。"""
    if ext in ("jpg", "jpeg"):
        return data[:3] == b"\xff\xd8\xff"
    if ext == "png":
        return data[:8] == b"\x89PNG\r\n\x1a\n"
    if ext == "webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


def save_avatar(db: Session, user: User, filename: str, data: bytes) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in AVATAR_ALLOWED_EXT:
        raise BizException(R.GENERIC_PARAM, "仅支持 jpg/png/webp 图片")
    if not data:
        raise BizException(R.GENERIC_PARAM, "文件为空")
    if len(data) > AVATAR_MAX_BYTES:
        raise BizException(R.GENERIC_PARAM, "图片超过 5MB")
    if not _image_magic_ok(ext, data):
        raise BizException(R.GENERIC_PARAM, "文件内容与图片格式不符")
    rel = Path("avatar") / f"{uuid.uuid4().hex}.{ext}"
    dest = Path(settings.upload_dir) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    old = user.avatar
    user.avatar = str(rel)
    audit(db, user_id=user.id, module="auth", action="avatar_update", detail={"file": filename})
    db.commit()
    if old:
        try:
            (Path(settings.upload_dir) / old).unlink(missing_ok=True)
        except OSError:
            pass
    return avatar_url(user)


def avatar_file(db: Session, uid: int) -> tuple[Path, str]:
    u = db.get(User, uid)
    if not u or u.deleted or not u.avatar:
        raise BizException(R.GENERIC_NOT_FOUND, "头像不存在")
    dest = Path(settings.upload_dir) / u.avatar
    if not dest.exists():
        raise BizException(R.GENERIC_NOT_FOUND, "头像文件已丢失")
    ext = dest.suffix.lstrip(".").lower()
    return dest, AVATAR_CONTENT_TYPES.get(ext, "application/octet-stream")


# ---- 紧急联系人 ----


def _contact_out(c: UserEmergencyContact) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "relation": c.relation,
        "phone": c.phone,
        "remark": c.remark,
        "createTime": c.create_time.strftime("%Y-%m-%d %H:%M:%S") if c.create_time else "",
    }


def list_contacts(db: Session, user: User) -> list[dict]:
    rows = db.scalars(
        select(UserEmergencyContact)
        .where(UserEmergencyContact.user_id == user.id, UserEmergencyContact.deleted == 0)
        .order_by(UserEmergencyContact.id)
    ).all()
    return [_contact_out(c) for c in rows]


def _own_contact(db: Session, user: User, cid: int) -> UserEmergencyContact:
    """只按 user_id+id 取：他人联系人一律 404（不暴露存在性）。"""
    c = db.get(UserEmergencyContact, cid)
    if not c or c.deleted or c.user_id != user.id:
        raise BizException(R.GENERIC_NOT_FOUND)
    return c


def create_contact(db: Session, user: User, name: str, relation: str, phone: str, remark: str) -> dict:
    c = UserEmergencyContact(
        user_id=user.id, name=name, relation=relation, phone=phone, remark=remark, create_by=user.id
    )
    db.add(c)
    db.flush()
    audit(db, user_id=user.id, module="auth", action="contact_create", biz_type="user_contact", biz_id=c.id)
    db.commit()
    return _contact_out(c)


def update_contact(db: Session, user: User, cid: int, name: str, relation: str, phone: str, remark: str) -> dict:
    c = _own_contact(db, user, cid)
    c.name, c.relation, c.phone, c.remark = name, relation, phone, remark
    c.update_by = user.id
    audit(db, user_id=user.id, module="auth", action="contact_update", biz_type="user_contact", biz_id=c.id)
    db.commit()
    return _contact_out(c)


def delete_contact(db: Session, user: User, cid: int) -> None:
    c = _own_contact(db, user, cid)
    c.deleted = 1
    c.update_by = user.id
    audit(db, user_id=user.id, module="auth", action="contact_delete", biz_type="user_contact", biz_id=c.id)
    db.commit()


# ---- 银行卡 ----


def mask_card(card_no: str) -> str:
    """默认脱敏：仅保留后 4 位。"""
    return f"**** {card_no[-4:]}" if len(card_no) >= 4 else "****"


def _bank_out(b: UserBankAccount, full: bool = False) -> dict:
    return {
        "id": b.id,
        "bankName": b.bank_name,
        "cardNo": b.card_no if full else mask_card(b.card_no),
        "cardLast4": b.card_no[-4:] if len(b.card_no) >= 4 else "",
        "holderName": b.holder_name,
        "createTime": b.create_time.strftime("%Y-%m-%d %H:%M:%S") if b.create_time else "",
    }


def list_bank_accounts(db: Session, user: User) -> list[dict]:
    rows = db.scalars(
        select(UserBankAccount)
        .where(UserBankAccount.user_id == user.id, UserBankAccount.deleted == 0)
        .order_by(UserBankAccount.id)
    ).all()
    return [_bank_out(b) for b in rows]


def _own_bank(db: Session, user: User, bid: int) -> UserBankAccount:
    b = db.get(UserBankAccount, bid)
    if not b or b.deleted or b.user_id != user.id:
        raise BizException(R.GENERIC_NOT_FOUND)
    return b


def create_bank_account(db: Session, user: User, bank_name: str, card_no: str, holder_name: str) -> dict:
    b = UserBankAccount(
        user_id=user.id, bank_name=bank_name, card_no=card_no, holder_name=holder_name, create_by=user.id
    )
    db.add(b)
    db.flush()
    # 审计只落后 4 位，不记完整卡号明文
    audit(db, user_id=user.id, module="auth", action="bank_create", biz_type="user_bank", biz_id=b.id,
          detail={"bankName": bank_name, "cardLast4": b.card_no[-4:]})
    db.commit()
    return _bank_out(b)


def update_bank_account(db: Session, user: User, bid: int, bank_name: str, card_no: str, holder_name: str) -> dict:
    b = _own_bank(db, user, bid)
    b.bank_name, b.card_no, b.holder_name = bank_name, card_no, holder_name
    b.update_by = user.id
    audit(db, user_id=user.id, module="auth", action="bank_update", biz_type="user_bank", biz_id=b.id,
          detail={"bankName": bank_name, "cardLast4": card_no[-4:]})
    db.commit()
    return _bank_out(b)


def delete_bank_account(db: Session, user: User, bid: int) -> None:
    b = _own_bank(db, user, bid)
    b.deleted = 1
    b.update_by = user.id
    audit(db, user_id=user.id, module="auth", action="bank_delete", biz_type="user_bank", biz_id=b.id,
          detail={"cardLast4": b.card_no[-4:]})
    db.commit()


def reveal_bank_account(db: Session, user: User, bid: int) -> dict:
    """查看完整卡号：需 step-up（路由已校验），留痕只记后 4 位。"""
    b = _own_bank(db, user, bid)
    audit(db, user_id=user.id, module="auth", action="bank_reveal", biz_type="user_bank", biz_id=b.id,
          detail={"cardLast4": b.card_no[-4:]})
    db.commit()
    return _bank_out(b, full=True)
