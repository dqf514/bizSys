"""B8 作业申请流程（CSV 第 32 项）：叉车 / 吊装 / 高处 / 动火 四类作业许可申请。

设计口径
--------
- **不新建模块**：作业申请复用 OA 域（``oa_form`` 模板 + ``oa_instance`` 单据）与审批引擎
  （``biz_type='oa'``）——本质是 OA 模板分类 ``work_apply`` 下的一组模板 + 一组流程定义，
  因此作业申请单天然出现在「新申请 / 我的申请 / 与我相关」里。
- **幂等**：按 ``OaForm.key`` 判断；已存在则跳过（不覆盖运营期在 OA 设计器里改过的模板）。
- **脱敏**：只采集作业许可必需信息，**不收集身份证号等敏感信息**；模板内不含任何真实
  姓名 / 手机号 / 证件号（由填写人自行填写）。
- **审批人可解析**：安全员审核走 ``ROLE=security_officer``（种子内置 ``security1`` 持有）；
  部门负责人审批走 ``DEPT_LEADER``，解析不到时回退到 ``security_officer`` 兜底角色，
  避免出现「节点无审批人」把流程卡死的情况。
"""

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.admin.models import DictItem
from app.modules.approval.graph import build_process_graph, dumps_graph
from app.modules.approval.models import ApprovalDefinition, ApprovalNode
from app.modules.oa.models import OaForm

#: OA 模板分类（作业申请）
WORK_APPLY_CATEGORY = "work_apply"

#: 流程通用选项 —— 10 个键全部显式写出（缺失即 False，语义与 E1 企微模板一致）
GENERAL_OPTIONS: dict[str, bool] = {
    "allowModifyFlow": False,
    "allowModifyCc": False,
    "allowWithdrawAfterApproved": False,
    "commentSignRequired": False,
    "allowAddSign": True,
    "commentRequired": True,
    "executorCommentRequired": True,
    "executorCanModify": False,
    "allowProxySubmit": False,
    "detailTablePermission": False,
}

#: 流程变量声明（暴露字段 + E1 的 ``org.*`` / ``form.*`` 命名空间）
WORK_APPLY_VARIABLES: dict[str, dict] = {
    "applicant": {"type": "number", "label": "申请人"},
    "work_dept": {"type": "string", "label": "作业部门"},
    "work_location": {"type": "string", "label": "作业地点"},
    "risk_level": {"type": "string", "label": "风险等级"},
    "org": {"type": "object", "label": "发起人组织信息"},
    "form": {"type": "object", "label": "表单信息"},
}

#: 四类作业申请共用的字段（key / label / type / required / options 由 OA 设计器直接消费）
_COMMON_FIELDS: list[dict] = [
    {
        "key": "applicant",
        "label": "申请人",
        "type": "user",
        "required": True,
        "span": 12,
        "exposeVariable": True,
    },
    {
        "key": "work_dept",
        "label": "作业部门",
        "type": "text",
        "required": True,
        "span": 12,
        "exposeVariable": True,
    },
    {
        "key": "work_location",
        "label": "作业地点",
        "type": "text",
        "required": True,
        "span": 12,
        "exposeVariable": True,
    },
    {
        "key": "work_time",
        "label": "作业时间",
        "type": "daterange",
        "required": True,
        "span": 24,
    },
    {
        "key": "work_content",
        "label": "作业内容",
        "type": "textarea",
        "required": True,
        "span": 24,
    },
    {
        "key": "equipment",
        "label": "涉及设备/车辆",
        "type": "text",
        "required": True,
        "span": 12,
    },
    {
        "key": "risk_level",
        "label": "风险等级",
        "type": "select",
        "required": True,
        "span": 12,
        "exposeVariable": True,
        "options": ["低", "中", "高"],
    },
    {
        "key": "safety_measure",
        "label": "安全措施",
        "type": "textarea",
        "required": True,
        "span": 24,
    },
    {
        "key": "emergency_contact",
        "label": "应急联系人",
        "type": "text",
        "required": True,
        "span": 12,
    },
    {
        "key": "emergency_phone",
        "label": "联系电话",
        "type": "phone",
        "required": True,
        "span": 12,
    },
]

#: 四类作业申请模板（按企业真实作业许可单据的差异化项拆分）
WORK_APPLY_TEMPLATES: list[dict] = [
    {
        "key": "work_apply_forklift",
        "name": "叉车作业申请",
        "icon": "Tools",
        "sort": 210,
        "description": "叉车取送、装卸、厂内转运等作业的作业许可申请",
        "after": "equipment",
        "extras": [
            {
                "key": "vehicle_no",
                "label": "叉车编号/车牌",
                "type": "text",
                "required": True,
                "span": 12,
            },
            {
                "key": "driver",
                "label": "叉车司机",
                "type": "user",
                "required": True,
                "span": 12,
            },
            {
                "key": "cargo_desc",
                "label": "搬运物品说明",
                "type": "text",
                "required": False,
                "span": 24,
            },
        ],
    },
    {
        "key": "work_apply_lifting",
        "name": "吊装作业申请",
        "icon": "Operation",
        "sort": 211,
        "description": "起重吊装、大件搬移等作业的作业许可申请",
        "after": "equipment",
        "extras": [
            {
                "key": "lifting_equipment",
                "label": "吊装设备/索具",
                "type": "text",
                "required": True,
                "span": 12,
            },
            {
                "key": "load_weight",
                "label": "吊装物重量（吨）",
                "type": "number",
                "required": True,
                "span": 12,
            },
            {
                "key": "crane_operator",
                "label": "起重指挥/司索人员",
                "type": "user",
                "required": True,
                "span": 24,
            },
        ],
    },
    {
        "key": "work_apply_height",
        "name": "高处作业申请",
        "icon": "Position",
        "sort": 212,
        "description": "2 米及以上高处、临边、悬空等作业的作业许可申请",
        "after": "equipment",
        "extras": [
            {
                "key": "work_height",
                "label": "作业高度（米）",
                "type": "number",
                "required": True,
                "span": 12,
            },
            {
                "key": "platform",
                "label": "作业平台/防护设施",
                "type": "text",
                "required": False,
                "span": 12,
            },
            {
                "key": "fall_protection",
                "label": "防坠落措施",
                "type": "textarea",
                "required": True,
                "span": 24,
            },
        ],
    },
    {
        "key": "work_apply_hot_work",
        "name": "动火作业申请",
        "icon": "Warning",
        "sort": 213,
        "description": "电焊、气割、明火加热等动火作业的作业许可申请",
        "after": "equipment",
        "extras": [
            {
                "key": "hot_work_type",
                "label": "动火方式",
                "type": "select",
                "required": True,
                "span": 12,
                "options": ["电焊", "气割", "明火加热", "其他"],
            },
            {
                "key": "hot_work_area",
                "label": "动火部位",
                "type": "text",
                "required": True,
                "span": 12,
            },
            {
                "key": "gas_cylinder",
                "label": "气瓶种类及数量",
                "type": "text",
                "required": False,
                "span": 12,
            },
            {
                "key": "fire_watch",
                "label": "监护人",
                "type": "user",
                "required": True,
                "span": 12,
            },
        ],
    },
]


def _build_fields(extras: list[dict], after_key: str) -> list[dict]:
    """共用字段 + 该作业类型的差异字段（差异项插在 ``after_key`` 之后）。"""
    fields = [dict(f) for f in _COMMON_FIELDS]
    idx = next((i for i, f in enumerate(fields) if f["key"] == after_key), len(fields) - 1)
    return fields[: idx + 1] + [dict(e) for e in extras] + fields[idx + 1 :]


def _ensure_category_dict(db: Session) -> None:
    """OA 表单分类字典补 ``work_apply``（否则「新申请」目录里归到「其他」）。"""
    exists = db.scalar(
        select(DictItem)
        .where(
            DictItem.dict_type_code == "oa_category",
            DictItem.value == WORK_APPLY_CATEGORY,
            DictItem.deleted == 0,
        )
        .limit(1)
    )
    if exists is None:
        db.add(
            DictItem(
                dict_type_code="oa_category",
                label="作业申请",
                label_en="Work Permit",
                value=WORK_APPLY_CATEGORY,
                sort=90,
            )
        )
        db.flush()


def _ensure_definition(db: Session, tpl: dict) -> ApprovalDefinition:
    """作业申请审批流程定义（安全员审核 → 部门负责人审批，两级或签）。"""
    from app.modules.approval import service as approval_svc  # noqa: PLC0415
    from app.modules.approval.schemas import DefinitionIn, NodeIn  # noqa: PLC0415

    code = f"{tpl['key']}_approve"
    body = DefinitionIn(
        code=code,
        name=f"{tpl['name']}审批",
        biz_type="oa",
        enabled=1,
        remark=f"{tpl['name']}：安全员审核 → 部门负责人审批（两级或签）",
        variables_schema=dict(WORK_APPLY_VARIABLES),
        options=dict(GENERAL_OPTIONS),
        nodes=[
            NodeIn(
                seq=1,
                node_name="安全员审核",
                node_type="approval",
                sign_mode="or",
                approver_type="ROLE",
                approver_value="security_officer",
                approver_name="安保员",
            ),
            NodeIn(
                seq=2,
                node_name="部门负责人审批",
                node_type="approval",
                sign_mode="or",
                approver_type="DEPT_LEADER",
                approver_value="security_officer",
                approver_name="部门负责人",
            ),
        ],
    )
    d = _latest_definition(db, code)
    if d is None:
        approval_svc.create_definition(db, body)
    else:
        approval_svc.update_definition(db, d.id, body)
    d = _latest_definition(db, code)
    if d is None:  # pragma: no cover - 理论上不会发生
        raise RuntimeError(f"作业申请流程定义写入失败：{code}")
    # 显式生成 LogicFlow 流程图（与 OA 流程设计器生成的图等价）
    nodes = list(
        db.scalars(
            select(ApprovalNode)
            .where(ApprovalNode.definition_id == d.id, ApprovalNode.deleted == 0)
            .order_by(ApprovalNode.seq)
        ).all()
    )
    d.process_graph = dumps_graph(build_process_graph(nodes))
    db.flush()
    return d


def _latest_definition(db: Session, code: str) -> ApprovalDefinition | None:
    return db.scalar(
        select(ApprovalDefinition)
        .where(ApprovalDefinition.code == code, ApprovalDefinition.deleted == 0)
        .order_by(ApprovalDefinition.flow_version.desc(), ApprovalDefinition.id.desc())
        .limit(1)
    )


def import_work_apply_forms(db: Session) -> dict:
    """幂等导入 4 类作业申请模板 + 对应审批流程定义。

    返回：``{"created": n, "skipped": n, "forms": [key...], "definitions": [code...]}``
    """
    stats: dict = {"created": 0, "skipped": 0, "forms": [], "definitions": []}
    _ensure_category_dict(db)
    for tpl in WORK_APPLY_TEMPLATES:
        exists = db.scalar(select(OaForm).where(OaForm.key == tpl["key"], OaForm.deleted == 0).limit(1))
        if exists is not None:
            stats["skipped"] += 1
            stats["forms"].append(tpl["key"])
            continue
        definition = _ensure_definition(db, tpl)
        form = OaForm(
            key=tpl["key"],
            name=tpl["name"],
            form_version=1,
            status="published",
            category=WORK_APPLY_CATEGORY,
            icon=tpl["icon"],
            sort=tpl["sort"],
            description=tpl["description"],
            schema_json=json.dumps(
                {"fields": _build_fields(tpl["extras"], tpl["after"])},
                ensure_ascii=False,
            ),
            flow_definition_id=definition.id,
            published_at=datetime.now(),
        )
        db.add(form)
        db.flush()
        stats["created"] += 1
        stats["forms"].append(tpl["key"])
        stats["definitions"].append(definition.code)
    db.flush()
    return stats


__all__ = [
    "GENERAL_OPTIONS",
    "WORK_APPLY_CATEGORY",
    "WORK_APPLY_TEMPLATES",
    "WORK_APPLY_VARIABLES",
    "import_work_apply_forms",
]
