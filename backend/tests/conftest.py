"""pytest 基建：独立测试库 bizsys_test（建表 + 复用幂等种子），必须先设 DB_URL 再导入 app。"""

import os
import pathlib
import re

# 优先级：环境变量 DB_URL（CI）> 本地 .env > 默认（本机 3307 开发库）
_ENV = pathlib.Path(__file__).resolve().parent.parent / ".env"
_URL = "mysql+pymysql://root:bizsys123@127.0.0.1:3307/bizsys?charset=utf8mb4"
if _ENV.exists():
    for _line in _ENV.read_text(encoding="utf-8").splitlines():
        if _line.startswith("DB_URL="):
            _URL = _line.split("=", 1)[1].strip()
if os.environ.get("DB_URL"):
    _URL = os.environ["DB_URL"]

TEST_URL = re.sub(r"(//[^/]+/)[^?/]+", r"\1bizsys_test", _URL, count=1)
os.environ["DB_URL"] = TEST_URL

# 隔离上传目录：test_zz_purge 会执行真实 purge()，其中删除 uploads 业务子目录是
# 文件系统操作（不随测试库回滚）。必须在导入 app（settings 单例化）之前重定向，
# 否则每次全量测试都会清空生产 uploads（report/contract/partner/portal/task_progress）。
import tempfile  # noqa: E402

os.environ.setdefault("UPLOAD_DIR", tempfile.mkdtemp(prefix="bizsys_test_uploads_"))
# 审计链锚点文件同样隔离到临时目录（锚点写在 DB 之外，不能污染开发目录）
os.environ.setdefault("AUDIT_ANCHOR_DIR", tempfile.mkdtemp(prefix="bizsys_test_audit_anchor_"))

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

# 确保测试库存在（连 server 级）
_server_url = re.sub(r"/[^?/]+(\?.*)?$", r"\1", TEST_URL)
_admin_engine = create_engine(_server_url, isolation_level="AUTOCOMMIT")
with _admin_engine.connect() as _conn:
    _conn.execute(text("CREATE DATABASE IF NOT EXISTS bizsys_test CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"))
_admin_engine.dispose()

from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402  导入即注册全部模块表

Base.metadata.create_all(bind=engine)


def _ensure_columns(table: str, cols: dict[str, str]) -> None:
    """测试库跨次运行残留：create_all 只建新表，不会给已存在的表补列。

    这里按需补齐后续新增的列（幂等），保证本地旧测试库也能跑新用例。
    """
    with engine.begin() as conn:
        existing = {r[0] for r in conn.execute(text(f"SHOW COLUMNS FROM {table}")).all()}
        for name, ddl in cols.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


def _drop_columns(table: str, cols: list[str]) -> None:
    """删列（幂等）—— 用于把旧测试库调整到"只追加"的新结构。"""
    with engine.begin() as conn:
        existing = {r[0] for r in conn.execute(text(f"SHOW COLUMNS FROM {table}")).all()}
        for name in cols:
            if name in existing:
                conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {name}"))


def _ensure_indexes(table: str, idx: dict[str, str]) -> None:
    # SHOW INDEX 的列序：Table, Non_unique, Key_name, ... → 索引名在第 3 列
    with engine.begin() as conn:
        existing = {r[2] for r in conn.execute(text(f"SHOW INDEX FROM {table}")).all()}
        for name, ddl in idx.items():
            if name not in existing:
                conn.execute(text(ddl))


def _modify_column(table: str, column: str, ddl: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} MODIFY COLUMN {column} {ddl}"))


_ensure_columns(
    "partner_user",
    {
        "account_type": "account_type VARCHAR(16) NULL DEFAULT 'supplier' COMMENT 'customer/supplier'",
        "perm_scope": "perm_scope VARCHAR(64) NULL DEFAULT 'tender' COMMENT 'tender/entrust/staff'",
        "manager_id": "manager_id BIGINT NULL COMMENT '归属客户经理'",
        "manager_name": "manager_name VARCHAR(64) NULL DEFAULT '' COMMENT '归属客户经理姓名'",
        "staff_limit": "staff_limit INT NULL DEFAULT 5 COMMENT '人员登记名额上限'",
    },
)

# B4 补充：存货呆滞预警阈值（ast_item.stagnant_days）
_ensure_columns(
    "ast_item",
    {
        "stagnant_days": "stagnant_days INT NULL DEFAULT 90 COMMENT '呆滞预警阈值（天，0=不预警）'",
    },
)

# B5 补充：任务字段扩展（task_task）
_ensure_columns(
    "task_task",
    {
        "plan_start_date": "plan_start_date DATE NULL COMMENT '计划开始日期'",
        "duration_hours": "duration_hours NUMERIC(10,2) NULL DEFAULT 8 COMMENT '预计工时（小时）'",
        "progress": "progress INT NULL DEFAULT 0 COMMENT '进度百分比 0-100'",
        "priority": "priority INT NULL DEFAULT 5 COMMENT '优先级 1(最高)~9(最低)'",
        "role_group": "role_group VARCHAR(32) NULL DEFAULT '' COMMENT '角色分组 sim/model/test/outsource'",
        "process_stage": "process_stage VARCHAR(32) NULL DEFAULT '' COMMENT '当前工序编码'",
        "mesh_count": "mesh_count INT NULL COMMENT '网格数（万单元）'",
        "solver": "solver VARCHAR(32) NULL DEFAULT '' COMMENT '求解器'",
        "compute_resource": "compute_resource VARCHAR(64) NULL DEFAULT '' COMMENT '算力资源池'",
        "compute_cores": "compute_cores INT NULL DEFAULT 0 COMMENT '核数'",
        "compute_nodes": "compute_nodes INT NULL DEFAULT 0 COMMENT '节点数'",
    },
)

# F5 补充：流程驱动支撑列
_ensure_columns(
    "prj_project",
    {
        "flow_instance_id": "flow_instance_id BIGINT NULL COMMENT '立项审批实例'",
    },
)

_ensure_columns(
    "hr_timesheet",
    {
        "flow_instance_id": "flow_instance_id BIGINT NULL COMMENT '工时审批实例'",
    },
)

_ensure_columns(
    "fin_payment",
    {
        "status": "status VARCHAR(16) NOT NULL DEFAULT 'draft' COMMENT 'draft/approving/confirmed/rejected'",
        "flow_instance_id": "flow_instance_id BIGINT NULL COMMENT '回款复核审批实例'",
    },
)

_ensure_columns(
    "ast_disposal",
    {
        "flow_instance_id": "flow_instance_id BIGINT NULL COMMENT '处置审批实例'",
    },
)

_ensure_columns(
    "ast_receipt",
    {
        "flow_instance_id": "flow_instance_id BIGINT NULL COMMENT '验收审批实例'",
    },
)

_ensure_columns(
    "rpt_report",
    {
        "seal_flow_instance_id": "seal_flow_instance_id BIGINT NULL COMMENT '用章申请审批实例'",
    },
)

# F6 补充：访客单挂审批实例 + 门户提交账号
_ensure_columns(
    "vis_visit",
    {
        "flow_instance_id": "flow_instance_id BIGINT NULL COMMENT '审批引擎实例 id'",
        "partner_user_id": "partner_user_id BIGINT NULL COMMENT '门户合作方账号 id'",
    },
)

# B9 补充：审计证据链（字段级 + 哈希链）+ 只追加结构
_ensure_columns(
    "sys_audit_log",
    {
        "field_name": "field_name VARCHAR(64) NOT NULL DEFAULT '' COMMENT '变更字段名'",
        "old_value": "old_value TEXT NULL COMMENT '变更前值'",
        "new_value": "new_value TEXT NULL COMMENT '变更后值'",
        "reason": "reason TEXT NULL COMMENT '变更原因'",
        "user_agent": "user_agent VARCHAR(255) NOT NULL DEFAULT '' COMMENT '终端 UA'",
        "chain_seq": "chain_seq BIGINT NULL COMMENT '链上序号'",
        "prev_hash": "prev_hash VARCHAR(64) NOT NULL DEFAULT '' COMMENT '上一行哈希'",
        "row_hash": "row_hash VARCHAR(64) NOT NULL DEFAULT '' COMMENT '本行哈希'",
        "hash_alg": "hash_alg VARCHAR(16) NOT NULL DEFAULT '' COMMENT '哈希算法标识'",
    },
)
# 毫秒精度：row_hash 含 create_time，秒精度会让链校验重算必然不一致
_modify_column(
    "sys_audit_log",
    "create_time",
    "DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '写入时间'",
)
# 只追加：物理删掉可改可删的列（与迁移 n8 一致）
_drop_columns("sys_audit_log", ["deleted", "version", "update_time", "update_by", "create_by"])
_ensure_indexes(
    "sys_audit_log",
    {
        "ix_sys_audit_log_chain_seq": (
            "CREATE UNIQUE INDEX ix_sys_audit_log_chain_seq ON sys_audit_log (chain_seq)"
        ),
    },
)
# 链头单行（链上唯一权威游标）
with engine.begin() as conn:
    conn.execute(
        text(
            "INSERT IGNORE INTO sys_audit_chain_head "
            "(chain_key, last_seq, last_hash, last_row_id, anchored_seq, anchored_hash, "
            "write_failures, key_version, deleted, version) "
            "VALUES ('main', 0, '', 0, 0, '', 0, 'v1', 0, 0)"
        )
    )
    # 测试库跨次运行残留：上一轮用例可能删过链行（篡改检测用例），
    # 整链校验会因此必然失败。这里把链行清掉、链头归零，让每个测试会话
    # 都从 seq=1 重新开始，保证链校验用例可重复。存量无链行（chain_seq IS NULL）
    # 的历史审计保留不动（验证 legacyRows 口径）。
    conn.execute(text("DELETE FROM sys_audit_log WHERE chain_seq IS NOT NULL"))
    conn.execute(
        text(
            "UPDATE sys_audit_chain_head SET last_seq=0, last_hash='', last_row_id=0, "
            "anchored_seq=0, anchored_hash='', write_failures=0 WHERE chain_key='main'"
        )
    )

# B9 补充：NDA 密码学签名绑定列（存量标 legacy）
_ensure_columns(
    "vis_nda",
    {
        "signed_by_id": "signed_by_id BIGINT NULL COMMENT '签署人 id'",
        "signed_by_name": "signed_by_name VARCHAR(64) NOT NULL DEFAULT '' COMMENT '签署人姓名'",
        "signed_ip": "signed_ip VARCHAR(64) NOT NULL DEFAULT '' COMMENT '签署真实 IP'",
        "sign_alg": "sign_alg VARCHAR(16) NOT NULL DEFAULT '' COMMENT '签名算法'",
        "sign_version": "sign_version VARCHAR(16) NOT NULL DEFAULT '' COMMENT '签名口径'",
    },
)

# B9 补充：报告签章绑定列 + 三级审核角色
_ensure_columns(
    "rpt_report",
    {
        "seal_by_name": "seal_by_name VARCHAR(64) NOT NULL DEFAULT '' COMMENT '签章人姓名'",
        "seal_content_hash": "seal_content_hash VARCHAR(64) NOT NULL DEFAULT '' COMMENT '签章内容哈希'",
        "seal_signature": "seal_signature VARCHAR(64) NOT NULL DEFAULT '' COMMENT '签章签名'",
        "seal_alg": "seal_alg VARCHAR(16) NOT NULL DEFAULT '' COMMENT '签名算法'",
        "preparer_id": "preparer_id BIGINT NULL COMMENT '编制人 id'",
        "preparer_name": "preparer_name VARCHAR(64) NOT NULL DEFAULT '' COMMENT '编制人姓名'",
        "reviewer_id": "reviewer_id BIGINT NULL COMMENT '复核人 id'",
        "reviewer_name": "reviewer_name VARCHAR(64) NOT NULL DEFAULT '' COMMENT '复核人姓名'",
        "approver_id": "approver_id BIGINT NULL COMMENT '批准人 id'",
        "approver_name": "approver_name VARCHAR(64) NOT NULL DEFAULT '' COMMENT '批准人姓名'",
    },
)

# 存量回款行按迁移口径置为已确认（测试库跨次运行残留）
with engine.begin() as conn:
    conn.execute(text("UPDATE fin_payment SET status = 'confirmed' WHERE status IS NULL OR status = 'draft'"))

# B9-C3 补充：人员授权台账（hr_authorization 是新表，create_all 自动建）
# 变更轨迹的生效时间改毫秒精度 —— 同一秒内的多次状态变更要能区分先后，
# 否则「回溯任一历史时点状态」只能精确到秒。
_modify_column(
    "hr_authorization_event",
    "effective_at",
    "DATETIME(3) NULL DEFAULT NULL COMMENT '生效时间（毫秒精度）'",
)

from app.seeds import init_data as seed  # noqa: E402

_seed_session = SessionLocal()
try:
    seed.main()
finally:
    _seed_session.close()


@pytest.fixture(scope="session")
def client():
    from starlette.testclient import TestClient

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="session")
def admin_headers(client):
    return _login(client, "admin", "Admin@123456")


def captcha_fields(client) -> dict:
    """获取图形验证码并直接从 Redis 读答案（测试与 dev 共用 Redis 实例）。"""
    from app.core.redis import get_redis

    r = client.get("/api/v1/auth/captcha").json()
    cid = r["data"]["captchaId"]
    return {"captchaId": cid, "captchaText": get_redis().get(f"captcha:{cid}")}


def post_login(client, username: str, password: str):
    """带图形验证码的登录请求，返回原始响应（不断言）。"""
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password, **captcha_fields(client)},
    )


def _login(client, username: str, password: str) -> dict:
    r = post_login(client, username, password)
    data = r.json()
    assert data["code"] == 0, data
    return {"Authorization": f"Bearer {data['data']['access_token']}"}


@pytest.fixture(scope="session")
def manager_headers(client):
    return _login(client, "manager1", "Test@123456")


@pytest.fixture(scope="session")
def leader_headers(client):
    return _login(client, "leader1", "Test@123456")


def approve_instance(biz_type: str, biz_id: int, times: int = 1, comment: str = "ok") -> None:
    """在测试库中直接推进某业务单据的审批实例（F5 流程驱动用例专用）。

    与 HTTP 待办接口等价，但不受"谁有权限看到待办"影响。
    """
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.modules.approval import service as approval
    from app.modules.approval.models import ApprovalInstance, ApprovalTask
    from app.modules.auth.models import User

    db = SessionLocal()
    try:
        for _ in range(times):
            target = None
            for t in db.scalars(
                select(ApprovalTask).where(ApprovalTask.status == "pending", ApprovalTask.deleted == 0)
            ):
                inst = db.get(ApprovalInstance, t.instance_id)
                if inst and inst.biz_type == biz_type and inst.biz_id == biz_id:
                    target = t
                    break
            assert target, f"no pending task for {biz_type}/{biz_id}"
            approval.approve(db, target.id, db.get(User, target.assignee_id), comment)
            db.commit()
    finally:
        db.close()


@pytest.fixture()
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()
