"""员工主数据纯逻辑层（B10-1 / HR L1 员工一人一档）。

职责：
- **证件号加密与脱敏**：`id_no` 以 AES-GCM 密文（`enc:` 前缀）落库，域分隔密钥
  `hr-employee-idno`（与配置密钥、电子签名密钥互不复用）；出参一律掩码，
  明文只有 `GET /hr/employees/{id}/id-no` 一条出口且访问留痕。
- **建档冲突校验**：工号唯一、证件号唯一、兼职冲突（一人只能有一条生效兼职档案；
  兼职人员不得担任关键岗位）。
- **与 `sys_user` 的联动**：1:1 关联、冗余字段同步（`employee_no` / `hire_date`）。
- **名单管控**：黑名单 / 白名单。

**不依赖 router**：路由层负责鉴权与事务，本模块只做纯逻辑。
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.crypto import decrypt_text_domain, encrypt_text_domain
from app.core.exceptions import BizException
from app.modules.admin.models import Dept, UserDept
from app.modules.auth.models import User
from app.modules.hr.constants import CONTROL_TYPE_CN, EMPLOY_STATUS_CN, EMPLOY_TYPE_CN
from app.modules.hr.models import HrEmployee, HrEmployeeControl, HrPosition

# 证件号加密的域分隔标识（禁止与其他用途共用密钥）
IDNO_DOMAIN = "hr-employee-idno"

# 在职状态里"不算在职"的（用于兼职冲突等判定）
_CLOSED_STATUSES = ("resigned", "retired")


def encrypt_id_no(plain: str) -> str:
    """证件号明文 → 密文（`enc:` 前缀）。空值原样返回。"""
    v = (plain or "").strip()
    if not v:
        return ""
    return encrypt_text_domain(IDNO_DOMAIN, v)


def decrypt_id_no(value: str) -> str:
    """密文 → 明文（兼容历史明文）。"""
    if not value:
        return ""
    return decrypt_text_domain(IDNO_DOMAIN, value)


def mask_id_no(plain: str) -> str:
    """证件号掩码：保留前 4 后 4，中间等长星号。

    短号码退化为保留前 2 位；空值返回空串。
    """
    v = (plain or "").strip()
    if not v:
        return ""
    if len(v) <= 4:
        return "*" * len(v)
    if len(v) <= 8:
        return v[:2] + "*" * (len(v) - 2)
    return v[:4] + "*" * (len(v) - 8) + v[-4:]


def _dept_name(db: Session, dept_id: int | None) -> str:
    if not dept_id:
        return ""
    d = db.get(Dept, dept_id)
    return d.name if d else ""


def _position_name(db: Session, position_id: int | None) -> str:
    if not position_id:
        return ""
    p = db.get(HrPosition, position_id)
    return p.name if p else ""


def employee_out(db: Session, e: HrEmployee) -> dict:
    """员工档案出参（camelCase，证件号**始终掩码**）。"""
    u = db.get(User, e.user_id) if e.user_id else None
    return {
        "id": e.id,
        "employeeNo": e.employee_no,
        "userId": e.user_id,
        "userName": (u.name or u.username) if u else "",
        "name": e.name,
        "idNo": mask_id_no(decrypt_id_no(e.id_no)),
        "idType": e.id_type,
        "gender": e.gender,
        "birthDate": e.birth_date.isoformat() if e.birth_date else "",
        "education": e.education,
        "major": e.major,
        "mobile": e.mobile,
        "email": e.email,
        "employType": e.employ_type,
        "employTypeText": EMPLOY_TYPE_CN.get(e.employ_type, e.employ_type),
        "employStatus": e.employ_status,
        "employStatusText": EMPLOY_STATUS_CN.get(e.employ_status, e.employ_status),
        "deptId": e.dept_id,
        "deptName": _dept_name(db, e.dept_id),
        "positionId": e.position_id,
        "positionName": _position_name(db, e.position_id),
        "hireDate": e.hire_date.isoformat() if e.hire_date else "",
        "leaveDate": e.leave_date.isoformat() if e.leave_date else "",
        "contractNo": e.contract_no,
        "contractStart": e.contract_start.isoformat() if e.contract_start else "",
        "contractEnd": e.contract_end.isoformat() if e.contract_end else "",
        "emergencyContact": e.emergency_contact,
        "emergencyMobile": e.emergency_mobile,
        "status": e.status,
        "remark": e.remark,
        "createTime": e.create_time.isoformat() if e.create_time else "",
    }


def control_out(c: HrEmployeeControl) -> dict:
    """名单管控出参。"""
    return {
        "id": c.id,
        "employeeId": c.employee_id,
        "userId": c.user_id,
        "controlType": c.control_type,
        "controlTypeText": CONTROL_TYPE_CN.get(c.control_type, c.control_type),
        "reason": c.reason,
        "effectiveFrom": c.effective_from.isoformat() if c.effective_from else "",
        "effectiveTo": c.effective_to.isoformat() if c.effective_to else "",
        "status": c.status,
        "remark": c.remark,
        "createTime": c.create_time.isoformat() if c.create_time else "",
    }


def active_controls(db: Session, employee_id: int) -> list[HrEmployeeControl]:
    """员工当前生效中的名单管控记录。"""
    return list(
        db.scalars(
            select(HrEmployeeControl).where(
                HrEmployeeControl.employee_id == employee_id,
                HrEmployeeControl.deleted == 0,
                HrEmployeeControl.status == "enabled",
            )
        ).all()
    )


def is_blacklisted(db: Session, employee_id: int, on_date: date | None = None) -> bool:
    """该员工是否在生效黑名单内（入职 / 返聘前必查）。"""
    for c in active_controls(db, employee_id):
        if c.control_type != "blacklist":
            continue
        if c.effective_from and on_date and on_date < c.effective_from:
            continue
        if c.effective_to and on_date and on_date > c.effective_to:
            continue
        return True
    return False


def write_control(
    db: Session,
    emp: HrEmployee,
    *,
    control_type: str,
    reason: str = "",
    effective_from: date | None = None,
    effective_to: date | None = None,
    status: str = "enabled",
    remark: str = "",
    operator_id: int | None = None,
) -> HrEmployeeControl:
    """写入名单管控。

    `hr_employee_control` 对 `(employee_id, control_type, deleted)` 有唯一约束，
    因此同一员工同一名单类型**只有一条记录**：重复写入走更新（改原因 / 有效期 / 状态）。
    """
    row = db.scalar(
        select(HrEmployeeControl).where(
            HrEmployeeControl.employee_id == emp.id,
            HrEmployeeControl.control_type == control_type,
            HrEmployeeControl.deleted == 0,
        )
    )
    if row is None:
        row = HrEmployeeControl(
            employee_id=emp.id,
            user_id=emp.user_id,
            control_type=control_type,
            create_by=operator_id,
        )
        db.add(row)
    row.user_id = emp.user_id
    row.reason = reason
    row.effective_from = effective_from
    row.effective_to = effective_to
    row.status = status
    row.remark = remark
    row.update_by = operator_id
    db.flush()
    return row


def check_employee_conflicts(
    db: Session,
    *,
    employee_no: str,
    id_no: str = "",
    employ_type: str = "labor",
    position_id: int | None = None,
    user_id: int | None = None,
    exclude_id: int | None = None,
) -> None:
    """建档 / 改档的冲突校验（不通过直接抛 `BizException`）。

    规则：
    1. **工号唯一** —— 同一工号只能有一份档案（63013）；
    2. **证件号唯一** —— 同一证件号只能有一份档案（63013）。
       证件号是随机 nonce 密文，无法直接 SQL 比对，只能解密后逐条比对；
       HR 档案量级（千级）下开销可忽略。
    3. **兼职冲突**（63016）—— 同一人员只能有一条生效中的兼职档案；
       兼职人员不得担任关键岗位（技术负责人 / 质量负责人 / 授权签字人等）。
    """
    q = select(HrEmployee.id).where(HrEmployee.employee_no == employee_no, HrEmployee.deleted == 0)
    if exclude_id:
        q = q.where(HrEmployee.id != exclude_id)
    if db.scalar(q):
        raise BizException(R.HR_EMP_DUPLICATE, f"工号已存在：{employee_no}")

    plain_id = (id_no or "").strip()
    if plain_id:
        rows = db.scalars(
            select(HrEmployee).where(HrEmployee.id_no != "", HrEmployee.deleted == 0)
        ).all()
        for other in rows:
            if exclude_id and other.id == exclude_id:
                continue
            if decrypt_id_no(other.id_no) == plain_id:
                raise BizException(R.HR_EMP_DUPLICATE, "证件号已被其他员工档案使用")

    if employ_type == "part_time":
        if user_id:
            q2 = select(HrEmployee.id).where(
                HrEmployee.user_id == user_id,
                HrEmployee.employ_type == "part_time",
                HrEmployee.deleted == 0,
            )
            if exclude_id:
                q2 = q2.where(HrEmployee.id != exclude_id)
            for row in db.scalars(q2).all():
                if row.employ_status not in _CLOSED_STATUSES:
                    raise BizException(R.HR_EMP_CONFLICT, "该人员已存在生效中的兼职档案")
        if position_id:
            pos = db.get(HrPosition, position_id)
            if pos and pos.key_role:
                raise BizException(R.HR_EMP_CONFLICT, f"兼职人员不得担任关键岗位「{pos.name}」")


def sync_user_redundant(db: Session, emp: HrEmployee) -> None:
    """把 HR 主数据同步到 `sys_user` 的冗余列。

    `sys_user.employee_no` / `hire_date` 自 B10-1 起**以 `hr_employee` 为准**；
    人工在 admin 域改这两个字段会造成漂移，以 HR 档案为准。
    `job_level`（职级）仍由 admin 域维护 —— HR L1 不引入职级字典（B10-2）。
    """
    if not emp.user_id:
        return
    u = db.get(User, emp.user_id)
    if not u:
        return
    u.employee_no = emp.employee_no
    u.hire_date = emp.hire_date
    db.flush()


def link_user(db: Session, emp: HrEmployee, user_id: int | None) -> None:
    """绑定 / 解绑系统账号（1:1）。

    绑定时同步冗余列；**换绑或解绑**时把旧账号上的工号与入职日期清掉
    （档案仍在 HR 侧，冗余列以 HR 为准）。
    """
    old_user_id = emp.user_id
    emp.user_id = user_id
    db.flush()
    if old_user_id and old_user_id != user_id:
        old = db.get(User, old_user_id)
        if old and old.employee_no == emp.employee_no:
            old.employee_no = ""
            old.hire_date = None
    if user_id:
        sync_user_redundant(db, emp)
    db.flush()


def employee_memberships(db: Session, emp: HrEmployee) -> list[dict]:
    """员工的部门任职（`sys_user_dept`）—— 详情页聚合用。"""
    if not emp.user_id:
        return []
    rows = db.scalars(
        select(UserDept).where(UserDept.user_id == emp.user_id, UserDept.deleted == 0)
    ).all()
    out = []
    for r in rows:
        d = db.get(Dept, r.dept_id) if r.dept_id else None
        out.append(
            {
                "deptId": r.dept_id,
                "deptName": d.name if d else "",
                "isPrimary": r.is_primary,
                "isLeader": r.is_leader,
            }
        )
    return out
