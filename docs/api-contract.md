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

- 7xxxx 审批补充（F5）：70005 流程已启用，不允许人工直通（须走审批）· 70006 该类单据的流程已停用，不允许提交审批

## 鉴权 /auth
- `GET /auth/captcha`（免登录）→ `{captchaId,svg}`：4 位随机字符 SVG（排除 0/O/1/I/L），Redis 存 5 分钟、
  验证一次性销毁；同一 captchaId 连续错 3 次作废；非生产环境（ENV≠prod）额外回显 `debugText` 便于自动化测试
- `POST /auth/login` `{username,password,captchaId,captchaText,remember?}` → `{access_token,refresh_token,token_type,remember,user}`
  （user 含 `mfaEnabled`）；验证码错误或过期 20009（不计入密码失败锁定）；
  **`remember`（默认 false）= 登录页「记住登录状态」**：true → refresh token **30 天**（claim `rem=true`，
  前端存 localStorage，跨浏览器重启免登录）；false → **12 小时**（claim `rem=false`，前端存 sessionStorage，
  关浏览器即失效）；access token 固定 15 分钟，由前端在 20001 时静默续期。
  若用户已开启 MFA 则不发 token，改回 `{mfaRequired:true,mfaToken,channels:[{channel:"sms"|"email",target(掩码)}]}`
- MFA 二步验证（mfaToken 为 5 分钟 typ=mfa_pending JWT + Redis 一次性凭证）：
  - `POST /auth/mfa/send` `{mfaToken,channel}` → `{sent,cooldown:60,mode}`：6 位数字码存 Redis 5 分钟，
    每通道 60 秒冷却（429/20013）；通道未配置时非生产走调试通道并回显 `debugCode`（生产绝不回显，未配置报 90001）
  - `POST /auth/mfa/verify` `{mfaToken,code}` → 与 login 相同结构；错码 20011，连续错 5 次作废本次登录（20010）；
    **会话口径沿用登录时的 `remember`**（mfa_pending claim `rem`）
  - `POST /auth/mfa/toggle`（登录）`{enabled}` + `X-Step-Up-Token` 头 → `{mfaEnabled}`；
    开启前须已登记手机或邮箱（否则 20014）
- `POST /auth/refresh` `{refresh_token}` → `{access_token,refresh_token,token_type,remember,user}`
  （旋转：旧 refresh_token 立即吊销；**新 token 的会话口径继承原 token 的 `rem`**，不按默认值重签；
  前端**必须把返回的新 refresh_token 存回**，否则下一次续期会拿到已吊销的旧 token）
- `POST /auth/logout`（可带 `{refresh_token}` 吊销）
- `POST /auth/password` `{old_password,new_password,refresh_token?}`（新密码至少 8 位；原密码错误 20004）
  —— **改密后吊销该用户其余全部登录会话**（会话最长 30 天，不吊销等于旧密码仍可用）；
  带上 `refresh_token` 时保留该设备会话（当前设备改密后不强制下线）
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
- 流程与事件开关（F5）：`GET /admin/automation`（admin:automation:list）→ `{flows:[...],events:[...]}`；
  `PUT /admin/automation`（admin:automation:edit）`{flows:[{bizType,enabled}],events:[{key,enabled}]}` → 同结构。
  详见「流程驱动 / 事件驱动（F5）」章节
- `GET /admin/audit-logs`（分页）· `GET /admin/audit-logs/export`（同检索参数 xlsx，沿用 admin:audit:list）
  · `GET /admin/audit-logs/{id}/evidence`（单条证据：链上位置 + 重算哈希比对）
  列表 / 证据 / 导出均含 **`ip`** 与 **`ipRegion`**（IP 属地，后端离线 ip2region 库解析，
  如「安徽省 宣城市」；回环→「本机」，内网/保留地址→「内网」，查不到→空串）
- `GET /admin/login-logs`（分页，沿用 admin:audit:list）
  → `{items:[{id,username,success,reason,ip,ipRegion,userAgent,createTime}],total,page,size}`
  （`q` 匹配用户名；`filters[success]=1/0` 只看成功 / 失败；默认按 id 倒序）
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
- `GET /approval/flow-capabilities`（**仅登录**）→ `{items:[{bizType,label,managed,enabled,definitionReady,submitFrom[],statuses:{approving,approved,rejected,withdrawn},submitPerm}]}`：
  流程能力清单，供各单据页判断「提交审批」还是「人工直通」；`enabled` 来自流程总开关 `flow.<bizType>.enabled`。
  见「流程驱动 / 事件驱动（F5）」章节
- 错误码：70001 无待办 / 70002 非当前审批人 / 70003 意见必填 / 70004 已有进行中实例 / 70005 流程已启用不允许人工直通 / 70006 流程已停用不允许提交审批

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
- 经营与协同（Collaboration）：知识库 KnowledgeBase / 在线任务委托 EntrustList / 客户自助账号 CustomerAccounts /
  客户方人员备案 PartnerStaff。
  **「客户自助 PortalHome / 在线委托 PortalOrders」是外部门户入口，已在内网导航隐藏**
  （`HIDDEN_MENUS` 强制 visible=0，权限点仍由菜单承载）—— 门户是独立认证的第二套外壳，
  内网人员点进去只会跳到门户登录页；门户用户仍可直接访问 `/portal`。
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

## 流程驱动 / 事件驱动（F5）

系统不再是"事后记账本"：业务单据由**流程**推动状态流转，由**业务事件**驱动跨域联动；两者都可被管理员**开关**。

### 1. 流程注册表（后端 `app/modules/approval/registry.py`）

17 类单据统一登记在 `BINDINGS`（`FlowBinding`），字段：`bizType` `label` `modelPath` `definitionCode`
`managed`（是否域内自管状态回写）`submitFrom`（可发起审批的状态）`approving/approved/rejected/withdrawn` 四个状态口径
`submitPerm` `docNoField` `note` `passThrough` `passThroughStatus` `passThroughHook` `onApproved` `onRejected`。

| bizType | 名称 | 流程定义 code | 发起状态 | 审批中 | 通过后 | 驳回 | 发起权限 |
|---|---|---|---|---|---|---|---|
| contract | 合同 | contract_approve | （历史） | — | — | — | contract:contract:submit |
| task | 任务立项 | 按 bizType 解析 | （历史） | — | — | — | task:task:submit |
| report | 检测报告 | report_sign | （历史） | — | — | — | report:report:submit |
| sales_quotation | 销售报价 | quote_approve | （历史） | — | — | — | sales:quotation:submit |
| settlement | 结算单 | 按 bizType 解析 | （历史） | — | — | — | finance:settlement:submit |
| invoice | 发票 | invoice_apply | （历史） | — | — | — | finance:invoice:submit |
| purchase_request | 采购申请 | purchase_request_approve | （历史） | — | — | — | procurement:request:submit |
| purchase_contract | 采购合同 | purchase_contract_approve | （历史） | — | — | — | procurement:contract:submit |
| tender_award | 定标 | tender_award_approve | （历史） | — | — | — | procurement:tender:award |
| oa | OA 申请 | 按实例钉版本 | （历史） | — | — | — | oa:apply:submit |
| **project** | 项目立项 | project_approve | draft / rejected | approving | planning | rejected | project:submit |
| **timesheet** | 工时填报 | timesheet_approve | draft / rejected | approving | approved | rejected | hr:timesheet:submit |
| **asset_receipt** | 到货验收 | asset_receipt_approve | draft / rejected | approving | accepted | rejected | asset:receipt:submit |
| **asset_disposal** | 资产处置 | asset_disposal_approve | draft / rejected | approving | approved | rejected | asset:disposal:submit |
| **payment** | 回款单 | payment_confirm | draft / rejected | approving | confirmed | rejected | finance:payment:submit |
| **report_seal** | 报告用章 | report_seal_approve | approved | sealing | seal_approved | approved | report:seal:apply |
| **visitor_visit** | 访客预约 | visitor_visit_approve | pending | approving | approved | rejected | visitor:visit:submit |

- **通过后的副作用**（`onApproved` / `onRejected` 钩子）：到货验收通过才生成入库流水；资产处置通过才可核销；
  回款确认后才核销结算单应收；工时审批通过才计入项目成本。
- **未配置启用的流程定义** → 该类单据按**人工审核口径直通**（`passThrough`），落到 `passThroughStatus`，不产生审批实例。
- **流程总开关关闭**（`flow.<bizType>.enabled = 0`）→ 该类单据**不能提交审批**，接口返回 **70006**；
  同时**恢复人工直通后门**（原人工动作端点不再被 70005 拦截）。

### 2. 流程与事件开关（管理端）

- `GET /admin/automation`（`admin:automation:list`）→
  `{flows:[{bizType,label,definitionCode,definitionReady,definitionName,managed,switchKey,enabled,submitFrom[],statuses:{approving,approved,rejected,withdrawn},submitPerm,note}],events:[{event,label,description,switches:[{key,name,critical,enabled}]}]}`
- `PUT /admin/automation`（`admin:automation:edit`）`{flows:[{bizType,enabled}],events:[{key,enabled}]}` → 同结构。
  落 `sys_config`，写入即生效；变更写 `sys_audit_log`。
- 前端页面：系统管理 → 流程与事件开关（`admin/AutomationSettings`，菜单 `menu.automation`）。

### 3. 流程能力清单（供单据页判断提交还是人工直通）

- `GET /approval/flow-capabilities`（**仅登录**，无额外权限）→ `{items:[{bizType,label,managed,enabled,definitionReady,submitFrom[],statuses:{...},submitPerm}]}`
  前端 `useFlowCapability()` 缓存该结果：流程启用 → 显示「提交审批」；流程停用 → 显示历史人工动作（验收 / 批准 / 签章）。

### 4. 流程驱动的单据端点（F5 新增）

| 端点 | 权限 | 说明 |
|---|---|---|
| `POST /project/projects/{pid}/submit` | project:submit | 提交立项审批；流程停用 → 70006 |
| `POST /hr/timesheets/{tid}/submit` | hr:timesheet:submit \| hr:timesheet:create | 提交工时审批 |
| `POST /finance/payments/{pid}/submit` | finance:payment:submit | 提交回款复核 |
| `POST /asset/receipts/{rid}/submit` | asset:receipt:submit | 提交到货验收 |
| `POST /asset/disposals/{did}/submit` | asset:disposal:submit | 提交资产处置 |
| `POST /report/reports/{rid}/seal-apply` | report:seal:apply | 提交用章申请（申请 ≠ 签章，签章仍走 `POST /report/reports/{id}/seal`） |
| `GET /finance/payments/counts` | finance:payment:list | 回款页签计数 `{all,draft,approving,confirmed,rejected}` |

- 已有历史人工端点在流程启用时被拦截并返回 **70005**（例：`POST /asset/receipts/{rid}/accept`、
  `POST /report/reports/{id}/seal`），需改走提交审批；流程停用后恢复可用。

### 4.1 填报端的「保存草稿 / 提交审批」约定（前端强制，全站一致）

凡注册在 `BINDINGS` 的单据，其**填报弹窗/详情页**必须提供两个明确动作，避免填报者误解：

| 按钮 | 文案键 | 行为 |
|---|---|---|
| 保存草稿 | `common.action.saveDraft` | 只落库（状态 `draft`），**不**发起审批 |
| 提交审批 | `common.action.submitApproval` | 落库后立即调 `POST …/submit` 发起审批（primary） |

- **没有草稿态的单据**（`settlement` / `invoice` / `report_seal` / `visitor` 登记）：只有**一个** primary 按钮，
  文案必须是「提交审批」，**不得**写「提交」或「保存」；结算单等在表单上方用 `el-alert` 说明
  "提交后立即发起审批"（`finance.settlement.submitTip`）。
- 「提交审批」按钮按权限点隐藏（`v-permission`）；`v-permission` 支持**数组**表示"任一权限满足"。
- 流程总开关关闭时（`GET /approval/flow-capabilities` 的 `flowEnabled(bizType)` 为 false）只显示「保存草稿」。
- 新增单据类型时：先在 `registry.py::BINDINGS` 登记（`submit_from` 必须含 `draft`），再按上表加两个按钮。

### 5. 事件目录与触发开关

事件总线 `app/common/events.py` 在**同一事务内同步派发**；每个处理器可挂开关键 `event.trigger.<事件>.<处理器>`，
默认开启，关闭即不再执行该联动。

| 事件 | 用途 |
|---|---|
| ApprovalCompleted / ApprovalRejected / ApprovalWithdrawn | 审批通过 / 驳回 / 撤回 → 单据状态回写与后续联动 |
| ApprovalTodoCreated | 生成待办 → 站内信 / 企微 / 短信推送（`event.trigger.ApprovalTodoCreated.notify.todo`，非关键） |
| TaskAssigned | 任务分配到人 → 提醒被指派人 + **自动推进项目状态**（`event.trigger.TaskAssigned.project.start`） |
| FlowStarted | 单据提交审批 → 广播「进入审批」 |
| DocumentStatusChanged | 任意单据状态迁移 → 跨域数据流转 |
| SchedulePlanPublished | 排程方案发布 → 同步甘特与任务计划日期 |
| TaskCompleted | 任务完成 → 自动生成结算单等下游单据 |

- 开关清单由 `GET /admin/automation` 的 `events[].switches` 给出；`critical=true` 的处理器失败会回滚业务事务。

## F6 对外门户扩展（门户专业化 + 访客闭环 + 移动优先）

### 1. 门户新增端点

| 端点 | 权限/登录 | 说明 |
|---|---|---|
| `POST /portal/auth/refresh` | 门户 token | 刷新门户 token（refresh token 存 Redis `portal_refresh:{jti}`，7 天；`typ=portal_refresh`、`aud=portal`） |
| `GET /portal/account` · `PUT /portal/account` | 门户登录 | 读取/修改本账号资料（公司名称、联系人、电话、邮箱） |
| `POST /portal/account/password` | 门户登录 | 修改密码（旧密码校验） |
| `GET /portal/branding` | 公开 | 站点名/Logo/公司全称/地址/电话/邮箱/备案号（门户页脚用） |
| `GET /portal/tenders?page=&size=` | 公开 | 公告列表分页（原为一次拉全量） |

### 2. 门户访客预约（`app/modules/portal/visit_router.py`，prefix `/portal`）

| 端点 | 登录 | 说明 |
|---|---|---|
| `GET /portal/hosts?q=` | 公开 | 被访人选择；**只暴露姓名/部门/职位**，不暴露手机号/邮箱 |
| `GET /portal/zones` | 公开 | 可申请区域（仅 enabled） |
| `POST /portal/visits` | 门户登录 + `perm_scope` 含 `visit` | 提交预约 → `vis_visit(status=pending, source=portal)` → 提交审批引擎 |
| `GET /portal/visits` · `GET /portal/visits/{id}` | 门户登录 | 我的预约 / 详情（审批时间线、当前节点、凭证状态） |
| `POST /portal/visits/{id}/cancel` | 门户登录 | 取消（仅 pending/approving） |
| `GET /portal/visits/{id}/credential` | 门户登录 | 通行凭证（凭证号/有效期/授权区域） |
| `GET /portal/visits/{id}/credential/qr` | 门户登录 | 凭证二维码（`image/svg+xml`；segno 生成，零传递依赖） |
| `GET /portal/visits/{id}/pass?code=` | 公开 | 扫码落地页（校验凭证码） |
| `POST /portal/visits/{id}/checkin` · `.../checkout` | 门户登录 | 访客自助签到/签离；**拒绝放行也必须留痕**（`except BizException: db.commit(); raise`） |

### 3. 门户经营数据（`app/modules/portal/experience_router.py`，prefix `/portal`）

| 端点 | 说明 |
|---|---|
| `GET /portal/progress` | 进度看板：委托/任务/结算/发票/回款聚合，按账号绑定往来单位过滤 |
| `GET /portal/reports` | 已归档报告列表（`rpt_report` join `task_task`），**不含内部意见与审批人** |
| `POST /portal/reports/{id}/download-code` | 生成一次性下载码（Redis `portal_dl:{rid}`） |
| `GET /portal/reports/{id}/download?code=` | 下载报告文件（码校验后即焚） |
| `GET /portal/billing` | 结算 / 开票 / 回款状态聚合 |
| `GET /portal/handovers` | 样品样车借还记录 |

**隔离口径**：一律按 `partner_user.customer_id` 过滤；报告只暴露 `sealed/seal_approved/approved` 状态；下载码一次性。

### 4. 动态审批人类型（`FORM_USER` / `FORM_ROLE` / `FORM_DEPT_LEADER`）

门户单据的审批人**每单不同**（如访客单的被访人由表单指定），因此审批引擎新增三类「按表单字段解析」的审批人：

| 类型 | `approver_value` 含义 | 解析 |
|---|---|---|
| `FORM_USER` | 流程变量名（如 `hostUserId`），值为用户 id | `select(User).where(id==v, enabled)` |
| `FORM_ROLE` | 流程变量名，值为角色 code | 复用 `_resolve_role_users` |
| `FORM_DEPT_LEADER` | 流程变量名，值为部门 id | `org.dept_leader_ids(db, dept_id)` |

- 可用变量键由流程定义的 `variables_schema`（JSON：`{key: {type, label}}`）声明，设计器据此给出下拉。
- 外部发起人不是 `sys_user`：引擎用 `FlowInitiator(id=0, name="合作方·XX")`，`approval_instance.initiator_id = 0`（真实用户 id 从 1 起，不冲突）；
  组织类节点（`DEPT_LEADER` 等）在门户单据上会 `auto_pass` 跳过——流程设计时需注意。
- `condition` 节点按 `instance.variables` 路由，敏感区域加签用条件节点表达（如 `securityLevel >= 3`）。

### 5. 访客单接入审批引擎

- `vis_visit` 新增 `flow_instance_id`（BigInteger，nullable，index）与状态 `approving`；迁移 `n7a2b3c4d5e6_portal_visitor_flow.py`（**手写**，见 CLAUDE.md 已知坑）。
- 流程绑定：`biz_type = visitor_visit`，`submitFrom=(pending,)`，`approving→approved/rejected`，`passThrough=True`（流程未配置或停用时直通）。
- 通过后的副作用（`app/modules/visitor/flow_handlers.py`）：置 `approved` + 下发通行凭证 + 短信通知访客 + 通知被访人；
  驳回置 `rejected`。引擎回写时同步写 `vis_approval` 镜像行，保持访客列表的审批历史 UI 不变。
- 域内 `POST /visitor/visits/{vid}/approve` 在访客单**已挂流程实例**时返回 **70005**（与 F5 其他单据同口径：流程已启用不允许人工直通）；
  流程停用或未配置时恢复可用。
- 总开关 `flow.visitor_visit.enabled`（`GET/PUT /admin/automation`）。

### 6. 错误码（F6 新增）

| 码 | 含义 |
|---|---|
| 98010 | 访客预约状态不允许该操作 |
| 98011 | 无权访问该访客预约 |
| 98012 | 凭证已过期或无效 |
| 98013 | 报告下载码无效或已使用 |

前端镜像在 `src/api/types.ts`。

## B9 检测机构合规基线（审计证据链 + 电子签名 + 人员授权）

> 对应《第三方检测机构运营平台合规开发原则》与《人力资源管理模块功能说明》。
> 逐条对照见 [`compliance-baseline.md`](compliance-baseline.md)。三个控制点：
> **C1 审计证据链**（字段级 + 哈希链 + 不可清空）、**C2 电子签名密码学绑定 + 签章后锁定**、**C3 人员授权台账 + 拦截点前置**。

### 1. C1 审计证据链

**`sys_audit_log` 表结构变更**（继承 `AppendOnlyModel`，**物理删除** `deleted` / `version` / `update_time` / `update_by`）

| 新增列 | 类型 | 说明 |
|---|---|---|
| `field_name` | String(64) | 变更字段名（合规 2.2「哪个字段」） |
| `old_value` | Text | 变更前值 |
| `new_value` | Text | 变更后值 |
| `reason` | Text | 变更原因 |
| `user_agent` | String(255) | 终端 UA |
| `chain_seq` | BigInteger **唯一索引** | 链上序号；**存量行为 NULL**（不回填，不伪造历史） |
| `prev_hash` | String(64) | 上一行哈希 |
| `row_hash` | String(64) | 本行哈希 |
| `hash_alg` | String(16) | 哈希算法标识（`HMAC-SHA256`） |

- `create_time` 精度改 **`DATETIME(3)`**（毫秒）。**row_hash 含时间戳，秒精度会让整链重算必失败** —— 迁移 / 模型 / `tests/conftest.py::_ensure_columns` 三处必须同时改。
- `row_hash = HMAC-SHA256(prev_hash ‖ canonical(row))`；`canonical` 按固定字段序生成 `name=value\n` 串，**字段重排 → 哈希不同**。
- 链头表 `sys_audit_chain_head`（单行 `chain_key='main'`）：`last_seq` / `last_hash` / `last_row_id` / `anchored_seq` / `anchored_hash` / `anchored_at` / `write_failures` / `key_version`。
  **链头是唯一权威游标**（`SELECT … FOR UPDATE NOWAIT`），**不用 `MAX(id)`** —— 并发下 `MAX(id)` 必然产生同 `prev_hash` 分叉。
- 失败台账 `sys_audit_failure`（只追加）：审计写不进去时留痕，**证据缺口本身也要留痕**。
- 迁移里加 `BEFORE UPDATE` / `BEFORE DELETE` 触发器 `SIGNAL SQLSTATE '45000'` 物理阻断 `sys_audit_log` 改删；`downgrade()` 必须 `DROP TRIGGER`。
- **`record()` 保持全部旧参数**，新增 keyword-only 且带默认值（`field_name` / `old_value` / `new_value` / `reason` / `user_agent` / `strict`）→ **全仓 283 处调用点零改动**。
  - 默认尽力而为：失败只记 `sys_audit_failure`，不阻断业务；
  - `strict=True`（或全局开关 `audit.strict.enabled`）时抛 **30005**，由调用方 `db.commit()` 回滚整个事务。
  - `trace_id` / `ip` / `user_agent` 缺省从 `app/core/reqctx.py` 的请求上下文取（`server_now` 每请求缓存一次）。

**客户端 IP 口径（`app/core/client_ip.py`）**

- 审计里的 `ip` / `sys_login_log.ip` / NDA 签名绑定的 IP 一律是**真实客户端 IP**，由 `client_ip(request)` 从 `X-Forwarded-For` 还原：
  - **跳数模式**（默认）：从链右侧往左数 `TRUSTED_PROXY_HOPS` 跳（默认 `2` = 上层网关 + 容器 nginx）；链短于跳数时取最左一条。
  - **网段模式**：配了 `TRUSTED_PROXY_CIDRS` 时以网段判定（优先于跳数），从右往左跳过受信任代理网段。
  - 回落链：无 `X-Forwarded-For` → `X-Real-IP` → TCP 对端地址。`TRUST_PROXY_HEADERS=false` 或 `TRUSTED_PROXY_HOPS=0` 时**不采信任何代理头**。
- **不要直接用 `request.client.host`** —— 应用在容器 nginx 之后，那只是 nginx / 网关容器的内网 IP。
- nginx 侧已透传 `X-Real-IP` / `X-Forwarded-For`（追加语义）；**网关侧也必须用追加语义**（nginx：`$proxy_add_x_forwarded_for`），原样透传客户端自带头会让链首可伪造。

**端点**（`app/modules/admin/router.py`，权限 `admin:audit:list`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/audit-logs` | 列表；出参新增 `fieldName` `oldValue` `newValue` `reason` `userAgent` `chainSeq` `rowHash` `hashAlg` `username` |
| GET | `/admin/audit-logs/chain/verify?mode=full\|since_anchor&fromSeq=` | 链完整性校验 → `{ok, mode, checked, firstSeq, lastSeq, headSeq, headHash, headMatchesLastRow, brokenAt:{seq,rowId,reason,expected,actual}, anchor:{seq,hash,at,file,truncated,match}, legacyRows, writeFailures, hashAlg, keyVersion}` |
| GET | `/admin/audit-logs/anchors` | 锚点历史（倒序）→ `{items:[{seq,hash,at,file}]}` |
| POST | `/admin/audit-logs/anchor` | 立即锚定当前链头 → `{seq, hash, at, file}` |
| GET | `/admin/audit-logs/{row_id}/evidence` | 单条证据详情 → 链上位置 + `recalculatedHash` + `hashValid`（存量行 `chainSeq` 为空 → `hashValid=false`） |
| GET | `/admin/audit-logs/export` | 导出新增字段级列与链序号 |

- `brokenAt.reason` 取值：`seq_gap`（断号 = 有行被删）/ `prev_hash_mismatch`（链接断裂）/ `row_hash_mismatch`（内容被改）/ `head_mismatch`（链头被改）。
- **锚点写在 DB 之外的文件** `backend/data/audit-anchor/anchor-YYYYMMDD.txt`（只追加，每行 `seq|hash|ts|hmac`）→ 整链被重写/截断时锚点对不上。DB 里的 `anchored_seq/anchored_hash` 只用于 UI 展示，**校验以文件为准**。备份成功后自动锚定。

**「一键清空」变更**（`app/modules/maintenance/service.py`）

- `sys_audit_log` / `vis_access_log` / `vis_nda` **移出清空清单** → 新常量 `RETAINED_AUDIT_TABLES`；`purge()` 返回体新增 `retainedAuditTables` 公开保留清单。
- `hr_authorization` / `hr_authorization_event` **必须登记进清空清单**（否则编号序列清零后撞唯一键，见 CLAUDE.md 已知坑）。

### 2. C2 电子签名密码学绑定

**`app/core/signature.py`**：HMAC-SHA256 签名/验签。密钥 `sha256("bizsys:evidence-signature:" + jwt_secret)`（与 `app/core/crypto.py` 同源、**域分隔前缀不同**）；`hmac.compare_digest` 比对。固定字段组 `NDA_FIELDS` / `REPORT_SEAL_FIELDS`。

**NDA**（`vis_nda` 新增列 `signed_by_id` `signed_by_name` `signed_ip` `sign_alg` `sign_version`）

- 签名绑定内容：`biz_type + nda_no + 姓名/单位/证件号/标题 + 签署时间 + 签署人 id/姓名 + 真实 IP + 手写图 sha256`。
  **用单号而不是自增 id** —— id 在 insert 前未知会造成循环依赖。
- 真实 IP 从 `reqctx.current().ip` 取（原先 `ip=""` 硬编码为空）；该值已是**还原后的真实客户端 IP**（见上文「客户端 IP 口径」）。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/visitor/nda/{nid}/verify` | → `{id, ndaNo, valid, verdict, alg, signedBy, signedAt, signedIp, reason}` |

- `verdict`：`valid`（签名与内容一致）/ `invalid`（内容被改或签名被伪造）/ **`legacy-unverifiable`**（存量行 —— 无密钥 sha256，离线可复算，**不能当密码学证据**）。
- 存量行迁移时标 `sign_version='legacy-sha256'`；前端打灰标「不可作为密码学证据」。
- 验签失败时写审计（`visitor` / `nda_verify`）。

**报告签章**（`rpt_report` 新增列 `seal_by_name` `seal_content_hash` `seal_signature` `seal_alg` + 三级角色 `preparer_id/name` `reviewer_id/name` `approver_id/name`）

- 内容哈希 `compute_content_hash(db, r)` = `sha256(最终PDF字节sha256 | report_no | task_item_id | sha256(conclusion))`；文件丢失返回空串（只能验签名）。
- **顺序铁律**：内容哈希必须在 `apply_seal_watermark()` **之后**算 —— 盖章会产出新 PDF，先算必然对不上。
- `seal_time` 列是 `DATETIME(0)`，签名载荷按**秒口径**计算。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/report/reports/{rid}/seal/verify` | → `{id, reportNo, signatureValid, contentMatch, contentUnavailable, alg, sealedBy, sealedAt, contentHash, reason}` |

- `signatureValid` = 签名未被伪造且单据关键字段未被改；`contentMatch` = 签章后内容没被改；`contentUnavailable` = 最终 PDF 已丢失。
- **签章后锁定**：`report/service.py::assert_report_editable()`，`status == 'sealed'` 抛 **61003**（统一挂到 `update_remark` / `update_conclusion` / AI 摘要采用 / AI 辅助采用）。

### 3. C3 人员授权台账

**表 `hr_authorization`**（继承 `BaseModel`；单号前缀 `AU`）

| 列 | 说明 |
|---|---|
| `auth_no` | 授权编号（唯一） |
| `user_id` / `user_name` | 被授权人 |
| `dept_id` / `dept_name` | 被授权人部门（新建/编辑时从 `sys_user` 回填） |
| `auth_type` | `test_item` 检测项目 / `device` 设备操作 / `report_role` 报告角色 / `signer` 授权签字 |
| `role_code` | `preparer` 编制 / `reviewer` 复核 / `approver` 批准 / `signer` 签字 |
| `scope_method` / `scope_params` | 检测方法/标准 + 方法参数 |
| `scope_device_id` / `scope_device_name` | 具体设备 |
| `scope_domain` | 业务域/专业域 |
| `scope_json` | 范围快照 —— **只做展示兜底，不做过滤依据** |
| `valid_from` / `valid_to` | 有效期 |
| `status` | `draft` / `approving` / `confirmed` / `active` / `suspended` / `expired` / `revoked` / `rejected` |
| `applicant_id/name` `approver_id/name` `approved_at` `activated_at` `flow_instance_id` `last_reason` `remark` | 申请与审批 |

索引：`(user_id, auth_type, status)`、`(auth_type, status)`、`(status, valid_to)`。

**表 `hr_authorization_event`**（继承 `AppendOnlyModel`，**只追加**，无 `deleted`/`version`）：`authorization_id` `auth_no` `event_type` `from_status` `to_status` `operator_id/name` `reason` `effective_at` `snapshot` → 支撑**回放任一历史时点的授权状态**。

**状态机**：`draft → confirmed → active ⇄ suspended → expired / revoked`（另有 `approving` / `rejected`）。
暂停 / 撤销 / 过期**原因必填**；每次变更写事件表 + **字段级审计**（`field_name='status'`、`old_value`、`new_value`、`reason`、`strict=True`）。

**端点**（`app/modules/hr/authorization_router.py`，prefix `/hr`）

| 方法 | 路径 | 权限码 | 说明 |
|---|---|---|---|
| GET | `/hr/authorizations` | `hr:authorization:list` | 列表；`q` 搜 `auth_no`/`user_name`/`scope_*`/`remark`；`filters[auth_type]` `filters[role_code]` `filters[user_id]` `filters[dept_id]` `filters[status]`；`range[valid_from]` `range[valid_to]`；`sort` |
| GET | `/hr/authorizations/counts` | `hr:authorization:list` | 状态页签计数（含 `all`） |
| GET | `/hr/authorizations/export` | `hr:authorization:export` | xlsx（与列表同一套过滤口径） |
| GET | `/hr/authorizations/options/users?q=` | `hr:authorization:list` | 被授权人远程检索 → `[{value,label,sub,deptName}]` |
| GET | `/hr/authorizations/{aid}` | `hr:authorization:list` | 详情（附 `timeline`） |
| GET | `/hr/authorizations/{aid}/timeline` | `hr:authorization:list` | 变更轨迹（只追加，倒序） |
| GET | `/hr/authorizations/{aid}/state-at?at=` | `hr:authorization:list` | **回放某历史时点的授权状态** |
| POST | `/hr/authorizations` | `hr:authorization:create` | 新建（草稿）；201 |
| PUT | `/hr/authorizations/{aid}` | `hr:authorization:edit` | 编辑（仅 `draft` / `rejected`） |
| POST | `/hr/authorizations/{aid}/submit` | `hr:authorization:submit` | 提交审批（**不允许人工直通**：未配置流程定义直接报错） |
| POST | `/hr/authorizations/{aid}/activate` | `hr:authorization:activate` | 生效（`confirmed → active`） |
| POST | `/hr/authorizations/{aid}/suspend` | `hr:authorization:activate` | 暂停（**原因必填**） |
| POST | `/hr/authorizations/{aid}/resume` | `hr:authorization:activate` | 恢复（`suspended → active`） |
| POST | `/hr/authorizations/{aid}/revoke` | `hr:authorization:revoke` | 撤销（**原因必填**；立即生效） |
| POST | `/hr/authorizations/{aid}/expire` | `hr:authorization:revoke` | 过期（**原因必填**） |

**拦截点前置**（`app/modules/hr/authorization.py::assert_authorized`）

| 位置 | 校验 |
|---|---|
| `report/router.py:224`（报告编制） | 编制人须有 `report_role=preparer` 授权（+ 方法维度 = `TaskItem.std`） |
| `report/router.py:307`（报告用章） | 用章人须有 `report_role=approver` 或 `signer` 授权 |
| `task/process_router.py:249,257`（派工 / 派设备） | 受派人须有该任务方法的 `test_item` 授权；派设备须有 `device` 授权 |
| `task/router.py:974`（检测进度录入） | 录入人须有 `test_item`（+ `device`）授权 |

- **超管旁路**（`role_code='super'`）+ **`sys_config` 双开关** `auth.enforce.report` / `auth.enforce.task`（默认开）。
- **不做跨请求缓存**（撤销必须立即生效）；请求内 memo 走 `db.info`。
- 越权抛 **63007**；授权过期抛 **63009**。

**SoD 动态探测**（`report/service.py::resolve_report_roles`）：从签批实例的 `approval_record` 取通过序列 → 编制/复核/批准；`node_count >= 2` 时**硬拦截**（三人不得同人 + 各自持对应角色授权 → 63008），否则**降级告警**写审计。管理员在「流程设置」给 `report_sign` 发新版本加节点 → `flow_version` 递增 → **代码零改动即变硬拦截**。

**流程绑定**（`app/modules/approval/registry.py`，BINDINGS 共 **18** 条）

```
FlowBinding(biz_type="hr_authorization", definition_code="hr_authorization_approve",
            submit_from=("draft","rejected"), approving_status="approving",
            approved_status="confirmed", rejected_status="rejected",
            pass_through=False, submit_perm="hr:authorization:submit", doc_no_field="auth_no")
```

`pass_through=False` → 未配置流程定义时提交直接报错，**授权不允许绕过审批**。总开关 `flow.hr_authorization.enabled`（`GET/PUT /admin/automation`）。
种子流程 `hr_authorization_approve`：科室（`DEPT_LEADER`）→ 技术负责人 `tech1` → 质量负责人 `qa1`。**不用 ROLE 节点**（无人拥有该角色时引擎会"解析失败自动跳过" → 审批形同虚设）。

### 4. B9 新增错误码

| 码 | 常量 | 含义 |
|---|---|---|
| 30003 | `ADMIN_AUDIT_CHAIN_BROKEN` | 审计链校验不通过（断链/篡改） |
| 30004 | `ADMIN_AUDIT_CHAIN_LOCK_TIMEOUT` | 审计链写入锁冲突，请重试 |
| 30005 | `ADMIN_AUDIT_WRITE_FAILED` | 审计写入失败，操作已回滚 |
| 61003 | `REPORT_SEALED_LOCKED` | 报告已签章锁定，需作废重做 |
| 61004 | `REPORT_SIGNATURE_INVALID` | 签章签名或内容哈希校验失败 |
| 63005 | `HR_AUTH_INVALID_STATE` | 授权状态不允许该操作 |
| 63006 | `HR_AUTH_NOT_FOUND` | 授权记录不存在 |
| 63007 | `HR_AUTH_DENIED` | 无相应授权（越权拦截） |
| 63008 | `HR_AUTH_SOD_VIOLATION` | 职责分离冲突（编制/复核/批准不得同人） |
| 63009 | `HR_AUTH_EXPIRED` | 授权已过期 |
| 98014 | `VISITOR_NDA_SIGNATURE_INVALID` | NDA 签名校验失败 |

前端镜像在 `src/api/types.ts`（**新增业务错误码必须同时在两侧登记**）。

### 5. 种子与菜单

- 菜单：`menu.hrCenter` 下新增 `menu.authorization` → 路径 `/hr/authorizations`，componentKey `hr/AuthorizationList`，权限 `hr:authorization:list`；按钮权限 `create` / `edit` / `submit` / `approve` / `activate` / `revoke` / `export`。
  `menu.staff`（`hr:staff:list` 占位页，承载 HR L1 人员档案）**保留不动**。
- 角色：新增 `hr_manager`（人事管理员，挂全部 `hr:authorization:*`）；`biz_user` 只加 `hr:authorization:list`（只读反查）—— 授权管理属质量/人事职责，与检测员**职责分离**。
- 账号：`tech1`（技术负责人）/ `qa1`（质量负责人）/ `hr1`（人事管理员），密码 `Test@123456`。
- 编号规则：新增 `hr_authorization` → 前缀 `AU`。

## B10-1 HR L1 组织架构 + 员工主数据 + 人事事务

> 对应《人力资源管理模块功能说明》**L1 基础人事管理**。组织架构与员工主数据是其余所有域的地基 ——
> 部门树决定审批链解析（`DEPT_LEADER` / `SUPERVISOR_CHAIN` 走 `sys_dept.parent_id`），
> 员工在职状态决定 B9 授权台账是否应当继续生效，离职当日清权目前**由本批次首次落进代码**。
>
> **单一写入口原则**：部门只有一张表 `sys_dept`（扩列），写入口统一留在 `POST/PUT /admin/depts`；
> HR 域只提供**岗位**（`hr_position`）与**变更轨迹**（`hr_org_change`），不新建部门表、不开双轨。

### 1. 数据模型

**`sys_dept` 扩展列**（迁移 `na2b3c4d5e6_hr_l1_org_employee.py`，全手写）

| 列 | 类型 | 说明 |
|---|---|---|
| `dept_type` | String(16) default `'dept'` | `site`场所 / `company`公司 / `division`事业部 / `dept`科室 / `lab`实验室 / `team`班组 |
| `site_code` | String(32) default `''` | 场所编码（多场所：总部 + 分支实验室） |
| `address` | String(255) default `''` | 办公地址 |
| `manager_id` | BigInteger nullable | 部门负责人 → `sys_user.id`，**权威写入方**，与任职表 `is_leader` 双向同步 |
| `effective_from` / `effective_to` | Date nullable | 有效期 |

**新表**（`app/modules/hr/models.py`）

| 表 | 基类 | 说明 |
|---|---|---|
| `hr_position` | `BaseModel` | 岗位说明书：`code` / `name` / `dept_id` / `site_id` / `position_type`(staff/manager/key) / `duty` / `requirement` / `report_to_id` / `key_role` / `primary_user_id`(A角) / `backup_user_id`(B角) / `status` |
| `hr_employee` | `BaseModel` | 员工一人一档：`employee_no`(unique) / `user_id`(1:1 → `sys_user`) / `name` / `id_no`(密文) / `id_type` / `gender` / `birth_date` / `education` / `major` / `mobile` / `email` / `employ_type`(labor/engage/part_time/intern) / `employ_status`(probation/regular/idle/resigned/retired) / `dept_id` / `position_id` / `hire_date` / `leave_date` / `contract_no` / `contract_start` / `contract_end` |
| `hr_employee_control` | `BaseModel` | 黑白名单：`employee_id` / `control_type`(blacklist/whitelist) / `reason` / `effective_from` / `effective_to` / `status` |
| `hr_employment` | `BaseModel` | 人事事务单据（单号前缀 `EM`）：`emp_no` / `event_type`(onboard/transfer/resign/rehire) / `employee_id` / `user_id` / `dept_id` / `new_dept_id` / `position_id` / `new_position_id` / `effective_date` / `status` / `flow_instance_id` / `applicant_id` / `approver_id` / `approved_at` / `create_account` / `account_username` / `account_password`(密文) / `account_roles` |
| `hr_employment_event` | `AppendOnlyModel` | 人事事务变更轨迹（**只追加**，无 `deleted` / `version`） |
| `hr_delegate` | `BaseModel` | 代理人（AB 角，**不借账号**）：`principal_id` / `agent_id` / `scope`(position/auth/task) / `position_id` / `auth_id` / `effective_from` / `effective_to` / `status`(enabled/expired/revoked) / `auto_takeover` |
| `hr_org_change` | `AppendOnlyModel` | 组织变更快照：`object_type`(dept/position/employee) / `object_id` / `change_type` / `before_json` / `after_json` / `operator_id` / `effective_at`(`DATETIME(3)`) / `reason` |

### 2. 敏感个人信息：加密 + 脱敏 + 明文唯一出口

- `hr_employee.id_no` 落库为 **AES-GCM 密文**（`enc:` 前缀，域 `hr-employee-idno`，与配置密钥 / 电子签名密钥**域分隔**）。
- 列表 / 详情出参**一律掩码**：前 4 + `*`×(len-8) + 后 4（如 `3301**********1234`）。
- **明文唯一出口**：`GET /hr/employees/{eid}/id-no`（权限 `hr:staff:idno`），**每次访问写 `sys_audit_log`**
  （action `hr_employee_idno_view`，字段级 + 哈希链）—— 谁查看了谁的证件号必须可归因。
- 证件号唯一性校验**只能解密后逐条比对**（密文不可 SQL 比对），HR 档案量级（千级）开销可忽略。

### 3. 端点

**组织架构**（`app/modules/hr/org_router.py`，prefix `/hr`）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/hr/org/positions` | `hr:position:list` | 岗位列表（分页 / `q` / `filters[dept_id]` / `filters[key_role]` / `filters[position_type]`） |
| GET | `/hr/org/positions/counts` | `hr:position:list` | 页签计数 |
| GET | `/hr/org/positions/export` | `hr:position:list` | 导出 |
| POST | `/hr/org/positions` | `hr:position:create` | 新建岗位 |
| PUT | `/hr/org/positions/{pid}` | `hr:position:edit` | 编辑岗位 |
| DELETE | `/hr/org/positions/{pid}` | `hr:position:edit` | 删除岗位（清理 A/B 角引用） |
| GET | `/hr/org/changes` | `hr:org:list` | 组织变更轨迹（`filters[object_type]` / `filters[object_id]` / `filters[change_type]`） |
| GET | `/hr/org/options` | `hr:org:list` | 下拉选项（场所 / 部门 / 岗位 / 关键岗位 / 人员） |

**部门（写入口在 admin 域）**：`POST/PUT /admin/depts`（`admin:dept:edit`）接收扩展字段；写 `manager_id` 时同步任职表 `is_leader=1`。

**员工主数据**（`app/modules/hr/employee_router.py`，prefix `/hr`）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/hr/employees` | `hr:staff:list` | 员工列表（`filters[employ_status]` / `filters[employ_type]` / `filters[dept_id]` / `filters[position_id]` / `filters[education]`） |
| GET | `/hr/employees/counts` | `hr:staff:list` | 页签计数（按 `employ_status`） |
| GET | `/hr/employees/options` | `hr:staff:list` | 人员下拉 |
| GET | `/hr/employees/export` | `hr:staff:export` | 导出（证件号仍为掩码） |
| GET | `/hr/employees/{eid}` | `hr:staff:list` | 详情（档案 + 任职 + 授权 + 代理 + 人事轨迹聚合） |
| GET | `/hr/employees/{eid}/id-no` | `hr:staff:idno` | **证件号明文唯一出口**（写审计） |
| GET | `/hr/employees/{eid}/timeline` | `hr:staff:list` | 档案变更时间线 |
| POST | `/hr/employees` | `hr:staff:create` | 建档（工号 / 证件号 / 兼职冲突 / 关键岗位校验） |
| PUT | `/hr/employees/{eid}` | `hr:staff:edit` | 改档 |
| DELETE | `/hr/employees/{eid}` | `hr:staff:edit` | 删除（有未完结人事事务时拒绝 → 63012） |
| POST | `/hr/employees/{eid}/control` | `hr:staff:edit` | 黑白名单管控 |

**人事事务 + 代理人**（`app/modules/hr/employment_router.py`，prefix `/hr`）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/hr/employments` | `hr:employment:list` | 事务列表（`filters[event_type]` / `status` / `range[effective_date]`） |
| GET | `/hr/employments/counts` | `hr:employment:list` | 页签计数 |
| GET | `/hr/employments/{eid}` | `hr:employment:list` | 详情 |
| GET | `/hr/employments/{eid}/timeline` | `hr:employment:list` | 变更轨迹 |
| POST | `/hr/employments` | `hr:employment:create` | 新建（草稿）；入职可勾选「开账号」并填初始密码 / 角色 |
| PUT | `/hr/employments/{eid}` | `hr:employment:edit` | 编辑（仅 `draft` / `rejected` 可编辑） |
| POST | `/hr/employments/{eid}/submit` | `hr:employment:submit` | 提交审批 |
| POST | `/hr/employments/{eid}/withdraw` | `hr:employment:submit` | 撤回（仅发起人且无人处理） |
| POST | `/hr/employments/{eid}/effect` | `hr:employment:effect` | **生效**（执行副作用，见下） |
| GET | `/hr/delegates` | `hr:delegate:list` | 代理人列表 |
| POST/PUT/DELETE | `/hr/delegates[/{did}]` | `hr:delegate:edit` | 代理人维护（`scope=position` 必须给 `positionId`） |

### 4. `hr_employment` 状态机与「审批通过 ≠ 生效」

```
draft ──submit──▶ approving ──approve──▶ approved ──effect──▶ effective
  ▲                   │                      │
  └──withdraw─────────┘◀────reject───────────┘
                      reject ──▶ rejected ──(改档/重新提交)──▶ draft
```

- **`approved`（审批通过）≠ `effective`（副作用已执行）**。离职需**择时生效**（离职当日回收权限），
  因此必须有一个独立的 `POST /hr/employments/{eid}/effect` 动作。
- 流程绑定（`app/modules/approval/registry.py::BINDINGS` 第 **19** 条）：
  `biz_type="hr_employment"` / `definition_code="hr_employment_approve"` / **`pass_through=False`**
  —— 人事事务**不允许人工直通**（合规红线）；流程总开关关闭时提交报 **70006**。
- 状态守卫：`draft` 直接 `effect` → **63014**；`approving` 不可编辑；`approved` 不可编辑。

**生效副作用（`app/modules/hr/employment.py::effect_employment()`，全部写字段级审计 `strict=True`）**

| 事件 | 副作用 |
|---|---|
| **onboard** 入职 | 建 `sys_user`（登录名 = 工号或表单指定；**自动生成**的初始密码明文**只在生效响应里出现一次**，HR 表单填的密码不回显）→ 按岗位 `position_type` 绑默认角色（`staff` → `biz_user`）→ 建立主部门任职（`is_primary=1`）→ 回填 `hr_employee.user_id` → 同步 `sys_user.employee_no` / `hire_date` → `employ_status=probation` |
| **transfer** 调岗 | 更新 `hr_employee.dept_id/position_id` → 更新 `sys_user.dept_id/dept_name` → 同步主部门任职（唯一 `is_primary=1`） |
| **resign** 离职 | `sys_user.status='disabled'`（**不删除**，ALCOA 完整）→ `mfa_enabled=0` → **撤销 B9 授权台账**（该用户全部 `active/suspended/confirmed` → `revoked` + 写 `hr_authorization_event`）→ **代理失效**（作为委托人 → `expired`；作为代理人且委托人已离职 → 一并 `expired`）→ **清岗位 A/B 角** → `employ_status='resigned'` + `leave_date` → 写一条「**物理权限（门禁 / 钥匙 / 工牌）回收待现场确认**」审计（本系统无门禁对接，诚实标注外部依赖） |
| **rehire** 返聘 | **恢复原账号**（`status='enabled'`，保持一人一号历史连续）→ `employ_status='regular'`。**不恢复授权** —— 能力须重新确认 |

### 5. B10-1 新增错误码

| 码 | 常量 | 含义 |
|---|---|---|
| 63010 | `HR_ORG_INVALID_STATE` | 组织架构状态不允许该操作 |
| 63011 | `HR_EMP_NOT_FOUND` | 员工档案不存在 |
| 63012 | `HR_EMP_INVALID_STATE` | 员工档案状态不允许该操作（如存在未完结人事事务时删除） |
| 63013 | `HR_EMP_DUPLICATE` | 工号 / 证件号重复 |
| 63014 | `HR_EMPLOYMENT_INVALID_STATE` | 人事事务状态不允许该操作 |
| 63015 | `HR_EMPLOYMENT_NOT_FOUND` | 人事事务单不存在 |
| 63016 | `HR_EMP_CONFLICT` | 员工冲突（兼职重复 / 兼职任关键岗位 / 黑名单入职） |
| 63017 | `HR_POSITION_NOT_FOUND` | 岗位不存在 |
| 63018 | `HR_DELEGATE_INVALID_STATE` | 代理人配置状态不允许该操作（如 `scope=position` 未指定岗位） |

前端镜像在 `src/api/types.ts::ERROR_CODES`。

### 6. 种子与菜单

- 菜单：`menu.hrCenter` 下新增
  - `menu.hrOrg` → `/hr/org`，componentKey `hr/OrgStructureList`，权限 `hr:org:list`；
  - `menu.hrPosition` → `/hr/positions`，componentKey `hr/PositionList`，权限 `hr:position:list`；
  - `menu.hrEmployment` → `/hr/employments`，componentKey `hr/PersonnelAffairsList`，权限 `hr:employment:list`。
  `menu.staff` → `/hr/staff`，componentKey `hr/StaffList`，权限 `hr:staff:list`（**占位页已替换为真实列表**）。
- 按钮权限：`hr:position:create/edit` `hr:staff:create/edit/export/idno` `hr:employment:create/edit/submit/effect` `hr:delegate:list/edit`。
- 角色：`hr_manager`（人事管理员）加 `hr:org:list` `hr:position:*` `hr:staff:*` `hr:employment:*` `hr:delegate:*`
  + 菜单 `menu.dept`（从而拿到 `admin:dept:list` / `admin:dept:edit` —— 人事管理员本就该维护部门树）；
  **`biz_user` 不加员工档案权限**（个人信息隔离）。
- 审批流程定义 `hr_employment_approve`：`(1,"人事主管审核","hr1") → (2,"总经理审批","admin")`
  —— **用固定 USER 节点**（ROLE 节点在无人拥有该角色时会被引擎跳过）。
- 编号规则：`hr_employment` → 前缀 `EM`（如 `EM202611230001`）。

## E1 企业微信审批 + 组织数据移植（39 模板 / 11 部门 / 23 标签 / 40 人）

> 本章记录「把企业微信在用的 39 个审批模板与组织架构完整移植到 bizSys」的落地口径。
> 数据落位：**不新建组织表** —— 部门进 `sys_dept`、标签进 `sys_role`（只做审批人来源）、人员进 `sys_user` + `sys_user_dept` + `hr_employee`。
> **隐私约束**：组织与人员**全模拟**（用户名 `mockNNN`、姓名 `模拟员工NN`），证件号 / 手机 / 邮箱 / 企微 vid **一律为空**，源 HTML 不入库。

### 1. 表单控件映射

| 企业微信控件 | 目标 `type` | 说明 |
| --- | --- | --- |
| Text / Textarea / Number / Money / Date / DateRange | `text` `textarea` `number` `money` `date` `daterange` | 一一对应 |
| Selector | `select` | 选项由「单选：A / B / C」解析，用**选项标签**作值（条件值同源） |
| File | `file` | 复用现有 URL 列表控件 |
| Contact（成员） | `user` | `contact.type=multi` → `multiple=true`（多选，值为人员 id 数组）；`contact.mode=department` → `resource` + `resource=dept` |
| Tips | `text_block` | 说明块，渲染 `description || label` |
| RelatedApproval | `resource` + `resource=oa_instance` + `relatedFormKeys` | 关联本系统已发起的其他审批单 |
| Table | `table` | 子列由「明细字段：…」解析，类型按列名推断（金额→money / 数量→number / 余→text） |
| Formula | `formula` | 表达式支持 `+ - * /`、字段引用、`SUM(表key.列key)`、`HOURS(字段key)` |
| PhoneNumber | `phone` | 手机号（`inputmode=tel`） |
| Location | `location` | 打卡地点文本（不接地图 SDK） |
| Attendance / Vacation / PunchCorrection | `attendance` | 假勤原子控件（`refType` = attendance / vacation / punch），值 `{kind, detail, hours}` |
| Onboarding / Regularization / Transfer / Resignation | `hr_ref` | 人事原子控件（`refType` = onboard / regular / transfer / resign） |

> **`daterange` 不可作为流程变量**（`EXPOSABLE_TYPES` 不含它）。企微对「时长」按小时做数值比较，导入器为此合成 `HOURS(<fieldkey>)` 公式字段（`hours_<fieldkey>`）暴露给引擎，原始 daterange 保持不暴露。

### 2. 条件判断

- 条件规则支持**规则组** `{logic: "and"|"or", rules: [...]}`（可嵌套），单条规则的操作符：
  `eq` `ne` `gt` `gte` `lt` `lte` `in` `contains` `between` `empty` `not_empty`。
- `between` 的值为区间 `[lo, hi]`（或 `{min,max}` / `{lo,hi}`）。
- 企微 op 编码 → 引擎 op（**文档未给出 op 语义**，按 21 条条件的显示文案交叉推定）：

| 企微 op | 引擎 op | 佐证 |
| --- | --- | --- |
| op1 | `eq` | — |
| op2 | `gt` | 差旅「大于 3 天」= op2 / 72（小时） |
| op3 | `lt` | 「十万以下」= op3 / 100000 |
| op4 | `gte` | 「百万以上」= op4 / 1000000 |
| op5 | `lte` | 请假 op5 / 72 |
| op6 | `between` | 「1000-10000」「10w-100w」 |

> **待人工复核（导入报告首屏列出）**：
> - op2 / op4 的 `gt` / `gte` 归属仅在「恰好等于阈值」时有差异；
> - 2 处 `op6 / undefined` 区间阈值缺失 → 按条件标题重建（`reconstructed=true`）；
> - 1 处 `op2 / undefined`（通用审批单「预算金额」）阈值不可知 → 落 `gt 0`（`needs_review=true`）；
> - 3 处字段权限键未能对应到明细列 → 已忽略。

### 3. 节点类型与审批人来源

| 企微 | 目标 `nodeType` / `approverType` |
| --- | --- |
| 审批节点 | `approval`（签署方式 `or` / `and` / `sequential`） |
| 条件分支 | `condition`（`branches[{expr,targetSeq}]` + `defaultSeq`） |
| 抄送节点 | `cc`（不阻塞） |
| 办理节点 | `executor`（新增：单人处理；`options.executorCommentRequired` 时办理意见必填） |
| 指定成员 / 指定联系人 | `USER` |
| 直属上级 / 部门负责人 | `DEPT_LEADER` / `PARENT_DEPT_LEADER` / `SUPERVISOR_CHAIN`（按发起人组织解析） |
| 角色 | `ROLE` |
| **标签** | `ROLE`（`wc_tag_<slug>` —— 标签 → 角色的**唯一通道**，不额外绑定菜单权限） |
| 申请人自选 | `FORM_USER`（`approverValue` 存**流程变量名**，由 `variables_schema` 声明） |

图结构**线性化**：企微是「树 + 一个多父抄送节点」的 DAG，引擎按 seq 线性推进 → 导入器做 DFS 前序遍历产出节点序列，共享节点按路径复制（与企微「每条路径各发一次抄送」语义一致），分支 `targetSeq` 在 seq 分配后回填，环路用 visited 集合防呆。

### 4. 流程通用选项（`approval_definition.options`）

JSON，10 个键；**未配置时全部保持既有行为**（向后兼容）：

| 键 | 含义 | 生效点 |
| --- | --- | --- |
| `commentRequired` | 审批意见必填 | `engine.approve`（**通过**也必须填）→ `70003` |
| `commentSignRequired` | 审批意见需签名 | `engine.approve` / `engine.reject` 缺签名 → `70003`；签名写入 `approval_record.payload.signature` |
| `executorCommentRequired` | 办理意见必填 | `engine.approve`（办理节点）→ `70003` |
| `allowAddSign` | 允许加签 | `engine.add_sign`（显式 `false` 才禁止） |
| `allowWithdrawAfterApproved` | 通过后申请人可撤销 | `engine.withdraw` |
| `allowModifyFlow` / `allowModifyCc` | 审批人可改流程 / 可改抄送 | 预留 |
| `executorCanModify` | 办理人可修改表单 | 预留 |
| `allowProxySubmit` | 允许他人代提交 | 预留 |
| `detailTablePermission` | 明细表权限控制 | 预留 |

> **签名只作用于审批节点**（办理节点走「办理意见必填」口径）。前端在待办上按 `ApprovalTask.commentSignRequired` 展示 `SignaturePad`，签名以 PNG dataURL 随 `commentSignature` 提交。
> 待办出参新增 `commentRequired` / `commentSignRequired` / `executorCommentRequired` / `allowAddSign` 四个标记。

### 5. 节点字段权限（`approval_node.field_permissions`）

JSON：`{字段key: "editable" | "viewonly" | "hidden"}`。
生效于 `GET /oa/instances/{id}`：按**当前调用者所在待办节点**取掩码 —— `hidden` 字段从 schema 与 data 中剔除，`viewonly` 字段下发 `readOnly: true`（前端渲染为只读）。企微 1487 条「仅可见」记录全部迁为 `viewonly`。

### 6. 表单可见范围（`oa_form.scope_json`）

JSON：`{"depts": [...], "roles": [...], "users": [...]}`，**空 = 全员可见**。`GET /oa/catalog` 按当前用户的部门 / 角色 / 账号过滤。

### 7. 流程包 JSON 化（`bizsys.flowpackage/v1`）

一套 schema 承载「OA 表单 + 审批定义」，用于批量导入导出：

```jsonc
{
  "schema": "bizsys.flowpackage/v1",
  "exportedAt": "2026-11-24T10:00:00",
  "packages": [{
    "code": "wc_payment_apply_approve",   // 流程定义 code
    "name": "付款申请",
    "bizType": "oa",
    "enabled": true,
    "remark": "",
    "flowVersion": 1,
    "source": "wecom",                     // wecom / bizsys
    "form": { "key": "wc_payment_apply", "name": "…", "category": "…", "icon": "", "sort": 0,
              "description": "", "scope": { "depts": [], "roles": [], "users": [] },
              "fields": [ /* OaField[] */ ] },
    "flow": { "variablesSchema": {}, "options": {}, "nodes": [ /* 节点 */ ], "edges": [ ] }
  }]
}
```

**幂等**：导入按 `code` upsert 流程定义、按 `form.key` upsert 表单，重复导入不产生重复行。

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/approval/packages/export-all` | `admin:flow:export` | 导出全部流程包（JSON 文件，可按 `?biz_type=` 过滤） |
| GET | `/approval/definitions/{code}/package` | `admin:flow:export` | 导出单个流程包 |
| POST | `/approval/packages/import` | `admin:flow:import` | 导入流程包（`?dry_run=true` 只校验不落库） |
| GET | `/oa/admin/forms/{id}/package` | `admin:flow:export` | 导出单个 OA 表单包（含绑定流程） |

导入返回：`{total, created, updated, formCreated, formUpdated, errors[], dryRun}`；**非法包不中断整体**，逐条记入 `errors`。

### 8. 模拟组织种子

| 企微概念 | 落位 | 键 |
| --- | --- | --- |
| 11 个部门（3 层） | `sys_dept` | `code = WC01…WC11` |
| 23 个标签 | `sys_role` | `code = wc_tag_<slug>`，`remark = "企业微信标签：<名>"` |
| 40 名人员 | `sys_user` + `sys_user_dept` + `hr_employee` | `username = mock001…mock040`、`name = 模拟员工NN`、密码 `Mock@123456`；首条任职 `is_primary=1` |
| 标签 → 成员 | `sys_user_role` | 每人按标签挂 `wc_tag_*` 角色 |
| 岗位职务（30） | `hr_position` | 按 title 去重生成 `WCP001…` |

> `sys_dept` 仍是全站唯一部门表，写入口仍只有 `POST/PUT /admin/depts` —— 本批次**只读种子**，不新增第二个写入口。
> 企微标签映射成的 `sys_role` **只做审批人来源**，不生成菜单权限。

### 9. 新增迁移与错误码

- 迁移（**手写**，`alembic/env.py` 未 import oa/hr 等模型）：
  - `nc2b3c4d5e6_wecom_flow_upgrade.py` —— `approval_definition.options` + `approval_node.field_permissions`；
  - `nd2b3c4d5e6_oa_form_scope.py` —— `oa_form.scope_json`。
- 错误码：**复用既有 `70003`（审批意见必填）**，签名缺失同样以 `70003` + 「审批意见需签名」返回；无新增错误码段。

### 10. 种子与菜单

- 菜单：`menu.sysData` 下新增 `menu.flowPackages` → `/admin/flowpackages`，componentKey `admin/FlowPackageList`，权限 `admin:flow:export`；按钮子菜单 `flow-package-import` 承载 `admin:flow:import`（**一码一菜单**）。
- 种子：`app/seeds/init_data.py::main()` 幂等调用 `wecom_org.import_org(db)` 与 `wecom_templates.import_templates(db)`。
- 产物：`backend/app/seeds/data/wecom_flow_packages.json`（39 个流程包，同 schema）——既是迁移产物，也是「批量导入导出」的现成样例。

## B11 知识与文档中心 + 全站回收站

> 覆盖「标准与方法库 / 体系文件 / 公司制度 / 设备操作说明 / 上墙看板 / 标志标识标牌」等企业文档共享场景；
> 同时给**全站所有删除动作**加一层统一回收体系（软删 → 回收站 → 保留期内禁止彻底删除）。

### 1. 数据模型（`app/modules/knowledge/models.py`，`kb_*` 前缀）

| 表 | 基类 | 说明 |
| --- | --- | --- |
| `kb_category` | `BaseModel` | **多级可定义**文档分类树（物化路径 `path = /1/3/7/`，`level` 层级） |
| `kb_space` | `BaseModel` | 空间：`personal` 个人空间 / `shared` 共享空间 |
| `kb_folder` | `BaseModel` | 空间下的文件夹（可挂分类，可单独对外共享） |
| `kb_document` | `BaseModel` | 文档主表（作者 `owner_id` / 编辑者 `editor_ids` / 当前版本 `current_version`） |
| `kb_version` | `BaseModel` | 版本历史（回滚 = 以历史版本内容生成新版本，历史不丢） |
| `kb_file` | `BaseModel` | 物理文件登记（`sha256` 去重校验） |
| `kb_permission` | `BaseModel` | 授权条目（`user`/`role`/`dept` × `read`/`edit`/`manage`，`is_external` 标外部人员） |
| `kb_share_link` | `BaseModel` | 外部分享链接（`token` / `perm=read|upload|edit` / `require_phone` / `expire_at`） |
| `kb_link_log` | `AppendOnlyModel` | 外部链接访问与上传留痕（**只追加**，不可删改） |
| `sys_recycle_bin` | `BaseModel` | **全站统一回收站登记表**（一张表管所有模块） |

### 2. 文档分类（多级可定义，树形浏览）

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/knowledge/categories` | `knowledge:category:list` **或** `knowledge:document:list` | 返回**分类树**（顶层节点 + `children`） |
| POST | `/knowledge/categories` | `knowledge:category:edit` | 新增分类（`parentId` 可空 = 顶级） |
| PUT | `/knowledge/categories/{cid}` | `knowledge:category:edit` | 改分类（含**改上级 → 重算 `level`/`path`**） |
| DELETE | `/knowledge/categories/{cid}` | `knowledge:category:edit` | 删除分类（**有子分类或被引用时拒绝** → 94008） |

- `level` 由父链推导（顶级 = 1），`path` 形如 `/12/34/`；改上级时**整棵子树的 `level`/`path` 一起重算**。
- **环路保护**：把分类挂到自己的子孙下 → 94008。
- 分类树同时作为「文档类型」的落地：`doc_type` = `document`（通用文档）/ `system`（体系文件）/ `board`（上墙看板）/ `sign`（标志标识标牌）/ `manual`（设备操作说明）/ `rule`（公司制度）/ `standard`（标准与方法库）。

### 3. 空间与文件夹

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/knowledge/spaces` | `knowledge:space:list` **或** `knowledge:document:list` | 空间列表（**置顶优先**，附 `deptName` 供共享分组） |
| POST | `/knowledge/spaces` | `knowledge:space:edit` | 新建空间（可带 `pinned`） |
| PUT | `/knowledge/spaces/{sid}` | `knowledge:space:edit` | 改空间（含 `pinned`） |
| POST | `/knowledge/spaces/{sid}/pin` | `knowledge:space:edit` | **置顶 / 取消置顶**（微盘左栏「置顶」分组，`{"pinned": 1}`） |
| DELETE | `/knowledge/spaces/{sid}` | `knowledge:space:edit` | 删空间（进回收站） |
| GET | `/knowledge/folders` | `knowledge:document:list` | 文件夹列表（按 `spaceId`） |
| GET | `/knowledge/folders/tree` | `knowledge:document:list` | 文件夹**树** |
| POST | `/knowledge/folders` | `knowledge:document:create` | 新建文件夹（`spaceId` / `parentId` / `categoryId`） |
| PUT | `/knowledge/folders/{fid}` | `knowledge:document:edit` | 改文件夹 |
| DELETE | `/knowledge/folders/{fid}` | `knowledge:document:edit` | 删文件夹（进回收站） |

> 分类管理 / 空间管理 **B12 起不再作为独立导航入口**（能力并入文档中心页面），
> 但权限码与端点保留 —— `knowledge:category:list` / `:edit` / `knowledge:space:list` / `:edit`
> 改挂在「文档中心」菜单的**按钮子项**上（`knowledge-doc-category-*` / `knowledge-doc-space-*`）。

### 3.1 微盘式目录浏览（B12）

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/knowledge/browse` | `knowledge:document:list` | **一次返回「子文件夹 + 文档」**（微盘式目录浏览） |

查询参数：`spaceId` / `folderId` / `categoryId` / `q` / `page` / `size` / `sort`（`name`｜`updateTime`｜`size`）/ `order`（`asc`｜`desc`）。

```jsonc
{
  "code": 0,
  "data": {
    "space": { "id": 1, "name": "技术部共享空间", "pinned": 1, "deptName": "技术部" },
    "breadcrumb": [{ "id": 7, "name": "公司制度", "spaceId": 1 }],
    "stats": { "myDocCount": 12, "mySize": 1048576 },
    "folders": [
      {
        "id": 7, "name": "公司制度", "spaceId": 1, "docCount": 3,
        "externalAccess": true,     // 存在生效的外部分享链接
        "restricted": false          // 设置了成员权限
      }
    ],
    "documents": {
      "items": [{ "id": 20, "title": "…", "updaterName": "张三", "externalAccess": false, "restricted": true }],
      "total": 3, "page": 1, "size": 50
    }
  }
}
```

- **可见口径与文档列表完全一致**（共用 `service.visible_document_where`），不会出现「列表看不到、目录里看到」。
- 子文件夹**不分页**（目录层级浅），文档按页返回 —— 与微盘 / 网盘惯例一致。
- 文件夹可见性：所属空间可见 / 自身或祖先链有授权 / 其下存在可见文档（祖先链自动展开）。
- `externalAccess` / `restricted` 两个标记对应微盘的「外部可访问 / 限制成员权限」角标。

### 4. 文档：上传 / 批量上传 / 预览 / 下载 / 版本

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/knowledge/documents` | `knowledge:document:list` | 列表（`q`/`spaceId`/`folderId`/`categoryId`/`docType`/`sort`） |
| GET | `/knowledge/documents/{did}` | `knowledge:document:list` | 详情（含当前用户的 `perm` 档位） |
| POST | `/knowledge/documents` | `knowledge:document:create` | **单个上传**（multipart） |
| POST | `/knowledge/documents/batch` | `knowledge:document:create` | **批量上传**（multipart 多文件） |
| PUT | `/knowledge/documents/{did}` | `knowledge:document:edit` | 改元信息 / 状态（`draft`/`published`/`archived`） |
| DELETE | `/knowledge/documents/{did}` | `knowledge:document:delete` | 删除（**进回收站**，文件不立即删盘） |
| GET | `/knowledge/documents/{did}/versions` | `knowledge:document:list` | 版本历史（倒序） |
| POST | `/knowledge/documents/{did}/versions` | `knowledge:document:edit` | 上传新版本 |
| POST | `/knowledge/documents/{did}/rollback/{vid}` | `knowledge:document:edit` | **回滚**到某历史版本（生成新版本号，历史保留） |
| GET | `/knowledge/documents/{did}/preview` | `knowledge:preview` | **在线预览**（服务端抽文本） |
| GET | `/knowledge/documents/{did}/raw` | `knowledge:preview` | 内联原文件（浏览器内嵌预览） |
| GET | `/knowledge/documents/{did}/download` | `knowledge:download` | 附件下载 |

> **表单字段用 snake_case**（本仓惯例，multipart 不用 camelCase）：
> `title` / `space_id` / `folder_id` / `category_id` / `doc_type` / `comment`；
> 查询参数仍走 camelCase 别名（`spaceId` / `folderId` / `categoryId` / `docType`）。

**格式与大小限制（在系统管理区单独设置）**：

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/knowledge/settings` | `knowledge:setting:list` | 读当前生效配置（`allowedExt` / `maxMb` / `previewMaxChars`） |
| PUT | `/knowledge/settings` | `knowledge:setting:edit` | 改配置（写 `sys_config`：`knowledge.allowed_ext` / `knowledge.max_mb` / `knowledge.preview_max_chars`） |

- `allowedExt` 传**空数组 = 清空配置 → 回落系统默认格式**（不传该键 = 保持不变）。
- 违反格式 → **94003**；超出大小 → **94004**。
- 批量上传**不因单个失败而整体回滚**：返回 `{total, success, items:[{ok, name, error}]}`，失败项带原因。
- 默认允许格式：办公文档族（`pdf doc docx xls xlsx ppt pptx txt csv md zip` 等），可用 `PUT /knowledge/settings` 收窄或放宽。

**在线预览实现**：服务端按扩展名抽文本 —— `txt/md/csv` 直接读文本；`docx` 用 `python-docx`；`xlsx` 用 `openpyxl`；`pdf` 用 `pypdf`。抽出的文本按 `previewMaxChars` 截断（默认 20000）。**前端不引入新的 npm 依赖**。

### 5. 文档权限（作者 / 编辑者 / 内部外部 / 只读可编辑）

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/knowledge/documents/{did}/permissions` | `knowledge:document:share` | 授权列表 |
| PUT | `/knowledge/documents/{did}/permissions` | `knowledge:document:share` | **整体覆盖**授权列表 |
| DELETE | `/knowledge/permissions/{pid}` | `knowledge:document:share` | 撤销一条授权 |

授权条目：`{subjectType: user|role|dept, subjectId, subjectName, perm: read|edit|manage, isExternal: 0|1, expireAt?}`。

- 档位数值：`read(1) < edit(2) < manage(3)`。
- 作者与空间拥有者天然 `manage`；`editor_ids` 里的编辑者天然 `edit`。
- **无任何授权的普通用户看不到该文档**（列表过滤 + 详情 94002）；超级管理员 `role_code="super"` 旁路。
- 授权可带 `expireAt`（到期自动失效）。

### 6. 外部分享链接（内部/外部 × 只读/可编辑 × 手机验证码）

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/knowledge/links` | `knowledge:link:list` | 分享链接列表（含 `token` / `status` / 计数） |
| POST | `/knowledge/links` | `knowledge:link:create` | 生成链接（`resourceType=folder|document` / `perm=read|upload|edit` / `requirePhone` / `expireDays` / `maxUpload`） |
| DELETE | `/knowledge/links/{lid}` | `knowledge:link:delete` | **关闭**链接（`status=closed`，链接立即失效） |

**公开端点（无需登录）**：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/knowledge/public/links/{token}` | 链接信息（`status`/`perm`/`requirePhone`/标题） |
| POST | `/knowledge/public/links/{token}/code` | 发短信验证码（`{phone}`） |
| POST | `/knowledge/public/links/{token}/verify` | 校验验证码 → 返回**访问令牌** `access` |
| GET | `/knowledge/public/links/{token}/documents?access=` | 浏览该链接下的文件清单 |
| GET | `/knowledge/public/links/{token}/raw/{did}?access=` | 下载 / 预览文件 |
| POST | `/knowledge/public/links/{token}/upload?access=` | **外部人员上传**文件到该文件夹 |

- 验证流程：手机号 → 短信验证码 → `access` 令牌（Redis，**2 小时**过期）。
- `access` 令牌通过**查询参数**传递（公开端点无 Authorization 头）。
- 未验证即访问 → **94007**；验证码错误/失效 → **94009**；链接过期或已关闭 → **94006**。
- 只读链接调用上传 → **94002**。
- 每次外部访问 / 上传都写 `kb_link_log`（只追加留痕）。
- 前端公开页：`/knowledge/share/:token`（**免登录公开路由**，`guards.ts::PUBLIC_PREFIX_PATHS`），页内完成验证 → 浏览 / 上传。

### 7. 全站统一回收站

**核心设计**：业务表**仍用 `deleted` 标记逻辑删除**，**不新增列**（116 张 `BaseModel` 表 + `AppendOnlyModel` 表没有 `deleted`）；删除人 / 删除时间 / 保留期到期时间统一记在登记表 `sys_recycle_bin`。

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/admin/recycle` | `admin:recycle:list` | 回收站列表（按 `module` / `q` / `status` 过滤） |
| GET | `/admin/recycle/modules` | `admin:recycle:list` | 按模块统计（`module` / `count`） |
| GET | `/admin/recycle/settings` | `admin:recycle:list` | 读保留期（默认 **180 天**） |
| PUT | `/admin/recycle/settings` | `admin:recycle:setting` | 改保留期（`{"retentionDays": 180}`） |
| POST | `/admin/recycle/{rid}/restore` | `admin:recycle:restore` | **恢复**（含级联子行、含改名让位还原） |
| POST | `/admin/recycle/{rid}/purge` | `admin:recycle:purge` | **彻底删除**（保留期内一律拒绝 → 30006） |

- 保留期存 `sys_config` 的 `recycle.retention_days`（默认 180），到期日 = 删除时间 + 保留期。
- **判定软删一律用 `deleted != 0`** —— 全仓有 **3 处**历史写法把 `deleted` 赋成自身 id（工时填报 / OA 表单 / 报价模板），因为那些表唯一键含 `deleted`，写 1 会撞键。
- **恢复是通用的**：按登记表里的表名 + 主键把 `deleted` 置回 0，并回填 `restore_fields`（用于「改名让位」的场景，如用户/角色/字典项改名成 `#del{id}`）。
- **级联软删的子行**（排程方案 → 排程行、项目 → 项目任务）一并登记、恢复时一起回滚。
- 保留期内 `purge` → **30006**（响应文案带剩余天数与到期日）；条目不存在 → **30007**；恢复失败 → **30008**；条目不在回收站 → **30009**。

**已知边界（诚实标注，不假装闭环）**：

1. 「整体替换」语义下的子行是物理删除（`db.delete` / `delete-orphan`），恢复父记录时这些子行**不会**回来（任务条目 / 样品、BOM 子件行、流程定义节点）。
2. 磁盘文件（合同附件、合作方附件、头像等）在软删时会被立即 `unlink`，恢复后拿不回文件；**知识库域的文件不做即时 unlink**（由 `kb_file` 登记，到期清理）。
3. `kb_link_log` 是只追加的合规留痕表 → 登记进 `RETAINED_AUDIT_TABLES`（**不进「一键清空」清单**）。

### 8. 权限码与菜单

| 权限码 | 菜单 | 路径 / componentKey |
| --- | --- | --- |
| `knowledge:document:list` / `:create` / `:edit` / `:delete` / `:share` / `:preview` / `:download` | `menu.knowledgeDocuments` | `/knowledge/documents` → `knowledge/DocumentCenter` |
| `knowledge:category:list` / `:edit` | `menu.knowledgeDocuments` 的**按钮子项** | B12 起并入文档中心页面，不再是独立菜单 |
| `knowledge:space:list` / `:edit` | `menu.knowledgeDocuments` 的**按钮子项** | B12 起并入文档中心页面，不再是独立菜单 |
| `knowledge:link:list` / `:create` / `:delete` | `menu.knowledgeLinks` | `/knowledge/links` → `knowledge/ShareLinkList` |
| `knowledge:setting:list` / `:edit` | `menu.knowledgeSettings` | `/knowledge/settings` → `admin/KnowledgeSettings`（系统管理区） |
| `admin:recycle:list` / `:restore` / `:purge` / `:setting` | `menu.recycle` | `/admin/recycle` → `admin/RecycleBinList`（系统管理区） |

- 「知识与文档」目录组（`menu.knowledgeDocs`）挂在**经营与协同**分区下（与客户自助 / 在线委托同区），保持导航仍为 10 个顶层分区。
- 「知识中心设置」与「回收站」挂在**系统管理**分区（分别属「系统与审计」/「系统与审计」分组）。
- **B12 菜单下线**：分类管理 / 空间管理不再是独立导航入口。种子 `init_data.py::REMOVED_MENUS`
  登记了这两个菜单，运行种子时把它们**逻辑删除**（`deleted=1` / `visible=0`），
  并把角色授权**物理删除后改挂**到承载同一权限码的新按钮上 ——
  `sys_role_menu` 不按 `deleted` 过滤（见 `auth/models.py::User.perm_codes`），软删不会真正收回权限。

### 9. 新增错误码

| 错误码 | 常量 | 含义 |
| --- | --- | --- |
| 94001 | `KNOWLEDGE_NOT_FOUND` | 文档 / 目录不存在 |
| 94002 | `KNOWLEDGE_PERMISSION_DENIED` | 没有该文档的操作权限 |
| 94003 | `KNOWLEDGE_FILE_TYPE_UNSUPPORTED` | 不支持该文件格式 |
| 94004 | `KNOWLEDGE_FILE_TOO_LARGE` | 文件超过允许的大小上限 |
| 94005 | `KNOWLEDGE_INVALID_STATE` | 当前文档状态不允许该操作 |
| 94006 | `KNOWLEDGE_LINK_EXPIRED` | 分享链接已过期或已被关闭 |
| 94007 | `KNOWLEDGE_LINK_VERIFY_REQUIRED` | 请先完成手机号验证 |
| 94008 | `KNOWLEDGE_CATEGORY_INVALID` | 文档分类非法（存在子分类或被引用） |
| 94009 | `KNOWLEDGE_LINK_CODE_INVALID` | 验证码错误或已失效 |
| 30006 | `RECYCLE_RETENTION_ACTIVE` | 该记录处于保留期内，暂不能彻底删除 |
| 30007 | `RECYCLE_ENTRY_NOT_FOUND` | 回收站记录不存在 |
| 30008 | `RECYCLE_RESTORE_FAILED` | 恢复失败，记录已被物理删除或数据表已变更 |
| 30009 | `RECYCLE_NOT_RECYLED` | 该记录不在回收站中 |

（后端 `app/core/response.py` 与前端 `src/api/types.ts` **双侧登记**。）

### 10. 新增迁移

- `ne2b3c4d5e6_knowledge_recycle.py`（**手写**，`alembic/env.py` 未 import knowledge / recycle 模型，autogenerate 会误删表）：
  建 `kb_category` / `kb_space` / `kb_folder` / `kb_file` / `kb_document` / `kb_version` / `kb_permission` / `kb_share_link` / `kb_link_log` / `sys_recycle_bin`。
- `sys_recycle_bin` **已登记进 `maintenance/service.py::_PURGE_TABLES`**（清空时连同编号序列一起清）；`kb_link_log` 登记进 `RETAINED_AUDIT_TABLES`（保留，不清）。
- `nf2b3c4d5e6_kb_space_pin.py`（**手写**）：`kb_space` 加 `pinned` 列（微盘左栏「置顶」分组）+ 索引。

## 变更日志（Keep a Changelog + 语义化版本）

**单一数据源 = 仓库根目录 `CHANGELOG.md`**（代码拥有、随版本走；镜像内由 `deploy/backend.Dockerfile` 的 `COPY CHANGELOG.md` 提供）。后端只解析不改写。

### 端点

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/admin/changelog` | 仅登录 | 返回当前版本号与全部版本条目 |

```jsonc
{
  "code": 0,
  "data": {
    "currentVersion": "0.7.0",       // 应用版本号（Settings.app_version）
    "latestVersion": "0.7.0",        // CHANGELOG.md 顶部版本
    "latestDate": "2026-11-23",
    "releases": [
      {
        "version": "0.7.0",
        "date": "2026-11-23",
        "sections": [
          {
            "type": "added",         // added/changed/deprecated/removed/fixed/security
            "items": [{ "text": "变更说明", "children": ["缩进子条目"] }]
          }
        ]
      }
    ]
  }
}
```

### Markdown 格式

```markdown
## [0.7.0] - 2026-11-23

### Added
- 变更说明
  - 缩进子条目
### Fixed
- 修复说明
```

- 解析器：`app/modules/admin/changelog.py::parse_changelog`（按 mtime 缓存，改文件即时生效）。
- 定位顺序：`CHANGELOG_PATH` 环境变量 → 仓库根 → 工作目录 → `/app/CHANGELOG.md`。
- 分类名未登记时原样透传（前端回退显示原名）。

### 版本号一致性（CI 校验）

`CHANGELOG.md` 顶部版本 == `Settings.app_version` == `frontend/package.json` == `backend/pyproject.toml`（含 `uv.lock`），版本号严格递减 —— 由 `tests/test_changelog.py` 断言。

### 菜单

- `menu.changelog` → `/admin/changelog`，componentKey `admin/ChangelogList`，权限 `admin:changelog:list`，挂在「系统管理 → 系统与审计」分组下。

## 前端组件键（componentKey → 懒加载组件）
```
workbench/Dashboard  crm/CustomerList  contract/ContractList  task/TaskList
finance/SettlementList  finance/InvoiceList  finance/PaymentList
procurement/PurchaseRequestList  procurement/PurchaseContractList  procurement/StockOrderList
procurement/TenderList  procurement/PartnerAccountList
report/ReportList
hr/TimesheetFill  hr/TimesheetStats  hr/AuthorizationList
hr/OrgStructureList  hr/PositionList  hr/StaffList  hr/PersonnelAffairsList
sales/QuotationList  sales/QuoteTemplateList
approval/TodoList
admin/UserList  admin/RoleList  admin/MenuList  admin/DictList
admin/NumberRuleList  admin/AuditLogList  admin/DeptList  admin/FlowDefList
admin/AiUsage  admin/AiSettings  admin/AutomationSettings  admin/ChangelogList
admin/RecycleBinList  admin/KnowledgeSettings
asset/PurchaseOrderList  asset/ReceiptList  asset/WarehouseList  asset/InventoryItemList
asset/StockLedgerList  asset/StockCountList  asset/PrototypeList  asset/PrototypeLoanList
asset/FixedAssetList  asset/DisposalList  asset/ToolList
asset/MaterialList  asset/BomList
project/ProjectList  production/ScheduleBoard
knowledge/DocumentCenter  knowledge/ShareLinkList
knowledge/ShareAccess
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
