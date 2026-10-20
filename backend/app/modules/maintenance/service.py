"""数据维护：备份设置 / 一键清空测试数据（高危）。

清空范围（显式表清单，失败整体回滚）：
- 业务数据：合同+附件、任务+明细+样品+样品流转、报告+文件、结算/开票/收款、客户、OA 表单+实例；
- 审批运行数据：实例/待办/时间线/抄送/已读水位；
- 系统运行数据：通知、审计日志、登录日志、编号序列（归零）；
- 用户：除 username=admin 外的全部用户及其角色绑定/任职/偏好；
- 文件：uploads 下 contract/report 业务目录（branding 品牌文件保留）。
保留：流程定义与节点、角色/菜单/权限、字典、编号规则、部门、系统配置（sys_config）、admin 账号。
"""

from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.config import settings
from app.core.exceptions import BizException
from app.core.security import verify_password
from app.modules.admin.models import AuditLog, LoginLog, Notify, NumberSeq, UserDept, UserPref, UserRole
from app.modules.approval.models import (
    ApprovalCc,
    ApprovalInstance,
    ApprovalRecord,
    ApprovalTask,
    ApprovalViewState,
)
from app.modules.auth.models import User
from app.modules.contract.models import Contract, ContractAttachment
from app.modules.crm.models import Customer
from app.modules.finance.models import Invoice, Payment, Settlement
from app.modules.maintenance import backup as backup_svc
from app.modules.oa.models import OaForm, OaInstance
from app.modules.report.models import Report, ReportFile
from app.modules.settings.service import get_value, set_value
from app.modules.task.models import Task, TaskItem, TaskSample, TaskSampleFlow

# ---- 配置键 ----
KEY_BACKUP_ENABLED = "backup.enabled"
KEY_BACKUP_TIME = "backup.time"
KEY_BACKUP_RETENTION = "backup.retention"
KEY_BACKUP_DIR = "backup.dir"
KEY_SHOW_DEMO = "site.show_demo_accounts"

DEFAULT_BACKUP_TIME = "02:00"
DEFAULT_RETENTION = 7

# 清空表清单（子表在前，注意外键顺序）
_PURGE_TABLES = [
    ApprovalViewState,
    ApprovalCc,
    ApprovalTask,
    ApprovalRecord,
    ApprovalInstance,
    OaInstance,
    OaForm,
    ContractAttachment,
    Contract,
    TaskSampleFlow,
    TaskSample,
    TaskItem,
    Task,
    ReportFile,
    Report,
    Invoice,
    Payment,
    Settlement,
    Customer,
    Notify,
    AuditLog,
    LoginLog,
    NumberSeq,
]

# uploads 下属于业务数据的子目录（branding 等品牌文件保留）
_PURGE_UPLOAD_DIRS = ("contract", "report")

CONFIRM_WORD = "CLEAR"


def settings_out(db: Session) -> dict:
    return {
        "backup": {
            "enabled": get_value(db, KEY_BACKUP_ENABLED) == "1",
            "time": get_value(db, KEY_BACKUP_TIME, DEFAULT_BACKUP_TIME),
            "retention": int(get_value(db, KEY_BACKUP_RETENTION, str(DEFAULT_RETENTION)) or DEFAULT_RETENTION),
            "dir": get_value(db, KEY_BACKUP_DIR),
            "mysqldumpAvailable": bool(backup_svc.mysqldump_path()),
            "dbBackend": "sqlite" if settings.db_url.startswith("sqlite") else "mysql",
        },
        "showDemoAccounts": get_value(db, KEY_SHOW_DEMO) == "1",
    }


def update_settings(db: Session, body, user_id: int) -> dict:
    if body.backup is not None:
        b = body.backup
        if b.enabled is not None:
            set_value(db, KEY_BACKUP_ENABLED, "1" if b.enabled else "0", user_id, "每日自动备份开关")
        if b.time is not None:
            set_value(db, KEY_BACKUP_TIME, b.time, user_id, "每日备份时刻 HH:MM")
        if b.retention is not None:
            set_value(db, KEY_BACKUP_RETENTION, str(b.retention), user_id, "备份保留份数")
        if b.dir is not None:
            set_value(db, KEY_BACKUP_DIR, b.dir.strip(), user_id, "备份目录")
    if body.show_demo_accounts is not None:
        set_value(db, KEY_SHOW_DEMO, "1" if body.show_demo_accounts else "0", user_id, "登录页显示演示账号")
    db.flush()
    return settings_out(db)


def do_backup(db: Session, kind: str) -> dict:
    info = backup_svc.run_backup(kind=kind, configured_dir=get_value(db, KEY_BACKUP_DIR))
    retention = int(get_value(db, KEY_BACKUP_RETENTION, str(DEFAULT_RETENTION)) or DEFAULT_RETENTION)
    backup_svc.apply_retention(retention, get_value(db, KEY_BACKUP_DIR))
    return info


def purge(db: Session, admin: User, password: str, confirm: str, force_backup_skip: bool) -> dict:
    """一键清空测试数据。要求当前管理员密码 + 确认词；执行前自动备份（失败则阻止）。"""
    if not verify_password(password, admin.password_hash):
        raise BizException(R.AUTH_OLD_PASSWORD_WRONG, "当前密码不正确")
    if confirm != CONFIRM_WORD:
        raise BizException(R.GENERIC_PARAM, f"请输入确认词 {CONFIRM_WORD}")

    backup_info = None
    try:
        backup_info = do_backup(db, kind="manual")
    except Exception as exc:  # noqa: BLE001 备份失败默认阻止清空
        if not force_backup_skip:
            raise BizException(
                R.GENERIC_PARAM, f"清空前自动备份失败（{exc.__class__.__name__}），已阻止操作；"
                "如确认跳过备份请勾选 forceBackupSkip"
            ) from exc

    counts: dict[str, int] = {}
    for model in _PURGE_TABLES:
        result = db.execute(delete(model))
        counts[model.__tablename__] = result.rowcount

    # 非 admin 用户及其关联（角色绑定/任职/偏好）
    admin_id = admin.id
    for model in (UserRole, UserDept, UserPref):
        counts[model.__tablename__] = db.execute(delete(model).where(model.user_id != admin_id)).rowcount
    counts["sys_user"] = db.execute(delete(User).where(User.id != admin_id)).rowcount

    # 上传目录业务文件
    removed_files = 0
    for sub in _PURGE_UPLOAD_DIRS:
        d = Path(settings.upload_dir) / sub
        if d.exists():
            for f in d.rglob("*"):
                if f.is_file():
                    try:
                        f.unlink()
                        removed_files += 1
                    except OSError:
                        pass
    counts["upload_files"] = removed_files

    # 吊销全部 refresh token（所有会话下线，含 admin 自己——前端跳登录页）
    try:
        from app.core.redis import get_redis

        r = get_redis()
        keys = list(r.scan_iter("refresh:*"))
        if keys:
            r.delete(*keys)
        counts["refresh_tokens_revoked"] = len(keys)
    except Exception:  # noqa: BLE001 Redis 不可用不阻断清空（access token 短效且用户已删）
        counts["refresh_tokens_revoked"] = -1

    return {"counts": counts, "backup": backup_info}
