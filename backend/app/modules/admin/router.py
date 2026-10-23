"""系统管理路由 /api/v1/admin。"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit import record as audit
from app.common.filters import apply_list_filters
from app.common.pagination import PageParams
from app.core import response as R
from app.core.db import get_db
from app.core.deps import SUPER_ROLE, get_current_user, require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.core.security import hash_password
from app.modules.admin import org
from app.modules.admin import schemas as S
from app.modules.admin import service as svc
from app.modules.admin.models import (
    AuditLog,
    Dept,
    DictItem,
    DictType,
    Menu,
    Notify,
    NumberRule,
    Role,
    UserDept,
)
from app.modules.auth.models import User
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
    page: int = Query(1, ge=1),
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
        sort_cols={"update_time", "create_time", "id", "last_login_at"},
    )
    rows = db.scalars(stmt).all()
    return {"items": [_user_out(db, u) for u in rows], "total": total, "page": page, "size": size}


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
    u = User(
        username=body.username,
        password_hash=hash_password(body.password),
        name=body.name,
        dept_id=body.dept_id,
        dept_name=body.dept_name,
        mobile=body.mobile,
        email=body.email,
        status=body.status,
        create_by=current.id,
    )
    db.add(u)
    db.flush()
    org.sync_primary_membership(db, u)
    svc.set_user_roles(db, u.id, body.role_ids)
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
    page: int = Query(1, ge=1),
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
    current: User = Depends(get_current_user),
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
    page: int = Query(1, ge=1),
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
        sort_cols={"id", "create_time"},
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
                "traceId": r.trace_id,
                "ip": r.ip,
                "createTime": _t(r.create_time),
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "size": size,
    }


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
    rows = db.scalars(
        select(Dept).where(Dept.deleted == 0, Dept.status == "enabled").order_by(Dept.sort, Dept.id)
    ).all()
    return [{"id": d.id, "parentId": d.parent_id, "name": d.name, "code": d.code, "sort": d.sort} for d in rows]


@router.post("/depts", status_code=201)
def create_dept(
    body: S.DeptIn,
    current: User = Depends(require_perm("admin:dept:edit")),
    db: Session = Depends(get_db),
):
    db.add(Dept(**body.model_dump(), create_by=current.id))
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
    for k, v in body.model_dump().items():
        setattr(d, k, v)
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
    audit(db, user_id=current.id, module="admin", action="dept_members", biz_type="dept", biz_id=did)
    db.commit()
    return None


# ---------------- 站内通知（登录即可读自己的） ----------------
@router.get("/notifies")
def list_notifies(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Notify).where(Notify.user_id == current.id, Notify.deleted == 0)
    unread = (request.query_params.get("status") or "") == "unread"
    if unread:
        stmt = stmt.where(Notify.read_flag == 0)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Notify.id.desc()).offset((page - 1) * size).limit(size)).all()
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
