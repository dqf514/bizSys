# 合作方门户使用指南

合作方门户（`/portal`）面向供应商、客户等外部合作方，**移动优先**：首页、公告、我的参与、在线委托、人员备案、访客预约、进度看板、报告查阅、对账单、样品交接单全部可在手机上完成。

与内部系统账号体系完全隔离：独立 JWT（`typ=portal_access`，`aud=portal`），与内部 token 双向不可用；门户账号不并入 `sys_user`，存 `partner_user` 表，通过 `perm_scope` 字段控制可用的功能域（`tender` / `entrust` / `staff` / `visit`）。

---

## 一、页面结构

| 页面 | 路径 | 登录要求 | 说明 |
| --- | --- | --- | --- |
| 门户首页 | `/portal` | 免登录 | 品牌区 + 服务入口宫格 + 最新公告 + 我的进度摘要 |
| 招标公告 | `/portal/tenders` | 免登录 | 桌面左清单右详情；移动端清单→详情单栏切换 |
| 注册 | `/portal/register` | 免登录 | 走门户布局（顶栏/页脚/移动 Dock），不再是全屏覆盖层 |
| 登录 | `/login?tab=partner` | 免登录 | 已并入主登录页的「合作方登录」页签 |
| 我的参与 | `/portal/my` | 需门户登录 | 我的报名 / 我的投标 / 中标结果 |
| 在线委托 | `/portal/orders` | 需门户登录 | 下单 + 我的委托台账 |
| 人员备案 | `/portal/staff` | 需门户登录 | 外来人员登记与 NDA 签署状态 |
| 访客预约 | `/portal/visits` | 需门户登录 | 提交预约、查看审批进度与通行凭证 |
| 访客详情 | `/portal/visits/:id` | 需门户登录 | 审批时间线 + 凭证二维码 + 扫码签到/签离 |
| 进度看板 | `/portal/progress` | 需门户登录 | 委托/任务/结算/发票/回款聚合 |
| 报告查阅 | `/portal/reports` | 需门户登录 | 已归档报告在线查阅（一次性下载码） |
| 对账单 | `/portal/billing` | 需门户登录 | 结算 / 开票 / 回款状态 |
| 样品交接单 | `/portal/handovers` | 需门户登录 | 样品样车借出/归还记录 |

旧路由兼容：`/portal/login` → `/login?tab=partner`（保留 redirect）；`/portal/tenders/{id}` → `/portal/tenders?id={id}`。

---

## 二、合作方侧流程

### 1. 账号

1. 打开 `/portal` 浏览公告（无需账号）。
2. 注册：账号（4-64 位字母数字）、密码（≥8 位）、公司类型（供应商/客户）、公司名称、联系人/电话/邮箱。
3. 等待采购方审核；审核通过前不能登录（提示 96004）。
4. 登录后可在「我的」修改资料与改密（`/portal/account`）。

### 2. 招投标

1. `/portal/tenders` 浏览公告，支持关键词检索（编号/名称）与状态筛选（全部/已发布/评标中/定标审批中/已定标）；移动端状态筛选走**底部弹层**。
2. 公告详情显示报名/投标截止倒计时（≤3 天或已截止标红）；移动端主操作（报名/投标）**吸底**。
3. 报名（可传资质附件）→ 报名审核通过后投标（可传投标文件，截止前重复提交即改标）。
4. 定标后在公告详情/工作台查看中标公示。

### 3. 在线委托（需 `entrust` 权限范围）

- `/portal/orders` 下单（明细行：物料编码/名称/规格/数量/是否需要报告），提交后进入内部任务流程。
- 台账可取消**尚未开始**的委托。

### 4. 人员备案（需 `staff` 权限范围）

- `/portal/staff` 登记外来人员（类型、姓名、证件、手机、进出日期、NDA 签署状态）。
- NDA 需签署，内部「访客与安全 → 保密协议」页可查看；内部签署使用**手写签名板**（`SignaturePad.vue`，触屏可写）。

### 5. 访客预约闭环（需 `visit` 权限范围）★

这是本轮打通的核心链路：**外部发起 → 内部审批 → 通行凭证 → 扫码签到/签离**，审批链可在「系统管理 → 流程设置」里设计。

```
门户提交预约
   ↓  vis_visit.status = pending → 提交审批引擎（biz_type = visitor_visit）
内部审批（被访人 → 安保，条件节点可按敏感级别加签）
   ↓  通过：vis_visit.status = approved，自动下发通行凭证（vis_credential）+ 短信通知
   ↓  驳回：vis_visit.status = rejected
访客在门户查看凭证二维码 → 到访扫码签到（check_in）→ 离场签离（checkout）
```

| 步骤 | 门户动作 | 内部动作 |
| --- | --- | --- |
| 预约 | `POST /portal/visits`，填来访人、被访人、来访时段、区域、事由、车牌、NDA 确认 | 被访人在「流程待办」收到待办（站内信 + 企微） |
| 审批 | — | 审批通过后自动生成凭证并短信通知访客 |
| 凭证 | `GET /portal/visits/{id}/credential` 查看凭证号/有效期/授权区域；`GET /portal/visits/{id}/credential/qr` 取二维码（SVG） | 内部「访客」列表可见同一凭证 |
| 签到 | `POST /portal/visits/{id}/checkin`（或扫码 `/portal/visits/{id}/pass?code=`） | 访客域审计表 `visitor_access_log` 追加留痕 |
| 签离 | `POST /portal/visits/{id}/checkout` | 凭证状态转已离场 |
| 取消 | `POST /portal/visits/{id}/cancel`（仅待审批/审批中） | — |

> **审批链可配置**：流程定义 `biz_type = visitor_visit` 的节点在「流程设置」中编辑。节点审批人类型支持 `FORM_USER` / `FORM_ROLE` / `FORM_DEPT_LEADER`，其「审批人」取**表单变量名**（如 `hostUserId` = 被访人），而不是固定用户 id。变量清单在流程定义的「流程变量」里声明。

---

## 三、外部可见的经营数据（W3）

| 能力 | 端点 | 隔离口径 |
| --- | --- | --- |
| 进度看板 | `GET /portal/progress` | 按账号绑定往来单位过滤；聚合委托/任务/结算/发票/回款 |
| 报告查阅 | `GET /portal/reports` | 仅**本往来单位**任务下、已归档（sealed/approved）的报告；不含内部意见与审批人 |
| 报告下载 | `POST /portal/reports/{id}/download-code` → `GET /portal/reports/{id}/download?code=` | 下载码一次性，校验后即焚 |
| 对账单 | `GET /portal/billing` | 结算 / 开票 / 回款状态 |
| 样品交接单 | `GET /portal/handovers` | 本往来单位名下的样品样车借还记录 |

---

## 四、移动端说明

- 门户是**独立外壳**（`PortalLayout`），不复用内部 `AppShell`；底部 `PortalMobileDock` 提供首页/公告/我的等快捷入口，并处理 `env(safe-area-inset-bottom)`。
- 所有列表在窄屏（<768px）自动**降级为卡片流**（`ResponsiveTable.vue`）：第一列作卡片标题，其余列渲染为「标签：值」行。
- 底部主操作吸底：审批意见/同意/驳回（`ApprovalActionbar`）、报名/投标提交、预约提交。
- 弹层型筛选（公告状态）走**底部弹层**而非顶部长条。
- 表单在窄屏 `label-position="top"`，输入框最小触控高度 44px；手机号 `inputmode="tel"`、邮箱 `inputmode="email"`。
- 支持「添加到主屏」：`manifest.webmanifest` + `apple-touch-icon` + `theme-color`（明暗双值）。

---

## 五、管理侧

### 合作方账号

入口：**往来单位** 页面顶部切换到「合作方账号」视图（`/crm/customers?tab=accounts`）；或往来单位详情抽屉的「门户账号」tab。

| 操作 | 说明 |
| --- | --- |
| 审核（通过/拒绝/停用） | 通过时可绑定供应商往来单位（用于定标后生成采购合同） |
| 新建账号 | 直接启用、无需审核；可一并绑定往来单位 |
| 编辑资料/改绑/解绑 | **清空即解绑**；解绑后不能投标，定标后也无法生成合同 |
| 重置密码 | 自动生成随机密码或指定（8-64 位）；新密码仅展示一次 |
| 删除 | 软删；已有报名/投标记录的账号不能删除（96007），只能停用 |

权限码：`procurement:partner:list/create/edit/review/delete`。

### 门户功能范围（perm_scope）

在合作方账号编辑里勾选可用功能域：

| 值 | 能力 |
| --- | --- |
| `tender` | 招投标 |
| `entrust` | 在线任务委托 |
| `staff` | 外来人员备案 |
| `visit` | 访客预约 |

### 访客审批流程设计

「系统管理 → 流程设置」→ 业务类型 `visitor_visit`：

1. **流程变量**：声明 `hostUserId`、`hostDeptId`、`hostName`、`securityLevel`、`zoneIds`、`customerId` 等表单变量。
2. **节点审批人类型**：
   - `FORM_USER` — 取变量里的用户 id（被访人）
   - `FORM_ROLE` — 取变量里的角色 code
   - `FORM_DEPT_LEADER` — 取变量里的部门 id 的部门负责人
3. **条件节点**：按 `instance.variables` 路由，例如 `securityLevel >= 3` 走敏感区域加签。
4. **总开关**：`flow.visitor_visit.enabled`（系统管理 → 自动化开关）。关闭时流程直通（直接置为已通过），域内人工审批接口恢复可用。

---

## 六、对接说明

详见 `docs/api-contract.md` 的「合作方门户 /portal」与「F6 对外门户扩展」两节。

错误码：

| 码 | 含义 |
| --- | --- |
| 96004 | 账号待审核 / 未启用 |
| 96007 | 存在关联记录，不可删除 |
| 98011 | 无权访问该访客预约 |
| 98012 | 凭证已过期或无效 |
| 98013 | 报告下载码无效或已使用 |
