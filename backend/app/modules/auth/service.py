"""鉴权业务：登录/刷新/登出/me，图形验证码与 MFA 二步验证。"""

import random
import re
import secrets
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
    create_mfa_pending_token,
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


# ---------------- 图形验证码 ----------------

CAPTCHA_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # 排除易混淆字符 0/O/1/I/L
CAPTCHA_TTL_SEC = 300
CAPTCHA_FAIL_LIMIT = 3  # 同一验证码连续错 3 次作废，强制刷新

_CAPTCHA_PALETTE = ["#2f54eb", "#13c2c2", "#eb2f96", "#fa8c16", "#52c41a", "#722ed1"]


def _captcha_svg(text: str) -> str:
    """自绘 SVG 验证码：字符随机旋转/位移 + 干扰曲线 + 噪点（不过度扭曲，保证人眼可读）。"""
    rnd = random.SystemRandom()
    width, height = 132, 44
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f6f8fa"/>',
    ]
    for _ in range(3):
        x1, y1 = rnd.uniform(0, 20), rnd.uniform(8, height - 8)
        x2, y2 = rnd.uniform(width - 20, width), rnd.uniform(8, height - 8)
        c1x, c1y = rnd.uniform(30, 60), rnd.uniform(0, height)
        c2x, c2y = rnd.uniform(70, 100), rnd.uniform(0, height)
        color = rnd.choice(_CAPTCHA_PALETTE)
        parts.append(
            f'<path d="M{x1:.1f} {y1:.1f} C{c1x:.1f} {c1y:.1f} {c2x:.1f} {c2y:.1f} {x2:.1f} {y2:.1f}" '
            f'stroke="{color}" stroke-width="1" fill="none" opacity="0.5"/>'
        )
    for i, ch in enumerate(text):
        x = 18 + i * 28 + rnd.uniform(-3, 3)
        y = 30 + rnd.uniform(-4, 4)
        rot = rnd.uniform(-25, 25)
        color = rnd.choice(_CAPTCHA_PALETTE)
        parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" transform="rotate({rot:.1f} {x:.1f} {y:.1f})" '
            f'font-family="Verdana, Geneva, sans-serif" font-size="24" font-weight="700" fill="{color}">{ch}</text>'
        )
    for _ in range(30):
        parts.append(
            f'<circle cx="{rnd.uniform(0, width):.1f}" cy="{rnd.uniform(0, height):.1f}" r="1" '
            f'fill="{rnd.choice(_CAPTCHA_PALETTE)}" opacity="0.4"/>'
        )
    parts.append("</svg>")
    return "".join(parts)


def create_captcha() -> dict:
    """生成一次性图形验证码：答案存 Redis（5 分钟），验证即销毁。"""
    text = "".join(secrets.choice(CAPTCHA_CHARS) for _ in range(4))
    cid = uuid.uuid4().hex
    get_redis().setex(f"captcha:{cid}", CAPTCHA_TTL_SEC, text.lower())
    out = {"captchaId": cid, "svg": _captcha_svg(text)}
    if settings.is_dev:
        # 仅 dev/sit/test 回显答案，便于自动化测试；生产（ENV=prod）绝不返回
        out["debugText"] = text
    return out


def _check_captcha(captcha_id: str, text: str) -> None:
    """校验并销毁验证码；连续错误达上限同样作废。失败不计入密码锁定计数。"""
    r = get_redis()
    key = f"captcha:{captcha_id}"
    answer = r.get(key)
    if not answer:
        raise BizException(R.AUTH_CAPTCHA_INVALID, http_status=400)
    if answer != text.strip().lower():
        fail_key = f"captcha_fail:{captcha_id}"
        n = r.incr(fail_key)
        r.expire(fail_key, CAPTCHA_TTL_SEC)
        if n >= CAPTCHA_FAIL_LIMIT:
            r.delete(key)
            r.delete(fail_key)
        raise BizException(R.AUTH_CAPTCHA_INVALID, http_status=400)
    r.delete(key)
    r.delete(f"captcha_fail:{captcha_id}")


# ---------------- MFA 二步验证 ----------------

MFA_PENDING_TTL_SEC = 5 * 60
MFA_CODE_TTL_SEC = 5 * 60
MFA_SEND_COOLDOWN_SEC = 60
MFA_CODE_FAIL_LIMIT = 5


def mask_mobile(mobile: str) -> str:
    return f"{mobile[:3]}****{mobile[-4:]}" if len(mobile) >= 7 else "****"


def mask_email(email: str) -> str:
    if "@" not in email:
        return "****"
    local, domain = email.split("@", 1)
    return f"{local[:1]}***@{domain}"


def _mfa_channels(user: User) -> list[dict]:
    """可用验证通道（按登记的手机/邮箱，掩码回显；未登记的不出现）。"""
    channels = []
    if user.mobile:
        channels.append({"channel": "sms", "target": mask_mobile(user.mobile)})
    if user.email:
        channels.append({"channel": "email", "target": mask_email(user.email)})
    return channels


def _issue_tokens(db: Session, user: User, username: str, ip: str, ua: str) -> dict:
    """登录最终放行：签发 access/refresh + 审计 + 登录日志。"""
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


def _mfa_challenge(db: Session, user: User, username: str, ip: str) -> dict:
    """密码已通过且用户开启 MFA：不发正式 token，转入二步验证。"""
    token, jti = create_mfa_pending_token(user.id, minutes=MFA_PENDING_TTL_SEC // 60)
    get_redis().setex(f"mfa:{jti}", MFA_PENDING_TTL_SEC, str(user.id))
    audit(db, user_id=user.id, module="auth", action="login_mfa_challenge", detail={"username": username}, ip=ip)
    db.commit()
    return {"mfaRequired": True, "mfaToken": token, "channels": _mfa_channels(user)}


def login(db: Session, username: str, password: str, captcha_id: str, captcha_text: str,
          ip: str = "", ua: str = "") -> dict:
    _check_captcha(captcha_id, captcha_text)
    _fail_guard(username)
    user: User | None = db.query(User).filter(User.username == username, User.deleted == 0).first()
    ok = bool(user) and verify_password(password, user.password_hash)
    if ok and user.status == "enabled":
        _clear_fail(username)
        if user.mfa_enabled:
            return _mfa_challenge(db, user, username, ip)
        return _issue_tokens(db, user, username, ip, ua)

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


def _mfa_pending_user(db: Session, mfa_token: str) -> tuple[User, str]:
    """校验 mfa_pending token + Redis 一次性凭证；任何失败一律 20010。"""
    try:
        payload = decode_token(mfa_token, "mfa_pending")
    except Exception:
        raise BizException(R.AUTH_MFA_TOKEN_INVALID, http_status=401) from None
    jti = payload.get("jti", "")
    r = get_redis()
    if not jti or r.get(f"mfa:{jti}") != payload.get("sub"):
        raise BizException(R.AUTH_MFA_TOKEN_INVALID, http_status=401)
    user = db.get(User, int(payload["sub"]))
    if not user or user.deleted or user.status != "enabled":
        raise BizException(R.AUTH_MFA_TOKEN_INVALID, http_status=401)
    return user, jti


def mfa_send(db: Session, mfa_token: str, channel: str, ip: str = "") -> dict:
    """发送二步验证码：60s 冷却；通道未配置时走调试通道（仅非生产回显 debugCode）。"""
    from app.modules.settings import notify

    user, jti = _mfa_pending_user(db, mfa_token)
    if channel == "sms" and not user.mobile:
        raise BizException(R.AUTH_MFA_CHANNEL_UNAVAILABLE)
    if channel == "email" and not user.email:
        raise BizException(R.AUTH_MFA_CHANNEL_UNAVAILABLE)
    r = get_redis()
    cool_key = f"mfa_send:{jti}:{channel}"
    if r.get(cool_key):
        raise BizException(R.AUTH_MFA_SEND_TOO_OFTEN, http_status=429)
    r.setex(cool_key, MFA_SEND_COOLDOWN_SEC, "1")

    code = f"{secrets.randbelow(1000000):06d}"
    r.setex(f"mfa_code:{jti}", MFA_CODE_TTL_SEC, code)
    r.delete(f"mfa_code_fail:{jti}")

    if channel == "sms":
        mode = notify.send_sms(db, user.mobile, code)
    else:
        mode = notify.send_login_code_email(db, user.email, code)
    audit(
        db,
        user_id=user.id,
        module="auth",
        action="mfa_send",
        detail={"channel": channel, "target": mask_mobile(user.mobile) if channel == "sms" else mask_email(user.email)},
        ip=ip,
    )
    db.commit()
    out: dict = {"sent": True, "cooldown": MFA_SEND_COOLDOWN_SEC, "mode": mode}
    if settings.is_dev:
        out["debugCode"] = code  # 仅非生产环境回显，生产（ENV=prod）绝不返回
    return out


def _clear_mfa_keys(r, jti: str) -> None:
    r.delete(f"mfa:{jti}", f"mfa_code:{jti}", f"mfa_code_fail:{jti}",
             f"mfa_send:{jti}:sms", f"mfa_send:{jti}:email")


def mfa_verify(db: Session, mfa_token: str, code: str, ip: str = "", ua: str = "") -> dict:
    """校验二步验证码：成功即发正式 token；连续错 5 次作废本次登录。"""
    user, jti = _mfa_pending_user(db, mfa_token)
    r = get_redis()
    stored = r.get(f"mfa_code:{jti}")
    if not stored:
        raise BizException(R.AUTH_MFA_CODE_INVALID, "请先获取验证码", http_status=400)
    if stored != code:
        fail_key = f"mfa_code_fail:{jti}"
        n = r.incr(fail_key)
        r.expire(fail_key, MFA_CODE_TTL_SEC)
        audit(db, user_id=user.id, module="auth", action="mfa_verify_failed", ip=ip)
        db.commit()
        if n >= MFA_CODE_FAIL_LIMIT:
            _clear_mfa_keys(r, jti)
            raise BizException(R.AUTH_MFA_CODE_INVALID, "错误次数过多，请重新登录", http_status=400)
        raise BizException(R.AUTH_MFA_CODE_INVALID, http_status=400)
    _clear_mfa_keys(r, jti)
    return _issue_tokens(db, user, user.username, ip, ua)


def mfa_toggle(db: Session, user: User, enabled: bool, step_up_token: str, ip: str = "") -> dict:
    """开关二步验证：需 step-up；开启前须已登记手机或邮箱。"""
    verify_step_up(user, step_up_token)
    if enabled and not (user.mobile or user.email):
        raise BizException(R.AUTH_MFA_NO_CHANNEL_BOUND)
    user.mfa_enabled = 1 if enabled else 0
    audit(db, user_id=user.id, module="auth", action="mfa_enable" if enabled else "mfa_disable", ip=ip)
    db.commit()
    return {"mfaEnabled": bool(user.mfa_enabled)}


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
        "mfaEnabled": bool(user.mfa_enabled),
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
        "mfaEnabled": bool(user.mfa_enabled),
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
