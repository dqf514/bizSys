"""B10-1 HR L1 组织与人事：跨文件共用的枚举取值。

集中在一处，避免 `schemas.py` / `org.py` / `employee.py` / `employment.py`
各自定义一份导致取值漂移。前后端必须使用**同一套字符串**。
"""

# —— 组织架构（部门类型）——
DEPT_TYPES = ["site", "company", "division", "dept", "lab", "team"]

DEPT_TYPE_CN = {
    "site": "场所",
    "company": "公司",
    "division": "事业部",
    "dept": "科室",
    "lab": "实验室",
    "team": "班组",
}

# —— 岗位类型 ——
POSITION_TYPES = ["staff", "manager", "key"]

POSITION_TYPE_CN = {
    "staff": "普通岗",
    "manager": "管理岗",
    "key": "关键岗位",
}

# 关键岗位标记（HR docx 2.1：技术负责人 / 质量负责人 / 授权签字人 / 监督员 /
# 样品管理员 / 设备管理员）—— 与 CMA/CNAS 的人员资质要求对应。
KEY_ROLES = [
    "tech_leader",
    "qa_leader",
    "signer",
    "supervisor",
    "sample_manager",
    "device_manager",
]

KEY_ROLE_CN = {
    "tech_leader": "技术负责人",
    "qa_leader": "质量负责人",
    "signer": "授权签字人",
    "supervisor": "监督员",
    "sample_manager": "样品管理员",
    "device_manager": "设备管理员",
}

# —— 员工雇佣类型 ——
EMPLOY_TYPES = ["labor", "engage", "part_time", "intern"]

EMPLOY_TYPE_CN = {
    "labor": "劳动合同",
    "engage": "聘用",
    "part_time": "兼职",
    "intern": "实习",
}

# —— 员工在职状态 ——
EMPLOY_STATUSES = ["probation", "regular", "idle", "resigned", "retired"]

EMPLOY_STATUS_CN = {
    "probation": "试用",
    "regular": "正式",
    "idle": "待岗",
    "resigned": "离职",
    "retired": "退休",
}

# —— 员工名单管控 ——
CONTROL_TYPES = ["blacklist", "whitelist"]

CONTROL_TYPE_CN = {
    "blacklist": "黑名单",
    "whitelist": "白名单",
}

# —— 人事事务类型 ——
EVENT_TYPES = ["onboard", "transfer", "resign", "rehire"]

EVENT_TYPE_CN = {
    "onboard": "入职",
    "transfer": "调岗",
    "resign": "离职",
    "rehire": "返聘",
}

# —— 人事事务单据状态 ——
EMPLOYMENT_STATUSES = ["draft", "approving", "approved", "effective", "rejected"]

EMPLOYMENT_STATUS_CN = {
    "draft": "草稿",
    "approving": "审批中",
    "approved": "已通过",
    "effective": "已生效",
    "rejected": "已驳回",
}

# —— 代理范围 ——
DELEGATE_SCOPES = ["position", "auth", "task"]

DELEGATE_SCOPE_CN = {
    "position": "岗位",
    "auth": "授权",
    "task": "任务",
}
