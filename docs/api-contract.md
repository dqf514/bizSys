# bizSys API 契约（前后端共用，v1）

> 所有路由前缀 `/api/v1`。**统一响应信封**：`{"code":0,"message":"ok","data":...,"traceId":"..."}`。
> `code=0` 成功；非 0 为业务错误（HTTP 状态码可能仍为 200/401/403/404/422/500）。
> 鉴权：`Authorization: Bearer <access_token>`。
> 分页：请求 `?page=1&size=20`（1 ≤ page ≤ 1e9，1 ≤ size ≤ 200，越界 422/10001），响应 `data = {items, total, page, size}`。
> 检索：`q=关键词`（模糊）`status=xx`（状态页签，`all` 表示不过滤）
>  `filters[字段]=值`（等值/逗号多值） `range[字段]=起|止` `sort=字段:asc|desc`。
> 排序：sort 字段为后端 snake_case 列名，**各端点有白名单**；非法/空值静默回退默认排序，不报错。
> 白名单：tasks `task_name,task_type,customer_name,biz_block,status,create_time,id`；samples `sample_no,name,in_stock,task_name,task_no,customer_name,sample_date,create_time,id`；customers `customer_type,grade,status,name,create_time,id`；contracts `name,customer_name,status,start_date,end_date,contract_type,contract_no,create_time,id`；settlements `invoiceable_amount,task_no,contract_no,customer_name,status,confirm_status,create_time,id`；invoices `invoice_no,status,create_time,id`；payments `pay_type,payer_name,create_time,id`；reports `file_name,status,seal_time,create_time,id`；admin/users `username,name,status,create_time,id`；admin/roles `code,name,status,create_time,id`；admin/audit-logs `module,action,user_id,create_time,id`；approval/tasks `create_time,at,status,title,id`（按 kind 子集：todo=create_time/id，done=at/id，initiated=create_time/status/title/id）；approval/cc `create_time,id`；oa instances（my/admin）`display_no,form_name,category,applicant_name,status,create_time,finished_at,id`。

## 错误码分段
0 成功 · 1xxxx 通用 · 2xxxx 鉴权 · 3xxxx 系统管理 · 4xxxx CRM · 5xxxx 合同 · 6xxxx 任务 · 7xxxx 审批 · 8xxxx 财务 · 9xxxx 集成占位 · 95xxx 采购 · 96xxx 招投标/门户

## 鉴权 /auth
- `GET /auth/captcha`（免登录）→ `{captchaId,svg}`：4 位随机字符 SVG（排除 0/O/1/I/L），Redis 存 5 分钟、
  验证一次性销毁；同一 captchaId 连续错 3 次作废；非生产环境（ENV≠prod）额外回显 `debugText` 便于自动化测试
- `POST /auth/login` `{username,password,captchaId,captchaText}` → `{access_token,refresh_token,token_type,user}`
  （user 含 `mfaEnabled`）；验证码错误或过期 20009（不计入密码失败锁定）；
  若用户已开启 MFA 则不发 token，改回 `{mfaRequired:true,mfaToken,channels:[{channel:"sms"|"email",target(掩码)}]}`
- MFA 二步验证（mfaToken 为 5 分钟 typ=mfa_pending JWT + Redis 一次性凭证）：
  - `POST /auth/mfa/send` `{mfaToken,channel}` → `{sent,cooldown:60,mode}`：6 位数字码存 Redis 5 分钟，
    每通道 60 秒冷却（429/20013）；通道未配置时非生产走调试通道并回显 `debugCode`（生产绝不回显，未配置报 90001）
  - `POST /auth/mfa/verify` `{mfaToken,code}` → 与 login 相同结构；错码 20011，连续错 5 次作废本次登录（20010）
  - `POST /auth/mfa/toggle`（登录）`{enabled}` + `X-Step-Up-Token` 头 → `{mfaEnabled}`；
    开启前须已登记手机或邮箱（否则 20014）
- `POST /auth/refresh` `{refresh_token}` → `{access_token,refresh_token,token_type,user}`（旋转：旧 refresh_token 立即吊销）
- `POST /auth/logout`（可带 `{refresh_token}` 吊销）
- `POST /auth/password` `{old_password,new_password}`（新密码至少 8 位；原密码错误 20004）
- `GET /auth/me` → `{id,username,name,deptId,deptName,email,mobile,roles[],perms[],prefs{},menus[],allMenuPaths[]}`
  - menus 节点：`{id,parentId,name,titleKey,path,componentKey,icon,permission,menuType:"dir"|"menu",sort,visible,children[]}`
  - titleKey 为 vue-i18n 键（如 `menu.customer`）；componentKey 为前端组件键（如 `crm/CustomerList`）
  - allMenuPaths 为全量菜单路由路径（不过滤权限）：前端据此区分 404（路径不存在）与 403（无权限）
  - 导航树只返回 visible=1 菜单（含 super）；隐藏菜单（如批次A 隐藏的 ApprovalCenter）不出现在导航，
    但其路径仍在 allMenuPaths 中，前端以静态路由深链直达（/approval）
- 企业微信扫码登录（免登录，凭据见系统设置；配置/联调步骤见 docs/wecom-setup.md）：
  - `GET /auth/wecom/qr-url?redirect_uri=` → `{url,state}`（state 存 Redis 10min 一次性，防 CSRF；未启用/未配置 90001）
  - `POST /auth/wecom/callback` `{code,state}` → 与 /auth/login 相同结构；错误码：20005 企微账号未绑定本地用户 / 20006 state 无效或已过期

### 个人档案（批次B，登录即可，仅本人数据；越权一律 404/403）
- `GET /auth/profile` → `{id,username,name,mobile,email,employeeNo,hireDate,jobLevel,avatarUrl,deptName,leaderName,mfaEnabled,roles[]}`
  （employeeNo/hireDate/jobLevel 组织字段由管理员维护、本人只读；leaderName 沿部门负责人链向上取，无则空串）
- `PATCH /auth/profile` `{mobile,email}`：电话/邮箱任一变更要求 `X-Step-Up-Token` 头，否则 403/20007；
  邮箱格式校验 + 全库唯一（20008，为邮箱验证码登录预留）；电话格式校验（为短信登录预留）
- `POST /auth/step-up` `{password, method="password"}` → `{stepUpToken, expiresIn:300}`：
  密码重验签发 5 分钟 step-up JWT（typ=step_up）；method 预留 sms/email；密码错误 20004
- `POST /auth/profile/avatar`（multipart file）：jpg/png/webp + ≤5MB + 魔数校验，UUID 存储名（uploads/avatar/），
  旧文件自动清理 → `{avatarUrl}`；`GET /auth/avatar/{uid}` 公开读图（同 /public/logo，<img> 无法带 Authorization）
- 紧急联系人：`GET/POST /auth/profile/contacts` · `PUT/DELETE /auth/profile/contacts/{id}`
  `{name,relation,phone,remark}`（多条，非敏感不需 step-up）
- 银行卡（增删改/查看完整卡号均需 step-up）：`GET/POST /auth/profile/bank-accounts` ·
  `PUT/DELETE /auth/profile/bank-accounts/{id}` · `GET /auth/profile/bank-accounts/{id}/reveal`
  `{bankName,cardNo,holderName}`；列表卡号默认脱敏（`**** 后4位`），reveal 返回完整卡号；
  审计只记后 4 位，不落完整卡号明文

## 系统管理 /admin（权限码 admin:*）
- `GET /admin/users`（分页检索）· `POST /admin/users` `{username,password,name,deptId,deptName,mobile,email,status,roleIds[],employeeNo,hireDate,jobLevel}`
  `PUT /admin/users/{id}` · `DELETE /admin/users/{id}` · `POST /admin/users/{id}/reset-password` `{password}`
  `POST /admin/users/export`（同检索参数，返回 xlsx 流）
  （employeeNo/hireDate/jobLevel 为批次B 组织字段，沿用 admin:user:create / admin:user:edit）
- `GET /admin/users/counts`（沿用 admin:user:list）→ `{enabled,disabled,all}`（状态页签计数）
- `GET /admin/users/options?q=&limit=20` → `[{id,label,sub}]`（登录即可读：流程/通知选人用，仅 enabled 用户）
- `GET /admin/roles` · `POST/PUT/DELETE /admin/roles[/{id}]` · `PUT /admin/roles/{id}/menus` `{menuIds[]}`
  （RoleIn 校验：dataScope ∈ all/dept/self，status ∈ enabled/disabled，非法值 422/10001）
- `GET /admin/menus/tree?include_buttons=`（任一权限可读：admin:menu:list 或 admin:role:edit——角色授权弹窗共用此树）
  · `POST/PUT/DELETE /admin/menus[/{id}]`
- `GET /admin/dict/types`（含 items）· `GET /admin/dict/items?type=code` → `[{label,labelEn,value,extra}]`
  `POST /admin/dict/types` · `POST/PUT/DELETE /admin/dict/items[/{id}]`
  `GET /admin/dict/types/export`（平铺类型+字典项 xlsx，沿用 admin:dict:list）
- `GET/POST/PUT /admin/number-rules`（预览 preview 字段）
- `GET /admin/audit-logs`（分页）· `GET /admin/audit-logs/export`（同检索参数 xlsx，沿用 admin:audit:list）
- `PUT /admin/prefs` `{prefs:{theme,locale,density,navCollapsed,...}}`
- `GET /admin/depts` → `[{id,parentId,name,code,sort}]` · `POST/PUT /admin/depts`
  `GET /admin/depts/export`（含停用部门，沿用 admin:dept:list）
- 数据维护（/admin/maintenance）：备份设置/备份管理/一键清空（略，见系统设置章节）；
  记录时间修正（admin:maintenance:retime，仅超管）：
  `GET /admin/maintenance/retime/lookup?bizType=&key=` → `{id,label,fields:[{field,fieldLabel,value}]}`
  （bizType ∈ approval_record(按ID)/report(report_no)/settlement/invoice/payment(单号)）
  `POST /admin/maintenance/retime` `{bizType,id,field,value(YYYY-MM-DD HH:MM:SS 本地时区),reason(必填)}`
  → 白名单字段改值（approval_record.at；report.create_time/seal_time；结算/发票/到账 create_time），
  sys_audit_log 留痕 `{field,old,new,reason}`
- 系统设置（sys_config，Secret AES-GCM 加密落库、接口只回 xxxSet 布尔）：
  - `GET /admin/settings`（admin:setting:list）→ `{siteName,logoUrl,wecom:{enabled,corpId,agentId,secretSet,callbackUrl},messaging:{...}}`
  - `PUT /admin/settings`（admin:setting:edit）`{siteName?,wecom?:{...},messaging?:{...}}`（各密文字段空=不修改）
  - 消息通道 messaging：`email:{host,port(0=默认),security:ssl|starttls|none,username,passwordSet,sender}` +
    `sms:{provider:aliyun|tencent|huawei|custom_http, aliyun/tencent/huawei:{各厂商字段+密钥Set},
    customHttp:{url,paramTemplate(phone/code 占位),authHeaderSet}}`；
    发送能力：SMTP 与 custom_http 为真实通道；三家厂商短信已落库预设字段、网关签名未联调（遗留项）
  - `POST /admin/settings/messaging/test`（admin:setting:edit）`{channel:"sms"|"email",target}` →
    `{sent,mode:"real"|"debug"}`（非生产调试通道回显 debugCode；审计 settings_messaging_test）
  - `POST /admin/settings/logo`（admin:setting:edit，multipart file；限 png/jpg/svg/webp ≤2MB）→ `{logoUrl}`
- 免登录公共接口：`GET /public/branding` → `{siteName,logoUrl,wecomEnabled}` · `GET /public/logo` → Logo 文件流
- 站内通知（登录即可，读自己的）：`GET /admin/notifies?status=unread&page&size`
  `GET /admin/notifies/unread-count` → `{count}` · `POST /admin/notifies/{id}/read` · `POST /admin/notifies/read-all`

## CRM 往来单位 /crm（客户/供应商统一档案，partner_type ∈ customer/supplier/both）
- `GET /crm/customers` 分页：字段
  `{id,customerNo,name,partnerType,code,customerType,taxNo,grade,status,address,country,province,city,bankName,bankAccount,payOrg,licenseFileId,supplyCategory,supplierRating,remark,createTime,updateTime}`
  检索：`q`（name/customerNo/taxNo）、`status`（enabled/disabled/all）、`filters[partner_type]`（customer/supplier/both）
- `POST /crm/customers` · `PUT /crm/customers/{id}` · `DELETE /crm/customers/{id}`
  （partner_type 默认 customer；供应商附加 supplyCategory（字典 supply_category）/supplierRating（复用 customer_grade））
- `POST /crm/customers/export` · `GET /crm/customers/template` · `POST /crm/customers/import`（multipart file；导出/模板含 partnerType 列）
- `GET /crm/customers/options?q=&limit=20&partner_type=` → `[{id,label,sub,partnerType,payOrg,taxNo,...}]`
  （模糊选择器专用；partner_type=supplier 仅供应商含 both，=customer 仅客户含 both，缺省不过滤）
- `GET /crm/customers/counts`（沿用 crm:customer:list）→ `{enabled,disabled,all}`（状态页签计数）
- `GET /crm/customers/{id}` 详情：summary 含 `{contractCount,contractTotal,taskCount,settledTotal,paidTotal,purchaseContractCount,purchaseTotal}`（后两项为供应商指标）
- 联系人（表 crm_partner_contact，读 `crm:customer:list`、写 `crm:customer:edit`）：
  `GET/POST /crm/customers/{id}/contacts` · `PUT/DELETE /crm/contacts/{cid}`
  字段 `{id,name,position,phone,email,isPrimary,remark}`；isPrimary 每单位唯一（置主同事务清其他），列表按 isPrimary desc, id asc
- 附件（表 crm_partner_attachment，读 `crm:customer:list`、写 `crm:customer:edit`）：
  `GET /crm/customers/{id}/attachments?category=` · `POST /crm/customers/{id}/attachments`（multipart file+category+remark）
  · `GET /crm/attachments/{aid}` 下载 · `DELETE /crm/attachments/{aid}`（逻辑删+磁盘移除）
  category ∈ 字典 partner_attachment_category（license 营业执照/qualification 资质证明/contract 合同文件/other 其他）；
  扩展名白名单沿用 upload_ext_set 且校验魔数（pdf/jpg/png/zip/docx/xlsx/doc/xls），存 uploads/partner/
- `GET /crm/customers/{id}/procurement`（权限 `procurement:contract:list`）
  → `{contracts:[{id,contractNo,name,amount,status,signDate,createTime}],requests:[{id,requestNo,title,status,createTime}]}`（requests 为合同关联申请去重）
- 门户账号：详情抽屉"门户账号"tab 用 `GET /procurement/partners?filters[customer_id]={id}`（权限 `procurement:partner:list`）；
  列表页"合作方账号"视图（`?tab=accounts`）承载全部账号审核管理，沿用 `procurement:partner:list/review`
- 审计：partner_contact_create/update/delete、partner_attachment_upload/delete（module=crm）
- 权限码：`crm:customer:list/create/edit/delete/list:export/import`

## 采购 /procurement（一期：申请→合同会签→出入库；设计见 docs/procurement-design.md）
- 申请/合同状态机同销售合同：`draft → approving → approved / rejected / voided`，审批中禁编辑；
  编号提交审批时发放（PR…/CG…）；出入库登记即发放（RK…/CK…），`registered → confirmed`（确认后只读）。
- `GET /procurement/requests` 分页（q=标题/编号/任务号/任务名；filters[task_id,purchase_method]；sort 白名单）
  · `GET /procurement/requests/counts` → `{draft,approving,approved,rejected,voided,all}`
  · `GET /procurement/requests/{id}` 详情（items + 审批 timeline + contractId/contractNo/contractStatus 互跳字段）
- `POST /procurement/requests` · `PUT /procurement/requests/{id}`（仅 draft/rejected，乐观锁 version）
  · `DELETE`（仅 draft）· `POST /{id}/submit`（发 PR 编号 + 启动 purchase_request_approve 两级顺序审批）
  · `POST /{id}/void` · `POST /requests/export`
- `POST /procurement/requests/{id}/generate-contract` `{supplierId,name?,amount?,payCycle?,delivery?,remark?}`
  （仅 approved 申请，否则 95003；供应商须为启用的 supplier/both 往来单位，否则 95002；幂等：一申请一合同）
- `GET /procurement/contracts` · counts · `GET /{id}`（含 timeline + stockOrders 互跳）
  · POST/PUT/DELETE · `POST /{id}/submit`（发 CG 编号 + purchase_contract_approve：节点1 会签 sign_mode=and
  （manager1+leader1 全员通过）→ 节点2 分管领导终审）· `POST /{id}/void` · `POST /contracts/export`
- `GET /procurement/stock-orders` 分页（q=单号/合同号/合同名；filters[order_type,contract_id,warehouse,source_type]；
  source_type：purchase=采购（含历史空来源）/sample=样品；样品单行补挂 sampleNo/sampleName/vin/taskId/taskNo/taskName）
  · counts → `{registered,confirmed,all}` · `GET /{id}`（含 sourceType/sourceId 及样品来源信息）
  · `POST`（items 至少一行；contractId 仅可挂已通过的采购合同，否则 95001）
  · `PUT /{id}`（仅 registered，orderType 不可改）
  · `POST /{id}/confirm`（行锁，确认后只读；source_type=sample 时同事务回写样品 in_stock + 写 task_sample_flow 流水，
    样品已删/已在目标状态则 10002/60001 整体回滚）
  · `DELETE`（仅 registered）· `POST /stock-orders/export`（含来源/来源单据列）
- 权限码：`procurement:request:list/create/edit/submit/delete/list:export`、
  `procurement:contract:list/create/edit/submit/delete/list:export`、
  `procurement:stock:list/create/edit/confirm/delete/list:export`
- 错误码：95001 当前采购单据状态不允许该操作 / 95002 供应商不存在或非供应商往来单位 / 95003 采购申请未审批通过
- 编号规则：purchase_request=PR、purchase_contract=CG、stock_in=RK、stock_out=CK（yyyymmdd+4 位，按日重置）
- 字典：purchase_method（询价/单一来源/竞争性谈判/公开招标）、supply_category、warehouse
- 种子流程 USER 节点按用户 id 引用：一键清空重建用户后由 tests/test_zz_purge.py 收尾按 approver_name 同位映射修复
  （CSV 会签节点同规则）
- 菜单：业务系统 → 采购管理（Procurement）→ 采购申请/采购合同/出入库；存量库归位靠
  `backend/scripts/migrate_nav_procurement.py`（幂等，沿用批次E 模式）

### 二期：招投标 + 合作方门户（/procurement/tenders、/procurement/partners、/portal）
- 招标状态机（简化）：`draft → published → evaluating → awarding → awarded`，另 `terminated`；
  报名/投标窗口由 `reg_deadline`/`bid_deadline` 控制（发布时仅校验 reg≤bid，门户侧强制截止 96002）；
  `start-evaluation` 为内部动作，进入评标即关闭门户报名/投标。
- `GET /procurement/tenders` 分页（q=名称/编号/申请号；filters[status,tender_method]；sort 白名单）
  · counts → `{draft,published,evaluating,awarding,awarded,terminated,all}`
  · `GET /{id}` 详情（registrations + bids(evals/avgScore/isWinner) + 定标 timeline + contractId/No/Status）
- `POST /procurement/tenders` · `PUT /{id}`（仅 draft，乐观锁）· `DELETE`（仅 draft）
  · `POST /{id}/publish`（发 ZB 编号）· `POST /{id}/terminate`（awarding 需先撤回审批）
  · `POST /{id}/start-evaluation` · `POST /{id}/registrations/{rid}/review` `{approve,comment?}`
  · `POST /{id}/evals` `{bidId,score(0-100),comment?,recommend?}`（仅 evaluating，一评标人一投标一条，重复覆盖）
  · `POST /{id}/award` `{bidId}`（→ awarding + tender_award_approve 单级审批；通过自动 awarded 落 winner_*，驳回/撤回回 evaluating）
  · `POST /{id}/generate-contract`（awarded → 采购合同草稿：供应商=中标账号绑定往来单位、金额=中标价；幂等一项目一合同；未绑定往来单位 95002）
  · `POST /tenders/export` · 附件下载 `GET /tenders/registrations/{rid}/attachment`、`GET /tenders/bids/{bid}/proposal`
- 合作方账号审核与 CRUD：`GET /procurement/partners`（q=账号/公司/联系人/电话；filters[status,customer_id]——customer_id
  供往来单位详情"门户账号"tab 查绑定账号；返回含 customerName）· counts
  · `POST /partners/{pid}/review` `{approve,comment?,customerId?}`（通过可绑供应商往来单位；对 enabled 账号 approve=false 即停用）
  · `POST /partners`（201，管理侧新建：username/password(≥8)/companyName/contactName/phone/email/customerId?，直接 enabled，无需审核；重名 96005，绑非供应商 95002）
  · `PUT /partners/{pid}`（编辑资料；payload 显式带 customerId 时改绑(int)/解绑(null)，缺省不动；解绑后不能投标/生成合同）
  · `POST /partners/{pid}/password`（重置密码：缺省服务端生成 12 位随机密码，仅本次响应返回一次；也可指定 8-64 位）
  · `DELETE /partners/{pid}`（软删；已有报名/投标记录 → 96007 只能停用；删除后用户名加 `#del{id}` 后缀释放唯一索引）
  · 前端入口已并入往来单位（/crm/customers 的"合作方账号"视图 + 详情抽屉"门户账号"tab），
    采购管理菜单 PartnerAccounts 隐藏保留（visible=0，权限载体），旧深链 /procurement/partners → /crm/customers?tab=accounts
- 权限码：`procurement:tender:list/create/edit/delete/publish/terminate/review/evaluate/award/list:export`、
  `procurement:partner:list/create/edit/review/delete`
- 编号规则：tender=ZB（发布时发放）；字典：tender_method（public 公开招标 / invite 邀请招标）

### 合作方门户 /portal（独立认证，与内部账号体系完全隔离）
- 账号：partner_user 独立表（注册即 pending，内部审核 enabled 后方可登录；rejected/disabled 不可登录）。
- 认证：`POST /portal/auth/register` · `POST /portal/auth/login`（登录锁定同内部：5 次/15 分钟）
  · `GET /portal/auth/me` · `POST /portal/auth/logout`；
  token 为独立 JWT（`typ=portal_access`、`aud=portal`，12h 无刷新）：内部 `decode_token` 不校验 audience，
  带 aud 的门户 token 直接 InvalidAudience → 401；门户 `decode_portal_token` 强制 audience=portal，内部 token（无 aud）→ 401，双向隔离。
- 白名单能力（仅公告口径 + 本人数据，任何内部单据/他人投标不暴露）：
  `GET /portal/tenders`（仅 published/evaluating/awarding/awarded，附 myRegistrationStatus/myBidId/isWinner）
  · `GET /portal/tenders/{id}`（含 myRegistration/myBid；awarded 时公开 winnerName/winnerAmount 中标公示）
  —— 以上两个公告端点**免登录公开**（可选 token：匿名时 my* 字段为空），路由守卫仅 /portal/my 强制登录；
  · `POST /portal/tenders/{id}/register`（multipart：contact_name/contact_phone/file；行锁+报名截止+防重复）
  · `GET /portal/registrations` · `POST /portal/tenders/{id}/bid`（multipart：price/comment/file；报名审核通过前置 96003，截止 96002，同项目重复提交即改标覆盖）
  · `GET /portal/bids`（列表含 tenderStatus/regDeadline/bidDeadline 供工作台倒计时）· 本人附件下载 `GET /portal/registrations/{rid}/attachment`、`GET /portal/bids/{bid}/proposal`
- 门户附件落 `uploads/portal/`（扩展名白名单 + 50MB 上限同内部）；purge 清单含 pur_tender* / partner_user / uploads/portal。
- 前端入口 `/portal`（PortalRegister/PortalLayout/PortalTenderList/PortalTenderDetailPanel/PortalMy），
  独立 axios 实例（token key `bs.portal_token`，401 回 `/login?tab=partner&redirect=...`，无 refresh），路由守卫对 /portal 前缀走独立分支。
  合作方登录已内嵌主登录页 `/login` 的分段切换（员工/合作方，无图形码、无 MFA），旧路由 `/portal/login` → 重定向 `/login?tab=partner`（保留 redirect），
  `/portal/tenders/:id` → 重定向 `/portal/tenders?id=N`；门户"内部员工入口"与内部登录页"合作方登录"分段互跳。
  PortalLayout 接品牌设置（站点名/Logo）+ 语言切换；招标公告为单页左右布局（左清单支持本地检索/状态筛选，右详情面板，`?id=` 与地址栏同步，
  移动端单栏清单→详情带返回），公告匿名可看，报名/投标区匿名时显示登录/注册引导卡；
  内部招标详情抽屉提供"对外公告链接"复制（`/portal/tenders?id=N`）。
- 错误码（96xxx）：96001 招标状态不允许该操作 / 96002 已超过截止时间 / 96003 报名未通过审核不能投标 /
  96004 账号待审核或已停用 / 96005 账号已存在 / 96006 项目尚未定标 / 96007 账号已有报名/投标记录不能删除

## 合同 /contract
- 状态机：`draft 草稿 → approving 审批中 → approved 已通过 / rejected 已驳回（可改后重新提交）/ voided 已作废`；审批中禁止编辑。
- `GET /contract/contracts` 分页：
  `{id,contractNo,name,customerId,customerName,contractType,subjectType,amount,startDate,endDate,payCycle,delivery,sealType,handlerId,handlerName,frameworkNo,paymentOrg,remark,status,flowInstanceId,attachments:[{id,fileName,size}],createTime,updateTime}`
- `POST /contract/contracts` · `PUT /contract/contracts/{id}`（仅 draft/rejected）· `DELETE`（仅 draft → 逻辑删）
  校验：amount 必须 >0 且 ≤ 999999999999.99（Numeric(14,2) 口径）；endDate 不得早于 startDate（违反 422/10001）
- `POST /contract/contracts/{id}/submit` → 启动审批（创建 approval instance，状态→approving）
- `POST /contract/contracts/{id}/void` → 作废（审批中需先撤回；已作废 50001）
- `GET /contract/contracts/{id}` 详情（含附件、审批时间线可选）
- `POST /contract/contracts/{id}/attachments`（multipart file）· `GET /contract/attachments/{fileId}`（下载流）
- `DELETE /contract/attachments/{fileId}`（contract:edit；仅 draft/rejected 合同可删，审批中 50002；逻辑删 + 审计）
- `POST /contract/contracts/export` · `GET /contract/contracts/options`（仅 approved，建任务时用）
- `GET /contract/contracts/framework-options?customer_id=&q=&limit=` → `[{id,label,sub,customerId,customerName}]`
  （仅 approved 且 contract_type=framework 的合同；id=框架合同号，编辑合同"框架合同号"下拉用，可按客户过滤）
- `GET /contract/contracts/counts`（沿用 contract:list）→ `{draft,approving,approved,rejected,voided,all}`（状态页签计数）
- 权限码：`contract:list/create/edit/submit/delete/list:export`

## 审批中心 /approval（自研引擎）
- `GET /approval/tasks?tab=todo|done|initiated&page&size&q=` →
  `{items:[{id,instanceId,bizType,bizId,title,status,nodeName,comment,initiatorName,assigneeName,createTime,actedAt}],...}`
  - todo=我待办(status=pending & assignee=me)；done=我已办；initiated=我发起的实例
  - `q` 按单标题模糊检索（各 tab 均生效）
- `GET /approval/tasks/counts` → `{todo,done,initiated,cc}`（页签计数，登录可用）
- `GET /approval/tasks/export?tab=todo|done|initiated&q=`（xlsx 流，与列表同为登录可用）
- `GET /approval/cc?page&size&unread=&q=`（抄送我的；`q` 按标题模糊检索）
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

## OA /oa
- `GET /oa/instances/my?status=&page&size&q=`（oa:my；`q` 按单号/表单名模糊检索）·
  `GET /oa/instances/my/export?status=&q=`（xlsx 流，沿用 oa:my）
- `GET /oa/instances/my/counts`（沿用 oa:my）→ `{running,approved,rejected,withdrawn,terminated,all}`
- `GET /oa/related?tab=todo|done|cc&page&size&q=`（复用通用审批端点，biz_type=oa；`q` 按标题模糊检索）
- `GET /oa/related/counts` → `{todo,done,cc}`（页签计数）
- 管理端单据检索：`GET /oa/admin/instances?status=&keyword=&stuckDays=&page&size`（oa:admin:handle）·
  `GET /oa/admin/instances/counts` → `{running,approved,rejected,withdrawn,terminated,all}`
- 资源控件检索（oa:apply，OA 填写人只读）：
  - `GET /oa/resources/meta` → `[{type,label,fields:[{key,label}]}]`
    （type ∈ customer/contract/task/report/dept/user/oa_instance；fields 为可带出字段清单，设计器配 mappings 用）
  - `GET /oa/resources/{rtype}?q&page&size` → `{items:[{id,label,sub,fields:{...}}],total}`
    合同只列 status=approved；oa_instance 只列本人可见（申请人/有待办/已办/被抄送）；dept/user 只列 enabled
- 表单字段 schema 扩展（全部可选，存量兼容；提交时服务端同语义校验）：
  - 条件逻辑：`showWhen/requiredWhen/readonlyWhen` = `{logic:"and|or",rules:[{field,op,value}]}`，
    op ∈ eq/ne/gt/gte/lt/lte/contains/empty/not_empty；showWhen 不满足 → 隐藏且服务端跳过校验
  - 控件联动：`cascade:{parent,map:{父值:[可选选项]}}`（父值不在 map 回退全选项）；
    `optionsSource:"manual|dict"` + `dictType`（字典源不做选项成员校验）
  - 资源控件：`type:"resource"` + `resource` + `mappings:[{from,to}]`，值形状 `{id:int,name:str}`，选中后按 mappings 带出
  - 布局控件 `divider`/`text_block`（key 允许为空、不占数据位）；`span`(12/24)、`description`、`defaultValue`
  - schema_json 读写统一 camelCase（历史 snake_case 存量读取时归一化）

## 任务 /task
- 状态机（2026-10 精简）：`draft 创建待提交 → in_progress 分配执行中 → finished 已完成 → settled 已结算`，
  流程态 `approving 立项审批中` / `rejected 已驳回`，终态 `stopped 已停止`
  （原 assigning/assigned 并入 in_progress、closed 并入 finished，迁移 e5f6a7b8c9d0 改写存量；
  finished → settled 由财务模块创建结算单触发，见「财务」章节；
  财务进度 `settleStatus`（invoiced/paid）以徽标形式随列表/详情返回，不占主状态）
- `GET /task/tasks` 分页（宽表冗余）：
  `{id,taskNo,taskName,taskType,taskTypeLabel,contractId,contractNo,customerId,customerName,
    bizBlock,bizBlockLabel,deptId,deptName,ownerId,ownerName,content,partySystem,receiver,receiverUnit,
    planFinishDate,status,settleStatus,reportCount,sampleCount,createTime,updateTime}`
  检索：`q`（taskNo/taskName/customerName）、`status` 页签
- `GET /task/tasks/counts` → `{draft:1,in_progress:0,...}`（状态页签计数）
- `POST /task/tasks` `{taskName,taskType,contractId,content,receiver,receiverUnit,bizBlock,deptId,planFinishDate,partySystem,items:[],samples:[]}`
  → 自动 `taskNo`；仅允许选择 `approved` 合同（否则 60002）
- `PUT /task/tasks/{id}`（仅 draft/rejected）· `DELETE`（仅 draft）
- 状态动作：`POST /task/tasks/{id}/submit|finish|stop`（非法流转 60001；submit 触发站内通知；
  finish 时存在 needReport=1 且未签章（reportStatus≠sealed）的条目 → 60003，消息列出未完成条目）
  - 合法流转表：`draft/rejected --submit--> approving`（绑定立项定义）或 `in_progress`（直通）；
    `approving` 审批通过 `--> in_progress`；`in_progress --finish--> finished`；
    `draft/approving/rejected/in_progress/finished --stop--> stopped`（终态）
  - 前端按钮：draft/rejected 显示「提交分配」(submit)；in_progress 显示「完成」(finish)；
    非终态显示「停止」(stop)
- `GET /task/tasks/{id}` → 详情含 `items[]` `samples[]` `logs[]`
  （`logs` 为该任务全部样品的 `task_sample_flow` 流水，按时间倒序：
  `[{id,sampleNo,action:"in"|"out",operatorName,createTime,remark}]`）
- 子条目 `task_item`：`{id,itemCode,name,std,dept,inspector,qty,settleType,needReport,reportNo,reportStatus}`
  嵌套路由 `POST /task/tasks/{id}/items` · `PUT /task/items/{itemId}` · `DELETE /task/items/{itemId}`
  `needReport=true` → 自动分配 `reportNo`（BG 规则）
- 样品 `task_sample`：`{id,sampleNo,name,model,vin,vehicleType,sampleDate,inStock:"in"|"out",pendingOrder}`
  `POST /task/tasks/{id}/samples`（sampleNo 自动 `任务号-01`）
  · `PUT /task/samples/{sid}`（存在未确认出入库单时禁止改 in_stock，60001）
  · `DELETE`（存在未确认出入库单时禁止，60001）
  · `POST /task/samples/{sid}/in` `/out` —— 统一走采购出入库流程：登记生成 StockOrder
    （order_type=in/out、source_type=sample、source_id=样品 id，明细带样品名/型号/VIN/编号，RK/CK 编号登记即发，
    审计 stock_order_create），返回样品带 `pendingOrder:{id,orderNo,orderType,status}`；样品 `in_stock`
    在采购侧 `POST /procurement/stock-orders/{oid}/confirm` 确认后才翻转并写 `task_sample_flow` 流水；
    有未确认单时重复登记 60001
  · `POST /task/samples/{sid}/stock-cancel` —— 取消未确认登记（单据逻辑删，样品状态不变）
  · `pendingOrder` 由查询派生（source_type=sample + status=registered），不落 task_sample 字段；
    详情 `samples[]` 与样品列表/导出行均带
- 跨任务样品列表（样品管理页，批次A）：
  `GET /task/samples` 分页（`task:sample:list`），行 = 样品字段 + `{taskId,taskNo,taskName,customerName,createTime}`；
  检索：`q`（样品编号/名称/VIN/任务名/客户名）、`status=in|out` 页签、`sort=create_time|sample_date|id:asc|desc`
- `GET /task/samples/counts`（`task:sample:list`）→ `{in,out,all}`
- `POST /task/samples/export`（`task:sample:list:export`，xlsx 中文表头，同列表过滤条件）
- `POST /task/tasks/export`
- 权限码：`task:list/create/edit/assign/submit/list:export`（delete/其他状态动作用 `task:edit`）、
  `task:sample:list`、`task:sample:list:export`（种子挂 super/biz_user）

## 财务 /finance
- 结算单状态机：`pending 待开票 → invoicing 开票审批中 → invoiced 已开票 → paid 已到账`；
  审批驳回/撤回 → 回 `pending`。
- 客户确认（开票前置）：结算审批通过（pending）后需"发送客户确认"（站内通知 + 留痕，confirmStatus→pending），
  由内部人员代客标记"已确认/有异议"（confirmStatus→confirmed/objected，confirmBy/confirmTime/confirmNote 留痕）；
  confirmStatus 仅 confirmed 才允许申请开票（否则 80001）。
- 主链路：任务 finished → 建任务人创建结算单（任务 → settled，一任务一单）→ 发送客户确认 → 客户确认
  → 申请开票（审批流 invoice_apply）→ 审批通过生成发票行 → 财务登记发票信息 → 到账登记（累计到账 ≥ 结算金额 → paid）。
- `GET /finance/settlements` 分页：
  `{id,settlementNo,taskId,taskNo,customerName,contractNo,amount,invoiceableAmount,status,statusText,remark,
    approvalInstanceId,confirmStatus,confirmBy,confirmTime,confirmNote,createBy,createTime}`
  检索：`q`（settlementNo/taskNo/customerName/contractNo）、`status` 页签、`filters[confirm_status]`
- `GET /finance/settlements/counts`（沿用 finance:settlement:list）→
  `{approving,pending,invoicing,invoiced,paid,rejected,all}`（状态页签计数）
- `GET /finance/settlements/task-options?q=` → `[{value,label,sub}]`
  （仅 `finished` 且无结算单的任务；value=taskId，label=任务编号，sub=客户名称/合同号）
- `POST /finance/settlements` `{taskId,amount,invoiceableAmount?,remark?}` → 201；
  仅任务创建人（或超管）可对 finished 任务创建；`settlementNo` 走 HK 编号规则；成功后任务 finished → settled。
  错误：80001 任务状态不允许结算 / 80002 该任务已有结算单 / 80003 非任务创建人
- `GET /finance/settlements/{id}` → 详情 + `invoices[]` + `payments[]` + `paidAmount` + 开票审批 `timeline`
  + `confirmRecords[]`（确认留痕：`{id,action:send|confirm|object,operatorName,receiverName,note,createTime}`）
- `POST /finance/settlements/{id}/send-confirm` `{receiverId,note?}`（finance:settlement:confirm）→
  站内通知收件人 + 留痕 + confirmStatus→pending；仅 status=pending 可发送
- `POST /finance/settlements/{id}/confirm` `{action:confirm|object,note?}`（finance:settlement:confirm）→
  代客标记 confirmed/objected（confirmBy/confirmTime/confirmNote + 留痕）；需已发送（pending/objected）
- `POST /finance/settlements/{id}/apply-invoice` `{comment?}` → 启动开票审批
  （bizType=invoice，definition=invoice_apply），结算单 → invoicing；审批通过 → invoiced 并生成发票行；
  **前置：confirmStatus=confirmed，否则 80001**
- `PUT /finance/invoices/{id}` `{invoiceNo,amount,invoiceDate?}` → 财务登记发票信息
- `GET /finance/invoices` 分页：
  `{id,invoiceNo,settlementId,settlementNo,taskNo,customerName,amount,invoiceDate,status,statusText,createBy,createTime}`
  （settlementNo/taskNo/customerName 关联 fin_settlement 带出；status ∈ `approving 审批中 / issued 已开票`）
  检索：`q`（invoiceNo/settlementNo/customerName）、`status` 页签
- `GET /finance/invoices/counts`（沿用 finance:invoice:list）→ `{approving,issued,all}`（状态页签计数）
- `GET /finance/payments` 分页：
  `{id,paymentNo,settlementId,settlementNo,payType,payerName,payerAccount,amount,bank,paidAt,remark,createBy,createTime}`
- `POST /finance/payments` `{settlementId,payType,payerName,payerAccount?,amount,bank?,paidAt,remark?}` → 201；
  仅 invoiced 状态结算单可登记；`paymentNo` 走 DZ 编号规则；累计到账 ≥ 结算金额 → 结算单 paid
- `GET /finance/settlements/export` · `GET /finance/invoices/export` · `GET /finance/payments/export`
  （同检索参数，返回 xlsx 流）
- 权限码：`finance:settlement:list/create/export/confirm`、`finance:invoice:apply/edit/list/export`、
  `finance:payment:list/create/export`
- 菜单：财务管理 → 结算信息（FinanceSettlements）/ 开票申请（FinanceInvoices，`/finance/invoices`）/
  到账信息（FinancePayments）

## 导航结构（批次A 定形 / 批次E 归一）
- 顶层：工作台（Workbench）→ 业务系统（BizSystem 目录）→ OA系统（OaSystem）→ 系统管理（System）；
  流程中心（ApprovalCenter）visible=0 隐藏保留（approval:view 权限载体），/approval 走前端静态路由深链。
  前端侧栏将四个顶级目录渲染为「区」（工作台钉顶部，各区带标题，无权限的区整区隐藏）。
- 业务系统子级顺序：往来单位（Customers，`/crm/customers`，页面级视图：往来单位/合作方账号）/ 合同管理 / 任务管理 / 报告管理 /
  样品管理（Samples，`/task/samples`，componentKey `task/SampleList`）/ 采购管理（Procurement，子级
  采购申请→采购合同→出入库→招标管理；合作方账号 PartnerAccounts visible=0 隐藏保留作权限载体）/
  财务管理（子级 开票申请→结算信息→到账信息 不变）。
- 存量库结构归并靠 `backend/scripts/migrate_nav_batch_e.py`（幂等：name 主键 + path 兜底，
  去重同名目录、归位异名同 path 残留、parent_id/sort 归一）；种子只保证新库直接产出目标结构
  （_seed_menus 不回写 parent_id/sort，保留管理员结构调整）。

## 报告 /report
- 状态机：`uploaded 已上传待审 → approving 审批中 → approved 批准通过 → sealed 签章完成`；
  审批驳回 → `rejected 已驳回`（可重新提交），撤回 → 回 `uploaded`。
- 主链路：条目 needReport=1 自动分配 reportNo（BG 规则）→ 上传报告 → 签批（审批流 report_sign）
  → 批准自动转 PDF → 签章（seal_by/seal_time 留痕）→ sealed；**存在未签章报告条目的任务 finish 拒绝（60003）**。
- `GET /report/reports` 分页：
  `{id,reportNo,taskId,taskNo,taskItemId,itemName,contractId,contractNo,customerId,customerName,fileName,status,statusText,pdfReady,
    sealBy,sealTime,remark,approvalInstanceId,createBy,createTime}`
  检索：`q`（reportNo/fileName/任务号/任务名/条目名/客户名）、`status` 页签
- `GET /report/reports/counts`（沿用 report:list）→ `{uploaded,approving,approved,rejected,sealed,all}`（状态页签计数）
- `GET /report/reports/item-options?q=` → `[{value,label,sub}]`
  （仅 needReport=1 且尚无未删除报告的条目；value=taskItemId，label=报告编号，sub=任务号/条目名）
- `POST /report/reports`（multipart：`item_id` + `file`；限 pdf/doc/docx ≤ upload_max_mb）→ 201；
  一条目仅一条未删除报告（重复 61001）；创建即 uploaded 并同步 `task_item.reportStatus`
- `POST /report/reports/{id}/submit` `{comment?}`（report:submit）→ 启动签批
  （bizType=report，definition=report_sign），→ approving；仅 uploaded/rejected 可提交（否则 61002）
- 审批事件：通过 → approved + 自动转 PDF（探测 soffice/LibreOffice；未安装或失败降级为
  pdfFileId=原件并在 remark 标注，不阻断流程）；驳回 → rejected；撤回 → uploaded
- `POST /report/reports/{id}/seal` `{comment?}`（report:seal；仅 approved）→ 签章占位适配器
  （CA 未定前：seal_by/seal_time 留痕 + 审计；pypdf 可用时末页叠加文字水印），→ sealed
- `GET /report/reports/{id}` → 详情 + 签批 `timeline`
- `GET /report/reports/{id}/download?pdf=0|1`（原件 / 转换后 PDF 流）
- `GET /report/reports/export`（同检索参数，返回 xlsx 流）
- 权限码：`report:list/create/submit/seal/export`
- 错误码：60003 存在未完成签章的报告，任务不能结束 / 61001 该条目已存在报告 / 61002 当前报告状态不允许该操作
- 菜单：报告管理（Reports，`/report/reports`，componentKey `report/ReportList`）

## 前端组件键（componentKey → 懒加载组件）
```
workbench/Dashboard  crm/CustomerList  contract/ContractList  task/TaskList
finance/SettlementList  finance/InvoiceList  finance/PaymentList
procurement/PurchaseRequestList  procurement/PurchaseContractList  procurement/StockOrderList
procurement/TenderList  procurement/PartnerAccountList
report/ReportList
approval/TodoList
admin/UserList  admin/RoleList  admin/MenuList  admin/DictList
admin/NumberRuleList  admin/AuditLogList  admin/DeptList  admin/FlowDefList
```

## 字典（sys_dict）
`customer_type / customer_grade / contract_type / task_type / biz_block / pay_cycle / delivery_way / pay_type / purchase_method / supply_category / warehouse / tender_method`
读取：`GET /admin/dict/items?type={code}`（仅 enabled，按 sort 排序）

## 种子账号
| 用户名 | 密码 | 角色 |
|---|---|---|
| admin | Admin@123456 | 超级管理员 |
| manager1 | Test@123456 | 部门负责人（审批人演示） |
| leader1 | Test@123456 | 分管领导（审批人演示） |
