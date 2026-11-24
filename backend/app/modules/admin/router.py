"""系统管理路由 /api/v1/admin。"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit import evidence_detail, list_anchors, verify_chain, write_anchor
from app.common.audit import record as audit
from app.common.filters import apply_list_filters
from app.common.pagination import PAGE_MAX, PageParams
from app.core import ipgeo
from app.core import response as R
from app.core.config import settings
from app.core.db import get_db
from app.core.deps import SUPER_ROLE, get_current_user, require_any_perm, require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.core.security import hash_password
from app.modules.admin import changelog as changelog_svc
from app.modules.admin import org
from app.modules.admin import schemas as S
from app.modules.admin import service as svc
from app.modules.admin.models import (
    AuditLog,
    Dept,
    DictItem,
    DictType,
    LoginLog,
    Menu,
    Notify,
    NumberRule,
    Role,
    UserDept,
)
from app.modules.auth.models import User

# 组织架构扩展（B10-1）：admin 域仍是**部门树的唯一写入口**，组织变更轨迹
# 由 HR 域的纯逻辑层落库（只追加快照）。走 service 而非 router 互引。
from app.modules.hr import org as hr_org
from app.services.excel import export_xlsx_styled, now_filename
from app.services.numbering import preview_no, reset_seq

router = APIRouter(prefix="/admin", tags=["admin"], route_class=EnvelopeRoute)


def _t(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return v or ""


def _user_out(db: Session, u: User, with_roles: bool = True) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "name": u.name,
        "deptId": u.dept_id,
        "deptName": u.dept_name,
        "mobile": u.mobile,
        "email": u.email,
        "status": u.status,
        "employeeNo": u.employee_no,
        "hireDate": u.hire_date.isoformat() if u.hire_date else "",
        "jobLevel": u.job_level,
        "roles": u.role_codes if with_roles else [],
        "createTime": _t(u.create_time),
        "lastLoginAt": _t(u.last_login_at),
    }


# ---------------- 用户 ----------------
@router.get("/users/options")
def user_options(
    q: str = Query("", max_length=64),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """启用用户下拉（登录即可读：流程/通知选人用）。"""
    stmt = select(User).where(User.deleted == 0, User.status == "enabled")
    if q.strip():
        like = f"%{q.strip()}%"
        from sqlalchemy import or_

        stmt = stmt.where(or_(User.username.like(like), User.name.like(like)))
    rows = db.scalars(stmt.order_by(User.id).limit(limit)).all()
    return [{"id": u.id, "label": u.name or u.username, "sub": u.username} for u in rows]


@router.get("/users")
def list_users(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("admin:user:list")),
    db: Session = Depends(get_db),
):
    pp = PageParams(page=page, size=size)
    stmt = select(User)
    stmt, total = apply_list_filters(
        stmt,
        User,
        request.query_params,
        db,
        pp,
        search_cols=["username", "name", "mobile"],
        filter_cols={"status", "dept_id"},
        sort_cols={"update_time", "create_time", "id", "last_login_at", "username", "name", "status"},
    )
    rows = db.scalars(stmt).all()
    return {"items": [_user_out(db, u) for u in rows], "total": total, "page": page, "size": size}


@router.get("/users/counts")
def user_counts(
    user: User = Depends(require_perm("admin:user:list")),
    db: Session = Depends(get_db),
):
    """状态页签计数（全部/enabled/disabled）。"""
    rows = db.execute(select(User.status, func.count()).where(User.deleted == 0).group_by(User.status)).all()
    data = {"enabled": 0, "disabled": 0}
    data.update({s: n for s, n in rows if s in data})
    data["all"] = sum(data.values())
    return data


@router.post("/users", status_code=201)
def create_user(
    body: S.UserIn,
    current: User = Depends(require_perm("admin:user:create")),
    db: Session = Depends(get_db),
):
    if db.scalar(select(User).where(User.username == body.username, User.deleted == 0)):
        raise BizException(R.ADMIN_USERNAME_EXISTS)
    if not body.password:
        raise BizException(R.GENERIC_PARAM, "初始密码必填")
    u = svc.create_user_account(
        db,
        username=body.username,
        name=body.name,
        password=body.password,
        dept_id=body.dept_id,
        dept_name=body.dept_name,
        mobile=body.mobile,
        email=body.email,
        role_ids=body.role_ids,
        employee_no=body.employee_no,
        hire_date=body.hire_date,
        status=body.status,
        operator_id=current.id,
    )
    u.job_level = body.job_level
    audit(db, user_id=current.id, module="admin", action="user_create", biz_type="user", biz_id=u.id)
    db.commit()
    return _user_out(db, u)


@router.put("/users/{uid}")
def update_user(
    uid: int,
    body: S.UserIn,
    current: User = Depends(require_perm("admin:user:edit")),
    db: Session = Depends(get_db),
):
    u = db.get(User, uid)
    if not u or u.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if body.username != u.username and db.scalar(select(User).where(User.username == body.username, User.deleted == 0)):
        raise BizException(R.ADMIN_USERNAME_EXISTS)
    u.username = body.username
    u.name = body.name
    u.dept_id = body.dept_id
    u.dept_name = body.dept_name
    u.mobile = body.mobile
    u.email = body.email
    u.status = body.status
    u.employee_no = body.employee_no
    u.hire_date = body.hire_date
    u.job_level = body.job_level
    u.update_by = current.id
    if body.password:
        u.password_hash = hash_password(body.password)
    org.sync_primary_membership(db, u)
    svc.set_user_roles(db, u.id, body.role_ids)
    audit(db, user_id=current.id, module="admin", action="user_update", biz_type="user", biz_id=u.id)
    db.commit()
    return _user_out(db, u)


@router.delete("/users/{uid}")
def delete_user(
    uid: int,
    current: User = Depends(require_perm("admin:user:delete")),
    db: Session = Depends(get_db),
):
    if uid == current.id:
        raise BizException(R.GENERIC_PARAM, "不能删除自己")
    u = db.get(User, uid)
    if not u or u.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    u.deleted = 1
    # username 有物理唯一索引，逻辑删后释放登录名，避免同名重建触发 500
    u.username = f"{u.username[:50]}#del{u.id}"
    audit(db, user_id=current.id, module="admin", action="user_delete", biz_type="user", biz_id=uid)
    db.commit()
    return None


@router.post("/users/{uid}/reset-password")
def reset_password(
    uid: int,
    body: S.ResetPasswordIn,
    current: User = Depends(require_perm("admin:user:edit")),
    db: Session = Depends(get_db),
):
    u = db.get(User, uid)
    if not u or u.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    u.password_hash = hash_password(body.password)
    audit(db, user_id=current.id, module="admin", action="user_reset_pwd", biz_type="user", biz_id=uid)
    db.commit()
    return None


USER_EXPORT_COLS = [
    {"key": "username", "label": "用户名", "width": 18},
    {"key": "name", "label": "姓名", "width": 14},
    {"key": "deptName", "label": "部门", "width": 20},
    {"key": "mobile", "label": "手机", "width": 16},
    {"key": "email", "label": "邮箱", "width": 24},
    {"key": "status", "label": "状态", "width": 10},
    {"key": "roles", "label": "角色", "width": 24, "formatter": lambda v, r: ",".join(v)},
    {"key": "createTime", "label": "创建时间", "width": 20},
]


@router.post("/users/export")
def export_users(
    request: Request,
    current: User = Depends(require_perm("admin:user:list:export")),
    db: Session = Depends(get_db),
):
    from types import SimpleNamespace

    stmt = select(User)
    stmt, _ = apply_list_filters(
        stmt,
        User,
        request.query_params,
        db,
        SimpleNamespace(page=1, size=100_000),
        search_cols=["username", "name", "mobile"],
        filter_cols={"status"},
    )
    rows = [_user_out(db, u) for u in db.scalars(stmt).all()]
    payload = export_xlsx_styled(rows, USER_EXPORT_COLS, "users")
    audit(
        db,
        user_id=current.id,
        module="admin",
        action="user_export",
        detail={"count": len(rows)},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('users')}"},
    )


# ---------------- 角色 ----------------
def _role_out(db: Session, r: Role) -> dict:
    return {
        "id": r.id,
        "code": r.code,
        "name": r.name,
        "dataScope": r.data_scope,
        "status": r.status,
        "remark": r.remark,
        "menuIds": svc.role_menu_ids(db, r.id),
        "createTime": _t(r.create_time),
    }


@router.get("/roles")
def list_roles(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(50, ge=1, le=200),
    current: User = Depends(require_perm("admin:role:list")),
    db: Session = Depends(get_db),
):
    pp = PageParams(page=page, size=size)
    stmt, total = apply_list_filters(
        select(Role),
        Role,
        request.query_params,
        db,
        pp,
        search_cols=["code", "name"],
        filter_cols={"status"},
        sort_cols={"id", "create_time", "update_time", "code", "name", "status"},
    )
    rows = db.scalars(stmt).all()
    return {"items": [_role_out(db, r) for r in rows], "total": total, "page": page, "size": size}


@router.post("/roles", status_code=201)
def create_role(
    body: S.RoleIn,
    current: User = Depends(require_perm("admin:role:create")),
    db: Session = Depends(get_db),
):
    if db.scalar(select(Role).where(Role.code == body.code, Role.deleted == 0)):
        raise BizException(R.GENERIC_PARAM, "角色编码已存在")
    r = Role(**body.model_dump(), create_by=current.id)
    db.add(r)
    audit(db, user_id=current.id, module="admin", action="role_create", biz_type="role")
    db.commit()
    return _role_out(db, r)


@router.put("/roles/{rid}")
def update_role(
    rid: int,
    body: S.RoleIn,
    current: User = Depends(require_perm("admin:role:edit")),
    db: Session = Depends(get_db),
):
    r = db.get(Role, rid)
    if not r or r.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    audit(db, user_id=current.id, module="admin", action="role_update", biz_type="role", biz_id=rid)
    db.commit()
    return _role_out(db, r)


@router.delete("/roles/{rid}")
def delete_role(
    rid: int,
    current: User = Depends(require_perm("admin:role:delete")),
    db: Session = Depends(get_db),
):
    r = db.get(Role, rid)
    if not r or r.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if r.code == SUPER_ROLE:
        raise BizException(R.GENERIC_PARAM, "内置超管角色不可删")
    r.deleted = 1
    # code 有物理唯一索引，逻辑删后释放编码，避免同名重建触发 500
    r.code = f"{r.code[:50]}#del{r.id}"
    db.commit()
    return None


@router.put("/roles/{rid}/menus")
def set_role_menus(
    rid: int,
    body: S.RoleMenusIn,
    current: User = Depends(require_perm("admin:role:edit")),
    db: Session = Depends(get_db),
):
    r = db.get(Role, rid)
    if not r or r.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.set_role_menus(db, rid, body.menu_ids)
    audit(db, user_id=current.id, module="admin", action="role_menus", biz_type="role", biz_id=rid)
    db.commit()
    return None


# ---------------- 菜单 ----------------
@router.get("/menus/tree")
def menus_tree(
    include_buttons: bool = False,
    # 全量菜单树：菜单管理（admin:menu:list）与角色授权弹窗（admin:role:edit）共用；
    # 前端导航用 /auth/me 的 menu_tree_for_user，不走这里
    current: User = Depends(require_any_perm("admin:menu:list", "admin:role:edit")),
    db: Session = Depends(get_db),
):
    return svc.menu_tree_all(db, include_buttons=include_buttons)


@router.post("/menus", status_code=201)
def create_menu(
    body: S.MenuIn,
    current: User = Depends(require_perm("admin:menu:create")),
    db: Session = Depends(get_db),
):
    m = Menu(**body.model_dump(), create_by=current.id)
    db.add(m)
    db.commit()
    return svc.menu_tree_all(db, include_buttons=True)


@router.put("/menus/{mid}")
def update_menu(
    mid: int,
    body: S.MenuIn,
    current: User = Depends(require_perm("admin:menu:edit")),
    db: Session = Depends(get_db),
):
    m = db.get(Menu, mid)
    if not m or m.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    for k, v in body.model_dump().items():
        setattr(m, k, v)
    db.commit()
    return svc.menu_tree_all(db, include_buttons=True)


@router.delete("/menus/{mid}")
def delete_menu(
    mid: int,
    current: User = Depends(require_perm("admin:menu:delete")),
    db: Session = Depends(get_db),
):
    m = db.get(Menu, mid)
    if not m or m.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if db.scalar(select(Menu).where(Menu.parent_id == mid, Menu.deleted == 0)):
        raise BizException(R.GENERIC_PARAM, "存在子菜单，不能删除")
    m.deleted = 1
    db.commit()
    return None


# ---------------- 字典 ----------------
def _dtype_out(t: DictType) -> dict:
    return {
        "id": t.id,
        "code": t.code,
        "name": t.name,
        "remark": t.remark,
        "items": [
            {
                "id": i.id,
                "dictTypeCode": i.dict_type_code,
                "label": i.label,
                "labelEn": i.label_en,
                "value": i.value,
                "sort": i.sort,
                "status": i.status,
                "extra": i.extra,
            }
            for i in sorted(t.items, key=lambda x: x.sort)
        ],
    }


@router.get("/dict/types")
def dict_types(
    request: Request,
    current: User = Depends(require_perm("admin:dict:list")),
    db: Session = Depends(get_db),
):
    rows = db.scalars(select(DictType).where(DictType.deleted == 0).order_by(DictType.code)).all()
    return [_dtype_out(t) for t in rows]


@router.get("/dict/items")
def dict_items(
    code: str = Query(..., alias="type"),
    enabled_only: bool = True,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """业务下拉数据源：GET /admin/dict/items?type=task_type"""
    stmt = select(DictItem).where(DictItem.dict_type_code == code, DictItem.deleted == 0)
    if enabled_only:
        stmt = stmt.where(DictItem.status == "enabled")
    rows = db.scalars(stmt.order_by(DictItem.sort, DictItem.id)).all()
    return [{"label": i.label, "labelEn": i.label_en, "value": i.value, "extra": i.extra} for i in rows]


DICT_EXPORT_COLS = [
    {"key": "typeCode", "label": "类型编码", "width": 20},
    {"key": "typeName", "label": "类型名称", "width": 18},
    {"key": "label", "label": "标签", "width": 16},
    {"key": "labelEn", "label": "英文标签", "width": 18},
    {"key": "value", "label": "字典值", "width": 16},
    {"key": "sort", "label": "排序", "width": 8},
    {"key": "status", "label": "状态", "width": 8},
]


@router.get("/dict/types/export")
def export_dict_types(
    current: User = Depends(require_perm("admin:dict:list")),
    db: Session = Depends(get_db),
):
    """字典导出（平铺类型+字典项，沿用 admin:dict:list 查看权限）。"""
    types = db.scalars(select(DictType).where(DictType.deleted == 0).order_by(DictType.code)).all()
    status_cn = {"enabled": "启用", "disabled": "停用"}
    rows = []
    for t in types:
        for i in sorted((x for x in t.items if x.deleted == 0), key=lambda x: x.sort):
            rows.append(
                {
                    "typeCode": t.code,
                    "typeName": t.name,
                    "label": i.label,
                    "labelEn": i.label_en,
                    "value": i.value,
                    "sort": i.sort,
                    "status": status_cn.get(i.status, i.status),
                }
            )
    payload = export_xlsx_styled(rows, DICT_EXPORT_COLS, "dicts")
    audit(db, user_id=current.id, module="admin", action="dict_export", detail={"count": len(rows)})
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('dicts')}"},
    )


@router.post("/dict/types", status_code=201)
def create_dict_type(
    body: S.DictTypeIn,
    current: User = Depends(require_perm("admin:dict:edit")),
    db: Session = Depends(get_db),
):
    if db.scalar(select(DictType).where(DictType.code == body.code, DictType.deleted == 0)):
        raise BizException(R.GENERIC_PARAM, "字典类型已存在")
    db.add(DictType(**body.model_dump(), create_by=current.id))
    db.commit()
    return None


@router.post("/dict/items", status_code=201)
def create_dict_item(
    body: S.DictItemIn,
    current: User = Depends(require_perm("admin:dict:edit")),
    db: Session = Depends(get_db),
):
    if db.scalar(
        select(DictItem.id).where(
            DictItem.dict_type_code == body.dict_type_code,
            DictItem.value == body.value,
            DictItem.deleted == 0,
        )
    ):
        raise BizException(R.GENERIC_PARAM, "该字典类型下字典值已存在")
    db.add(DictItem(**body.model_dump(), create_by=current.id))
    db.commit()
    return None


@router.put("/dict/items/{did}")
def update_dict_item(
    did: int,
    body: S.DictItemIn,
    current: User = Depends(require_perm("admin:dict:edit")),
    db: Session = Depends(get_db),
):
    item = db.get(DictItem, did)
    if not item or item.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    dup = db.scalar(
        select(DictItem.id).where(
            DictItem.dict_type_code == body.dict_type_code,
            DictItem.value == body.value,
            DictItem.deleted == 0,
            DictItem.id != did,
        )
    )
    if dup:
        raise BizException(R.GENERIC_PARAM, "该字典类型下字典值已存在")
    for k, v in body.model_dump().items():
        setattr(item, k, v)
    db.commit()
    return None


@router.delete("/dict/items/{did}")
def delete_dict_item(
    did: int,
    current: User = Depends(require_perm("admin:dict:edit")),
    db: Session = Depends(get_db),
):
    item = db.get(DictItem, did)
    if item:
        item.deleted = 1
        # (dict_type_code, value) 有物理唯一约束，逻辑删后释放字典值，避免重建触发 500
        item.value = f"{item.value[:50]}#del{item.id}"
        db.commit()
    return None


# ---------------- 编号规则 ----------------
def _rule_out(r: NumberRule) -> dict:
    return {
        "id": r.id,
        "bizType": r.biz_type,
        "categoryKey": r.category_key,
        "prefix": r.prefix,
        "dateFormat": r.date_format,
        "yearDigits": r.year_digits,
        "monthDigits": r.month_digits,
        "dayDigits": r.day_digits,
        "seqLen": r.seq_len,
        "seqStart": r.seq_start,
        "separator": r.separator,
        "resetCycle": r.reset_cycle,
        "enabled": r.enabled,
        "example": r.example,
        "preview": preview_no(r),
    }


@router.get("/number-rules")
def list_number_rules(
    current: User = Depends(require_perm("admin:numbering:list")),
    db: Session = Depends(get_db),
):
    rows = db.scalars(select(NumberRule).where(NumberRule.deleted == 0).order_by(NumberRule.id)).all()
    return [_rule_out(r) for r in rows]


@router.post("/number-rules", status_code=201)
def create_number_rule(
    body: S.NumberRuleIn,
    current: User = Depends(require_perm("admin:numbering:edit")),
    db: Session = Depends(get_db),
):
    if db.scalar(
        select(NumberRule).where(
            NumberRule.biz_type == body.biz_type,
            NumberRule.category_key == body.category_key,
            NumberRule.deleted == 0,
        )
    ):
        raise BizException(R.ADMIN_NUMBER_CONFLICT)
    r = NumberRule(**body.model_dump(), create_by=current.id)
    db.add(r)
    db.commit()
    return _rule_out(r)


@router.put("/number-rules/{rid}")
def update_number_rule(
    rid: int,
    body: S.NumberRuleIn,
    current: User = Depends(require_perm("admin:numbering:edit")),
    db: Session = Depends(get_db),
):
    r = db.get(NumberRule, rid)
    if not r or r.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    dup = db.scalar(
        select(NumberRule).where(
            NumberRule.biz_type == body.biz_type,
            NumberRule.category_key == body.category_key,
            NumberRule.deleted == 0,
            NumberRule.id != rid,
        )
    )
    if dup:
        raise BizException(R.ADMIN_NUMBER_CONFLICT)
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    db.commit()
    return _rule_out(r)


@router.post("/number-rules/preview")
def preview_number_rule(
    body: S.NumberRulePreviewIn,
    current: User = Depends(require_perm("admin:numbering:edit")),
):
    """实时预览（不落库、不占号）。"""
    return {"preview": preview_no(NumberRule(**body.model_dump()))}


@router.post("/number-rules/{rid}/reset")
def reset_number_rule(
    rid: int,
    body: S.NumberSeqResetIn,
    current: User = Depends(require_perm("admin:numbering:edit")),
    db: Session = Depends(get_db),
):
    r = db.get(NumberRule, rid)
    if not r or r.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    period = reset_seq(db, r, body.value)
    audit(
        db,
        user_id=current.id,
        module="admin",
        action="number_rule_reset",
        biz_type="number_rule",
        biz_id=rid,
        detail=f"{r.biz_type}/{r.category_key or '-'} period={period} value={body.value}",
    )
    db.commit()
    return {"period": period, "value": body.value}


# ---------------- 审计日志 ----------------
@router.get("/audit-logs")
def list_audit_logs(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    current: User = Depends(require_perm("admin:audit:list")),
    db: Session = Depends(get_db),
):
    pp = PageParams(page=page, size=size)
    stmt, total = apply_list_filters(
        select(AuditLog),
        AuditLog,
        request.query_params,
        db,
        pp,
        search_cols=["module", "action"],
        filter_cols={"module", "user_id", "biz_type"},
        sort_cols={"id", "create_time", "module", "action", "user_id"},
        default_sort=("id", "desc"),
    )
    rows = db.scalars(stmt).all()
    usernames = {
        u.id: u.username for u in db.scalars(select(User).where(User.id.in_({r.user_id for r in rows if r.user_id})))
    }
    return {
        "items": [
            {
                "id": r.id,
                "username": usernames.get(r.user_id, "") if r.user_id else "",
                "module": r.module,
                "action": r.action,
                "bizType": r.biz_type,
                "bizId": r.biz_id,
                "detail": r.detail,
                "fieldName": r.field_name,
                "oldValue": r.old_value,
                "newValue": r.new_value,
                "reason": r.reason,
                "userAgent": r.user_agent,
                "traceId": r.trace_id,
                "ip": r.ip,
                "ipRegion": ipgeo.resolve_region(r.ip),
                "chainSeq": r.chain_seq,
                "rowHash": r.row_hash,
                "hashAlg": r.hash_alg,
                "createTime": _t(r.create_time),
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "size": size,
    }


# ---------------- 登录日志 ----------------
@router.get("/login-logs")
def list_login_logs(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    current: User = Depends(require_perm("admin:audit:list")),
    db: Session = Depends(get_db),
):
    """登录日志（含客户端 IP 属地）。沿用审计查看权限 admin:audit:list，不另设权限码。"""
    pp = PageParams(page=page, size=size)
    extra: list = []
    success_raw = (request.query_params.get("filters[success]") or "").strip()
    if success_raw in ("0", "1"):
        extra.append(LoginLog.success == int(success_raw))
    stmt, total = apply_list_filters(
        select(LoginLog),
        LoginLog,
        request.query_params,
        db,
        pp,
        search_cols=["username"],
        sort_cols={"id", "create_time", "username"},
        default_sort=("id", "desc"),
        extra_where=extra,
    )
    rows = db.scalars(stmt).all()
    return {
        "items": [
            {
                "id": r.id,
                "username": r.username,
                "success": r.success,
                "reason": r.reason,
                "ip": r.ip,
                "ipRegion": ipgeo.resolve_region(r.ip),
                "userAgent": r.ua,
                "createTime": _t(r.create_time),
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "size": size,
    }


# ---------------- 审计证据链（B9） ----------------
@router.get("/audit-logs/chain/verify")
def verify_audit_chain(
    mode: str = Query("full", pattern="^(full|since_anchor)$"),
    from_seq: int | None = Query(None, alias="fromSeq", ge=1),
    current: User = Depends(require_perm("admin:audit:list")),
    db: Session = Depends(get_db),
):
    """审计链完整性校验：断链 / 篡改 / 截断 / 链头被改。"""
    result = verify_chain(db, mode=mode, from_seq=from_seq)
    audit(
        db,
        user_id=current.id,
        module="admin",
        action="audit_chain_verify",
        detail={"mode": mode, "ok": result["ok"], "checked": result["checked"]},
    )
    db.commit()
    return result


@router.get("/audit-logs/anchors")
def list_audit_anchors(
    current: User = Depends(require_perm("admin:audit:list")),
    db: Session = Depends(get_db),
):
    """锚点历史（DB 之外的文件为准，用于发现整链重写/截断）。"""
    return {"items": list_anchors()}


@router.post("/audit-logs/anchor")
def create_audit_anchor(
    current: User = Depends(require_perm("admin:audit:list")),
    db: Session = Depends(get_db),
):
    """立即锚定当前链头。"""
    info = write_anchor(db)
    audit(
        db,
        user_id=current.id,
        module="admin",
        action="audit_anchor_create",
        detail={"seq": info["seq"], "hash": info["hash"]},
        strict=True,
    )
    db.commit()
    return info


@router.get("/audit-logs/{row_id}/evidence")
def get_audit_evidence(
    row_id: int,
    current: User = Depends(require_perm("admin:audit:list")),
    db: Session = Depends(get_db),
):
    """单条审计证据详情：链上位置 + 重算哈希比对。"""
    return evidence_detail(db, row_id)


AUDIT_EXPORT_COLS = [
    {"key": "username", "label": "操作人", "width": 14},
    {"key": "module", "label": "模块", "width": 12},
    {"key": "action", "label": "动作", "width": 20},
    {"key": "bizType", "label": "业务类型", "width": 12},
    {"key": "bizId", "label": "业务ID", "width": 10},
    {"key": "fieldName", "label": "变更字段", "width": 16},
    {"key": "oldValue", "label": "变更前", "width": 24},
    {"key": "newValue", "label": "变更后", "width": 24},
    {"key": "reason", "label": "变更原因", "width": 24},
    {"key": "detail", "label": "明细", "width": 40},
    {"key": "chainSeq", "label": "链序号", "width": 10},
    {"key": "rowHash", "label": "链哈希", "width": 24},
    {"key": "traceId", "label": "追踪ID", "width": 24},
    {"key": "ip", "label": "IP", "width": 14},
    {"key": "ipRegion", "label": "属地", "width": 16},
    {"key": "userAgent", "label": "终端", "width": 28},
    {"key": "createTime", "label": "时间", "width": 19},
]


@router.get("/audit-logs/export")
def export_audit_logs(
    request: Request,
    current: User = Depends(require_perm("admin:audit:list")),
    db: Session = Depends(get_db),
):
    """审计日志导出（沿用 admin:audit:list 查看权限，复用列表筛选）。"""
    from types import SimpleNamespace

    stmt, _ = apply_list_filters(
        select(AuditLog),
        AuditLog,
        request.query_params,
        db,
        SimpleNamespace(page=1, size=100_000),
        search_cols=["module", "action"],
        filter_cols={"module", "user_id", "biz_type"},
        sort_cols={"id", "create_time", "module", "action", "user_id"},
        default_sort=("id", "desc"),
    )
    logs = db.scalars(stmt).all()
    usernames = {
        u.id: u.username for u in db.scalars(select(User).where(User.id.in_({r.user_id for r in logs if r.user_id})))
    }
    rows = [
        {
            "username": usernames.get(r.user_id, "") if r.user_id else "",
            "module": r.module,
            "action": r.action,
            "bizType": r.biz_type or "",
            "bizId": r.biz_id or "",
            "fieldName": r.field_name or "",
            "oldValue": r.old_value or "",
            "newValue": r.new_value or "",
            "reason": r.reason or "",
            "detail": r.detail or "",
            "chainSeq": r.chain_seq or "",
            "rowHash": r.row_hash or "",
            "traceId": r.trace_id or "",
            "ip": r.ip or "",
            "ipRegion": ipgeo.resolve_region(r.ip),
            "userAgent": r.user_agent or "",
            "createTime": _t(r.create_time),
        }
        for r in logs
    ]
    payload = export_xlsx_styled(rows, AUDIT_EXPORT_COLS, "audit_logs")
    audit(
        db,
        user_id=current.id,
        module="admin",
        action="audit_export",
        detail={"count": len(rows)},
        strict=True,
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('audit_logs')}"},
    )


# ---------------- 偏好 ----------------
@router.put("/prefs")
def save_prefs(
    body: S.PrefIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc.upsert_prefs(db, current.id, body.prefs)
    db.commit()
    return None


# ---------------- 部门/业务板块 ----------------
@router.get("/depts")
def list_depts(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """部门树（B10-1 起含组织架构扩展列：层级 / 场所 / 负责人 / 有效期）。

    仍是**全站唯一的部门写入口**（HR 组织架构页复用本端点，不另开写接口）。
    """
    rows = db.scalars(
        select(Dept).where(Dept.deleted == 0, Dept.status == "enabled").order_by(Dept.sort, Dept.id)
    ).all()
    member_counts, position_counts = hr_org.dept_counts(db)
    manager_names = hr_org.user_names(db, [d.manager_id for d in rows if d.manager_id])
    return [hr_org.dept_out(db, d, member_counts, position_counts, manager_names) for d in rows]


DEPT_EXPORT_COLS = [
    {"key": "name", "label": "部门名称", "width": 22},
    {"key": "code", "label": "部门编码", "width": 12},
    {"key": "parentName", "label": "上级部门", "width": 22},
    {"key": "deptTypeText", "label": "层级", "width": 10},
    {"key": "siteCode", "label": "场所编码", "width": 14},
    {"key": "managerName", "label": "部门负责人", "width": 14},
    {"key": "memberCount", "label": "在编人数", "width": 10},
    {"key": "sort", "label": "排序", "width": 8},
    {"key": "status", "label": "状态", "width": 8},
]


@router.get("/depts/export")
def export_depts(
    current: User = Depends(require_perm("admin:dept:list")),
    db: Session = Depends(get_db),
):
    """部门导出（沿用 admin:dept:list 查看权限；含停用部门，状态列区分）。"""
    rows = db.scalars(select(Dept).where(Dept.deleted == 0).order_by(Dept.sort, Dept.id)).all()
    name_map = {d.id: d.name for d in rows}
    status_cn = {"enabled": "启用", "disabled": "停用"}
    member_counts, _ = hr_org.dept_counts(db)
    manager_names = hr_org.user_names(db, [d.manager_id for d in rows if d.manager_id])
    items = [
        {
            "name": d.name,
            "code": d.code,
            "parentName": name_map.get(d.parent_id, "") if d.parent_id else "",
            "deptTypeText": hr_org.DEPT_TYPE_CN.get(d.dept_type, d.dept_type),
            "siteCode": d.site_code,
            "managerName": manager_names.get(d.manager_id, "") if d.manager_id else "",
            "memberCount": member_counts.get(d.id, 0),
            "sort": d.sort,
            "status": status_cn.get(d.status, d.status),
        }
        for d in rows
    ]
    payload = export_xlsx_styled(items, DEPT_EXPORT_COLS, "depts")
    audit(db, user_id=current.id, module="admin", action="dept_export", detail={"count": len(items)})
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('depts')}"},
    )


@router.post("/depts", status_code=201)
def create_dept(
    body: S.DeptIn,
    current: User = Depends(require_perm("admin:dept:edit")),
    db: Session = Depends(get_db),
):
    data = body.model_dump()
    manager_id = data.pop("manager_id", None)
    d = Dept(**data, create_by=current.id)
    db.add(d)
    db.flush()
    # 部门负责人与任职表 is_leader 双向同步
    org.apply_dept_manager(db, d, manager_id)
    db.flush()
    # 组织变更轨迹（只追加快照，历史版本留存）
    hr_org.write_org_change(
        db,
        object_type="dept",
        object_id=d.id,
        object_name=d.name,
        change_type="create",
        before=None,
        after=hr_org.dept_out(db, d),
        operator_id=current.id,
        operator_name=current.name or current.username,
        reason="新建部门",
    )
    audit(db, user_id=current.id, module="admin", action="dept_create", biz_type="dept", biz_id=d.id)
    db.commit()
    return None


@router.put("/depts/{did}")
def update_dept(
    did: int,
    body: S.DeptIn,
    current: User = Depends(require_perm("admin:dept:edit")),
    db: Session = Depends(get_db),
):
    d = db.get(Dept, did)
    if not d or d.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    before = hr_org.dept_out(db, d)
    data = body.model_dump()
    manager_id = data.pop("manager_id", None)
    for k, v in data.items():
        setattr(d, k, v)
    org.apply_dept_manager(db, d, manager_id)
    db.flush()
    after = hr_org.dept_out(db, d)
    change_type = "move" if before.get("parentId") != after.get("parentId") else "update"
    hr_org.write_org_change(
        db,
        object_type="dept",
        object_id=d.id,
        object_name=d.name,
        change_type=change_type,
        before=before,
        after=after,
        operator_id=current.id,
        operator_name=current.name or current.username,
        reason="修改部门",
    )
    audit(db, user_id=current.id, module="admin", action="dept_update", biz_type="dept", biz_id=d.id)
    db.commit()
    return None


@router.get("/depts/{did}/members")
def list_dept_members(
    did: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """部门任职成员（登录即可读，供流程设计/部门管理展示）。"""
    rows = db.scalars(
        select(UserDept).where(UserDept.dept_id == did, UserDept.deleted == 0)
    ).all()
    users = (
        {u.id: u for u in db.scalars(select(User).where(User.id.in_([r.user_id for r in rows]))).all()}
        if rows
        else {}
    )
    return [
        {
            "userId": r.user_id,
            "username": users[r.user_id].username if r.user_id in users else "",
            "userName": (users[r.user_id].name or users[r.user_id].username) if r.user_id in users else "",
            "userStatus": users[r.user_id].status if r.user_id in users else "",
            "isPrimary": r.is_primary,
            "isLeader": r.is_leader,
        }
        for r in rows
        if r.user_id in users
    ]


@router.put("/depts/{did}/members")
def set_dept_members(
    did: int,
    body: S.DeptMembersIn,
    current: User = Depends(require_perm("admin:dept:edit")),
    db: Session = Depends(get_db),
):
    """整组替换部门任职成员；is_primary=1 的成员同步为该用户主部门。"""
    d = db.get(Dept, did)
    if not d or d.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    seen: set[int] = set()
    for m in body.members:
        if m.user_id in seen:
            raise BizException(R.GENERIC_PARAM, f"成员重复：user_id={m.user_id}")
        seen.add(m.user_id)
    users = (
        {u.id: u for u in db.scalars(select(User).where(User.id.in_(seen), User.deleted == 0)).all()}
        if seen
        else {}
    )
    missing = seen - set(users)
    if missing:
        raise BizException(R.GENERIC_NOT_FOUND, f"用户不存在：{sorted(missing)}")
    db.query(UserDept).filter(UserDept.dept_id == did).delete()
    db.flush()
    for m in body.members:
        db.add(
            UserDept(
                user_id=m.user_id,
                dept_id=did,
                is_primary=1 if m.is_primary else 0,
                is_leader=1 if m.is_leader else 0,
            )
        )
    db.flush()
    # 主部门同步：is_primary=1 的成员，user.dept_id 指向本部门并清掉其它任职的主标记
    for m in body.members:
        if not m.is_primary:
            continue
        u = users[m.user_id]
        u.dept_id = did
        u.dept_name = d.name
        org.sync_primary_membership(db, u)
    # 部门负责人反写：dept.manager_id 与任职表 is_leader 必须一致（B10-1）
    org.sync_dept_manager_from_members(db, d)
    audit(db, user_id=current.id, module="admin", action="dept_members", biz_type="dept", biz_id=did)
    db.commit()
    return None


# ---------------- 站内通知（登录即可读自己的） ----------------
@router.get("/notifies")
def list_notifies(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=100),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """我的站内通知。支持 q 关键词（标题/正文）、filters[biz_type] 分类、status=unread。"""
    extra = []
    if (request.query_params.get("status") or "") == "unread":
        extra.append(Notify.read_flag == 0)
    stmt = select(Notify).where(Notify.user_id == current.id)
    stmt, total = apply_list_filters(
        stmt,
        Notify,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=["title", "content"],
        filter_cols={"biz_type"},
        sort_cols={"create_time", "update_time", "id"},
        default_sort=("create_time", "desc"),
        extra_where=extra,
    )
    rows = db.scalars(stmt).all()
    return {
        "items": [
            {
                "id": n.id,
                "title": n.title,
                "content": n.content,
                "bizType": n.biz_type,
                "bizId": n.biz_id,
                "link": n.link,
                "readFlag": bool(n.read_flag),
                "createTime": _t(n.create_time),
            }
            for n in rows
        ],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/notifies/counts")
def notify_counts(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """消息中心页签计数：all / unread / 按业务分类（biz_type → 条数）。"""
    rows = db.execute(
        select(Notify.biz_type, Notify.read_flag, func.count())
        .where(Notify.user_id == current.id, Notify.deleted == 0)
        .group_by(Notify.biz_type, Notify.read_flag)
    ).all()
    by_biz_type: dict[str, int] = {}
    total = 0
    unread = 0
    for biz_type, read_flag, cnt in rows:
        total += cnt
        if not read_flag:
            unread += cnt
        if biz_type:
            by_biz_type[biz_type] = by_biz_type.get(biz_type, 0) + cnt
    return {"all": total, "unread": unread, "byBizType": by_biz_type}


@router.get("/notifies/unread-count")
def notify_unread_count(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.scalar(
        select(func.count()).select_from(
            select(Notify)
            .where(Notify.user_id == current.id, Notify.read_flag == 0, Notify.deleted == 0)
            .subquery()
        )
    ) or 0
    return {"count": n}


@router.post("/notifies/{nid}/read")
def mark_notify_read(
    nid: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    n = db.scalar(select(Notify).where(Notify.id == nid, Notify.user_id == current.id, Notify.deleted == 0))
    if not n:
        raise BizException(R.GENERIC_NOT_FOUND)
    n.read_flag = 1
    db.commit()
    return None


@router.post("/notifies/read-all")
def mark_all_read(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for n in db.scalars(
        select(Notify).where(Notify.user_id == current.id, Notify.read_flag == 0, Notify.deleted == 0)
    ):
        n.read_flag = 1
    db.commit()
    return None


# ---------------- 变更日志 ----------------
@router.get("/changelog")
def changelog(_: User = Depends(get_current_user)):
    """变更日志（Keep a Changelog + 语义化版本）。

    数据源 = 仓库根目录 `CHANGELOG.md`（代码拥有、随版本走），后端只解析不改写。
    仅需登录即可读；菜单入口在「系统管理 → 系统与审计 → 变更日志」。
    """
    releases = changelog_svc.load_releases()
    return {
        "currentVersion": settings.app_version,
        "latestVersion": releases[0].version if releases else "",
        "latestDate": releases[0].date if releases else "",
        "releases": [r.out() for r in releases],
    }
