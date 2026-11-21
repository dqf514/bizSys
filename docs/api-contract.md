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
0 成功 · 1xxxx 通用 · 2xxxx 鉴权 · 3xxxx 系统管理 · 4xxxx CRM · 5xxxx 合同 · 6xxxx 任务 · 7xxxx 审批 · 8xxxx 财务 · 9xxxx 集成占位 · 95xxx 采购 · 96xxx 招投标/门户 · 97xxx 资产与库存 · 98xxx 访客与安全 · 99xxx 生产排程/项目 · 63xxx 人事行政（HR） · 64xxx 销售（报价） · 65xxx AI 中心

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
  - `GET /admin/settings`（admin:setting:list）→ `{siteName,logoUrl,wecom:{enabled,corpId,agentId,secretSet,callbackUrl},messaging:{...},ai:{enabled,baseUrl,apiKeySet,model,visionModel,timeout}}`
  - `PUT /admin/settings`（admin:setting:edit）`{siteName?,wecom?:{...},messaging?:{...},ai?:{enabled,baseUrl,apiKey?,model,visionModel?,timeout}}`（各密文字段空=不修改）
  - 消息通道 messaging：`email:{host,port(0=默认),security:ssl|starttls|none,username,passwordSet,sender}` +
    `sms:{provider:aliyun|tencent|huawei|custom_http, aliyun/tencent/huawei:{各厂商字段+密钥Set},
    customHttp:{url,paramTemplate(phone/code 占位),authHeaderSet}}`；
    发送能力：SMTP 与 custom_http 为真实通道；三家厂商短信已落库预设字段、网关签名未联调（遗留项）
  - `POST /admin/settings/messaging/test`（admin:setting:edit）`{channel:"sms"|"email",target}` →
    `{sent,mode:"real"|"debug"}`（非生产调试通道回显 debugCode；审计 settings_messaging_test）
  - `POST /admin/settings/logo`（admin:setting:edit，multipart file；限 png/jpg/svg/webp ≤2MB）→ `{logoUrl}`
- 免登录公共接口：`GET /public/branding` → `{siteName,logoUrl,wecomEnabled}` · `GET /public/logo` → Logo 文件流
- 站内通知 / 消息中心（登录即可，读自己的）：
  - `GET /admin/notifies?page&size&q&filters[biz_type]&status=unread&sort=create_time:desc`
    → `{items:[{id,title,content,bizType,bizId,link,readFlag,createTime}],total,page,size}`
    （`q` 匹配标题/正文；`filters[biz_type]` 业务分类；`status=unread` 只看未读；默认按创建时间倒序）
  - `GET /admin/notifies/counts` → `{all,unread,byBizType:{biz_type:条数}}`（消息中心页签计数，`all` 最左）
  - `GET /admin/notifies/unread-count` → `{count}`
  - `POST /admin/notifies/{id}/read` · `POST /admin/notifies/read-all`

### AI 中心 /admin/ai（统一网关 + 用量监控 + 功能开关/配额；详见 docs/ai-center.md）
- 能力探测（登录即可，前端据此举入口显隐/提示）：`GET /ai/capabilities` →
  `{enabled,visionModel,features:{quote,contract_ocr,task_photo,report_summary,approval_assist,contract_risk,report_assist,nl_query,hr_prefill,oa_prefill,flow_route,flow_anomaly,tender_assist,sample_ocr,invoice_ocr,price_ref,assistant,daily_digest,knowledge}}`（feature=false 表示总开关未开/未配置/该功能被停用）
- 自然语言问数（登录即可，feature `nl_query`）：`POST /ai/nl-query` `{question,context?:{domain?,timeFrom?,timeTo?}}` →
  `{domain,domainLabel,text,rows:[{label,value}],link,timeRange:{from,to},criteria}`；
  AI 只产白名单意图（task_volume/contract_amount/receivable/settlement/work_hours/procurement/quotation），
  后端按域校验列表权限（无权限 20002）并以手写聚合模板执行（禁止自由 SQL）；
  subject=self 由后端解析为当前用户；非法域/解析失败 65004，未配置 65001，停用 65002；审计 ai_nl_query
- 用量监控（admin:ai:usage）：
  - `GET /admin/ai/usage` 分页（q=userName/error；filters[feature,status]；range[create_time]=起|止；sort 白名单
    `id,create_time,feature,status,user_name`）→ 行 `{id,userName,feature,model,promptTokens,completionTokens,totalTokens,cost:float|null,masking:off|standard|strict,durationMs,status:success|error|fallback,error,bizType,bizId,createTime}`
  - `GET /admin/ai/usage/export`（admin:ai:usage:export，xlsx 流，同检索参数；含估算成本/脱敏级别列）
  - `GET /admin/ai/stats?days=1..90` → `{days,cards:{totalCalls,successCalls,errorCalls,fallbackCalls,totalTokens,totalCost,successRate,activeUsers,avgDurationMs},trend:[{date,calls,tokens}],byFeature[],byUser[](top10),byModel[]({model,calls,tokens,cost})}`（全部 SQL 聚合；成本仅合计 cost 非空的 success 行）
- 用量设置（admin:ai:settings，存 sys_config）：
  - `GET /admin/ai/settings` → `{enabled,features:{...},quota:{userDailyCalls,userDailyTokens,globalDailyTokens},masking:off|standard|strict,modelPrices:[{model,input,output}]}`
  - `PUT /admin/ai/settings` `{features?,quota?,masking?,modelPrices?}`（quota 0=不限；masking 语义见 docs/ai-center.md §4，
    个人信息类 feature 强制 standard 起步；modelPrices 为每千 token 输入/输出单价，同模型重复行后者为准，
    空数组清空；审计 ai_settings_update）
- 提示词注册表（只读，admin:ai:settings）：`GET /admin/ai/prompts` →
  `[{key,feature,name,version,systemPreview(前100字)}]`；模板集中维护在 `app/services/prompts.py`（report_assist 拆
  conclusion/proofread/completeness 三条），在线不可编辑，调整需改代码并递增 version
- 连接参数仍在系统设置 AI 卡片：`ai.enabled/ai.base_url/ai.api_key(加密)/ai.model/ai.vision_model(空=复用 model)/ai.timeout`
- 错误码（65xxx）：65001 AI 未配置或功能已停用 / 65002 功能停用 / 65003 配额超限（quota:reason）/ 65004 AI 输出解析失败
- 权限码：`admin:ai:usage` / `admin:ai:usage:export` / `admin:ai:settings` / `admin:ai:knowledge`（默认仅 super）
- AI-4（全局助手/每日摘要/知识库问答，登录即可；知识库管理 admin:ai:knowledge）：
  - `POST /ai/assistant` `{message,menus?:[{title,path}]}` → `{type:query|navigate|guide,text,path,menuName,data?,sources[],entries?,degraded?}`；
    意图白名单路由：query 复用 nl_query（再次权限校验）；navigate 的 path 须在「服务端权限菜单树 ∩ 前端候选 + 静态深链」
    交集内才返回（幻觉路径降级为 guide）；guide 走知识库检索作答；只读接口，不产生任何业务写入（审计 ai_assistant）；
    AI 未配置时降级：菜单关键词命中→导航建议，否则知识库关键词搜索
  - `GET /ai/daily-digest`（feature `daily_digest`）→ `{summary,highlights[],degraded,todos:{approvalCount,approvals[],overdueTasks[],dueSoonTasks[]}}`；
    聚合当前用户待审批（approval_task pending）+ 进行中任务（3 天内/已逾期）；AI 不可用时回退模板摘要（degraded=true）
  - `POST /ai/daily-digest/push` `{summary,highlights}` → `{channel:wecom|notify}`；企微凭据就绪且已绑定 wecom_userid 推企微，
    否则（或企微失败）落 sys_notify 站内通知（biz_type=daily_digest，链接 /workbench）；审计 ai_digest_push
  - 知识库（feature `knowledge`；表 ai_knowledge）：
    - `POST /ai/knowledge/ask` `{question}` → `{answer,sources:[{id,title,category}],entries[],degraded}`；
      关键词检索 top3（标点分词 + 长词 2-gram）→ AI 仅基于条目作答并标注来源（usedIds 与命中取交集，空则兜底全部命中）；
      AI 未配置/停用/失败 → degraded=true，返回命中条目原文摘录（降级搜索）
    - `GET /ai/knowledge/search?q=` → `{entries[]}`（纯检索）
    - 管理端：`GET/POST /admin/ai/knowledge`、`PUT/DELETE /admin/ai/knowledge/{id}`（q 关键词/分类过滤，逻辑删除）；
      附件 `POST/GET /admin/ai/knowledge/{id}/attachment`（上传限 admin:ai:knowledge，下载登录即可）
    - 预置操作手册 7 条：alembic `l1a2b3c4d5e6` 插入 + seeds 兜底（同标题幂等）

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
- `GET /procurement/price-reference?itemName=&price=`（procurement:request:list）→
  `{stats:{count,avg,min,max,latestPrice,latestAt},deviationPercent,comment}`；
  同品名历史价格聚合（申请明细预估价 + 已确认入库单成交价，各取最近 200 条，纯计算不受开关影响）；
  comment 为 AI 偏离点评（feature `price_ref` 关闭/未配置/失败时为空串）
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
  · `POST /{id}/ai-bid-screen`（procurement:tender:evaluate，feature `tender_assist`，限 evaluating/awarding/awarded）→
    `{requirements:[≤10],bids:[{bidId,companyName,extractable,results:[{requirement,verdict:comply|deviate|manual,note}]}]}`：
    投标文件文本提取（pdf/docx/txt，每份截 4000，≤10 份，提取失败 extractable=false 全项 manual）+ 公告（截 6000）；
    bidId 白名单过滤、verdict 归一、缺失投标/要求按 manual 补齐；仅辅助不落库，评分仍人工
  · `GET /{id}/bid-compare`（同权限，确定性计算非 AI、不受开关约束）→
    `{budgetAmount,rows:[{bidId,companyName,price,deviationPercent,rank,submitAt}]}`（偏离度=(报价-预算)/预算*100，无预算 null；按价升序排名）
  · `GET /{id}/bid-compare/export`（同权限，xlsx 流；审计 tender_bid_compare_export）
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

## B2 客户自助体系（/crm 自助管理 + /task 在线委托 + /portal 客户自助）

> 需求来源：CSV 5（`docs/roadmap-2026-11.md` B2）。客户账号**不并入 `sys_user`**，沿用 `partner_user` 独立账号表 + 门户 token 体系。

### 账号模型（partner_user 扩展）
- `partner_user` 新增列：`account_type`（`supplier` 供应商 / `customer` 客户）、`perm_scope`（客户账号的权限范围，逗号分隔 `entrust,staff,tender`）、
  `manager_id` / `manager_name`（归属客户经理）、`staff_limit`（可登记的外来人员名额上限）。
- 注册即 `pending`，内部审核通过才可登录；`rejected` / `disabled` 不可登录（沿用门户 96004）。
- 客户账号的门户权限范围由 `perm_scope` 收敛：未授权能力在门户侧直接 404/403。

### 内部管理端 /crm（`crm/selfservice_router.py`，权限码 `crm:account:*` / `crm:staff:*`）
- 客户自助账号：
  - `GET /crm/accounts`（`crm:account:list`）分页，`q`（账号/公司/联系人）、`status` 页签（all/pending/enabled/rejected/disabled）；
    `GET /crm/accounts/counts` → 各状态计数
  - `GET /crm/accounts/{aid}` · `POST /crm/accounts/{aid}/review`（`crm:account:review`，`{action:approve|reject, comment, customerId, customerName, managerId, managerName, permScope, staffLimit}`）
    · `POST /crm/accounts/{aid}/toggle`（`crm:account:edit`，启用/停用；重复审核 40005）
- 客户方人员备案（外来试验/支持人员）：
  - `GET /crm/partner-staffs`（`crm:staff:list`）分页，`q`（姓名/客户/电话）、`status` 页签（all/pending/approved/rejected/disabled）
    · `GET /crm/partner-staffs/counts` · `GET /crm/partner-staffs/{sid}`
  - `POST /crm/partner-staffs`（`crm:staff:create`，内部代登记）· `POST /crm/partner-staffs/{sid}/review`（`crm:staff:review`，
    `{action:approve|reject, comment, bizOwnerName, visitPerm, ndaSigned}`）· `POST /crm/partner-staffs/{sid}/toggle`（`crm:staff:edit`）
    · `POST /crm/partner-staffs/export`（`crm:staff:export`）
- 错误码（4xxxx）：40002 人员备案状态不允许该操作 / 40003 人员记录不存在 / 40004 客户账号不存在 /
  40005 客户账号状态不允许该操作 / 40006 客户账号未绑定客户主体

### 在线任务委托 /task（`task/entrust_router.py`，权限码 `task:entrust:*`）
- 状态机：`submitted 待受理 → accepted 已受理（发号 WT）→ dispatched 已生成任务 → closed 已关闭`；
  旁路 `rejected 已驳回` / `cancelled 已取消`；受理后驳回不可再受理（60010）。
- `GET /task/entrusts`（`task:entrust:list`）分页，`q`（单号/标题/客户）、`status` 页签、委托类型与来源过滤；
  `GET /task/entrusts/counts` → 各状态计数；`GET /task/entrusts/{eid}` → 详情（含明细行 items）
- `POST /task/entrusts`（`task:entrust:create`，业务经理代提交；`source=staff`）
  `POST /task/entrusts/{eid}/review`（`task:entrust:review`，`{action:accept|reject, comment, bizOwnerId, bizOwnerName, handlerId, handlerName}`）
  —— 受理时自动取号 `WT`（`app/services/numbering.py`，biz_type `entrust`）并抄送业务负责人（站内通知）
  · `POST /task/entrusts/{eid}/dispatch`（`task:entrust:dispatch`，生成任务草稿并回写 `taskId/taskNo`；返回 `{entrust:{...}, taskId, taskName}`）
  · `POST /task/entrusts/{eid}/cancel`（`task:entrust:review`）· `POST /task/entrusts/export`（`task:entrust:export`）
- 错误码（6xxxx）：60010 委托单状态不允许该操作 / 60011 委托单不存在 / 60012 关联合同无效（非本客户 / 非已审批）

### 门户客户自助 /portal（独立认证，客户账号）
- `POST /portal/auth/register` 支持 `companyType=supplier|customer`（客户注册走 `customer`）
- `GET /portal/contracts` —— 本客户**已审批**合同（仅此可下单）
- `GET /portal/entrusts` —— 本人的委托单；`POST /portal/entrusts`（提交委托）· `POST /portal/entrusts/{eid}/cancel`（撤回）
- `GET /portal/staff` —— 本人登记的外来人员；`POST /portal/staff`（登记来访人员）
- 门户侧仅暴露本人数据；内部 token 与门户 token 双向隔离（门户 token 访问内部接口一律 401）。

## B3 访客与安全体系（/visitor）

> 需求来源：CSV 6–17（`docs/roadmap-2026-11.md` B3）。独立 `visitor` 域，落库表 `visitor_zone` `visitor_visit`
> `visitor_approval` `visitor_credential` `visitor_access_log` `visitor_nda` `visitor_blacklist`
> `visitor_sample_handover` `visitor_alert`。
> **角色隔离**：访客与安全域权限**不挂业务角色**，单独设 `security_officer`（安保员）角色（种子演示账号 `security1 / Test@123456`）。

### 访客单状态机（visitor_visit）
`pending 待审批 → approved 已通过 → visiting 在访中 → left 已签离`；旁路 `rejected 已驳回` / `cancelled 已取消` / `overdue 滞留超时`。
- 审批链：`host 被访人 → dept 部门 → zone 敏感区域`。区域 `need_extra_approval=1` 时追加 `zone` 级；
  区域 `need_nda=1` 且未签 NDA **不放行**（98007）。
- 凭证核验：签入时按 `visitor_zone` 的授权范围 + 有效期判定，超窗（98005）/ 黑名单命中（98004）一律拒绝，
  **拒绝也写 `visitor_access_log` 与 `visitor_alert`**（先提交事务再抛错，审计留痕不丢）。

### 区域分级（visitor_zone，权限码 `visitor:zone:*`）
- `GET /visitor/zones`（`visitor:zone:list`）分页，`q`（编码/名称）、`status` 页签（all/enabled/disabled）
  · `GET /visitor/zones/counts` → 各状态计数
- `POST /visitor/zones`（`visitor:zone:edit`）· `PUT /visitor/zones/{zid}` · `POST /visitor/zones/{zid}/toggle`
  · `DELETE /visitor/zones/{zid}`（有历史通行记录时拒绝删除）
- 区域类型字典 `visitor_zone_type`：公共接待区 / 样车接收区 / 试验区 / 准备区 / 生产加工区 / 工具仪器间 / 数据机房。

### 访客登记与审批（权限码 `visitor:visit:*`）
- `GET /visitor/visits`（`visitor:visit:list`）分页，`q`（姓名/单位/单号/手机号）、`status` 页签、
  `filters[visitor_type|source|zone_id]`；`GET /visitor/visits/counts` → 各状态计数
- `GET /visitor/visits/stats` → `{visiting,pending,approved,todayCheckins,openAlerts}`（在访/待审批/今日签入/未处置预警）
- `GET /visitor/visits/{vid}` → 详情（含审批时间线 `approvals` 与样品交接 `handovers`）
- `POST /visitor/visits`（`visitor:visit:create`）登记来访，签入/签离前自动取号 `VT`（biz_type `visit`）
- `POST /visitor/visits/{vid}/approve`（`visitor:visit:review`，`{action:approve|reject, comment, level}`）
  —— 驳回意见必填；`POST /visitor/visits/{vid}/cancel` · `POST /visitor/visits/export`（`visitor:visit:export`）
- `POST /visitor/visits/{vid}/checkin`（`visitor:visit:checkin`，`{method, device_id, credential_no}`）
  · `POST /visitor/visits/{vid}/checkout`（同上）—— 签入成功后自动下发 `visitor_credential`。

### 通行凭证（权限码 `visitor:credential:*`）
- `GET /visitor/credentials`（`visitor:credential:list`）分页，`q`（凭证号/姓名）
- `POST /visitor/credentials/verify`（`visitor:credential:verify`，`{credential_no, zone_id, method, device_id, direction}`）
  → `{pass, reason, credentialNo, visitId}` —— 门禁/闸机/梯控核验，放行与否均写审计日志
- `POST /visitor/credentials/{cid}/revoke`（`visitor:credential:edit`）作废凭证

### 合规审计日志（权限码 `visitor:audit:*`，**只追加不可删改**）
- `GET /visitor/access-logs`（`visitor:audit:list`）分页，`q`（访客/凭证/区域/设备）、
  `filters[event_type|result|method|visit_id|zone_id]`、`range[happened_at]`
- `GET /visitor/access-logs/summary?days=7`（`visitor:audit:report`）→ `{days,since,total,denied,byDay,byEvent}`（通行应急报表）
- `POST /visitor/access-logs/export`（`visitor:audit:export`）
- **只追加保证**：`visitor_access_log` 不含 `deleted` / `version` / `update_*` 列（`AppendOnlyModel`），
  API **不提供**任何 PUT/PATCH/DELETE，保留期 ≥180 天（`access-logs/summary` 的 `days` 上限 180）。

### 访客预警（权限码 `visitor:alert:*`）
- `GET /visitor/alerts`（`visitor:alert:list`）分页，`q`（描述/区域）、`filters[alert_type|status|level|visit_id]`
  · `GET /visitor/alerts/counts` → open/handled/ignored 计数
- `POST /visitor/alerts/scan`（`visitor:alert:handle`）滞留扫描 → `{scanned}`
- `POST /visitor/alerts/{aid}/handle`（`visitor:alert:handle`，`{status:handled|ignored, handle_remark}`）
- 预警类型：`overstay 滞留超时` / `tailgating 尾随进入` / `intrusion 闯入禁区` / `zone_denied 越权访问` / `blacklist 黑名单命中`。

### NDA 电子签（权限码 `visitor:nda:*`）
- `GET /visitor/nda`（`visitor:nda:list`）分页，`q`（编号/签署人/单位）· `GET /visitor/nda/counts`（signed/expired/revoked）
- `POST /visitor/nda`（`visitor:nda:sign`）签署 —— 存 `evidence_hash` 存证哈希防篡改，状态 `signed`
  · `POST /visitor/nda/{nid}/revoke`（`visitor:nda:sign`）作废

### 黑名单（权限码 `visitor:blacklist:*`）
- `GET /visitor/blacklist`（`visitor:blacklist:list`）分页，`q`（姓名/证件号/电话）· `GET /visitor/blacklist/counts`
- `POST /visitor/blacklist`（`visitor:blacklist:edit`）· `PUT /visitor/blacklist/{bid}` · `POST /visitor/blacklist/{bid}/toggle`

### 样品 / 样车交接（权限码 `visitor:handover:*`）
- `GET /visitor/handovers`（`visitor:handover:list`）分页，`q`（交接单号/样品编号/条码）、`filters[visit_id|sample_type|status]`
- `POST /visitor/handovers`（`visitor:handover:create`）登记交接，可关联访客单（`visit_id`）反查带入的样品/样车。

### 错误码（98xxx）
98001 状态不允许该操作 · 98002 记录不存在 · 98003 区域不存在 · 98004 命中黑名单 · 98005 超出计划来访时间窗
· 98006 凭证无效 · 98007 未签 NDA 不予放行 · 98008 重复登记

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
- `POST /contract/contracts/ai-parse`（contract:create，multipart file；pdf/docx/txt 文本提取，jpg/png 走多模态视觉模型）
  → `{fields:{name,customerName,amount,startDate,endDate,payCycle,delivery,sealType,paymentOrg,contactPerson,contactPhone,remark},customerCandidates:[{id,name}],source:"ai"}`；
  仅返回草稿不落库，客户候选由人工选择绑定；未配置/停用 65001，解析失败 65004
- `POST /contract/contracts/ai-risk-review`（contract:create，multipart：`payload`=表单字段 JSON 字符串，
  `file`/`attachment_id` 二选一可选作合同原文——file 限 pdf/docx/txt/jpg/png，attachment_id 取已上传附件）
  → `{risks:[{level:"high|mid|low",clause,issue,suggestion}],missingClauses:[],summary,withText}`；
  仅展示不落库（前端可复制/追加到备注由人工保存）；未配置 65001，停用 65002，解析失败 65004
- 权限码：`contract:list/create/edit/submit/delete/list:export`

## 销售 /sales（AI 报价：模板 → 报价单 → 审批 → 发送 → 反馈 → 转合同；设计见 docs/sales-quotation-design.md）
- 报价模板（`sales_quote_template`，(key, tpl_version, deleted) 唯一；版式全部收进 layout_json：
  headerHtml/introHtml/termsHtml/footerHtml/validDays/itemColumns[spec/unit/remark 白名单]）：
  - `GET /sales/templates`（全量）· `GET /sales/templates/options`（published 下拉，挂 sales:quote:create）
  - `POST /sales/templates` · `PUT /sales/templates/{id}`（仅 draft）· `GET /sales/templates/{id}`
  - `POST /sales/templates/{id}/new-version`（复制为 draft 新版本）· `POST /sales/templates/{id}/publish`
    （同 key 旧 published 版自动停用）· `POST /sales/templates/{id}/disable` · `DELETE`（仅 draft 且无引用，逻辑删）
  - 预置 3 套：standard 标准报价单 / simple 简洁版 / bilingual 中英文版（种子幂等）
- 报价单（`sales_quotation` + `sales_quotation_item` + `sales_quote_send_log`）：
  - 状态机：`draft 草稿 → approving 审批中 → approved 已通过 / rejected 已驳回（可改后重提）→ sent 已送达
    → accepted 客户接受 / declined 客户拒绝`；`voided 已作废` 预留。明细金额服务端重算（qty×unit_price），不信任前端合计
  - `GET /sales/quotations` 分页（q/status 页签）· `GET /sales/quotations/counts` · `GET /sales/quotations/export`（xlsx）
  - `POST /sales/quotations` · `PUT /sales/quotations/{id}`（仅 draft/rejected；选模板时落 layout_snapshot）·
    `DELETE`（仅 draft，逻辑删）· `GET /sales/quotations/{id}`（详情 + timeline + sendLogs）
  - `POST /sales/quotations/{id}/submit`：校验明细≥1、合计>0、valid_until≥today、模板 published（64002）；
    发 BJ 编号（编号规则 quotation，daily）+ 启动审批（biz_type=sales_quotation，定义 quote_approve：部门负责人→分管领导）
  - 审批事件订阅：通过 → approved（auto_send 且 contact_email 时自动发邮件留痕，异常不阻断）；
    驳回 → rejected；撤回 → draft
  - `POST /sales/quotations/{id}/send` `{channel:email|print|download, recipient?}`（仅 approved/sent）：
    email 复用 SMTP 设置（未配置走调试通道），print/download 仅留痕；全部落 send_log（result=real/debug/marked/skipped/failed）
  - `POST /sales/quotations/{id}/feedback` `{action:accept|decline, note?}`（仅 approved/sent）→ accepted/declined
  - `POST /sales/quotations/{id}/to-contract`（仅 accepted；幂等：已转返回 64004）→ 生成 ctr_contract 草稿
    （contract_type=sales，名称/金额/客户/联系人预填，备注注明来源单号）并回写 contract_id
  - `POST /sales/quotations/ai-generate` `{customerId, templateId?, requirement}` → 三级回退：
    AI 未配置 → 模板默认（source=template/ai_not_configured）；AI 失败或 JSON 结构非法 → 复制该客户最近报价
    （source=history，remark 标注复制来源）→ 无历史 → 模板兜底（source=template/ai_failed）；
    成功时 source=ai，金额仍服务端重算。结果不落库，ai_meta 由前端保存时透传。
    已接入 AI 中心网关（feature=quote）：功能停用 → 模板回退（fallbackReason=feature_disabled）；
    配额超限不静默回退，直接抛 65003
  - AI 配置在系统设置卡片：`sys_config ai.enabled/ai.base_url/ai.api_key(加密)/ai.model/ai.vision_model/ai.timeout`，
    OpenAI 兼容 `POST {base_url}/chat/completions`，429/5xx/网络重试 3 次；环回/内网端点自动绕过系统代理
- 权限码：`sales:quote:list/create/edit/submit/send/feedback/to-contract/export`（biz_user 默认）+
  `sales:template:list/create/edit/publish/delete`（默认仅 super）
- 错误码：64001 当前报价状态不允许该操作 / 64002 模板未发布 / 64003 模板键冲突 / 64004 报价单已转合同
- 打印：无壳路由 `/sales/quotations/{id}/print`（浏览器打印另存 PDF；非 approved 系状态显示草稿水印）
- 菜单：销售系统区（menu.salesSystem）子项 报价管理（Quotations，`/sales/quotations`，componentKey `sales/QuotationList`）/
  报价模板（QuoteTemplates，`/sales/templates`，componentKey `sales/QuoteTemplateList`）；存量库归并经 `backend/scripts/migrate_nav_sales.py`（委托批次E）

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
- `POST /approval/instances/{instanceId}/ai-assist`（登录可用，但限实例相关人：发起人/节点审批人/被抄送人，或持 approval:view；否则 20002）
  → `{summary,highlights:[],risks:[{level:"high|mid|low",text}],opinion,customerHistory?}`：
  上下文=单据快照（值截断）+提交说明+合同类单据按权限附客户历史统计（合同数/均价/偏离/近90天相近单/累计到账）；
  建议不落库，意见草稿由人工引用到审批意见框修改后随审批动作提交；未配置 65001，停用 65002，解析失败 65004
- 管理端：`GET /approval/definitions` · `POST /approval/definitions` · `PUT /approval/definitions/{id}`
  · `DELETE /approval/definitions/{id}`（admin:flow:edit；有运行中实例时拒绝，逻辑删）
  定义结构：`{id,code,name,bizType,enabled,nodes:[{seq,nodeName,approverType:"USER|ROLE",approverValue,approverName}]}`
- `POST /approval/definitions/ai-suggest`（admin:flow:edit，feature `flow_route`）`{bizType,name?,amount?,category?}` →
  `{nodes:[{nodeName,approverType,approverValue,approverName,signMode}],rationale}`：
  上下文=启用用户/角色清单（各≤50）+ 同 bizType 现有定义节点摘要（每 code 最新版 ≤5 条）；
  USER/ROLE 审批人逐一服务端校验存在且启用并回填 approverName，组织类型仅校验兜底角色 code，
  非法节点丢弃、全丢 65004；建议不落库，前端「采纳」才替换编辑中的节点（采纳后强制简易模式）
- 错误码：70001 无待办 / 70002 非当前审批人 / 70003 意见必填 / 70004 已有进行中实例

## 人事行政 /hr（工时填报：业务系统合同/任务 ↔ 人事数据的关联起点）
- 表 hr_timesheet：用户/工作日期/任务（快照 task_no/task_name/contract_id/contract_no/customer_id/customer_name）
  /hours Numeric(4,1)（>0 且 ≤24、0.5 步进，服务端校验）/content（必填 ≤500）/remark/status draft|submitted；
  (user_id, work_date, task_id, deleted) 唯一（软删写行 id，同 oa_form 模式）。
- 规则：可填报任务口径 = 任务 status=in_progress 且已关联合同；日期不允许未来（63004）；
  同人同日同任务防重 63001；提交后只读（改/删/重复提交 63002），本人可 withdraw 退回草稿再改；
  草稿可改可删；操作仅本人（他人 403）。
- 用户侧（hr:timesheet:create）：
  `GET /hr/timesheets/options/contracts?q=`（仅 approved 合同，远程检索）
  · `GET /hr/timesheets/options/tasks?contractId=&q=`（该合同下进行中任务，带客户名）
  · `GET /hr/timesheets/day?date=` → `{items,totalHours}` · `GET /hr/timesheets/week?date=` → 周一至周日逐日 `{date,totalHours,count,future}`
  · `POST /hr/timesheets`（201；body.submit=true 即保存并提交）· `PUT /hr/timesheets/{id}`（仅草稿）
  · `DELETE /hr/timesheets/{id}`（仅草稿）· `POST /hr/timesheets/{id}/submit` · `POST /hr/timesheets/{id}/withdraw`
  · `POST /hr/timesheets/ai-prefill`（hr:timesheet:create，feature `hr_prefill`）`{taskId,workDate}` →
    `{hours,content,basis:{progressCount,recentCount,dayUsedHours}}`：
    上下文=该任务最近 5 条进度日志 + 本人该任务最近 5 条工时 + 当日已报合计；
    hours 服务端 0.5 步进取整 clamp [0.5,24]、content 截 500；只回草稿不落库，人工修改后随保存/提交落库
- 我的工时（hr:timesheet:list）：`GET /hr/timesheets/my?status=&q=&range[work_date]=YYYY-MM-DD|YYYY-MM-DD&sort=&page&size`
  （q 按任务/合同/客户/内容模糊）· `GET /hr/timesheets/my/counts` → `{draft,submitted,all}`
  · `GET /hr/timesheets/my/export`（xlsx 流，复用 my 过滤）
- 工时统计（hr:timesheet:stats；仅 submitted 计入）：
  `GET /hr/timesheets/stats?dimension=task|contract|user&dateStart&dateEnd&deptId&userId&taskId`
  → `{dimension,rows,grandTotalHours}`（task 维度含 entryCount/userCount；contract 加 taskCount；user 加 deptName/taskCount/dayCount）
  · `GET /hr/timesheets/stats/detail?userId=&dateStart&dateEnd&taskId&page&size`（人员下钻明细）
  · `GET /hr/timesheets/stats/options?kind=dept|user|task&q=`（筛选项远程检索：dept/user 取有工时记录者）
  · `GET /hr/timesheets/stats/export`（hr:timesheet:stats:export，xlsx 按维度列）。
  遗留：部门经理行级数据范围未做（统计暂为全量视角，按需授权）。
- 权限码：hr:timesheet:create / hr:timesheet:list / hr:timesheet:list:export（biz_user 种子含此三项）
  / hr:timesheet:stats / hr:timesheet:stats:export（默认仅 super，按需分配）。
- 错误码：63001 同人同日同任务已填报 / 63002 当前工时状态不允许该操作 / 63003 任务不可填报（需进行中且关联合同）/ 63004 不允许填报未来日期。
- purge 清单含 hr_timesheet（硬删，先于 task_task）。

## OA /oa
- `GET /oa/instances/my?status=&page&size&q=`（oa:my；`q` 按单号/表单名模糊检索）·
  `GET /oa/instances/my/export?status=&q=`（xlsx 流，沿用 oa:my）
- `GET /oa/instances/my/counts`（沿用 oa:my）→ `{running,approved,rejected,withdrawn,terminated,all}`
- `GET /oa/related?tab=todo|done|cc&page&size&q=`（复用通用审批端点，biz_type=oa；`q` 按标题模糊检索）
- `GET /oa/related/counts` → `{todo,done,cc}`（页签计数）
- 管理端单据检索：`GET /oa/admin/instances?status=&keyword=&stuckDays=&page&size`（oa:admin:handle）·
  `GET /oa/admin/instances/counts` → `{running,approved,rejected,withdrawn,terminated,all}`
- `POST /oa/ai-prefill`（oa:apply，feature `oa_prefill`）`{formId}` → `{data,filledKeys,historyCount}`：
  按本人同 form.key 最近 3 条历史申请预填；仅 text/textarea/number/money/date/daterange/select/radio/checkbox
  可预填（file/user/resource/布局控件不预填）；select/radio 值须 ∈ options、checkbox ⊆ options、number/money 数值化，
  非法 key/值服务端丢弃；无历史直接回空不调 AI；只回草稿不落库
- 异常干预（oa:admin:handle）：`POST /oa/admin/instances/{id}/ai-anomaly`（feature `flow_anomaly`）→
  `{stuck:{nodeName,pending:[{assigneeId,assigneeName,hours}]},signals:[],analysis,suggestions:[{type:urge|transfer|restart|other,text,userId?,userName?}]}`：
  signals 服务端确定性生成（审批人停用/锁定、滞留时长 vs 同表单历史中位处理时长、组织节点解析不到人）；
  AI 只产 analysis/suggestions，转办人选只信服务端按 userName 匹配回的 userId；仅 running 且绑流程的单据
  · `POST /oa/admin/instances/{id}/urge`（非 AI、不受开关约束）`{comment?}` → `{instanceId,urged}`：
  给当前全部待办人各写一条 sys_notify（link=/approval）+ 审计 oa_urge；人工点击才发送
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
- `POST /task/samples/ai-ocr`（task:edit，feature `sample_ocr`，multipart file：jpg/jpeg/png）→
  `{name,model,vin,vehicleType,sampleDate,source:"ai"}`；样品标签照片多模态提取草稿，不落库（人工核对后随任务/样品保存）
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
- 进度记录（表 task_progress_log，拍照记进度：AI 草稿 → 人工确认才落库）：
  - `GET /task/tasks/{id}/progress`（task:list）→ `[{id,percent,note,imagePath,source:ai|manual,operatorName,createTime}]`
  - `POST /task/tasks/{id}/progress/ai-image`（task:edit，multipart file 限 jpg/jpeg/png；仅 in_progress 任务）：
    照片存 uploads/task_progress/ + AI 视觉分析 → `{percent,note,imagePath}` 草稿（不落库；未配置/停用 65001，分析失败 65004）
  - `POST /task/tasks/{id}/progress`（task:edit，201）`{percent:0-100,note,imagePath?,source}`：人工确认登记（仅 in_progress，否则 60001）
  - `GET /task/progress-images/{logId}`（task:list）：进度照片流（按日志行鉴权，防路径遍历）
- 权限码：`task:list/create/edit/assign/submit/list:export`（delete/其他状态动作用 `task:edit`）、
  `task:sample:list`、`task:sample:list:export`（种子挂 super/biz_user）

### B5 任务字段扩展 / 工序流转 / 七维分配 / 全过程追溯
- **字段扩展**（`task_task` 新增列，仅在请求显式携带时覆盖，避免部分更新被默认值冲掉）：
  `planStartDate` `durationHours` `priority` `roleGroup` `meshCount` `solver`
  `computeResource` `computeCores` `computeNodes`
  - `roleGroup`（角色分组）请求未指定时按 `taskType` 派生：`cfd→sim` `model→model` `windtunnel/test→test`
    `outsource→outsource`（未登记的类型按类型本身归组）
  - 负责人未指定时按字典 `task_owner_rule`（value=任务类型，extra=角色编码）解析该角色在职用户，
    命中不到再回落到当前登录人
- **工序流转**（表 `task_process`，一任务多工序，`seq` 排序；同一任务**同时只允许一道工序进行中**）：
  - `GET /task/tasks/{id}/processes` → `{items:[{id,seq,processCode,processName,status,statusText,isCurrent,
    plannedStart,plannedEnd,actualStart,actualEnd,operatorId,operatorName,deptId,deptName,remark}],total}`
  - `POST /task/tasks/{id}/processes` `{processCode,processName,seq?,plannedStart?,plannedEnd?,operatorId?,operatorName?,deptId?,deptName?,remark?}`（201）
  - `PUT /task/processes/{pid}`（不可改已 done/skipped 的工序，60020）· `DELETE /task/processes/{pid}`（进行中不可删，60020）
  - `POST /task/processes/{pid}/start|finish|skip`（非法状态流转 60020）
  - 工序状态机：`pending 待开始 → running 进行中 → done 已完成`（`skipped 已跳过` 为旁路终态）
  - 当前工序回写任务 `processStage`（列表/详情直接可见「当前处于哪道工序」）
- **七维分配**（表 `task_assignment`，维度字典 `task_dimension`：person 人 / equipment 机 / material 料 /
  method 法 / env 环 / test 测 / safety 安 / vehicle 样车）：
  - `GET /task/tasks/{id}/assignments` → `{items:[{id,dimension,dimensionText,resourceId,resourceCode,
    resourceName,qty,unit,status,statusText,assignerId,assignerName,plannedAt,confirmedAt,remark}],total}`
  - `POST /task/tasks/{id}/assignments`（201）· `PUT /task/assignments/{aid}` · `DELETE /task/assignments/{aid}`
  - 状态机：`pending 待分配 → allocated 已分配 → confirmed 已确认`（`rejected 已驳回` 为终态）；
    置 `confirmed` 时自动写 `confirmedAt`
  - 排程域读取其中 `equipment/person/vehicle`（时段独占）与 `material`（数量占用）维度
- **全过程追溯**（表 `task_trace`，节点字典：input 任务输入 / output_report 报告输出 /
  vehicle_return 样车归还 / model_ship 模型车发运 / accept 验收 / settle 结算）：
  - `GET /task/tasks/{id}/traces` → `{items:[{id,nodeCode,nodeName,nodeText,seq,happenAt,refNo,
    operatorId,operatorName,remark}],total}`
  - `POST /task/tasks/{id}/traces` `{nodeCode,nodeName?,seq?,happenAt?,refNo?,remark?}`（201）· `DELETE /task/traces/{tid}`
- **操作流程图**：`GET /task/tasks/{id}/operation-flow` → `{taskId,taskNo,taskName,status,processStage,
  processStageText,currentNode,nodes:[{type:"process"|"trace",code,name,status,statusText,seq,...}],total}`
  （工序节点在前、追溯节点在后，`currentNode` 为当前进行中的工序）
- **角色分组可见性**（CSV 21）：用户被授予 `task:group:<组>` 权限点后，**列表只返回本组任务、详情/编辑跨组被拒**
  （60021 `TASK_ROLE_GROUP_DENIED`）；超管与未授予任何分组权限的用户不受限
- 新增权限码：`task:process:edit` `task:assignment:edit` `task:trace:edit`
  `task:group:sim|model|test|outsource`
- 新增错误码：`60020 TASK_PROCESS_INVALID_STATE 工序状态不允许该操作`、
  `60021 TASK_ROLE_GROUP_DENIED 无权访问该角色分组的任务`
- 新增字典：`task_role_group` `task_process` `task_dimension` `task_owner_rule`

## 智能排程 /production（B5）
排程方案（`prd_plan`）+ 排程行（`prd_schedule`，任务 × 资源 × 时段）。单号前缀 `PL` / `SC`。
- 方案状态机：`draft 草稿 → published 已发布 → confirmed 已确认`（`cancelled 已取消`）
- 排程行状态机：`scheduled 已排期 → published 已发布 → confirmed 已确认 → done 已完成`
  （`conflict 冲突` / `cancelled 已取消`）
- 资源模型：`equipment/person/vehicle` 为**时段独占**（同一资源同一时间只允许一段占用），
  `material` 为**数量占用**（按存货可用量校验，缺料即冲突）
- `GET /production/plans` 分页（`production:schedule:list`）→ `{items:[{id,planNo,name,planDate,status,statusText,
  autoGenerated,taskCount,conflictCount,scheduleCount,generatedByName,publishedAt,remark,version,createTime,updateTime}],
  total,page,size}`；检索 `q`（planNo/name）、`status` 页签
- `GET /production/plans/counts` → `{all,draft,published,confirmed,cancelled}`
- `GET /production/plans/{id}` → 方案字段 + `schedules[]`
- `POST /production/plans`（201，`production:schedule:create`）`{name,planDate?,remark?}` — 手工建空方案
- `DELETE /production/plans/{id}`（已确认不可删，99001）
- **自动排期** `POST /production/plans/auto`（201，`production:schedule:auto`）
  `{name?,baseDate?,taskIds?[],projectId?,dateFrom?,dateTo?}` → 方案 + `schedules[]`
  - 算法（规则式贪心）：待排任务（默认 `draft/in_progress`，可按 `taskIds`/`projectId`/时间窗过滤）
    按「优先级升序 → 计划开始日升序」排序 → 自最早可行时间起逐时顺延，避开已占用时段
    → 物料先做可用量校验
  - **顺延成功不算冲突**（能排进空档即 `scheduled`）；只有顺延到上限仍排不下、或物料缺量才标 `conflict`
  - 无可排任务 → `99005 PRODUCTION_NO_TASK_TO_SCHEDULE`
- **发布方案** `POST /production/plans/{id}/publish`（`production:schedule:publish`）
  - 发布前二次校验资源时段冲突，命中 → `99004 PRODUCTION_SCHEDULE_CONFLICT`（消息列出重叠的方案/资源）
  - 通过后：排程行转 `published`、写 `publishedAt/publishedByName`、**回写任务的 `planStartDate/planFinishDate`**
- `POST /production/plans/{id}/cancel`（`production:schedule:publish`）→ 方案与未完成排程行转 `cancelled`
- **排程行**：
  - `GET /production/schedules` 分页 · `GET /production/schedules/counts` · `GET /production/schedules/gantt`
    （按资源分组的甘特数据）· `GET /production/schedules/{sid}`
  - `PUT /production/schedules/{sid}`（`production:schedule:edit`）人工调整资源/时间/数量；
    调整后 `source=manual` 并清空 `conflictReason`；乐观锁冲突 10003
  - `POST /production/schedules/{sid}/confirm`（`production:schedule:publish`）→ 置 `confirmed`
  - `DELETE /production/schedules/{sid}`（已确认不可删，99001）
  - `POST /production/schedules/export`（`production:schedule:list:export`，xlsx）
- **资源占用视图** `GET /production/resources/occupancy` → 按资源维度汇总**已发布/已确认**的占用时段
  `{items:[{resourceType,resourceTypeText,resourceId,resourceName,resourceCode,occupiedHours,taskCount,windows[]}],total}`
  （可加 `?resourceType=equipment` 过滤）
- 错误码：`99001 PRODUCTION_INVALID_STATE` `99002 PRODUCTION_PLAN_NOT_FOUND`
  `99003 PRODUCTION_SCHEDULE_NOT_FOUND` `99004 PRODUCTION_SCHEDULE_CONFLICT` `99005 PRODUCTION_NO_TASK_TO_SCHEDULE`

## 项目管理 /project（B5）
项目（`prj_project`）+ 项目任务/甘特行（`prj_project_task`）。单号前缀 `PJ`。
- 项目状态机：`draft 立项中 → planning 策划中 → executing 执行中 → accepting 验收中 → closed 已结项`
  （`cancelled 已取消`；**仅 `draft`/`cancelled` 可删除**，否则 99101）
- 甘特行状态机：`pending 未开始 → doing 进行中 → done 已完成`（`delayed 已延期`）
- `GET /project/projects` 分页（`project:list`）→ `{items:[{id,projectNo,name,customerId,customerName,
  contractId,contractNo,managerId,managerName,deptId,deptName,startDate,endDate,status,statusText,progress,
  budgetAmount,actualAmount,description,remark,taskCount,version,createTime,updateTime}],total,page,size}`
  检索：`q`（projectNo/name/customerName/contractNo/managerName）、`status` 页签
- `GET /project/projects/counts` → `{all,draft,planning,executing,accepting,closed,cancelled}`
- `GET /project/projects/{id}` → 项目字段 + `gantt`（甘特数据）
- `POST /project/projects`（201，`project:create`）`{name,customerId?,customerName?,contractId?,contractNo?,
  managerId?,managerName?,deptId?,deptName?,startDate?,endDate?,status?,budgetAmount?,description?,remark?}`
- `POST /project/projects/from-contract`（201，`project:create`）**基于合同立项**：
  合同必须 `approved`（否则 50001），合同信息覆盖入参（客户/合同号/负责人/金额）
- `PUT /project/projects/{id}`（`project:edit`，乐观锁）· `DELETE /project/projects/{id}`（`project:delete`）
- `POST /project/projects/export`（`project:list:export`，xlsx）
- **甘特**：
  - `GET /project/projects/{id}/gantt` → `{projectId,projectNo,projectName,status,progress,startDate,endDate,
    items:[{id,taskId,taskNo,taskName,seq,groupCode,groupText,ownerId,ownerName,startDate,endDate,progress,
    milestone,weight,status,dependsOn,source,remark}],milestones[],total}`
  - `GET /project/projects/{id}/tasks` 同上（行集合）
  - `POST /project/projects/{id}/tasks`（201，`project:edit`）手工新增甘特行（里程碑 `milestone=1`）
  - `PUT /project/project-tasks/{tid}`（`project:edit`）改进度/权重/状态 → **触发项目进度回算**
  - `DELETE /project/project-tasks/{tid}`（`project:edit`）
  - **自动生成甘特** `POST /project/projects/{id}/generate-tasks`（`project:edit`）
    `{taskIds?[],projectId?,groupCode?,overwrite?}` → 甘特数据 + `created`（本次新建行数）
    - 来源任务按「任务类型 → 分组」归类：`cfd→sim` `model→model` `windtunnel→test` `outsource→outsource`
    - 起止日期优先取**已发布/已确认的排程**（`prd_schedule`），其次取任务自身的 `planStartDate/planFinishDate`
    - 进度与业务任务同口径（`task.progress`），≥100 记 `done`、>0 记 `doing`
- **项目进度** = 各甘特行按 `weight` 加权平均（权重全 0 时按行数平均），每次增删改行自动回算
- 错误码：`99101 PROJECT_INVALID_STATE` `99102 PROJECT_NOT_FOUND` `99103 PROJECT_TASK_NOT_FOUND`

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
- `PUT /finance/invoices/{id}` `{invoiceNo,amount,taxRate?,buyerName?,sellerName?,invoiceDate?}` → 财务登记发票信息
- `POST /finance/invoices/{id}/ai-ocr`（finance:invoice:edit，feature `invoice_ocr`，multipart file：pdf/jpg/jpeg/png）→
  `{fields:{invoiceNo,amount,taxRate,buyer,seller,invoiceDate},amountCheck:{settlementAmount,matches,diff},source:"ai"}`；
  pdf 走文本提取、图片走多模态；字段截断归一；amountCheck 为服务端对结算金额的确定性复核（|diff|≤0.01 为一致），
  仅提示人工核对，登记落库仍走 PUT（审计 invoice_ai_ocr）
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

## 资产与库存 /asset（进出库管理 + 资产财务 + BOM）

> 三个 router 同前缀 `/asset`：`router.py`（进出库管理）、`finance_router.py`（资产财务）、
> `bom_router.py`（BOM 物料清单）。
> **统一框架**：不新建组织/公司/权限表 —— 部门取 `sys_dept`，供应公司取 `crm_customer`
> （`partner_type ∈ supplier/both` 且 `status=enabled`，否则 97006），权限码由 `sys_menu.permission` 承载。

- 错误码（97xxx 资产域）：
  97001 状态不允许该操作 · 97002 资产/单据不存在 · 97003 库存不足 · 97004 编码重复 ·
  97005 仓库无效 · 97006 供应公司无效 · 97007 借用未归还 · 97008 库位无效 ·
  97009 BOM/子件行不存在
- 单号规则（`app/services/numbering`，日周期）：`PO` 采购订单 · `YS` 验收单 · `PD` 盘点单 ·
  `LJ` 样件借出 · `LY` 工具领用 · `CZ` 处置单 · `BM` BOM 单号；
  计数器落后于存量数据时自动跳过已占用号。
- 所有列表统一 `apply_list_filters` 协议（`q` / `status` / `filters[k]` / `range[k]` / `sort=`），
  配 `…/counts` 页签计数接口；导出统一 `…/export`（xlsx 流）。

### 仓储与库位
- `GET /asset/warehouses` 分页：`{id,code,name,deptId,deptName,address,managerId,managerName,capacity,locationCount,qtyOnHand,stockAmount,phone,remark,status,statusText,version,createTime,updateTime}`
  检索：`q`（code/name/address/manager_name）、`status`、`filters[dept_id]`
- `GET /asset/warehouses/counts` → `{enabled,disabled,all}`
- `GET /asset/warehouses/stats` → `{warehouseCount,locationCount,batchCount,stockAmount,stockMap}`（页头统计卡）
- `GET /asset/warehouses/{id}` · `POST /asset/warehouses`（201）· `PUT /asset/warehouses/{id}` · `DELETE /asset/warehouses/{id}`
  - 入参 `{code*,name*,deptId?,address?,managerId?,managerName?,capacity?,phone?,remark?,status?,version?}`；
    `version` 为乐观锁（不匹配 10003）；编码全库重复 97004
  - 删除前置：仓库下仍有库位 97001；删除后详情 10002
- `GET /asset/locations`（`filters[warehouse_id]`）· `GET /asset/locations/all`（下拉全量）
  · `POST` / `PUT /asset/locations/{id}` / `DELETE /asset/locations/{id}`
  - 入参 `{warehouseId*,code*,name?,area?,capacity?,remark?,status?,version?}`；同仓编码重复 97004
  - 库位有库存时不可删除 97001；仓库有库位时不可删除 97001
- `GET /asset/locations/all` / `GET /asset/items/all` / `GET /asset/prototypes/all` / `GET /asset/tools/all`：下拉选项，不分页

### 库存物料
- `GET /asset/items` 分页：`{id,code,name,spec,unit,category,categoryText,unitPrice,safetyStock,maxStock,defaultWarehouseId,defaultLocationId,supplierId,supplierName,manufacturer,deptId,deptName,qtyOnHand,lowStock,stagnantDays,idleDays,lastMoveAt,stagnantLevel,stagnantLevelText,stagnant,stagnantAmount,warning,remark,status,statusText,version,createTime,updateTime}`
  检索：`q`（code/name/spec/supplier_name）、`status`、`filters[category]`、`filters[supplier_id]`、`filters[dept_id]`、`filters[default_warehouse_id]`
  （`filters[low_stock]=1` 为**分页后过滤**：`lowStock = 安全库存 > 0 且现存量 < 安全库存`）
- **呆滞预警（分页后过滤，与导出一致）**：
  - `filters[stagnant]=1` 命中呆滞物料 · `filters[stagnant_level]=normal|slow|stagnant|dead` 按分级
    · `filters[warning]=1` 命中「低库存 或 呆滞」的任一预警
  - `idleDays` = 距最后一次出入库流水的闲置天数（无流水按创建至今）；`stagnantLevel` 由
    `stagnantDays`（默认 90 天，可在物料上调整）倍数决定：<1× 正常 / 1~2× 缓慢 / 2~3× 呆滞 / ≥3× 死滞
  - `stagnantAmount` = 呆滞金额（现存量 × 单价）；`warning` = `lowStock || stagnant`
- `GET /asset/items/counts` → `{enabled,disabled,all,lowStock,stagnant,stagnantAmount,warning}`
- `GET /asset/items/{id}` · `POST /asset/items`（201）· `PUT /asset/items/{id}` · `DELETE /asset/items/{id}`
  - 入参 `{code*,name*,spec?,unit?,category?,unitPrice?,safetyStock?,maxStock?,stagnantDays?,defaultWarehouseId?,defaultLocationId?,supplierId?,manufacturer?,deptId?,remark?,status?,version?}`
  - 编码重复 97004；`supplierId` 必须是启用的 supplier/both 往来单位，否则 97006
  - 删除前置：物料仍有在库数量（结存 ≠ 0）97001
- `GET /asset/items/{id}/bom-refs` → `{itemId,itemCode,itemName,asParent:[{id,bomNo,parentItemId,parentItemCode,parentItemName,parentSpec,version,status,statusText,effectiveDate,lineCount}],asChild:[{bomId,bomNo,parentItemName,version,status,qty,lossRate,requiredQty,position}]}`
  - 该物料**作为父件**的 BOM 清单 与 **作为子件**被引用的 BOM 行

### BOM 物料清单（`bom_router.py`，权限码 `asset:bom:*`）
- `GET /asset/boms` 分页：`{id,bomNo,parentItemId,parentItemCode,parentItemName,parentSpec,version,status,statusText,effectiveDate,lineCount,remark,lockVersion,createTime,updateTime}`
  （`version` = BOM 版本号字符串；`lockVersion` = 乐观锁列）
  检索：`q`（bom_no/parent_item_code/parent_item_name）、`status`、`filters[parent_item_id]`
- `GET /asset/boms/counts` → `{draft,effective,obsolete,all}`
- `GET /asset/boms/{id}` → 详情 + `lines[]`（`{id,bomId,itemId,itemCode,itemName,spec,unit,qty,lossRate,requiredQty,refDesignator,position,remark}`）
  · `POST /asset/boms`（201）· `PUT /asset/boms/{id}` · `DELETE /asset/boms/{id}`
  - 入参 `{parentItemId*,bomVersion*,effectiveDate?,remark?,lines:[{itemId*,itemCode?,itemName*,spec?,unit?,qty*,lossRate?,refDesignator?,position?,remark?}],version?}`
  - `bomNo` 走 BM 规则；`bomVersion` 在**同一父件内唯一**，重复 97004；父件=子件（自引用）97001；
    BOM / 子件行不存在 97009；**仅 `draft` 可编辑可删**，生效态改删 97001
- `POST /asset/boms/{id}/activate` —— 激活：同一父件下**仅一个生效版本**，激活新版本自动把旧生效版本置 `obsolete`
- `POST /asset/boms/{id}/obsolete` —— 作废（生效态 → 作废态）
- `POST /asset/boms/{id}/copy` —— 复制版本：`V1.0 → V1.1`，生成 `draft` 副本（入参可选 `{bomVersion?,effectiveDate?}`）
- `GET /asset/boms/{id}/explode?max_depth=5` → `{bomId,bomNo,parentItemName,version,tree:[{itemId,itemCode,itemName,spec,unit,qty,lossRate,requiredQty,refDesignator,position,level,children[]}]}`
  - **多级展开**：子件本身是总成且有生效 BOM 时递归下钻（带**循环检测**，遇到自引用只保留当前层）；
    `level` 1 = 直接子件（根节点不出现在 tree 中）；`max_depth` 取值 1–10
- `GET /asset/boms/{id}/usage?qty=1` → `{bomId,bomNo,parentItemName,parentQty,lines:[{itemId,itemCode,itemName,spec,unit,unitQty,lossRate,requiredQty,actualOutQty,diffQty}]}`
  - 用量对比：`requiredQty = unitQty ×（1 + 损耗率）× 父件数量`（理论需求）；
    `actualOutQty` = 该子件的**出库流水累计领用**；`diffQty = requiredQty − actualOutQty`（差额，>0 为领料不足）
- `POST /asset/boms/export`（xlsx 流）

### 采购订单（状态机 draft → confirmed → closed）
- `GET /asset/purchase-orders` 分页：`{id,orderNo,title,supplierId,supplierName,deptId,deptName,orderDate,arriveDate,totalAmount,handlerId,handlerName,remark,status,statusText,items[],version,createTime,updateTime}`
- `GET /asset/purchase-orders/counts` → `{draft,confirmed,closed,all}`
- `GET /asset/purchase-orders/{id}`（含 `items[]` 与该单的 `receipts[]`）· `POST`（201）· `PUT` · `DELETE`
  - 入参 `{title*,supplierId*,deptId?,orderDate?,arriveDate?,totalAmount?,handlerId?,handlerName?,remark?,items:[{itemId?,itemCode?,itemName*,spec?,unit?,quantity*,price?,remark?}],version?}`
  - `orderNo` 走 PO 规则；仅 `draft` 可编辑/删除，否则 97001；`closed` 不可再确认
- `POST /asset/purchase-orders/{id}/confirm` · `POST /asset/purchase-orders/{id}/close`（状态推进）
- `POST /asset/purchase-orders/export`

### 验收单（出入库入口）
- `GET /asset/receipts` 分页：`{id,receiptNo,orderId,orderNo,warehouseId,warehouseName,supplierId,supplierName,arriveDate,totalQty,qualifiedQty,inspectorId,inspectorName,remark,status,statusText,items[],version,createTime,updateTime}`
- `GET /asset/receipts/counts` → `{draft,accepted,partial,rejected,all}`
- `GET /asset/receipts/{id}`（含 `items[]`）· `POST`（201）· `PUT` · `DELETE`
  - 入参 `{orderId?,warehouseId?,supplierId?,arriveDate?,inspectorId?,inspectorName?,remark?,items:[{itemId?,itemCode?,itemName*,spec?,unit?,quantity*,qualifiedQty*,locationId?,price?,remark?}],version?}`
  - `receiptNo` 走 YS 规则；`qualifiedQty ≤ quantity`；来源采购订单未确认（draft）不可验收 97001；
    对 `confirmed` 的订单建单即置 `closed`；验收（accept）后不可再改/删 97001
- `POST /asset/receipts/{id}/accept`：按合格数量写入库存流水（`direction=in`, `biz_type=receipt`）+ 回写库位在库数量；
  单据状态按合格比例落 `accepted`（全合格）/ `partial`（部分合格）/ `rejected`（无合格）
- `POST /asset/receipts/export`

### 库存流水（台账）
- `GET /asset/ledger` 分页：`{id,direction,directionText,itemId,itemCode,itemName,unit,warehouseId,warehouseName,locationId,locationCode,quantity,unitPrice,amount,reason,reasonText,bizType,bizId,bizNo,operatorId,operatorName,deptId,deptName,happenAt,remark,editable,version,createTime}`
  检索：`q`（bizNo/itemName）、`filters[biz_type]`、`filters[item_id]`、`filters[warehouse_id]`、`filters[direction]`、`range[happen_at]`
  （`editable=false` 表示系统流水（验收/盘点/借出写入），只读）
- `GET /asset/ledger/counts` → `{all,in,out}`
- `GET /asset/ledger/{id}` · `POST`（201，手工出入库）· `PUT` · `DELETE`
  - 入参 `{direction*(in|out),itemId*,warehouseId?,locationId?,quantity*,unitPrice?,reason?,deptId?,happenAt?,remark?,version?}`
  - 出库超库存 97003；**系统流水只读**（`biz_type ≠ manual`，由验收/盘点/借出写入），编辑/删除 97001；
    手工流水（`biz_type=manual`）可改可删并回滚结存
- `POST /asset/ledger/export`

### 库存盘点
- `GET /asset/counts` 分页：`{id,countNo,warehouseId,warehouseName,countDate,totalQty,diffCount,operatorId,operatorName,remark,status,statusText,items[],version,createTime}`
  （明细行含 `bookQty/actualQty/diffQty/diffAmount`）
- `GET /asset/counts/counts` → `{draft,counting,finished,all}`
- `GET /asset/counts/{id}`（含 `items[]`）· `POST`（201）· `PUT` · `DELETE`
  - 入参 `{warehouseId?,countDate?,operatorId?,operatorName?,remark?,items:[{itemId?,itemCode?,itemName*,unit?,locationId?,bookQty?,actualQty?,reason?}],version?}`
  - `countNo` 走 PD 规则；`draft → counting（start）→ finished（finish）`；
    完成后按盘盈/盘亏写流水（`in`/`out`）并更新结存；`finished` 不可删 97001
- `POST /asset/counts/export`

### 样件与借出
- `GET /asset/prototypes` 分页：`{id,code,name,kind,kindText,model,vin,deptId,deptName,locationId,locationName,purchaseDate,value,remark,status,statusText,version,createTime,updateTime}`
- `GET /asset/prototypes/counts` → `{all,in_stock,loaned,maintenance,scrapped}`
- `GET /asset/prototypes/{id}` · `POST` · `PUT` · `DELETE`（入参 `{code*,name*,kind?,model?,vin?,deptId?,locationId?,purchaseDate?,value?,remark?,status?,version?}`；编码重复 97004）
- `GET /asset/prototype-loans` 分页：`{id,loanNo,prototypeId,prototypeCode,prototypeName,borrowerId,borrowerName,deptId,deptName,loanDate,dueDate,returnDate,purpose,handlerId,handlerName,remark,status,statusText,version,createTime,updateTime}`
  检索：`q`（loanNo/prototypeName）、`status`、`filters[prototype_id]`、`range[due_date]`（逾期口径）
  （借出单状态 `borrowed`/`returned`；逾期由 `statusText` 标注）
- `GET /asset/prototype-loans/counts` → `{borrowed,returned,overdue,all}`
- `GET /asset/prototype-loans/{id}` · `POST`（201）· `PUT` · `DELETE`
  - 入参 `{prototypeId*,borrowerId?,borrowerName?,deptId?,loanDate?,dueDate?,purpose?,handlerId?,handlerName?,remark?,version?}`
  - `loanNo` 走 LJ 规则；借出后样件状态 `in_stock → loaned`；归还后 `loaned → in_stock`
- `POST /asset/prototype-loans/{id}/return` `{returnDate?,remark?}`；未归还时删样件 97007，归还后借出单不可改/删 97001
- `POST /asset/prototypes/export` · `POST /asset/prototype-loans/export`

### 固定资产与折旧
- `GET /asset/assets` 分页：`{id,assetNo,name,category,categoryText,model,spec,deptId,deptName,custodianId,custodianName,location,purchaseDate,originalValue,salvageRate,usefulLifeMonths,accumDepreciation,netValue,remark,status,statusText,version,createTime,updateTime}`
- `GET /asset/assets/counts` → `{in_use,idle,repaired,scrapped,all}`
- `GET /asset/assets/{id}`（含 `depreciations[]` 与 `disposals[]`）· `POST`（201）· `PUT` · `DELETE`
  - 入参 `{assetNo*,name*,category?,model?,spec?,deptId?,custodianId?,custodianName?,location?,purchaseDate?,originalValue?,salvageRate?,usefulLifeMonths?,remark?,status?,version?}`
  - 资产编号重复 97004；不存在 97002；`netValue = 原值 − 累计折旧 − 残值`
- `POST /asset/assets/{id}/depreciate` `{period*(YYYY-MM),method?(straight_line|double_declining|sum_of_years),remark?}`
  - 按折旧方法计算本期折旧并落一条折旧记录（同一期间重复计提 97001）；已报废资产不可计提 97001
- `GET /asset/depreciations`（`filters[asset_id]`）· `POST /asset/depreciations`（手工折旧）· `PUT/DELETE /asset/depreciations/{id}`
  - 入参 `{assetId*,period*,amount*,method?,remark?,version?}`
- `POST /asset/assets/export` · `POST /asset/depreciations/export`

### 处置与报废
- `GET /asset/disposals` 分页：`{id,disposalNo,assetId,assetNo,assetName,disposalType,disposalTypeText,applyDate,originalValue,netValue,disposalAmount,reason,handlerId,handlerName,approverId,approverName,approveAt,remark,status,statusText,version,createTime,updateTime}`
- `GET /asset/disposals/counts` → `{draft,approved,done,rejected,all}`
- `GET /asset/disposals/{id}` · `POST`（201）· `PUT` · `DELETE`
  - 入参 `{assetId*,disposalType?(scrap|sell|donate|transfer),applyDate?,disposalAmount?,reason?,handlerId?,handlerName?,remark?,version?}`
  - `disposalNo` 走 CZ 规则；同一资产存在未完结处置单 97001
- `POST /asset/disposals/{id}/approve` · `POST /asset/disposals/{id}/complete`
  - 状态机 `draft → approved → done`；`done` 时资产置 `scrapped`（scrap）或 `idle`（transfer）
- `POST /asset/disposals/export`

### 工具与领用
- `GET /asset/tools` 分页：`{id,toolNo,name,spec,model,category,unit,warehouseId,warehouseName,deptId,deptName,purchaseDate,value,remark,status,statusText,version,createTime,updateTime}`
- `GET /asset/tools/counts` → `{in_stock,loaned,maintenance,scrapped,all}`
- `GET /asset/tools/{id}` · `POST` · `PUT` · `DELETE`（入参 `{toolNo*,name*,spec?,model?,category?,unit?,warehouseId?,deptId?,purchaseDate?,value?,remark?,status?,version?}`；编号重复 97004）
- `GET /asset/tool-loans` 分页 · `GET /asset/tool-loans/counts` → `{borrowed,returned,overdue,all}`
  · `GET /asset/tool-loans/{id}` · `POST`（201）· `PUT` · `DELETE` · `POST /asset/tool-loans/{id}/return`
  - 入参 `{toolId*,borrowerId?,borrowerName?,deptId?,loanDate?,dueDate?,purpose?,remark?,version?}`；`loanNo` 走 LY 规则
- `POST /asset/tools/export` · `POST /asset/tool-loans/export`

### 权限码与菜单
- 权限码：`asset:warehouse:*` `asset:location:*` `asset:item:*` `asset:purchaseOrder:*` `asset:receipt:*`
  `asset:ledger:*` `asset:count:*` `asset:prototype:*` `asset:prototypeLoan:*` `asset:asset:*`
  `asset:depreciation:*` `asset:disposal:*` `asset:tool:*` `asset:toolLoan:*`
  `asset:bom:*` `asset:material:*`
  （`:list` `:create` `:edit` `:delete` `:list:export`，另有 `asset:receipt:accept` `asset:prototypeLoan:return`
  `asset:toolLoan:return` `asset:disposal:approve` `asset:disposal:complete` `asset:asset:depreciate` 等动作点；
  种子对 `biz_user` 角色按 `asset:` 前缀批量授权）
- 菜单：库存与资产（StockAsset 目录）→ 进出库管理（StockManagement：采购订单 / 验收单 / 仓库 / 库存物料 /
  库存流水 / 库存盘点 / 样件管理 / 样件借出）· 资产财务（AssetFinance：固定资产 / 处置报废 / 工具领用）；
  生产资源（Resources 目录）→ 样品与物料 → **物料台账**（`menu.material` → `asset/MaterialList`）·
  **物料清单**（`menu.bom` → `asset/BomList`）

## 导航结构（工作台 + 8 业务分区 + 底部系统管理）
- 顶层（顺序即侧栏顺序）：工作台（Workbench）→ 业务中心（BizSystem）→ 生产资源（Resources）→
  库存与资产（StockAsset）→ 销售中心（SalesSystem）→ 经营与协同（Collaboration）→ 行政人事（HrSystem）→
  流程与办公（OaSystem）→ 访客与安全（VisitorSafety）→ 系统管理（System，固定在侧栏底部）。
  前端侧栏把顶级目录渲染为「区」（工作台钉顶部，各区带标题，无权限的区整区隐藏）；
  流程中心（ApprovalCenter）已解除隐藏，作为 OaSystem 子项（`/approval` 仍可深链）。
- 业务中心（BizSystem）：往来单位 Customers / 合同管理 Contracts / 任务管理 Tasks / 报告管理 Reports /
  项目管理 Projects / 财务管理 Finance（开票申请 → 结算信息 → 到账信息）。
- 生产资源（Resources）：设备资产 Equipment / 排程甘特 ProductionSchedules /
  样品与物料 AssetsSamples（样品 Samples · 物料 Materials）/ 采购管理 Procurement / 产能看板 ProductionCapacity。
- 库存与资产（StockAsset）：进出库管理 StockManagement（采购订单 PurchaseOrders → 验收单 Receipts →
  仓库 Warehouses → 库存物料 InventoryItems → 库存流水 StockLedger → 库存盘点 StockCounts →
  样件管理 Prototypes → 样件借出 PrototypeLoans）· 资产财务 AssetFinance（固定资产 FixedAssets →
  处置报废 Disposals → 工具领用 ToolLoans）。
- 销售中心（SalesSystem）：报价管理 Quotations / 报价模板 QuoteTemplates / 营收分析 SalesRevenue。
- 经营与协同（Collaboration）：客户自助 PortalHome / 在线委托 PortalOrders / 知识库 KnowledgeBase。
- 行政人事（HrSystem）：工时填报 TimesheetFill / 工时统计 TimesheetStats / 人员档案 Staff。
- 流程与办公（OaSystem）：新申请 OaApply / 我的申请 OaMy / 相关申请 OaRelated / 申请统计 OaStats /
  作业申请 WorkApply / 流程中心 ApprovalCenter / 消息中心 Messages。
- 访客与安全（VisitorSafety）：访客登记 Visits / 区域与权限 VisitorZones / 保密协议 VisitorNda / 安全巡检 SafetyInspections。
- 系统管理（System）：组织与权限 SysOrg / 基础数据 SysData / 流程管理 OaAdmin / 运维中心 SysOps / AI 中心 AiCenter
  （AI 用量监控 AiUsage `admin:ai:usage` / AI 设置 AiSettings `admin:ai:settings`；连接参数仍在 系统设置 页 AI 卡片）。
- 存量库结构归并靠 `backend/scripts/migrate_nav_zones.py`（幂等，规范结构由种子 `MENU_TREE` 推导：
  name 主键 + path 兜底，去重同名目录、归位异名同 path 残留、parent_id/sort 归一）；
  种子只保证新库直接产出目标结构（_seed_menus 不回写 parent_id/sort，保留管理员结构调整），
  旧入口 `backend/scripts/migrate_nav_batch_e.py` 转发到新脚本。

## 报告 /report
- 状态机：`uploaded 已上传待审 → approving 审批中 → approved 批准通过 → sealed 签章完成`；
  审批驳回 → `rejected 已驳回`（可重新提交），撤回 → 回 `uploaded`。
- 主链路：条目 needReport=1 自动分配 reportNo（BG 规则）→ 上传报告 → 签批（审批流 report_sign）
  → 批准自动转 PDF → 签章（seal_by/seal_time 留痕）→ sealed；**存在未签章报告条目的任务 finish 拒绝（60003）**。
- `GET /report/reports` 分页：
  `{id,reportNo,taskId,taskNo,taskItemId,itemName,contractId,contractNo,customerId,customerName,fileName,status,statusText,pdfReady,
    sealBy,sealTime,remark,conclusion,approvalInstanceId,createBy,createTime}`
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
- `POST /report/reports/{id}/ai-summary`（report:create）→ `{summary,source:"ai"}`：
  基于报告文件文本（pdf/docx/txt 可提取时，失败降级为纯任务信息上下文）+ 任务信息生成摘要草稿，不落库；
  未配置/停用 65001，调用失败 65004
- `PUT /report/reports/{id}/remark`（report:create）`{remark}`：采用 AI 摘要/人工编辑结论，
  仅 uploaded/rejected 可改（审批中/已签章锁定，否则 61002）
- `POST /report/reports/{id}/ai-assist`（report:create）`{kind:"conclusion"|"proofread"|"completeness"}`：
  AI 全文辅助（feature `report_assist`），只展示不落库。
  conclusion → `{kind,conclusion}`（结论与不确定度段落草稿，人工编辑后经 PUT conclusion 采用）；
  proofread → `{kind,issues:[{position,original,suggestion}]}`（格式/错别字清单，采纳/忽略仅 UI 态）；
  completeness → `{kind,items:[{key,ok,detail}]}`（规则先行：编号一致性/签章信息/日期/条目缺漏，合并 AI 缺失项 aiCheck）。
  未配置 65001，功能停用 65002，解析失败 65004
- `PUT /report/reports/{id}/conclusion`（report:create）`{conclusion}`：采用结论段落库（report.conclusion 字段），
  仅 uploaded/rejected 可改（否则 61002）
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
hr/TimesheetFill  hr/TimesheetStats
sales/QuotationList  sales/QuoteTemplateList
approval/TodoList
admin/UserList  admin/RoleList  admin/MenuList  admin/DictList
admin/NumberRuleList  admin/AuditLogList  admin/DeptList  admin/FlowDefList
admin/AiUsage  admin/AiSettings
asset/PurchaseOrderList  asset/ReceiptList  asset/WarehouseList  asset/InventoryItemList
asset/StockLedgerList  asset/StockCountList  asset/PrototypeList  asset/PrototypeLoanList
asset/FixedAssetList  asset/DisposalList  asset/ToolList
asset/MaterialList  asset/BomList
project/ProjectList  production/ScheduleBoard
```

## 字典（sys_dict）
`customer_type / customer_grade / contract_type / task_type / biz_block / pay_cycle / delivery_way / pay_type / oa_category / purchase_method / supply_category / warehouse / tender_method / partner_attachment_category / stock_category / stock_reason / prototype_kind / asset_category / depreciation_method / disposal_type`
读取：`GET /admin/dict/items?type={code}`（仅 enabled，按 sort 排序）

## 种子账号
| 用户名 | 密码 | 角色 |
|---|---|---|
| admin | Admin@123456 | 超级管理员 |
| manager1 | Test@123456 | 部门负责人（审批人演示） |
| leader1 | Test@123456 | 分管领导（审批人演示） |
