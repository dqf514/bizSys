"""人事事务纯逻辑层（B10-1 / HR L1 人事异动）。

状态机：`draft → approving → approved → effective`，另有 `rejected`（可改后重提）。

**审批通过 ≠ 生效**：离职单需要「择时生效」（离职当日回收权限），所以副作用
**不挂在审批回调上**，统一由 `POST /hr/employments/{id}/effect` 触发
（`effect_employment()`）。这也是合规红线 —— 副作用只能由本模块执行，
**不得手工改 `sys_user.status`**（见 `docs/compliance-baseline.md`）。

四种事务的副作用：

| 事务 | 副作用 |
| --- | --- |
| `onboard` 入职 | 建 `sys_user`（可跳过）→ 建主部门任职 → 绑角色 → 回填 `hr_employee.user_id` → 同步冗余列 → 试用 |
| `transfer` 调岗 | 改档案归属 → 改 `sys_user.dept_id/dept_name` → 同步主部门任职 |
| `resign` 离职 | 禁用账号（**不删**）→ 关 MFA → 撤销授权 → 代理失效 → 清岗位 A/B 角 → 置离职 + 离职日期 |
| `rehire` 返聘 | 恢复原账号 → 正式在职；**不恢复授权** |

离职的完整副作用清单见 `docs/compliance-baseline.md` §6。
"""

import json
import secrets
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit import record
from app.core import response as R
from app.core.crypto import decrypt_text_domain, encrypt_text_domain
from app.core.exceptions import BizException
from app.modules.admin.models import Dept, Role, UserDept
from app.modules.admin.service import create_user_account
from app.modules.auth.models import User
from app.modules.hr import authorization as auth_svc
from app.modules.hr import employee as emp_svc
from app.modules.hr.constants import EVENT_TYPE_CN
from app.modules.hr.models import (
    HrDelegate,
    HrEmployee,
    HrEmployment,
    HrEmploymentEvent,
    HrPosition,
)

STATUS_DRAFT = "draft"
STATUS_APPROVING = "approving"
STATUS_APPROVED = "approved"
STATUS_EFFECTIVE = "effective"
STATUS_REJECTED = "rejected"

# 合法状态跃迁（其余一律拒绝 —— 状态机在数据层兜底，不靠前端）
TRANSITIONS: dict[str, tuple[str, ...]] = {
    STATUS_DRAFT: (STATUS_APPROVING,),
    STATUS_APPROVING: (STATUS_APPROVED, STATUS_REJECTED, STATUS_DRAFT),
    STATUS_APPROVED: (STATUS_EFFECTIVE,),
    STATUS_EFFECTIVE: (),
    STATUS_REJECTED: (STATUS_DRAFT, STATUS_APPROVING),
}

# 初始密码密文的域分隔标识（禁止与其他用途共用密钥）
ACCOUNT_PASSWORD_DOMAIN = "hr-account-password"

# 岗位类型 → 默认角色 code（仓库内暂无 manager 角色，管理岗同样落 biz_user，
# 由 HR 在入职单里显式指定角色覆盖 —— 角色能力映射属 B10-2）
DEFAULT_ROLE_BY_POSITION = {
    "staff": "biz_user",
    "manager": "biz_user",
    "key": "biz_user",
}


def _now() -> datetime:
    return datetime.now()


def encrypt_account_password(plain: str) -> str:
    v = (plain or "").strip()
    if not v:
        return ""
    return encrypt_text_domain(ACCOUNT_PASSWORD_DOMAIN, v)


def decrypt_account_password(value: str) -> str:
    if not value:
        return ""
    return decrypt_text_domain(ACCOUNT_PASSWORD_DOMAIN, value)


def snapshot(row: HrEmployment) -> dict:
    """变更时点的人事事务快照（写进只追加的事件表）。"""
    return {
        "empNo": row.emp_no,
        "eventType": row.event_type,
        "employeeId": row.employee_id,
        "userId": row.user_id or 0,
        "userName": row.user_name,
        "deptId": row.dept_id or 0,
        "deptName": row.dept_name,
        "newDeptId": row.new_dept_id or 0,
        "newDeptName": row.new_dept_name,
        "positionId": row.position_id or 0,
        "positionName": row.position_name,
        "newPositionId": row.new_position_id or 0,
        "newPositionName": row.new_position_name,
        "effectiveDate": row.effective_date.isoformat() if row.effective_date else "",
        "status": row.status,
        "reason": row.reason,
    }


def out(row: HrEmployment) -> dict:
    """人事事务出参（camelCase）。"""
    return {
        "id": row.id,
        "empNo": row.emp_no,
        "eventType": row.event_type,
        "eventTypeText": EVENT_TYPE_CN.get(row.event_type, row.event_type),
        "employeeId": row.employee_id,
        "userId": row.user_id,
        "userName": row.user_name,
        "deptId": row.dept_id,
        "deptName": row.dept_name,
        "newDeptId": row.new_dept_id,
        "newDeptName": row.new_dept_name,
        "positionId": row.position_id,
        "positionName": row.position_name,
        "newPositionId": row.new_position_id,
        "newPositionName": row.new_position_name,
        "effectiveDate": row.effective_date.isoformat() if row.effective_date else "",
        "reason": row.reason,
        "status": row.status,
        "flowInstanceId": row.flow_instance_id,
        "applicantId": row.applicant_id,
        "applicantName": row.applicant_name,
        "approverId": row.approver_id,
        "approverName": row.approver_name,
        "approvedAt": row.approved_at.isoformat() if row.approved_at else "",
        "remark": row.remark,
        "createAccount": row.create_account,
        "accountUsername": row.account_username,
        "createTime": row.create_time.isoformat() if row.create_time else "",
    }


def write_event(
    db: Session,
    row: HrEmployment,
    *,
    event_type: str,
    from_status: str,
    to_status: str,
    operator_id: int | None = None,
    operator_name: str = "",
    reason: str = "",
) -> HrEmploymentEvent:
    """写一条人事事务变更事件（**只追加**）。"""
    ev = HrEmploymentEvent(
        employment_id=row.id,
        emp_no=row.emp_no,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        operator_id=operator_id,
        operator_name=operator_name or "",
        reason=reason or "",
        effective_at=_now(),
        snapshot=json.dumps(snapshot(row), ensure_ascii=False),
    )
    db.add(ev)
    db.flush()
    return ev


def timeline(db: Session, employment_id: int) -> list[dict]:
    """人事事务变更轨迹（倒序）。"""
    rows = db.scalars(
        select(HrEmploymentEvent)
        .where(HrEmploymentEvent.employment_id == employment_id)
        .order_by(HrEmploymentEvent.id.desc())
    ).all()
    return [
        {
            "id": r.id,
            "employmentId": r.employment_id,
            "empNo": r.emp_no,
            "eventType": r.event_type,
            "fromStatus": r.from_status,
            "toStatus": r.to_status,
            "operatorId": r.operator_id,
            "operatorName": r.operator_name,
            "reason": r.reason,
            "effectiveAt": r.effective_at.isoformat() if r.effective_at else "",
        }
        for r in rows
    ]


def assert_transition(row: HrEmployment, to_status: str) -> None:
    """状态跃迁守卫（非法跃迁一律拒绝）。"""
    allowed = TRANSITIONS.get(row.status, ())
    if to_status not in allowed:
        raise BizException(
            R.HR_EMPLOYMENT_INVALID_STATE,
            f"人事事务状态「{row.status}」不允许变更为「{to_status}」",
        )


def dept_name_of(db: Session, dept_id: int | None) -> str:
    if not dept_id:
        return ""
    d = db.get(Dept, dept_id)
    return d.name if d else ""


def position_name_of(db: Session, position_id: int | None) -> str:
    if not position_id:
        return ""
    p = db.get(HrPosition, position_id)
    return p.name if p else ""


def _role_ids(db: Session, raw: str) -> list[int]:
    """解析入职单上的角色 id 串（逗号分隔）。"""
    out_ids: list[int] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if part.isdigit():
            rid = int(part)
            if rid not in out_ids:
                out_ids.append(rid)
    return out_ids


def _default_role_ids(db: Session, position_type: str) -> list[int]:
    """按岗位类型给默认角色（HR 未指定时用）。"""
    code = DEFAULT_ROLE_BY_POSITION.get(position_type, "biz_user")
    role = db.scalar(select(Role).where(Role.code == code, Role.deleted == 0))
    return [role.id] if role else []


def _generate_password() -> str:
    """生成初始密码（HR 未填时兜底；只在生效响应里返回一次）。"""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    return "B" + "".join(secrets.choice(alphabet) for _ in range(9)) + "@"


# ---------------- 生效副作用 ----------------


def effect_employment(
    db: Session,
    row: HrEmployment,
    *,
    operator_id: int | None = None,
    operator_name: str = "",
) -> dict:
    """执行人事事务的副作用（**只有本函数能改 `sys_user`**）。

    前置条件：单据状态必须是 `approved`（审批通过但未生效）。
    返回副作用摘要（开号信息 / 撤销授权数 / 失效代理数 / 清空的岗位 A、B 角数）。
    """
    if row.status != STATUS_APPROVED:
        raise BizException(
            R.HR_EMPLOYMENT_INVALID_STATE,
            f"人事事务当前状态「{row.status}」不允许生效（须先审批通过）",
        )
    emp = db.get(HrEmployee, row.employee_id)
    if not emp or emp.deleted:
        raise BizException(R.HR_EMP_NOT_FOUND, "员工档案不存在")

    if row.event_type == "onboard":
        result = _effect_onboard(db, row, emp, operator_id=operator_id, operator_name=operator_name)
    elif row.event_type == "transfer":
        result = _effect_transfer(db, row, emp, operator_id=operator_id, operator_name=operator_name)
    elif row.event_type == "resign":
        result = _effect_resign(db, row, emp, operator_id=operator_id, operator_name=operator_name)
    elif row.event_type == "rehire":
        result = _effect_rehire(db, row, emp, operator_id=operator_id, operator_name=operator_name)
    else:
        raise BizException(R.HR_EMPLOYMENT_INVALID_STATE, f"未知的人事事务类型：{row.event_type}")

    from_status = row.status
    row.status = STATUS_EFFECTIVE
    row.update_by = operator_id
    row.update_time = _now()
    db.flush()
    write_event(
        db,
        row,
        event_type="effect",
        from_status=from_status,
        to_status=STATUS_EFFECTIVE,
        operator_id=operator_id,
        operator_name=operator_name,
        reason=row.reason or "人事事务生效",
    )
    record(
        db,
        user_id=operator_id,
        module="hr",
        action="hr_employment_effect",
        biz_type="hr_employment",
        biz_id=row.id,
        field_name="status",
        old_value=from_status,
        new_value=STATUS_EFFECTIVE,
        detail={"empNo": row.emp_no, "eventType": row.event_type, "employeeId": emp.id},
        strict=True,
    )
    return result


def _effect_onboard(
    db: Session,
    row: HrEmployment,
    emp: HrEmployee,
    *,
    operator_id: int | None,
    operator_name: str,
) -> dict:
    """入职生效：建账号 → 建任职 → 绑角色 → 回填档案 → 试用。"""
    if emp.employ_status == "resigned":
        raise BizException(R.HR_EMPLOYMENT_INVALID_STATE, "该员工已离职，请走「返聘」事务")
    if emp_svc.is_blacklisted(db, emp.id, row.effective_date or date.today()):
        raise BizException(R.HR_EMP_CONFLICT, "该员工在生效黑名单内，不允许入职")
    if emp.employ_type == "part_time" and emp.position_id:
        pos = db.get(HrPosition, emp.position_id)
        if pos and pos.key_role:
            raise BizException(R.HR_EMP_CONFLICT, f"兼职人员不得担任关键岗位「{pos.name}」")

    dept_id = row.new_dept_id or row.dept_id or emp.dept_id
    position_id = row.new_position_id or row.position_id or emp.position_id

    account: dict = {}
    if row.create_account and not emp.user_id:
        username = (row.account_username or emp.employee_no).strip()
        password = decrypt_account_password(row.account_password)
        generated = False
        if not password:
            password = _generate_password()
            generated = True
        role_ids = _role_ids(db, row.account_roles)
        if not role_ids:
            pos = db.get(HrPosition, position_id) if position_id else None
            role_ids = _default_role_ids(db, pos.position_type if pos else "staff")
        try:
            u = create_user_account(
                db,
                username=username,
                name=emp.name,
                password=password,
                dept_id=dept_id,
                dept_name=dept_name_of(db, dept_id),
                mobile=emp.mobile,
                email=emp.email,
                role_ids=role_ids,
                employee_no=emp.employee_no,
                hire_date=row.effective_date or date.today(),
                operator_id=operator_id,
            )
        except BizException as exc:
            raise BizException(R.HR_EMP_CONFLICT, f"入职开号失败：{exc.message or exc}") from exc
        emp_svc.link_user(db, emp, u.id)
        row.user_id = u.id
        row.user_name = emp.name
        account = {"username": username, "userId": u.id}
        if generated:
            account["initialPassword"] = password
        record(
            db,
            user_id=operator_id,
            module="hr",
            action="hr_account_create",
            biz_type="sys_user",
            biz_id=u.id,
            field_name="username",
            old_value="",
            new_value=username,
            detail={"employeeNo": emp.employee_no, "name": emp.name, "empNo": row.emp_no},
            strict=True,
        )
    elif emp.user_id:
        u = db.get(User, emp.user_id)
        if u:
            u.dept_id = dept_id
            u.dept_name = dept_name_of(db, dept_id)
            u.status = "enabled"
            db.flush()

    emp.dept_id = dept_id
    emp.position_id = position_id
    emp.hire_date = row.effective_date or emp.hire_date or date.today()
    emp.leave_date = None
    emp.employ_status = "probation"
    db.flush()
    emp_svc.sync_user_redundant(db, emp)

    if emp.user_id:
        _sync_primary_membership(db, emp.user_id, dept_id)

    return {"account": account, "notes": ["入职生效：账号与任职已建立", "在职状态置为试用"]}


def _sync_primary_membership(db: Session, user_id: int, dept_id: int | None) -> None:
    """把主部门任职同步到新部门（调岗 / 入职共用）。"""
    if not dept_id:
        return
    rows = list(
        db.scalars(select(UserDept).where(UserDept.user_id == user_id, UserDept.deleted == 0)).all()
    )
    target = next((r for r in rows if r.dept_id == dept_id), None)
    for r in rows:
        r.is_primary = 1 if (target and r.id == target.id) else 0
    if target is None:
        db.add(UserDept(user_id=user_id, dept_id=dept_id, is_primary=1))
    db.flush()


def _effect_transfer(
    db: Session,
    row: HrEmployment,
    emp: HrEmployee,
    *,
    operator_id: int | None,
    operator_name: str,
) -> dict:
    """调岗生效：改档案归属 + 改账号部门 + 同步主部门任职。"""
    dept_id = row.new_dept_id or emp.dept_id
    position_id = row.new_position_id or emp.position_id
    if not dept_id:
        raise BizException(R.HR_EMPLOYMENT_INVALID_STATE, "调岗事务未指定目标部门")

    emp.dept_id = dept_id
    emp.position_id = position_id
    db.flush()
    emp_svc.sync_user_redundant(db, emp)

    if emp.user_id:
        u = db.get(User, emp.user_id)
        if u:
            u.dept_id = dept_id
            u.dept_name = dept_name_of(db, dept_id)
            db.flush()
            _sync_primary_membership(db, u.id, dept_id)

    record(
        db,
        user_id=operator_id,
        module="hr",
        action="hr_employee_transfer",
        biz_type="hr_employee",
        biz_id=emp.id,
        field_name="dept_id",
        old_value=str(row.dept_id or ""),
        new_value=str(dept_id),
        detail={"empNo": row.emp_no, "newDeptName": dept_name_of(db, dept_id)},
        strict=True,
    )
    return {
        "account": {},
        "notes": [
            f"调岗生效：部门 → {dept_name_of(db, dept_id) or dept_id}",
            f"岗位 → {position_name_of(db, position_id) or '未指定'}",
        ],
    }


def _effect_resign(
    db: Session,
    row: HrEmployment,
    emp: HrEmployee,
    *,
    operator_id: int | None,
    operator_name: str,
) -> dict:
    """离职生效：禁用账号 → 关 MFA → 撤授权 → 代理失效 → 清岗位 A/B 角。

    账号**不删除**（ALCOA 完整：离职记录与历史单据必须可追溯）。
    """
    if emp.employ_status == "resigned":
        raise BizException(R.HR_EMPLOYMENT_INVALID_STATE, "该员工已是离职状态")

    revoked = 0
    expired_delegates = 0
    cleared_positions = 0

    if emp.user_id:
        uid = emp.user_id
        u = db.get(User, uid)
        if u:
            u.status = "disabled"
            u.mfa_enabled = 0
            db.flush()
            record(
                db,
                user_id=operator_id,
                module="hr",
                action="hr_account_disable",
                biz_type="sys_user",
                biz_id=uid,
                field_name="status",
                old_value="enabled",
                new_value="disabled",
                detail={"employeeNo": emp.employee_no, "name": emp.name, "empNo": row.emp_no},
                strict=True,
            )

        # —— 撤销 B9 授权台账（写授权事件，保留可追溯）——
        auths = db.scalars(
            select(auth_svc.HrAuthorization).where(
                auth_svc.HrAuthorization.user_id == uid,
                auth_svc.HrAuthorization.deleted == 0,
                auth_svc.HrAuthorization.status.in_(
                    (auth_svc.STATUS_ACTIVE, auth_svc.STATUS_SUSPENDED, auth_svc.STATUS_CONFIRMED)
                ),
            )
        ).all()
        for a in auths:
            auth_svc.transition(
                db,
                a,
                auth_svc.STATUS_REVOKED,
                event_type="revoke",
                operator_id=operator_id,
                operator_name=operator_name,
                reason=f"员工离职生效（单号 {row.emp_no}），自动撤销授权",
            )
            revoked += 1

        # —— 代理失效：本人作为委托人的记录过期；委托人是离职者的代理人也过期 ——
        resigned_user_ids = set(
            db.scalars(
                select(HrEmployee.user_id).where(
                    HrEmployee.user_id.is_not(None), HrEmployee.employ_status == "resigned"
                )
            ).all()
        )
        for d in db.scalars(
            select(HrDelegate).where(HrDelegate.deleted == 0, HrDelegate.status == "enabled")
        ).all():
            hit = False
            if d.principal_id == uid:
                hit = True
            elif d.agent_id == uid and d.principal_id in resigned_user_ids:
                hit = True
            if hit:
                d.status = "expired"
                d.update_by = operator_id
                d.update_time = _now()
                expired_delegates += 1
        db.flush()

        # —— 清岗位 A/B 角（指向离职者的清空）——
        for p in db.scalars(
            select(HrPosition).where(
                HrPosition.deleted == 0,
                (HrPosition.primary_user_id == uid) | (HrPosition.backup_user_id == uid),
            )
        ).all():
            if p.primary_user_id == uid:
                p.primary_user_id = None
            if p.backup_user_id == uid:
                p.backup_user_id = None
            p.update_by = operator_id
            p.update_time = _now()
            cleared_positions += 1
        db.flush()

    emp.employ_status = "resigned"
    emp.leave_date = row.effective_date or date.today()
    db.flush()
    emp_svc.sync_user_redundant(db, emp)

    # 物理权限（门禁 / 钥匙 / 工牌）无系统对接 —— 诚实标注外部依赖，不假装已回收
    record(
        db,
        user_id=operator_id,
        module="hr",
        action="hr_physical_access_revoke",
        biz_type="hr_employee",
        biz_id=emp.id,
        field_name="physical_access",
        old_value="unknown",
        new_value="pending_manual",
        reason="离职当日回收全部系统与物理权限：系统侧已回收，物理侧（门禁/钥匙/工牌）待现场确认",
        detail={"employeeNo": emp.employee_no, "name": emp.name, "empNo": row.emp_no},
        strict=True,
    )

    return {
        "account": {},
        "notes": [
            "账号已禁用（MFA 已关闭），账号不删除以保留历史可追溯",
            f"已撤销授权 {revoked} 条",
            f"已失效代理 {expired_delegates} 条",
            f"已清空岗位 A/B 角 {cleared_positions} 处",
            "物理权限（门禁/钥匙/工牌）无系统对接，待现场确认",
        ],
        "revokedAuth": revoked,
        "expiredDelegates": expired_delegates,
        "clearedPositions": cleared_positions,
    }


def _effect_rehire(
    db: Session,
    row: HrEmployment,
    emp: HrEmployee,
    *,
    operator_id: int | None,
    operator_name: str,
) -> dict:
    """返聘生效：恢复原账号（一人一号的历史连续）+ 正式在职。

    **不恢复授权** —— 能力须重新走 B9 授权确认流程（合规红线）。
    """
    if emp.employ_status not in ("resigned", "retired"):
        raise BizException(R.HR_EMPLOYMENT_INVALID_STATE, "该员工不在离职/退休状态，无需返聘")
    if emp_svc.is_blacklisted(db, emp.id, row.effective_date or date.today()):
        raise BizException(R.HR_EMP_CONFLICT, "该员工在生效黑名单内，不允许返聘")

    dept_id = row.new_dept_id or emp.dept_id
    position_id = row.new_position_id or emp.position_id
    emp.dept_id = dept_id
    emp.position_id = position_id
    emp.hire_date = row.effective_date or date.today()
    emp.leave_date = None
    emp.employ_status = "regular"
    db.flush()
    emp_svc.sync_user_redundant(db, emp)

    account: dict = {}
    if emp.user_id:
        u = db.get(User, emp.user_id)
        if u:
            u.status = "enabled"
            u.dept_id = dept_id
            u.dept_name = dept_name_of(db, dept_id)
            db.flush()
            _sync_primary_membership(db, u.id, dept_id)
            account = {"username": u.username, "userId": u.id}
            record(
                db,
                user_id=operator_id,
                module="hr",
                action="hr_account_reenable",
                biz_type="sys_user",
                biz_id=u.id,
                field_name="status",
                old_value="disabled",
                new_value="enabled",
                detail={"employeeNo": emp.employee_no, "name": emp.name, "empNo": row.emp_no},
                strict=True,
            )

    return {
        "account": account,
        "notes": [
            "已恢复原账号（保持一人一号的历史连续）",
            "在职状态置为正式",
            "**授权不自动恢复** —— 能力须重新走授权确认流程",
        ],
    }

