# ADR-0002 自研轻量可配置审批引擎（弃 BPMN/Flowable）

- 状态：已接受（2026-10-09）
- 背景：需求方明确"结构从简，我们不用那么复杂"；本期审批仅合同/报告/开票三类，形态均为顺序多级审批。Python 生态无 Flowable 级别成熟 BPMN 引擎。
- 决策：自研 **5 表审批引擎**（approval_definition/node/instance/task/record），支持顺序多级、或签、加签、转办、驳回（意见必填）、撤回；节点按 `USER/ROLE/DEPT_LEADER` 配置，管理后台表格化配置界面，不做图形化设计器。
- 理由：
  1. 覆盖本期三类审批的全部形态，实现量小（约 2-3 天）且完全可控；
  2. 需求方审批制度尚未定稿（待朱忠明确认）——配置化节点意味着改制度只改配置不改码；
  3. 数据按 biz_type 解耦，二期若需 BPMN 网关/会签/子流程可替换引擎而不动业务表。
- 后果：业务接入统一走 ApprovalCenter 门面（start/approve/reject/withdraw/add_sign/transfer + 事件订阅）；不提供 BPMN 导入导出；审批历史用 approval_record 永久留痕 + 表单快照。
