"""B9-C1 审计证据链：字段级记录 + 哈希链 + 不可删改 + 链校验。

合规原则 2.2「审计追踪不是日志，而是证据链」/ 4.4「日志写入只追加，
采用 WORM 介质或哈希链保证不可篡改」。

注：测试库由 create_all 建表，**没有**迁移里的 BEFORE UPDATE/DELETE 触发器，
因此本文件直接用 SQL 篡改来验证"链校验能发现篡改"；应用层则靠
"无写接口 + 一键清空不删审计表"来保证不可删改。
"""

import uuid

from sqlalchemy import delete, insert, select

from app.common.audit import record as audit
from app.common.audit import verify_chain, write_anchor
from app.modules.admin.models import AuditChainHead, AuditLog

UUID = uuid.uuid4().hex[:8]


def _snapshot(row) -> dict:
    return {c.name: getattr(row, c.name) for c in AuditLog.__table__.columns}


def _write(db, **kwargs) -> AuditLog:
    """写一条审计并返回落库行。"""
    payload = {
        "user_id": 1,
        "module": "c1_test",
        "action": "chain_write",
        "biz_type": "c1",
        "biz_id": 1,
    }
    payload.update(kwargs)
    audit(db, **payload)
    db.commit()
    return db.scalars(select(AuditLog).order_by(AuditLog.id.desc())).first()


def test_chain_is_continuous_and_head_matches(db):
    _write(db, action="chain_a")
    _write(db, action="chain_b")
    _write(db, action="chain_c")
    result = verify_chain(db)
    assert result["ok"] is True
    assert result["brokenAt"] is None
    assert result["headMatchesLastRow"] is True
    assert result["checked"] >= 3
    assert result["hashAlg"] == "HMAC-SHA256"


def test_field_level_columns_are_recorded(db):
    row = _write(
        db,
        action="field_level",
        field_name="status",
        old_value="draft",
        new_value="active",
        reason="能力确认通过",
    )
    assert row.field_name == "status"
    assert row.old_value == "draft"
    assert row.new_value == "active"
    assert row.reason == "能力确认通过"
    assert row.chain_seq is not None
    assert row.row_hash and len(row.row_hash) == 64


def test_trace_id_and_user_agent_are_captured_from_request(client, admin_headers, db):
    """请求头里的 trace_id / UA / 客户端 IP 必须自动落审计（不改 280+ 个调用点）。"""
    client.post(
        "/api/v1/crm/customers",
        headers={**admin_headers, "X-Trace-Id": "trace-" + UUID, "User-Agent": "ComplianceProbe/1.0"},
        json={"name": f"C1客户_{UUID}", "level": "A"},
    )
    row = db.scalars(
        select(AuditLog).where(AuditLog.trace_id == "trace-" + UUID).order_by(AuditLog.id.desc())
    ).first()
    assert row is not None, "trace_id 未自动落库"
    assert row.user_agent == "ComplianceProbe/1.0"
    assert row.ip, "客户端 IP 未自动落库"


def test_tampered_content_is_detected(db):
    """直接改一行内容 → 校验报 row_hash_mismatch；改完必须还原。"""
    row = _write(db, action="tamper_target", detail="original")
    original = _snapshot(row)
    try:
        row.detail = "tampered"
        db.commit()

        result = verify_chain(db)
        assert result["ok"] is False
        assert result["brokenAt"] is not None
        assert result["brokenAt"]["reason"] == "row_hash_mismatch"
    finally:
        # 还原（审计链只允许追加，还原是测试收尾，不是业务行为）
        db.get(AuditLog, row.id).detail = original["detail"]
        db.commit()
    assert verify_chain(db)["ok"] is True


def test_deleted_row_is_detected(db):
    """删掉中间一行 → 校验报断链。"""
    _write(db, action="keep_1")
    target = _write(db, action="keep_2")
    _write(db, action="keep_3")
    original = _snapshot(target)
    try:
        db.execute(delete(AuditLog).where(AuditLog.id == target.id))
        db.commit()

        result = verify_chain(db)
        assert result["ok"] is False
        assert result["brokenAt"] is not None
        assert result["brokenAt"]["reason"] in {
            "seq_gap",
            "row_hash_mismatch",
            "prev_hash_mismatch",
        }
    finally:
        # 还原：连 id 一起插回，链恢复连续
        db.execute(insert(AuditLog).values(**original))
        db.commit()
    assert verify_chain(db)["ok"] is True


def test_head_tampering_is_detected(db):
    """改链头 → 校验报 head_mismatch。"""
    _write(db, action="head_target")
    head = db.scalar(select(AuditChainHead).where(AuditChainHead.chain_key == "main"))
    original_hash = head.last_hash
    try:
        head.last_hash = "0" * 64
        db.commit()

        result = verify_chain(db)
        assert result["ok"] is False
        assert result["headMatchesLastRow"] is False
        assert result["brokenAt"]["reason"] == "head_mismatch"
    finally:
        head.last_hash = original_hash
        db.commit()
    assert verify_chain(db)["ok"] is True


def test_anchor_detects_truncation(db):
    """锚点后删掉尾部行 → 校验报锚点截断。"""
    _write(db, action="anchor_tail")
    info = write_anchor(db)
    db.commit()
    assert info["seq"] > 0

    tail = db.scalars(select(AuditLog).order_by(AuditLog.id.desc())).first()
    original = _snapshot(tail)
    try:
        db.execute(delete(AuditLog).where(AuditLog.id == tail.id))
        db.commit()

        result = verify_chain(db, mode="since_anchor")
        assert result["anchor"] is not None
        assert result["anchor"]["truncated"] is True
        assert result["ok"] is False
    finally:
        db.execute(insert(AuditLog).values(**original))
        db.commit()


def test_audit_log_has_no_mutable_columns():
    """只追加：模型层面不得有 deleted / version / update_*。"""
    names = {c.name for c in AuditLog.__table__.columns}
    assert "deleted" not in names
    assert "version" not in names
    assert "update_time" not in names
    assert "update_by" not in names


def test_no_write_api_for_audit_logs(client, admin_headers):
    """审计日志不提供任何改 / 删接口。"""
    r = client.put("/api/v1/admin/audit-logs/1", headers=admin_headers, json={})
    assert r.status_code in {404, 405}
    r = client.delete("/api/v1/admin/audit-logs/1", headers=admin_headers)
    assert r.status_code in {404, 405}


def test_chain_verify_endpoint(client, admin_headers):
    r = client.get("/api/v1/admin/audit-logs/chain/verify", headers=admin_headers).json()
    assert r["code"] == 0, r
    assert r["data"]["ok"] is True
    assert r["data"]["hashAlg"] == "HMAC-SHA256"
    assert "legacyRows" in r["data"]


def test_anchor_endpoint(client, admin_headers):
    r = client.post("/api/v1/admin/audit-logs/anchor", headers=admin_headers).json()
    assert r["code"] == 0, r
    assert r["data"]["seq"] >= 0
    assert r["data"]["file"]

    r2 = client.get("/api/v1/admin/audit-logs/anchors", headers=admin_headers).json()
    assert r2["code"] == 0, r2
    assert r2["data"]["items"]


def test_evidence_endpoint(client, admin_headers, db):
    row = _write(db, action="evidence_detail")
    r = client.get(f"/api/v1/admin/audit-logs/{row.id}/evidence", headers=admin_headers).json()
    assert r["code"] == 0, r
    assert r["data"]["hashValid"] is True
    assert r["data"]["chainSeq"] == row.chain_seq
    assert r["data"]["rowHash"] == row.row_hash


def test_strict_audit_failure_raises_and_is_logged(db, monkeypatch):
    """strict=True 时审计写失败必须抛错（业务事务由调用方回滚），且失败本身留痕。"""
    from app.common import audit as audit_mod

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated audit failure")

    monkeypatch.setattr(audit_mod, "_write_row", _boom)
    try:
        audit(db, user_id=1, module="c1_test", action="strict_fail", strict=True)
    except Exception as exc:  # noqa: BLE001
        assert getattr(exc, "code", None) == 30005
    else:
        raise AssertionError("strict 模式下审计失败必须抛错")

    from app.modules.admin.models import AuditFailure

    failures = db.scalars(select(AuditFailure).where(AuditFailure.action == "strict_fail")).all()
    assert failures, "审计写入失败必须留痕"
    db.rollback()
