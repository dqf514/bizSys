# bizSys API 契约（前后端共用，v1）

> 所有路由前缀 `/api/v1`。**统一响应信封**：`{"code":0,"message":"ok","data":...,"traceId":"..."}`。
> `code=0` 成功；非 0 为业务错误（HTTP 状态码可能仍为 200/401/403/404/422/500）。
> 鉴权：`Authorization: Bearer <access_token>`。
> 分页：请求 `?page=1&size=20`，响应 `data = {items, total, page, size}`。
> 检索：`q=关键词`（模糊）`status=xx`（状态页签，`all` 表示不过滤）
>  `filters[字段]=值`（等值/逗号多值） `range[字段]=起|止` `sort=字段:asc|desc`。

## 错误码分段
0 成功 · 1xxxx 通用 · 2xxxx 鉴权 · 3xxxx 系统管理 · 4xxxx CRM · 5xxxx 合同 · 6xxxx 任务 · 7xxxx 审批 · 8xxxx 财务 · 9xxxx 集成占位

## 鉴权 /auth
- `POST /auth/login` `{username,password}` → `{access_token,refresh_token,token_type,user}`
- `POST /auth/refresh` `{refresh_token}` → `{access_token,refresh_token,token_type,user}`（旋转：旧 refresh_token 立即吊销）
- `POST /auth/logout`（可带 `{refresh_token}` 吊销）
- `POST /auth/password` `{old_password,new_password}`（新密码至少 8 位；原密码错误 20004）
- `GET /auth/me` → `{id,username,name,deptId,deptName,email,mobile,roles[],perms[],prefs{},menus[]}`
  - menus 节点：`{id,parentId,name,titleKey,path,componentKey,icon,permission,menuType:"dir"|"menu",sort,visible,children[]}`
  - titleKey 为 vue-i18n 键（如 `menu.customer`）；componentKey 为前端组件键（如 `crm/CustomerList`）
- 企业微信扫码登录（免登录，凭据见系统设置；配置/联调步骤见 docs/wecom-setup.md）：
  - `GET /auth/wecom/qr-url?redirect_uri=` → `{url,state}`（state 存 Redis 10min 一次性，防 CSRF；未启用/未配置 90001）
  - `POST /auth/wecom/callback` `{code,state}` → 与 /auth/login 相同结构；错误码：20005 企微账号未绑定本地用户 / 20006 state 无效或已过期

## 系统管理 /admin（权限码 admin:*）
- `GET /admin/users`（分页检索）· `POST /admin/users` `{username,password,name,deptId,deptName,mobile,email,status,roleIds[]}`
  `PUT /admin/users/{id}` · `DELETE /admin/users/{id}` · `POST /admin/users/{id}/reset-password` `{password}`
  `POST /admin/users/export`（同检索参数，返回 xlsx 流）
- `GET /admin/roles` · `POST/PUT/DELETE /admin/roles[/{id}]` · `PUT /admin/roles/{id}/menus` `{menuIds[]}`
- `GET /admin/menus/tree?include_buttons=` · `POST/PUT/DELETE /admin/menus[/{id}]`
- `GET /admin/dict/types`（含 items）· `GET /admin/dict/items?type=code` → `[{label,labelEn,value,extra}]`
  `POST /admin/dict/types` · `POST/PUT/DELETE /admin/dict/items[/{id}]`
- `GET/POST/PUT /admin/number-rules`（预览 preview 字段）
- `GET /admin/audit-logs`（分页）
- `PUT /admin/prefs` `{prefs:{theme,locale,density,navCollapsed,...}}`
- `GET /admin/depts` → `[{id,parentId,name,code,sort}]` · `POST/PUT /admin/depts`
- 系统设置（sys_config，Secret AES-GCM 加密落库、接口只回 secretSet 布尔）：
  - `GET /admin/settings`（admin:setting:list）→ `{siteName,logoUrl,wecom:{enabled,corpId,agentId,secretSet,callbackUrl}}`
  - `PUT /admin/settings`（admin:setting:edit）`{siteName?,wecom?:{enabled,corpId,agentId,secret?,callbackUrl?}}`（secret 空=不修改）
  - `POST /admin/settings/logo`（admin:setting:edit，multipart file；限 png/jpg/svg/webp ≤2MB）→ `{logoUrl}`
- 免登录公共接口：`GET /public/branding` → `{siteName,logoUrl,wecomEnabled}` · `GET /public/logo` → Logo 文件流
- 站内通知（登录即可，读自己的）：`GET /admin/notifies?status=unread&page&size`
  `GET /admin/notifies/unread-count` → `{count}` · `POST /admin/notifies/{id}/read` · `POST /admin/notifies/read-all`

## CRM 客户 /crm
- `GET /crm/customers` 分页：字段
  `{id,customerNo,name,code,customerType,taxNo,grade,status,address,country,province,city,bankName,bankAccount,payOrg,licenseFileId,remark,createTime,updateTime}`
  检索：`q`（name/customerNo/taxNo）、`status`（enabled/disabled/all）
- `POST /crm/customers` · `PUT /crm/customers/{id}` · `DELETE /crm/customers/{id}`
- `POST /crm/customers/export` · `GET /crm/customers/template` · `POST /crm/customers/import`（multipart file）
- `GET /crm/customers/options?q=&limit=20` → `[{id,label,sub}]`（模糊选择器专用，label=客户名，sub=客户编号）
- 权限码：`crm:customer:list/create/edit/delete/list:export/import`

## 合同 /contract
- 状态机：`draft 草稿 → approving 审批中 → approved 已通过 / rejected 已驳回（可改后重新提交）/ voided 已作废`；审批中禁止编辑。
- `GET /contract/contracts` 分页：
  `{id,contractNo,name,customerId,customerName,contractType,subjectType,amount,startDate,endDate,payCycle,delivery,sealType,handlerId,handlerName,frameworkNo,paymentOrg,remark,status,flowInstanceId,attachments:[{id,fileName,size}],createTime,updateTime}`
- `POST /contract/contracts` · `PUT /contract/contracts/{id}`（仅 draft/rejected）· `DELETE`（仅 draft → 逻辑删）
- `POST /contract/contracts/{id}/submit` → 启动审批（创建 approval instance，状态→approving）
- `POST /contract/contracts/{id}/void` → 作废（审批中需先撤回；已作废 50001）
- `GET /contract/contracts/{id}` 详情（含附件、审批时间线可选）
- `POST /contract/contracts/{id}/attachments`（multipart file）· `GET /contract/attachments/{fileId}`（下载流）
- `DELETE /contract/attachments/{fileId}`（contract:edit；仅 draft/rejected 合同可删，审批中 50002；逻辑删 + 审计）
- `POST /contract/contracts/export` · `GET /contract/contracts/options`（仅 approved，建任务时用）
- 权限码：`contract:list/create/edit/submit/delete/list:export`

## 审批中心 /approval（自研引擎）
- `GET /approval/tasks?tab=todo|done|initiated&page&size` →
  `{items:[{id,instanceId,bizType,bizId,title,status,nodeName,comment,initiatorName,assigneeName,createTime,actedAt}],...}`
  - todo=我待办(status=pending & assignee=me)；done=我已办；initiated=我发起的实例
- `GET /approval/instances/{instance_id}` → 实例快照 + 时间线（含 formSnapshot、records）
- `GET /approval/instances/{bizType}/{bizId}/timeline` →
  `{instanceId,status, currentNode, records:[{action:"start|agree|reject|withdraw|add_sign|transfer",operatorName,nodeName,comment,at}]}`
- `POST /approval/tasks/{taskId}/approve` `{comment}` · `/reject` `{comment}`（意见必填）
- `POST /approval/tasks/{taskId}/transfer` `{toUserId,comment}` · `/add-sign` `{approverId,comment}`
- `POST /approval/instances/{instanceId}/withdraw`
- 管理端：`GET /approval/definitions` · `POST /approval/definitions` · `PUT /approval/definitions/{id}`
  · `DELETE /approval/definitions/{id}`（admin:flow:edit；有运行中实例时拒绝，逻辑删）
  定义结构：`{id,code,name,bizType,enabled,nodes:[{seq,nodeName,approverType:"USER|ROLE",approverValue,approverName}]}`
- 错误码：70001 无待办 / 70002 非当前审批人 / 70003 意见必填 / 70004 已有进行中实例

## 任务 /task
- 状态机（本期）：`draft 已创建待提交 → assigning 已提交分配中 → assigned 已分配待完成
  → in_progress 执行中 → finished 已完成 → closed 已结束`，终态 `stopped 停止`、`settled 已结算`
  （closed → settled 由财务模块创建结算单触发，见「财务」章节）
- `GET /task/tasks` 分页（宽表冗余）：
  `{id,taskNo,taskName,taskType,taskTypeLabel,contractId,contractNo,customerId,customerName,
    bizBlock,bizBlockLabel,deptId,deptName,ownerId,ownerName,content,partySystem,receiver,receiverUnit,
    planFinishDate,status,reportCount,sampleCount,createTime,updateTime}`
  检索：`q`（taskNo/taskName/customerName）、`status` 页签
- `GET /task/tasks/counts` → `{draft:1,assigning:0,...}`（状态页签计数）
- `POST /task/tasks` `{taskName,taskType,contractId,content,receiver,receiverUnit,bizBlock,deptId,planFinishDate,partySystem,items:[],samples:[]}`
  → 自动 `taskNo`；仅允许选择 `approved` 合同（否则 60002）
- `PUT /task/tasks/{id}`（仅 draft）· `DELETE`（仅 draft）
- 状态动作：`POST /task/tasks/{id}/submit|start|finish|close|stop`（非法流转 60001；submit 触发站内通知）
  - 合法流转表：`draft --submit--> assigning`；`assigning --start--> assigned`（接单确认）；
    `assigned --start--> in_progress`（开始执行）；`in_progress --finish--> finished`；
    `finished --close--> closed`；任意非终态 `--stop--> stopped`（终态）
  - 前端按钮：draft 显示「提交分配」(submit)；assigning/assigned 显示「开始」(start)；
    in_progress 显示「完成」(finish)；finished 显示「结束」(close)；非终态显示「停止」(stop)
- `GET /task/tasks/{id}` → 详情含 `items[]` `samples[]` `logs[]`
  （`logs` 为该任务全部样品的 `task_sample_flow` 流水，按时间倒序：
  `[{id,sampleNo,action:"in"|"out",operatorName,createTime,remark}]`）
- 子条目 `task_item`：`{id,itemCode,name,std,dept,inspector,qty,settleType,needReport,reportNo,reportStatus}`
  嵌套路由 `POST /task/tasks/{id}/items` · `PUT /task/items/{itemId}` · `DELETE /task/items/{itemId}`
  `needReport=true` → 自动分配 `reportNo`（BG 规则）
- 样品 `task_sample`：`{id,sampleNo,name,model,vin,vehicleType,sampleDate,inStock:"in"|"out"}`
  `POST /task/tasks/{id}/samples`（sampleNo 自动 `任务号-01`）· `PUT /task/samples/{sid}` · `DELETE`
  `POST /task/samples/{sid}/in` `/out`（写 `task_sample_flow` 流水）
- `POST /task/tasks/export`
- 权限码：`task:list/create/edit/assign/submit/list:export`（delete/其他状态动作用 `task:edit`）

## 财务 /finance
- 结算单状态机：`pending 待开票 → invoicing 开票审批中 → invoiced 已开票 → paid 已到账`；
  审批驳回/撤回 → 回 `pending`。
- 主链路：任务 closed → 建任务人创建结算单（任务 → settled，一任务一单）→ 申请开票（审批流 invoice_apply）
  → 审批通过生成发票行 → 财务登记发票信息 → 到账登记（累计到账 ≥ 结算金额 → paid）。
- `GET /finance/settlements` 分页：
  `{id,settlementNo,taskId,taskNo,customerName,contractNo,amount,invoiceableAmount,status,statusText,remark,
    approvalInstanceId,createBy,createTime}`
  检索：`q`（settlementNo/taskNo/customerName/contractNo）、`status` 页签
- `GET /finance/settlements/task-options?q=` → `[{value,label,sub}]`
  （仅 `closed` 且无结算单的任务；value=taskId，label=任务编号，sub=客户名称/合同号）
- `POST /finance/settlements` `{taskId,amount,invoiceableAmount?,remark?}` → 201；
  仅任务创建人（或超管）可对 closed 任务创建；`settlementNo` 走 HK 编号规则；成功后任务 closed → settled。
  错误：80001 任务状态不允许结算 / 80002 该任务已有结算单 / 80003 非任务创建人
- `GET /finance/settlements/{id}` → 详情 + `invoices[]` + `payments[]` + `paidAmount` + 开票审批 `timeline`
- `POST /finance/settlements/{id}/apply-invoice` `{comment?}` → 启动开票审批
  （bizType=invoice，definition=invoice_apply），结算单 → invoicing；审批通过 → invoiced 并生成发票行
- `PUT /finance/invoices/{id}` `{invoiceNo,amount,invoiceDate?}` → 财务登记发票信息
- `GET /finance/invoices` 分页：
  `{id,invoiceNo,settlementId,settlementNo,taskNo,customerName,amount,invoiceDate,status,statusText,createBy,createTime}`
  （settlementNo/taskNo/customerName 关联 fin_settlement 带出；status ∈ `approving 审批中 / issued 已开票`）
  检索：`q`（invoiceNo/settlementNo/customerName）、`status` 页签
- `GET /finance/payments` 分页：
  `{id,paymentNo,settlementId,settlementNo,payType,payerName,payerAccount,amount,bank,paidAt,remark,createBy,createTime}`
- `POST /finance/payments` `{settlementId,payType,payerName,payerAccount?,amount,bank?,paidAt,remark?}` → 201；
  仅 invoiced 状态结算单可登记；`paymentNo` 走 DZ 编号规则；累计到账 ≥ 结算金额 → 结算单 paid
- `GET /finance/settlements/export` · `GET /finance/invoices/export` · `GET /finance/payments/export`
  （同检索参数，返回 xlsx 流）
- 权限码：`finance:settlement:list/create/export`、`finance:invoice:apply/edit/list/export`、
  `finance:payment:list/create/export`
- 菜单：财务管理 → 结算信息（FinanceSettlements）/ 开票申请（FinanceInvoices，`/finance/invoices`）/
  到账信息（FinancePayments）

## 前端组件键（componentKey → 懒加载组件）
```
workbench/Dashboard  crm/CustomerList  contract/ContractList  task/TaskList
finance/SettlementList  finance/InvoiceList  finance/PaymentList
approval/TodoList
admin/UserList  admin/RoleList  admin/MenuList  admin/DictList
admin/NumberRuleList  admin/AuditLogList  admin/DeptList  admin/FlowDefList
```

## 字典（sys_dict）
`customer_type / customer_grade / contract_type / task_type / biz_block / pay_cycle / delivery_way / pay_type`
读取：`GET /admin/dict/items?type={code}`（仅 enabled，按 sort 排序）

## 种子账号
| 用户名 | 密码 | 角色 |
|---|---|---|
| admin | Admin@123456 | 超级管理员 |
| manager1 | Test@123456 | 部门负责人（审批人演示） |
| leader1 | Test@123456 | 分管领导（审批人演示） |
