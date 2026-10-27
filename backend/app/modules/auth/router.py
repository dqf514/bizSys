"""鉴权路由 /api/v1/auth。"""

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.route import EnvelopeRoute
from app.modules.auth import service
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    BankAccountIn,
    ContactIn,
    LoginIn,
    MfaSendIn,
    MfaToggleIn,
    MfaVerifyIn,
    PasswordIn,
    ProfilePatchIn,
    RefreshIn,
    StepUpIn,
)

router = APIRouter(prefix="/auth", tags=["auth"], route_class=EnvelopeRoute)


@router.get("/captcha")
def captcha():
    """图形验证码（免登录）：4 位随机字符 SVG，5 分钟有效、一次性。"""
    return service.create_captcha()


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    return service.login(db, body.username, body.password, body.captcha_id, body.captcha_text, ip, ua)


@router.post("/mfa/send")
def mfa_send(body: MfaSendIn, request: Request, db: Session = Depends(get_db)):
    """MFA 第二步：发送验证码（短信/邮件），60 秒冷却。"""
    ip = request.client.host if request.client else ""
    return service.mfa_send(db, body.mfa_token, body.channel, ip)


@router.post("/mfa/verify")
def mfa_verify(body: MfaVerifyIn, request: Request, db: Session = Depends(get_db)):
    """MFA 第二步：校验验证码，通过即发正式 token。"""
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    return service.mfa_verify(db, body.mfa_token, body.code, ip, ua)


@router.post("/mfa/toggle")
def mfa_toggle(
    body: MfaToggleIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """开关本人二步验证：需 X-Step-Up-Token 二次验证。"""
    ip = request.client.host if request.client else ""
    return service.mfa_toggle(db, user, body.enabled, request.headers.get("x-step-up-token", ""), ip)


@router.post("/refresh")
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    return service.refresh(db, body.refresh_token)


@router.post("/logout")
def logout(
    body: RefreshIn | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service.logout(db, body.refresh_token if body else None, user)
    return None


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.me(db, user)


@router.post("/password")
def change_password(
    body: PasswordIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service.change_password(db, user, body.old_password, body.new_password)
    return None


# ---------------- 批次B 个人档案 / 二次验证 ----------------


@router.get("/profile")
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """本人完整档案（登录即可读，仅本人数据）。"""
    return service.get_profile(db, user)


@router.patch("/profile")
def update_profile(
    body: ProfilePatchIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改电话/邮箱：字段有变化时要求 X-Step-Up-Token（敏感变更）。"""
    token = request.headers.get("x-step-up-token", "")
    return service.update_profile(db, user, body.mobile.strip(), body.email.strip(), token)


@router.post("/step-up")
def step_up(
    body: StepUpIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """二次身份验证：密码重验 → 5 分钟 step-up token（method 预留 sms/email）。"""
    ip = request.client.host if request.client else ""
    return service.step_up(db, user, body.password, body.method, ip)


@router.post("/profile/avatar")
def upload_avatar(
    file: UploadFile,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """头像上传：扩展名 + 大小 + 魔数校验，UUID 存储名。"""
    url = service.save_avatar(db, user, file.filename or "", file.file.read())
    return {"avatarUrl": url}


@router.get("/avatar/{uid}")
def avatar(uid: int, db: Session = Depends(get_db)):
    """头像读取（公开，同 /public/logo：<img> 标签无法携带 Authorization）。"""
    dest, content_type = service.avatar_file(db, uid)
    return FileResponse(dest, media_type=content_type)


def _require_step_up(request: Request, user: User) -> None:
    service.verify_step_up(user, request.headers.get("x-step-up-token", ""))


# ---- 紧急联系人 ----


@router.get("/profile/contacts")
def list_contacts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.list_contacts(db, user)


@router.post("/profile/contacts", status_code=201)
def create_contact(
    body: ContactIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.create_contact(db, user, body.name, body.relation, body.phone, body.remark)


@router.put("/profile/contacts/{cid}")
def update_contact(
    cid: int,
    body: ContactIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.update_contact(db, user, cid, body.name, body.relation, body.phone, body.remark)


@router.delete("/profile/contacts/{cid}")
def delete_contact(
    cid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service.delete_contact(db, user, cid)
    return None


# ---- 银行卡（增删改/查看完整卡号均需 step-up） ----


@router.get("/profile/bank-accounts")
def list_bank_accounts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.list_bank_accounts(db, user)


@router.post("/profile/bank-accounts", status_code=201)
def create_bank_account(
    body: BankAccountIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_step_up(request, user)
    return service.create_bank_account(db, user, body.bank_name, body.card_no, body.holder_name)


@router.put("/profile/bank-accounts/{bid}")
def update_bank_account(
    bid: int,
    body: BankAccountIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_step_up(request, user)
    return service.update_bank_account(db, user, bid, body.bank_name, body.card_no, body.holder_name)


@router.delete("/profile/bank-accounts/{bid}")
def delete_bank_account(
    bid: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_step_up(request, user)
    service.delete_bank_account(db, user, bid)
    return None


@router.get("/profile/bank-accounts/{bid}/reveal")
def reveal_bank_account(
    bid: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_step_up(request, user)
    return service.reveal_bank_account(db, user, bid)
