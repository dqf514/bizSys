# ADR-0004 合并 TPCworkflow 引擎语义进审批模块（工作流引擎合并 F1，仅后端）

- 状态：已接受（2026-11-21）；取代 ADR-0002 中"仅顺序多级 + 同节点或签"的引擎范围（5 表骨架与门面模式保留）
- 背景：审批制度演进需要条件分支（如按合同金额路由）、会签/依次签、抄送与发起人进度未读角标；参考系统 TPCworkflow 已有成熟语义。
- 决策：在既有 5 表上扩展而非另起引擎：
  1. `approval_definition` 增加 `process_graph`（LogicFlow 兼容 JSON，线性定义由 `approval/graph.py` 自动生成等价图，F2 设计器直接读写）与 `variables_schema`；
  2. `approval_node` 增加 `node_type`（approval/condition/cc）、`sign_mode`（or/and/sequential）、`branches`/`default_seq`（条件分支：结构化表达式 `{field,op,value}`，op ∈ eq/ne/gt/gte/lt/lte/in/contains，禁止 eval，见 `approval/condition.py`）；
  3. `approval_instance` 增加 `variables`（发起时注入，如合同金额/类型）与 `current_node_ids`；`approval_task` 增加 `node_type`/`action_meta`（依次队列、加签来源）；`approval_record` 增加 `payload`，充当只追加时间线；
  4. 新增 `approval_cc`（抄送，不阻塞流转）与 `approval_view_state`（发起人未读水位，角标=非本人操作且未看过的时间线条目数）。
- 引擎语义对齐 TPCworkflow（workflow_engine.py / workflow_add_sign.py / condition_value.py）：
  - 或签一人通过即作废同节点其他普通待办，但加签待办保留且须处理完毕节点才推进；
  - 会签全员通过才推进；依次签同一时刻仅队列首人持有待办；
  - 条件节点按 variables 求值路由，未命中走 default_seq 或顺序下一节点；抄送节点写 approval_cc + cc 时间线后直接放行；
  - 驳回（意见必填）终止实例，业务侧重新提交即开新实例；撤回仍限发起人且无人已审；
  - 业务回调继续走 common/events.py 的 ApprovalCompleted/Rejected/Withdrawn 同事务事件。
- 与 TPC 的差异：不支持前/后加签模式（加签仅为当前节点追加审批人）、无 handler 办理节点/并行网关/表单引擎/草稿态/通知与邮件通道；图结构字段沿用 LogicFlow 的 `sourceNodeId/targetNodeId`（TPC 用 source/target）。
- 后果：contract/report/finance 三处调用签名不变（新增可选 `variables` 参数）；API 新增 `/approval/cc`、`/approval/cc/{id}/read`、`/approval/preview`、`/approval/instances/{id}/timeline`，我发起的列表带 `unreadCount`；前端流程中心与 LogicFlow 设计器留 F2。
