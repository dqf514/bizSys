/** Shared API types aligned with docs/api-contract.md */

export interface Envelope<T> {
  code: number
  message: string
  data: T
  traceId?: string
}

export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  size: number
}

export interface MenuNode {
  id: number
  parentId: number | null
  name: string
  titleKey: string
  path: string
  componentKey: string
  icon: string
  permission: string
  menuType: 'dir' | 'menu' | 'button'
  sort: number
  visible: number
  children?: MenuNode[]
}

export interface UserPrefs {
  theme?: string
  locale?: string
  density?: string
  accent?: string
  navCollapsed?: boolean
  [key: string]: unknown
}

export interface UserProfile {
  id: number
  username: string
  name: string
  deptId?: number | null
  deptName?: string | null
  dept_id?: number | null
  dept_name?: string | null
  email?: string
  mobile?: string
  avatarUrl?: string
  avatar_url?: string
  mfaEnabled?: boolean
  roles: string[]
  perms: string[]
  prefs?: UserPrefs
  menus?: MenuNode[]
  allMenuPaths?: string[]
}

/** 批次B 个人档案（GET /auth/profile） */
export interface ProfileInfo {
  id: number
  username: string
  name: string
  mobile: string
  email: string
  employeeNo: string
  hireDate: string
  jobLevel: string
  avatarUrl: string
  deptName: string
  leaderName: string
  mfaEnabled: boolean
  roles: string[]
}

export interface EmergencyContact {
  id: number
  name: string
  relation: string
  phone: string
  remark: string
  createTime: string
}

export interface BankAccount {
  id: number
  bankName: string
  cardNo: string
  cardLast4: string
  holderName: string
  createTime: string
}

export interface StepUpResult {
  stepUpToken: string
  expiresIn: number
}

export interface LoginResult {
  access_token: string
  refresh_token: string
  token_type: string
  user: UserProfile
}

/** 登录第二步（用户已开启 MFA）：密码通过但未签发 token */
export interface MfaChannel {
  channel: 'sms' | 'email'
  target: string
}

export interface MfaChallenge {
  mfaRequired: true
  mfaToken: string
  channels: MfaChannel[]
}

export type LoginOutcome = LoginResult | MfaChallenge

export interface CaptchaResult {
  captchaId: string
  svg: string
  /** 仅非生产环境（ENV != prod）回显，便于自动化测试 */
  debugText?: string
}

export interface MfaSendResult {
  sent: boolean
  cooldown: number
  mode: 'real' | 'debug'
  /** 仅非生产环境（ENV != prod）回显 */
  debugCode?: string
}

export interface RefreshResult {
  access_token: string
  user: UserProfile
}

export interface AdminUser {
  id: number
  username: string
  name: string
  deptId: number | null
  deptName: string | null
  mobile: string
  email: string
  status: 'enabled' | 'disabled'
  employeeNo?: string
  hireDate?: string
  jobLevel?: string
  roles: string[]
  roleIds?: number[]
  createTime: string
  lastLoginAt?: string | null
}

export interface Role {
  id: number
  code: string
  name: string
  dataScope: string
  status: string
  remark: string
  menuIds: number[]
  createTime: string
}

export interface DictItem {
  id?: number
  dictTypeCode?: string
  label: string
  labelEn: string
  value: string
  sort: number
  status: string
  extra: string
}

export interface DictType {
  id: number
  code: string
  name: string
  remark: string
  items: DictItem[]
}

export interface DictItemOption {
  label: string
  labelEn: string
  value: string
  extra: string
}

export interface NumberRule {
  id: number
  bizType: string
  categoryKey: string
  prefix: string
  dateFormat: string
  yearDigits: number
  monthDigits: number
  dayDigits: number
  seqLen: number
  seqStart: number
  separator: string
  resetCycle: string
  enabled: number | boolean
  example: string
  preview?: string
}

export interface AuditLog {
  id: number
  username: string
  module: string
  action: string
  bizType: string
  bizId: number | string | null
  detail: string
  traceId: string
  ip: string
  createTime: string
}

export interface Dept {
  id: number
  parentId: number | null
  name: string
  code: string
  sort: number
  children?: Dept[]
}

export type FlowNodeType = 'approval' | 'condition' | 'cc'
export type FlowSignMode = 'or' | 'and' | 'sequential'
/** 审批人类型：固定人/角色 + 组织任职（DEPT_LEADER 本部门负责人 / PARENT_DEPT_LEADER 上级部门负责人 / SUPERVISOR_CHAIN 逐级上级） */
export type FlowApproverType = 'USER' | 'ROLE' | 'DEPT_LEADER' | 'PARENT_DEPT_LEADER' | 'SUPERVISOR_CHAIN'

export interface FlowBranch {
  expr: { field: string; op: string; value: unknown }
  targetSeq: number
}

export interface FlowNode {
  seq: number
  nodeName: string
  nodeType?: FlowNodeType
  signMode?: FlowSignMode
  approverType: FlowApproverType
  approverValue: string | number
  approverName?: string
  chainLevels?: number | null
  branches?: FlowBranch[] | null
  defaultSeq?: number | null
}

/** LogicFlow getGraphData 兼容结构（后端 process_graph 原样存储） */
export interface FlowGraphNode {
  id: string
  type: string
  x: number
  y: number
  text?: string
  properties?: Record<string, unknown>
}

export interface FlowGraphEdge {
  id?: string
  /** 缺省时 LogicFlow 无法按 model.type 找到边视图，导致边不渲染 */
  type?: string
  sourceNodeId: string
  targetNodeId: string
  properties?: Record<string, unknown>
}

export interface FlowGraphData {
  nodes: FlowGraphNode[]
  edges: FlowGraphEdge[]
}

export interface FlowDef {
  id: number
  code: string
  name: string
  bizType: string
  /** 定义版本号（同 code 递增，从 1 起） */
  version?: number
  /** 同 code 最新版本号（列表接口给出，用于标记历史版本） */
  latestVersion?: number
  enabled: boolean | number
  remark?: string
  variablesSchema?: Record<string, unknown> | null
  processGraph?: FlowGraphData | null
  nodes: FlowNode[]
}

/** 保存流程定义的返回：有进行中实例时自动另存新版本 */
export interface FlowDefSaveResult extends FlowDef {
  newVersion?: boolean
  runningCount?: number
}

/** POST /approval/preview 的分支预演结果 */
export interface FlowPreviewNode {
  seq: number
  nodeName: string
  nodeType: FlowNodeType
  signMode: FlowSignMode
}

export interface FlowPreviewResult {
  definitionCode: string
  variables: Record<string, unknown>
  route: FlowPreviewNode[]
}

export interface Customer {
  id: number
  customerNo: string
  name: string
  partnerType: 'customer' | 'supplier' | 'both'
  code: string
  customerType: string
  taxNo: string
  grade: string
  status: 'enabled' | 'disabled'
  address: string
  country: string
  province: string
  city: string
  bankName: string
  bankAccount: string
  payOrg: string
  contactPerson: string
  contactPhone: string
  licenseFileId: string | number | null
  supplyCategory: string
  supplierRating: string
  remark: string
  createTime: string
  updateTime: string
}

export interface OptionItem {
  id: number | string
  label: string
  sub?: string
}

/** /crm/customers/options carries extra payload for form auto-fill */
export interface CustomerOption extends OptionItem {
  partnerType?: string
  payOrg?: string
  taxNo?: string
  contactPerson?: string
  contactPhone?: string
}

/** /contract/contracts/options carries the bound customer for chain display */
export interface ContractOption extends OptionItem {
  customerId?: number | null
  customerName?: string
  paymentOrg?: string
}

export interface CustomerSummary {
  contractCount: number
  contractTotal: number | string
  taskCount: number
  settledTotal: number | string
  paidTotal: number | string
  purchaseContractCount: number
  purchaseTotal: number | string
}

export interface CustomerDetail extends Customer {
  summary?: CustomerSummary
}

/** 往来单位联系人（crm_partner_contact） */
export interface PartnerContact {
  id?: number
  customerId?: number
  name: string
  position: string
  phone: string
  email: string
  isPrimary: boolean
  remark: string
  createTime?: string
}

/** 往来单位附件（crm_partner_attachment） */
export interface PartnerAttachment {
  id: number
  customerId: number
  category: string
  fileName: string
  size: number
  contentType: string
  remark: string
  uploaderName: string
  createTime: string
}

/** GET /crm/customers/{id}/procurement：供应商采购清单 */
export interface PartnerProcurement {
  contracts: {
    id: number
    contractNo: string
    name: string
    amount: number | null
    status: string
    signDate: string
    createTime: string
  }[]
  requests: {
    id: number
    requestNo: string
    title: string
    status: string
    createTime: string
  }[]
}

export interface Attachment {
  id: number | string
  fileName: string
  size: number
  category?: string
}

export type ContractStatus = 'draft' | 'approving' | 'approved' | 'rejected' | 'voided'

export interface Contract {
  id: number
  contractNo: string
  name: string
  customerId: number
  customerName: string
  contractType: string
  subjectType: string
  amount: number | string
  startDate: string
  endDate: string
  payCycle: string
  delivery: string
  sealType: string
  handlerId: number | null
  handlerName: string
  frameworkNo: string
  paymentOrg: string
  contactPerson: string
  contactPhone: string
  remark: string
  status: ContractStatus
  flowInstanceId: number | null
  attachments: Attachment[]
  createTime: string
  updateTime: string
}

export type TaskStatus =
  | 'draft'
  | 'approving'
  | 'rejected'
  | 'in_progress'
  | 'finished'
  | 'settled'
  | 'stopped'

export interface Task {
  id: number
  taskNo: string
  taskName: string
  taskType: string
  taskTypeLabel?: string
  contractId: number | null
  contractNo: string
  customerId: number | null
  customerName: string
  bizBlock: string
  bizBlockLabel?: string
  deptId: number | null
  deptName: string
  ownerId: number | null
  ownerName: string
  content: string
  partySystem: string
  receiver: string
  receiverUnit: string
  planFinishDate: string
  status: TaskStatus
  /** 财务进度（结算单状态）：invoiced=已开票 / paid=已到账，用于列表徽标 */
  settleStatus?: string
  reportCount: number
  sampleCount: number
  /** 计划开始日期（B5） */
  planStartDate?: string
  /** 预计工时（小时），排程用（B5） */
  durationHours?: number
  /** 进度百分比 0-100（B5） */
  progress?: number
  /** 优先级 1(最高)~9(最低)（B5） */
  priority?: number
  /** 角色分组 sim/model/test/outsource（B5） */
  roleGroup?: string
  roleGroupText?: string
  /** 当前工序编码（B5） */
  processStage?: string
  /** CFD 网格数（万单元）（B5） */
  meshCount?: number | null
  /** 求解器（B5） */
  solver?: string
  /** 算力资源池（B5） */
  computeResource?: string
  computeCores?: number
  computeNodes?: number
  createTime: string
  updateTime: string
  items?: TaskItem[]
  samples?: TaskSample[]
  logs?: TaskLog[]
  flow?: TaskFlowInfo | null
}

/** 工序流转（B5）：task_process */
export interface TaskProcess {
  id: number
  taskId: number
  seq: number
  processCode: string
  processName: string
  status: 'pending' | 'running' | 'done' | 'skipped'
  statusText?: string
  isCurrent: boolean
  plannedStart: string
  plannedEnd: string
  actualStart: string
  actualEnd: string
  operatorId: number | null
  operatorName: string
  deptId: number | null
  deptName: string
  remark: string
}

/** 七维分配（B5）：task_assignment */
export interface TaskAssignment {
  id: number
  taskId: number
  dimension: 'person' | 'equipment' | 'material' | 'method' | 'env' | 'test' | 'safety' | 'vehicle'
  dimensionText?: string
  resourceId: number | null
  resourceCode: string
  resourceName: string
  qty: number
  unit: string
  status: 'pending' | 'allocated' | 'confirmed' | 'rejected'
  statusText?: string
  assignerId: number | null
  assignerName: string
  plannedAt: string
  confirmedAt: string
  remark: string
}

/** 全过程追溯节点（B5）：task_trace */
export interface TaskTrace {
  id: number
  taskId: number
  nodeCode: string
  nodeName: string
  nodeText?: string
  seq: number
  happenAt: string
  refNo: string
  operatorId: number | null
  operatorName: string
  remark: string
}

/** 任务操作流程图节点（B5）：工序 + 追溯合并 */
export interface OperationFlowNode {
  type: 'process' | 'trace'
  code: string
  name: string
  status: string
  statusText: string
  seq: number
  plannedStart?: string
  plannedEnd?: string
  actualStart?: string
  actualEnd?: string
  happenAt?: string
  refNo?: string
  operatorName: string
  remark: string
}

export interface OperationFlow {
  taskId: number
  taskNo: string
  taskName: string
  status: string
  processStage: string
  currentNode: OperationFlowNode | null
  nodes: OperationFlowNode[]
  total: number
}

/** 任务详情附带的立项流程实例信息（GET /tasks/{id} 返回的 flow 字段） */
export interface TaskFlowInfo {
  instanceId: number
  status: string
  definitionCode: string
  timeline: TimelineRecord[]
}

export interface TaskItem {
  id?: number
  itemCode: string
  name: string
  std: string
  dept: string
  inspector: string
  qty: number | string
  settleType: string
  needReport: boolean
  reportNo?: string
  reportStatus?: string
}

export interface TaskSample {
  id?: number
  sampleNo: string
  name: string
  model: string
  vin: string
  vehicleType: string
  sampleDate: string
  inStock: 'in' | 'out'
  /** 未确认（registered）的出入库单；存在时样品处于「确认中」 */
  pendingOrder?: StockOrderRef | null
}

/** 跨任务样品列表行（GET /task/samples） */
export interface SampleRow extends TaskSample {
  id: number
  taskId: number
  taskNo: string
  taskName: string
  customerName: string
  createTime: string
}

export interface TaskLog {
  id: number
  sampleNo?: string
  action: string
  operatorName: string
  createTime: string
  remark: string
}

export interface TaskCounts {
  [status: string]: number
}

export type ApprovalAction =
  | 'start'
  | 'agree'
  | 'reject'
  | 'withdraw'
  | 'add_sign'
  | 'transfer'
  | 'cc'
  | 'route'

export interface ApprovalTask {
  id: number
  instanceId: number
  bizType: string
  bizId: number
  title: string
  status: string
  nodeName: string
  nodeType?: string
  taskKind?: string
  comment: string
  initiatorName: string
  assigneeName: string
  unreadCount?: number
  instanceStatus?: string
  createTime: string
  actedAt: string | null
}

export interface TimelineRecord {
  action: ApprovalAction
  operatorName: string
  nodeName: string
  seq?: number
  comment: string
  payload?: Record<string, unknown> | null
  at: string
}

export interface ApprovalTimeline {
  instanceId: number
  status: string
  currentNode: string
  records: TimelineRecord[]
}

export interface ApprovalInstanceDetail {
  instanceId: number
  bizType: string
  bizId: number
  title: string
  status: string
  initiatorName: string
  currentNode: string
  currentNodeIds?: number[]
  variables?: Record<string, unknown> | null
  definitionCode?: string
  processGraph?: FlowGraphData | null
  snapshot: Record<string, unknown> | null
  timeline?: TimelineRecord[]
}

/** GET /approval/cc 抄送条目 */
export interface ApprovalCcItem {
  id: number
  instanceId: number
  bizType: string
  bizId: number
  title: string
  instanceStatus: string
  nodeName: string
  initiatorName: string
  readAt: string
  createTime: string
}

/** Finance module — camelCase per backend convention */
export type SettlementStatus = 'approving' | 'pending' | 'invoicing' | 'invoiced' | 'paid' | 'rejected'

export interface Settlement {
  id: number
  settlementNo: string
  taskId: number
  taskNo: string
  customerId?: number | null
  customerName: string
  contractId?: number | null
  contractNo: string
  amount: number | string
  invoiceableAmount: number | string
  status: SettlementStatus
  statusText?: string
  remark: string
  approvalInstanceId?: number | null
  /** 客户确认状态：''=未发送 pending=待确认 confirmed=已确认 objected=有异议 */
  confirmStatus?: '' | 'pending' | 'confirmed' | 'objected'
  confirmBy?: string
  confirmTime?: string
  confirmNote?: string
  createBy: string | number
  createTime: string
}

export interface SettlementConfirmRecord {
  id: number
  action: 'send' | 'confirm' | 'object'
  operatorName: string
  receiverName: string
  note: string
  createTime: string
}

export interface Invoice {
  id: number
  settlementId?: number
  invoiceNo: string
  amount: number | string
  invoiceDate: string
  status: string
}

export type InvoiceStatus = 'approving' | 'issued'

export interface InvoiceListItem {
  id: number
  invoiceNo: string
  settlementId: number
  settlementNo: string
  taskNo: string
  contractId?: number | null
  customerId?: number | null
  customerName: string
  amount: number | string
  taxRate?: number | null
  buyerName?: string
  sellerName?: string
  invoiceDate: string
  status: InvoiceStatus
  statusText?: string
  createBy: string | number
  createTime: string
}

export interface Payment {
  id: number
  paymentNo: string
  settlementId: number
  settlementNo: string
  contractId?: number | null
  customerId?: number | null
  payType: string
  payerName: string
  payerAccount: string
  amount: number | string
  bank: string
  paidAt: string
  remark: string
  createBy: string | number
  createTime: string
}

export interface SettlementDetail extends Settlement {
  invoices: Invoice[]
  payments: Payment[]
  paidAmount?: number | null
  timeline?: TimelineRecord[]
  confirmRecords?: SettlementConfirmRecord[]
}

export interface SettlementTaskOption {
  value: number
  label: string
  sub?: string
}

/** GET /contract/contracts/{id}/finance-summary */
export interface ContractFinanceSummary {
  contractAmount: number | string
  settledTotal: number | string
  invoicedTotal: number | string
  paidTotal: number | string
  settlementCount: number
  invoiceCount: number
  paymentCount: number
}

/** Report module — camelCase per backend convention */
export type ReportStatus = 'uploaded' | 'approving' | 'approved' | 'rejected' | 'sealed'

export interface Report {
  id: number
  reportNo: string
  taskId: number
  taskNo: string
  taskItemId: number
  itemName: string
  contractId?: number | null
  contractNo?: string
  customerId?: number | null
  customerName: string
  fileName: string
  status: ReportStatus
  statusText?: string
  pdfReady?: boolean
  sealBy?: string
  sealTime?: string
  remark?: string
  conclusion?: string
  approvalInstanceId?: number | null
  createBy: string
  createTime: string
}

export interface ReportDetail extends Report {
  timeline?: TimelineRecord[]
}

export interface ReportItemOption {
  value: number
  label: string
  sub?: string
}

/** In-app notification from /admin/notifies */
export interface NotifyItem {
  id: number
  title: string
  content: string
  bizType: string
  bizId: number | null
  link: string
  readFlag: boolean
  createTime: string
}

/** 消息中心页签计数（GET /admin/notifies/counts） */
export interface NotifyCounts {
  all: number
  unread: number
  byBizType: Record<string, number>
}

/** Dashboard widget layout entry, persisted in user prefs (`dashboard` key, JSON string) */
export interface DashboardWidgetPref {
  key: string
  visible: boolean
}

export interface DashboardPrefs {
  widgets: DashboardWidgetPref[]
}

/** Query params following the contract search convention */
export interface ListQuery {
  page?: number
  size?: number
  q?: string
  status?: string
  sort?: string
  filters?: Record<string, string | number | boolean | undefined>
  range?: Record<string, string>
  [key: string]: unknown
}

/* ---------- OA ---------- */

export type OaFieldType =
  | 'text'
  | 'textarea'
  | 'number'
  | 'money'
  | 'date'
  | 'daterange'
  | 'select'
  | 'radio'
  | 'checkbox'
  | 'file'
  | 'user'
  | 'resource'
  | 'divider'
  | 'text_block'

export type OaConditionOp = 'eq' | 'ne' | 'gt' | 'gte' | 'lt' | 'lte' | 'contains' | 'empty' | 'not_empty'

export interface OaConditionRule {
  field: string
  op: OaConditionOp
  value: string
}

export interface OaConditionGroup {
  logic: 'and' | 'or'
  rules: OaConditionRule[]
}

export type OaResourceType = 'customer' | 'contract' | 'task' | 'report' | 'dept' | 'user' | 'oa_instance'

export interface OaFieldMapping {
  /** 资源字段 key（来自 /oa/resources/meta 的 fields） */
  from: string
  /** 本表单控件 key */
  to: string
}

export interface OaCascade {
  /** 父控件 key */
  parent: string
  /** 父值 → 可选选项 */
  map: Record<string, string[]>
}

export interface OaResourceValue {
  id: number
  name: string
}

export interface OaField {
  key: string
  label: string
  type: OaFieldType
  required?: boolean
  options?: string[]
  placeholder?: string
  maxlength?: number | null
  exposeVariable?: boolean
  /** 栅格宽度：12=半行 / 24=整行（默认整行） */
  span?: 12 | 24 | null
  description?: string
  defaultValue?: unknown
  /** 条件显示：不满足则隐藏（提交时忽略） */
  showWhen?: OaConditionGroup | null
  /** 条件必填：满足时按必填校验 */
  requiredWhen?: OaConditionGroup | null
  /** 条件只读：满足时禁用编辑（前端约束） */
  readonlyWhen?: OaConditionGroup | null
  optionsSource?: 'manual' | 'dict'
  dictType?: string
  cascade?: OaCascade | null
  /** type=resource 时的资源类型 */
  resource?: OaResourceType | ''
  /** 资源选中后的带出字段映射 */
  mappings?: OaFieldMapping[]
}

export interface OaResourceMeta {
  type: OaResourceType
  label: string
  fields: { key: string; label: string }[]
}

export interface OaResourceItem {
  id: number
  label: string
  sub: string
  fields: Record<string, unknown>
}

export type OaFormStatus = 'draft' | 'published' | 'disabled'

export interface OaForm {
  id: number
  key: string
  name: string
  formVersion: number
  status: OaFormStatus
  category: string
  icon: string
  sort: number
  description: string
  flowDefinitionId: number | null
  /** 绑定流程名（列表接口给出） */
  flowName?: string | null
  /** 绑定流程定义的版本（列表接口给出） */
  flowVersion?: number | null
  /** 绑定流程同 code 最新启用版本（flowVersion < flowLatestVersion 时可一键绑定最新版） */
  flowLatestVersion?: number | null
  fields: OaField[] | null
  publishedAt: string
  createTime: string
}

export interface OaCatalogGroup {
  category: string
  forms: OaForm[]
}

export interface OaInstanceItem {
  id: number
  displayNo: string
  formId: number
  formKey: string
  formName: string
  formVersion: number
  category: string
  applicantId: number
  applicantName: string
  status: string
  pendingNames: string
  pendingTasks: { id: number; seq: number; nodeName: string; assigneeId: number; assigneeName: string }[]
  flowInstanceId: number
  createTime: string
  finishedAt: string
}

export interface OaInstanceDetail extends OaInstanceItem {
  schema: { fields?: OaField[] }
  formData: Record<string, unknown>
  timeline: TimelineRecord[]
}

export interface OaStatsForm {
  formKey: string
  formName: string
  count: number
}

export interface OaStatsBacklog {
  formKey: string
  formName: string
  instances: number
  pendingTasks: number
}

export interface OaStats {
  total: number
  inFlight: number
  byStatus: Record<string, number>
  byForm: OaStatsForm[]
  avgDurationHours: number
  trend: { month: string; count: number }[]
  backlog?: OaStatsBacklog[]
}

export interface OaFlowDefOption {
  id: number
  code: string
  name: string
  bizType: string
  version?: number
}

/* ---------- Procurement ---------- */

export type PurchaseStatus = 'draft' | 'approving' | 'approved' | 'rejected' | 'voided'

export interface PurchaseRequestItem {
  id?: number
  itemName: string
  spec: string
  unit: string
  quantity: number | string
  estimatePrice?: number | string | null
  remark?: string
}

export interface PurchaseRequest {
  id: number
  requestNo: string
  title: string
  taskId: number | null
  taskNo: string
  taskName: string
  purchaseMethod: string
  budgetAmount: number | string | null
  expectDate: string
  reason: string
  remark: string
  status: PurchaseStatus
  statusText?: string
  flowInstanceId: number | null
  items: PurchaseRequestItem[]
  version?: number | null
  createTime: string
  updateTime: string
}

export interface PurchaseRequestDetail extends PurchaseRequest {
  timeline?: TimelineRecord[]
  contractId?: number | null
  contractNo?: string
  contractStatus?: string
}

export interface PurchaseContract {
  id: number
  contractNo: string
  name: string
  requestId: number | null
  requestNo: string
  supplierId: number
  supplierName: string
  amount: number | string | null
  signDate: string
  startDate: string
  endDate: string
  payCycle: string
  delivery: string
  handlerId: number | null
  handlerName: string
  remark: string
  status: PurchaseStatus
  statusText?: string
  flowInstanceId: number | null
  version?: number | null
  createTime: string
  updateTime: string
}

export interface StockOrderRef {
  id: number
  orderNo: string
  orderType: 'in' | 'out'
  status: string
}

export interface PurchaseContractDetail extends PurchaseContract {
  timeline?: TimelineRecord[]
  stockOrders?: StockOrderRef[]
}

export type StockOrderStatus = 'registered' | 'confirmed'

export interface StockOrderItem {
  id?: number
  itemName: string
  spec: string
  unit: string
  quantity: number | string
  price?: number | string | null
  remark?: string
}

export interface StockOrder {
  id: number
  orderNo: string
  orderType: 'in' | 'out'
  orderTypeText?: string
  sourceType?: string
  sourceTypeText?: string
  sourceId?: number | null
  /** sourceType=sample 时后端补挂的来源信息 */
  sampleNo?: string
  sampleName?: string
  vin?: string
  taskId?: number
  taskNo?: string
  taskName?: string
  contractId: number | null
  contractNo: string
  contractName: string
  warehouse: string
  handlerId: number | null
  handlerName: string
  orderDate: string
  remark: string
  status: StockOrderStatus
  statusText?: string
  items: StockOrderItem[]
  version?: number | null
  createTime: string
  updateTime: string
}

/* ---------- Tender (Phase 2) ---------- */

export type TenderStatus = 'draft' | 'published' | 'evaluating' | 'awarding' | 'awarded' | 'terminated'

export interface TenderProject {
  id: number
  tenderNo: string
  name: string
  requestId: number | null
  requestNo: string
  tenderMethod: string
  budgetAmount: number | string | null
  regDeadline: string
  bidDeadline: string
  openTime: string
  announcement: string
  status: TenderStatus
  statusText?: string
  awardBidId: number | null
  winnerBidId: number | null
  winnerName: string
  winnerAmount: number | string | null
  contractId: number | null
  flowInstanceId: number | null
  version?: number | null
  createTime: string
  updateTime: string
}

export interface TenderRegistration {
  id: number
  partnerUserId: number
  companyName: string
  contactName: string
  contactPhone: string
  qualificationName: string
  hasAttachment: boolean
  status: 'pending' | 'approved' | 'rejected'
  statusText?: string
  reviewName: string
  reviewAt: string
  reviewComment: string
  createTime: string
}

export interface TenderEval {
  id: number
  bidId: number
  evaluatorId: number
  evaluatorName: string
  score: number | string
  comment: string
  recommend: boolean
  createTime: string
}

export interface TenderBid {
  id: number
  partnerUserId: number
  registrationId: number
  companyName: string
  price: number | string
  comment: string
  proposalName: string
  hasProposal: boolean
  submitAt: string
  isWinner: boolean
  evals: TenderEval[]
  avgScore: number | null
}

export interface TenderProjectDetail extends TenderProject {
  registrations: TenderRegistration[]
  bids: TenderBid[]
  timeline?: TimelineRecord[]
  contractNo?: string
  contractStatus?: string
}

export interface PartnerAccount {
  id: number
  username: string
  companyName: string
  contactName: string
  phone: string
  email: string
  status: 'pending' | 'enabled' | 'rejected' | 'disabled'
  statusText?: string
  customerId: number | null
  customerName?: string
  reviewName: string
  reviewAt: string
  reviewComment: string
  lastLoginAt: string
  createTime: string
}

/* ---------- Portal (Phase 2) ---------- */

export interface PortalPartner {
  id: number
  username: string
  companyName: string
  contactName: string
  phone: string
  email: string
  status: string
  customerId: number | null
  /** B2：customer 客户自助 / supplier 供应商投标 */
  accountType?: string
  /** B2：权限范围（逗号分隔）tender / entrust / staff */
  permScope?: string
}

export interface PortalTender {
  id: number
  tenderNo: string
  name: string
  tenderMethod: string
  budgetAmount: number | string | null
  regDeadline: string
  bidDeadline: string
  openTime: string
  announcement: string
  status: TenderStatus
  winnerName: string
  winnerAmount: number | string | null
  myRegistrationStatus?: string
  myBidId?: number | null
  isWinner?: boolean
}

export interface PortalRegistration {
  id: number
  tenderId: number
  tenderNo: string
  tenderName: string
  tenderStatus?: string
  regDeadline?: string
  bidDeadline?: string
  companyName: string
  contactName: string
  contactPhone: string
  qualificationName: string
  status: 'pending' | 'approved' | 'rejected'
  reviewComment: string
  createTime: string
}

export interface PortalBid {
  id: number
  tenderId: number
  tenderNo: string
  tenderName: string
  tenderStatus?: string
  regDeadline?: string
  bidDeadline?: string
  price: number | string
  comment: string
  proposalName: string
  submitAt: string
  isWinner: boolean
}

export interface PortalTenderDetail extends PortalTender {
  myRegistration: PortalRegistration | null
  myBid: PortalBid | null
}


/* ---------- HR（人事行政） ---------- */

export interface HrTimesheetItem {
  id: number
  userId: number
  userName: string
  workDate: string
  taskId: number
  taskNo: string
  taskName: string
  contractId: number
  contractNo: string
  customerId: number
  customerName: string
  hours: number
  content: string
  remark: string
  status: string // draft / submitted
  submittedAt: string
  createTime: string
  updateTime: string
}

export interface HrContractOption {
  id: number
  contractNo: string
  name: string
  customerName: string
}

export interface HrTaskOption {
  id: number
  taskNo: string
  taskName: string
  contractId: number
  contractNo: string
  customerName: string
}

export interface HrDayData {
  items: HrTimesheetItem[]
  totalHours: number
}

export interface HrWeekDay {
  date: string
  totalHours: number
  count: number
  future: boolean
}

export interface HrWeekSummary {
  weekStart: string
  days: HrWeekDay[]
}

export interface HrStatsRow {
  taskId?: number
  taskNo?: string
  taskName?: string
  contractId?: number
  contractNo?: string
  customerName?: string
  userId?: number
  userName?: string
  deptName?: string
  totalHours: number
  entryCount: number
  userCount?: number
  taskCount?: number
  dayCount?: number
}

export interface HrStatsResult {
  dimension: string
  rows: HrStatsRow[]
  grandTotalHours: number
}

export interface HrStatsOption {
  id: number
  label: string
  deptName?: string
  contractNo?: string
}

// ---------------- 销售系统（AI 报价） ----------------

export interface QuoteItemColumnConf {
  key: string
  label: string
  visible: boolean
}

export interface QuoteTemplateLayout {
  headerHtml: string
  introHtml: string
  termsHtml: string
  footerHtml: string
  validDays: number
  itemColumns: QuoteItemColumnConf[]
}

export interface QuoteTemplate {
  id: number
  key: string
  name: string
  status: string
  tplVersion: number
  layout: QuoteTemplateLayout
  sort: number
  publishedAt: string
  createTime: string
  updateTime: string
}

export interface QuotationItem {
  id?: number
  seq?: number
  name: string
  spec: string
  unit: string
  qty: number
  unitPrice: number
  amount: number
  remark: string
}

export interface Quotation {
  id: number
  quoteNo: string
  title: string
  customerId: number
  customerName: string
  contactName: string
  contactPhone: string
  contactEmail: string
  templateId: number | null
  tplVersion: number
  requirement: string
  introHtml: string
  termsHtml: string
  totalAmount: number
  taxRate: number
  currency: string
  validUntil: string
  status: string
  aiMeta: string
  autoSend: boolean
  sentAt: string
  sentChannel: string
  sentTo: string
  feedbackNote: string
  flowInstanceId: number | null
  contractId: number | null
  createTime: string
  updateTime: string
  items?: QuotationItem[]
  layout?: QuoteTemplateLayout
  timeline?: TimelineRecord[]
  sendLogs?: QuoteSendLog[]
}

export interface QuoteSendLog {
  id: number
  channel: string
  recipient: string
  result: string
  detail: string
  senderName: string
  sentAt: string
}

export interface AiGenerateResult {
  source: 'ai' | 'template' | 'history'
  fallbackReason: string
  title: string
  introHtml: string
  termsHtml: string
  items: QuotationItem[]
  aiMeta: string
}

export interface QuotationPayload {
  title: string
  customerId: number | undefined
  contactName: string
  contactPhone: string
  contactEmail: string
  templateId?: number | null
  requirement: string
  introHtml: string
  termsHtml: string
  taxRate: number
  validUntil: string | null
  autoSend: boolean
  aiMeta: string
  items: Partial<QuotationItem>[]
}


// ---------------- AI 中心 ----------------

export type AiFeatureKey =
  | 'quote'
  | 'contract_ocr'
  | 'task_photo'
  | 'report_summary'
  | 'approval_assist'
  | 'contract_risk'
  | 'report_assist'
  | 'nl_query'
  | 'hr_prefill'
  | 'oa_prefill'
  | 'flow_route'
  | 'flow_anomaly'
  | 'tender_assist'
  | 'sample_ocr'
  | 'invoice_ocr'
  | 'price_ref'
  | 'assistant'
  | 'daily_digest'
  | 'knowledge'
export type AiUsageStatus = 'success' | 'error' | 'fallback'

export interface AiUsageRow {
  id: number
  userName: string
  feature: string
  model: string
  promptTokens: number
  completionTokens: number
  totalTokens: number
  cost: number | null
  masking: string
  durationMs: number
  status: AiUsageStatus
  error: string
  bizType: string
  bizId: number | null
  createTime: string
}

export interface AiUsageStats {
  days: number
  cards: {
    totalCalls: number
    successCalls: number
    errorCalls: number
    fallbackCalls: number
    totalTokens: number
    totalCost: number
    successRate: number
    activeUsers: number
    avgDurationMs: number
  }
  trend: { date: string; calls: number; tokens: number }[]
  byFeature: { feature: string; calls: number; tokens: number }[]
  byUser: { userName: string; calls: number; tokens: number }[]
  byModel: { model: string; calls: number; tokens: number; cost: number }[]
}

export type AiMaskingLevel = 'off' | 'standard' | 'strict'

export interface AiModelPrice {
  model: string
  input: number
  output: number
}

export interface AiPromptInfo {
  key: string
  feature: string
  name: string
  version: string
  systemPreview: string
}

export interface AiCenterSettings {
  enabled: boolean
  features: Record<AiFeatureKey, boolean>
  quota: {
    userDailyCalls: number
    userDailyTokens: number
    globalDailyTokens: number
  }
  masking: AiMaskingLevel
  modelPrices: AiModelPrice[]
}

export interface AiCapabilities {
  enabled: boolean
  visionModel: string
  features: Record<AiFeatureKey, boolean>
}

export interface ContractParseResult {
  fields: {
    name: string
    customerName: string
    amount: number
    startDate: string
    endDate: string
    payCycle: string
    delivery: string
    sealType: string
    paymentOrg: string
    contactPerson: string
    contactPhone: string
    remark: string
  }
  customerCandidates: { id: number; name: string }[]
  source: string
}

// ---------------- AI 审批助手 / 合同风险审查 ----------------

export interface ApprovalAssistRisk {
  level: 'high' | 'mid' | 'low'
  text: string
}

export interface ApprovalAssistResult {
  summary: string
  highlights: string[]
  risks: ApprovalAssistRisk[]
  opinion: string
  customerHistory?: {
    customerName: string
    contractCount: number
    avgAmount: number | null
    thisAmount: number
    deviationPercent: number | null
    recentSimilarCount: number
    paidTotal?: number
  }
}

export interface ContractRiskItem {
  level: 'high' | 'mid' | 'low'
  clause: string
  issue: string
  suggestion: string
}

export interface ContractRiskResult {
  risks: ContractRiskItem[]
  missingClauses: string[]
  summary: string
  withText: boolean
}

export interface TaskProgressLogItem {
  id: number
  percent: number
  note: string
  imagePath: string
  source: 'ai' | 'manual'
  operatorName: string
  createTime: string
}

export interface TaskProgressAiDraft {
  percent: number
  note: string
  imagePath: string
}

export interface ReportSummaryDraft {
  summary: string
  source: string
}

// ---------------- AI 报告全文辅助 / 自然语言问数 ----------------

export type ReportAssistKind = 'conclusion' | 'proofread' | 'completeness'

export interface ReportAssistIssue {
  position: string
  original: string
  suggestion: string
}

export interface ReportAssistCheckItem {
  key: string
  ok: boolean
  detail: string
}

export interface ReportAssistResult {
  kind: ReportAssistKind
  conclusion?: string
  issues?: ReportAssistIssue[]
  items?: ReportAssistCheckItem[]
}

export interface NlQueryContext {
  domain?: string
  timeFrom?: string
  timeTo?: string
}

export interface NlQueryAnswer {
  domain: string
  domainLabel: string
  text: string
  rows: { label: string; value: string | number }[]
  link: string
  timeRange: { from: string; to: string }
  criteria: string
}

// ---------------- AI-4：OCR / 价格参考 / 助手 / 摘要 / 知识库 ----------------

export interface SampleOcrResult {
  name: string
  model: string
  vin: string
  vehicleType: string
  sampleDate: string
  source: string
}

export interface InvoiceOcrResult {
  fields: {
    invoiceNo: string
    amount: number
    taxRate: number | null
    buyer: string
    seller: string
    invoiceDate: string
  }
  amountCheck: {
    settlementAmount: number | null
    matches: boolean | null
    diff: number | null
  }
  source: string
}

export interface PriceReferenceResult {
  itemName: string
  stats: {
    count: number
    avg: number | null
    min: number | null
    max: number | null
    latestPrice: number | null
    latestAt: string
  }
  deviationPercent: number | null
  comment: string
}

export type AssistantReplyType = 'query' | 'navigate' | 'guide'

export interface AssistantReply {
  type: AssistantReplyType
  text: string
  path: string
  menuName: string
  data: NlQueryAnswer | null
  sources: { id: number; title: string; category: string }[]
  entries?: KnowledgeEntry[]
  degraded?: boolean
}

export interface DailyDigestResult {
  summary: string
  highlights: string[]
  degraded: boolean
  todos: {
    date: string
    approvalCount: number
    approvals: { title: string; node: string }[]
    overdueTasks: { title: string; dueDate: string }[]
    dueSoonTasks: { title: string; dueDate: string }[]
  }
}

export interface KnowledgeEntry {
  id: number
  title: string
  category: string
  content: string
  excerpt: string
  attachmentName: string
  hasAttachment: boolean
  createTime: string
  updateTime: string
}

export interface KnowledgeAskResult {
  answer: string
  sources: { id: number; title: string; category: string }[]
  entries: KnowledgeEntry[]
  degraded: boolean
}

/* ---------- 库存与资产（asset 域） ---------- */

/** 通用基类：所有 ast_* 单据共有。 */
export interface AssetBase {
  id: number
  version: number | null
  createTime?: string
  updateTime?: string
}

export interface AssetWarehouse extends AssetBase {
  code: string
  name: string
  deptId?: number | null
  deptName: string
  address: string
  managerId?: number | null
  managerName: string
  capacity?: number | null
  locationCount: number
  qtyOnHand: number
  stockAmount: number
  phone: string
  remark: string
  status: string
  statusText: string
}

export interface AssetLocation extends AssetBase {
  warehouseId: number | null
  code: string
  name: string
  area: string
  capacity: number | null
  used: number
  qtyOnHand: number
  remark: string
  status: string
  statusText: string
}

export interface AssetLocationOption {
  id: number
  warehouseId: number
  warehouseName: string
  code: string
  name: string
  area: string
}

export interface AssetWarehouseStats {
  warehouseCount: number
  locationCount: number
  batchCount: number
  stockAmount: number
  stockMap: Record<string, number>
}

export interface AssetItem extends AssetBase {
  code: string
  name: string
  spec: string
  unit: string
  category: string
  categoryText: string
  unitPrice: number | null
  safetyStock: number
  maxStock: number
  defaultWarehouseId?: number | null
  defaultLocationId?: number | null
  supplierId?: number | null
  supplierName: string
  manufacturer: string
  deptId?: number | null
  deptName: string
  qtyOnHand: number
  lowStock: boolean
  /** 呆滞预警阈值（天，0=不预警） */
  stagnantDays: number
  /** 最近一次出入库距今天数 */
  idleDays: number
  /** 最近一次出入库时间 */
  lastMoveAt: string
  /** 呆滞分级 normal / slow / stagnant / dead */
  stagnantLevel: string
  stagnantLevelText: string
  /** 是否构成呆滞（有库存且超过阈值） */
  stagnant: boolean
  /** 呆滞金额（在库数量 × 单价） */
  stagnantAmount: number
  /** 任一预警命中（低库存或呆滞） */
  warning: boolean
  remark: string
  status: string
  statusText: string
}

export interface AssetItemOption {
  id: number
  code: string
  name: string
  spec: string
  unit: string
  unitPrice: number
}

export interface AssetPurchaseOrderItem {
  id?: number
  itemId?: number | null
  itemCode: string
  itemName: string
  spec: string
  unit: string
  quantity: number
  price: number | null
  remark: string
}

export interface AssetPurchaseOrder extends AssetBase {
  orderNo: string
  title: string
  supplierId: number | null
  supplierName: string
  deptId?: number | null
  deptName: string
  orderDate?: string | null
  arriveDate?: string | null
  totalAmount: number | null
  handlerId?: number | null
  handlerName: string
  remark: string
  status: string
  statusText: string
  items: AssetPurchaseOrderItem[]
}

export interface AssetReceiptItem {
  id?: number
  itemId?: number | null
  itemCode: string
  itemName: string
  spec: string
  unit: string
  quantity: number
  qualifiedQty: number
  locationId?: number | null
  locationCode: string
  price: number | null
  remark: string
}

export interface AssetReceipt extends AssetBase {
  receiptNo: string
  orderId?: number | null
  orderNo: string
  warehouseId?: number | null
  warehouseName: string
  supplierId?: number | null
  supplierName: string
  arriveDate?: string | null
  totalQty: number
  qualifiedQty: number
  inspectorId?: number | null
  inspectorName: string
  remark: string
  status: string
  statusText: string
  items: AssetReceiptItem[]
}

export interface AssetLedger extends AssetBase {
  direction: string
  directionText: string
  itemId?: number | null
  itemCode: string
  itemName: string
  unit: string
  warehouseId?: number | null
  warehouseName: string
  locationId?: number | null
  locationCode: string
  quantity: number
  unitPrice: number | null
  amount: number
  reason: string
  reasonText: string
  bizType: string
  bizId?: number | null
  bizNo: string
  operatorId?: number | null
  operatorName: string
  deptId?: number | null
  deptName: string
  happenAt?: string | null
  remark: string
  editable: boolean
}

export interface AssetStockCountItem {
  id?: number
  itemId?: number | null
  itemCode: string
  itemName: string
  unit: string
  locationId?: number | null
  locationCode: string
  bookQty: number
  actualQty: number
  diffQty: number
  price: number | null
  diffAmount: number
  reason: string
}

export interface AssetStockCount extends AssetBase {
  countNo: string
  warehouseId?: number | null
  warehouseName: string
  countDate?: string | null
  totalQty: number
  diffCount: number
  operatorId?: number | null
  operatorName: string
  remark: string
  status: string
  statusText: string
  items: AssetStockCountItem[]
}

export interface AssetPrototype extends AssetBase {
  code: string
  name: string
  kind: string
  kindText: string
  model: string
  vin: string
  deptId?: number | null
  deptName: string
  locationId?: number | null
  locationName: string
  purchaseDate?: string | null
  value: number | null
  remark: string
  status: string
  statusText: string
}

export interface AssetPrototypeOption {
  id: number
  code: string
  name: string
  model: string
  status: string
}

export interface AssetPrototypeLoan extends AssetBase {
  loanNo: string
  prototypeId: number | null
  prototypeCode: string
  prototypeName: string
  borrowerId?: number | null
  borrowerName: string
  deptId?: number | null
  deptName: string
  loanDate?: string | null
  dueDate?: string | null
  returnDate?: string | null
  purpose: string
  handlerId?: number | null
  handlerName: string
  remark: string
  status: string
  statusText: string
}

export interface AssetFixedAsset extends AssetBase {
  assetNo: string
  name: string
  category: string
  categoryText: string
  model: string
  spec: string
  deptId?: number | null
  deptName: string
  custodianId?: number | null
  custodianName: string
  location: string
  purchaseDate?: string | null
  originalValue: number | null
  salvageRate: number
  usefulLifeMonths: number
  accumDepreciation: number
  netValue: number
  remark: string
  status: string
  statusText: string
}

export interface AssetDepreciation extends AssetBase {
  assetId: number
  assetNo: string
  assetName: string
  period: string
  amount: number
  accumAmount: number
  netValue: number
  method: string
  methodText: string
  operatorId?: number | null
  operatorName: string
  happenAt?: string | null
  remark: string
}

export interface AssetDisposal extends AssetBase {
  disposalNo: string
  assetId: number | null
  assetNo: string
  assetName: string
  disposalType: string
  disposalTypeText: string
  applyDate?: string | null
  originalValue: number | null
  netValue: number | null
  disposalAmount: number | null
  reason: string
  handlerId?: number | null
  handlerName: string
  approverId?: number | null
  approverName: string
  approveAt?: string | null
  remark: string
  status: string
  statusText: string
}

export interface AssetTool extends AssetBase {
  toolNo: string
  name: string
  spec: string
  model: string
  category: string
  categoryText: string
  unit: string
  warehouseId?: number | null
  warehouseName: string
  deptId?: number | null
  deptName: string
  purchaseDate?: string | null
  value: number | null
  remark: string
  status: string
  statusText: string
}

export interface AssetToolOption {
  id: number
  toolNo: string
  name: string
  spec: string
  status: string
}

export interface AssetToolLoan extends AssetBase {
  loanNo: string
  toolId: number | null
  toolNo: string
  toolName: string
  borrowerId?: number | null
  borrowerName: string
  deptId?: number | null
  deptName: string
  loanDate?: string | null
  dueDate?: string | null
  returnDate?: string | null
  purpose: string
  remark: string
  status: string
  statusText: string
}

/* ---------------- B4 物料清单（BOM）与呆滞预警 ---------------- */

export interface AssetBomLine {
  id: number
  bomId: number
  itemId?: number | null
  itemCode: string
  itemName: string
  spec: string
  unit: string
  /** 单位用量（每 1 个父件） */
  qty: number
  /** 损耗率 % */
  lossRate: number
  /** 理论用量 = qty × (1 + 损耗率) */
  requiredQty: number
  /** 位号 */
  refDesignator: string
  /** 装配位置 / 工序 */
  position: string
  remark: string
}

export interface AssetBom {
  id: number
  bomNo: string
  parentItemId: number
  parentItemCode: string
  parentItemName: string
  parentSpec: string
  /** BOM 版本号（如 V1.0） */
  version: string
  /** draft / effective / obsolete */
  status: string
  statusText: string
  effectiveDate?: string | null
  lineCount: number
  remark: string
  /** 乐观锁版本号 */
  lockVersion: number
  createTime?: string
  updateTime?: string
  lines?: AssetBomLine[]
}

/** BOM 多级展开节点 */
export interface AssetBomNode {
  itemId?: number | null
  itemCode: string
  itemName: string
  spec: string
  unit: string
  qty: number
  lossRate: number
  requiredQty: number
  refDesignator: string
  position: string
  level: number
  children: AssetBomNode[]
}

export interface AssetBomExplode {
  bomId: number
  bomNo: string
  parentItemName: string
  version: string
  tree: AssetBomNode[]
}

/** BOM 用量对比行：理论需求 vs 实际领用 */
export interface AssetBomUsageLine {
  itemId?: number | null
  itemCode: string
  itemName: string
  spec: string
  unit: string
  unitQty: number
  lossRate: number
  requiredQty: number
  actualOutQty: number
  diffQty: number
  refDesignator: string
  position: string
}

export interface AssetBomUsage {
  bomId: number
  bomNo: string
  parentItemName: string
  parentQty: number
  lines: AssetBomUsageLine[]
}

/** 存货作为子件被引用的 BOM 行 */
export interface AssetBomRefChild {
  bomId: number
  bomNo: string
  parentItemName: string
  version: string
  status: string
  qty: number
  lossRate: number
  requiredQty: number
  position: string
}

/** 存货的 BOM 关联反查 */
export interface AssetItemBomRefs {
  itemId: number
  itemCode: string
  itemName: string
  asParent: AssetBom[]
  asChild: AssetBomRefChild[]
}

export interface AssetBomLineInput {
  itemId?: number | null
  itemCode?: string
  itemName: string
  spec?: string
  unit?: string
  qty: number
  lossRate?: number
  refDesignator?: string
  position?: string
  remark?: string
}

export interface AssetBomInput {
  parentItemId: number
  bomVersion: string
  effectiveDate?: string | null
  remark?: string
  lines: AssetBomLineInput[]
  version?: number | null
}

/* ---------------- B2 客户自助体系：在线委托 / 客户方人员 / 客户自助账号 ---------------- */

export interface TaskEntrustItem {
  id: number
  itemCode: string
  name: string
  std: string
  qty: number | null
  needReport: boolean
  reportType: string
  remark: string
}

/** 在线委托创建入参（后端 CamelModel，字段名 snake_case 可直接提交） */
export interface TaskEntrustItemInput {
  id?: number
  item_code?: string
  name?: string
  std?: string
  qty?: number
  need_report?: number
  report_type?: string
  remark?: string
}

export interface TaskEntrustCreate {
  title: string
  entrust_type?: string
  contract_id?: number | null
  requirement?: string
  sample_desc?: string
  plan_start_date?: string | null
  plan_end_date?: string | null
  priority?: string
  amount?: number | null
  remark?: string
  items?: TaskEntrustItemInput[]
}

export interface TaskEntrust {
  id: number
  entrustNo: string
  title: string
  entrustType: string
  entrustTypeLabel: string
  contractId: number | null
  contractNo: string
  customerId: number | null
  customerName: string
  bizBlock: string
  source: string
  sourceText: string
  applicantType: string
  applicantId: number | null
  applicantName: string
  applicantPhone: string
  requirement: string
  sampleDesc: string
  planStartDate: string
  planEndDate: string
  priority: string
  amount: number | null
  status: string
  statusText: string
  handlerId: number | null
  handlerName: string
  bizOwnerId: number | null
  bizOwnerName: string
  reviewBy: number | null
  reviewName: string
  reviewAt: string
  reviewComment: string
  taskId: number | null
  taskNo: string
  remark: string
  itemCount: number
  items?: TaskEntrustItem[]
  version?: number
  createTime: string
  updateTime: string
}

export interface PartnerStaff {
  id: number
  customerId: number | null
  customerName: string
  name: string
  gender: string
  idNo: string
  position: string
  phone: string
  email: string
  plateNo: string
  company: string
  staffType: string
  staffTypeLabel: string
  visitPurpose: string
  planVisitDate: string
  ndaSigned: boolean
  visitPerm: string
  source: string
  sourceText: string
  applicantName: string
  status: string
  statusText: string
  reviewBy: number | null
  reviewName: string
  reviewAt: string
  reviewComment: string
  bizOwnerId: number | null
  bizOwnerName: string
  visitorId: number | null
  remark: string
  createTime: string
  updateTime: string
}

export interface CustomerAccount {
  id: number
  username: string
  companyName: string
  contactName: string
  phone: string
  email: string
  status: string
  accountType: string
  permScope: string
  permScopeList: string[]
  customerId: number | null
  managerId: number | null
  managerName: string
  staffLimit: number | null
  reviewBy: number | null
  reviewName: string
  reviewAt: string
  reviewComment: string
  lastLoginAt: string
  createTime: string
}

export interface PortalContract {
  id: number
  contractNo: string
  name: string
  contractType: string
  amount: number | null
  startDate: string
  endDate: string
}

export interface PortalEntrust {
  id: number
  entrustNo: string
  title: string
  entrustType: string
  contractId: number | null
  contractNo: string
  customerName: string
  requirement: string
  sampleDesc: string
  planStartDate: string
  planEndDate: string
  priority: string
  status: string
  statusText: string
  reviewComment: string
  taskNo: string
  itemCount: number
  createTime: string
}

export interface PortalStaff {
  id: number
  customerName: string
  name: string
  gender: string
  position: string
  phone: string
  email: string
  plateNo: string
  company: string
  staffType: string
  visitPurpose: string
  planVisitDate: string
  ndaSigned: boolean
  status: string
  statusText: string
  reviewComment: string
  createTime: string
}

/* ---------------- 访客与安全（B3） ---------------- */

export interface VisitorZone {
  id: number
  code: string
  name: string
  zoneType: string
  zoneTypeText?: string
  securityLevel: number
  needExtraApproval: boolean
  needEscort: boolean
  needNda: boolean
  needDualPerson: boolean
  cameraControl: boolean
  deviceBinding?: string
  capacity: number
  status: string
  remark?: string
  createTime?: string
}

export interface VisitorZoneInput {
  code: string
  name: string
  zone_type?: string
  security_level?: number
  need_extra_approval?: boolean
  need_escort?: boolean
  need_nda?: boolean
  need_dual_person?: boolean
  camera_control?: boolean
  device_binding?: string
  capacity?: number
  status?: string
  remark?: string
}

export interface VisitorApprovalRecord {
  id: number
  level: string
  levelText?: string
  approverName: string
  action: string
  comment: string
  decidedAt: string
}

export interface VisitorVisit {
  id: number
  visitNo: string
  visitorName: string
  visitorCompany: string
  visitorType: string
  visitorTypeText?: string
  idNo: string
  phone: string
  plateNo: string
  hostUserId: number | null
  hostName: string
  hostDeptId: number | null
  hostDeptName: string
  purpose: string
  source: string
  sourceText?: string
  zoneIds: string
  zoneNames: string
  escortNames: string
  planStart: string
  planEnd: string
  checkinAt: string
  checkoutAt: string
  status: string
  statusText?: string
  requiredLevels: string
  approvedLevels: string
  ndaId: number | null
  credentialId: number | null
  credentialNo: string
  staffId: number | null
  customerId: number | null
  customerName: string
  remark: string
  version?: number
  createTime: string
  updateTime: string
  approvals?: VisitorApprovalRecord[]
  handovers?: {
    id: number
    handoverNo: string
    sampleNo: string
    sampleName: string
    handoverUserName: string
    receiveUserName: string
    handoverAt: string
  }[]
}

export interface VisitorVisitInput {
  visitor_name: string
  visitor_company?: string
  visitor_type?: string
  id_no?: string
  phone?: string
  plate_no?: string
  host_user_id?: number | null
  host_name?: string
  host_dept_id?: number | null
  host_dept_name?: string
  purpose?: string
  source?: string
  zone_ids?: string
  escort_names?: string
  plan_start?: string | null
  plan_end?: string | null
  staff_id?: number | null
  customer_id?: number | null
  customer_name?: string
  remark?: string
}

export interface VisitorCredential {
  id: number
  credentialNo: string
  visitId: number | null
  visitorName: string
  credentialType: string
  credentialTypeText?: string
  zoneIds: string
  zoneNames: string
  validFrom: string
  validTo: string
  status: string
  code: string
  usedAt: string
  usedCount: number
  createTime: string
}

export interface VisitorAccessLog {
  id: number
  visitId: number | null
  credentialNo: string
  visitorName: string
  zoneId: number | null
  zoneName: string
  direction: string
  eventType: string
  method: string
  result: string
  deviceId: string
  operatorName: string
  happenedAt: string
  detail: string
}

export interface VisitorAccessLogSummary {
  days: number
  since: string
  total: number
  denied: number
  byDay: Record<string, number>
  byEvent: Record<string, number>
}

export interface VisitorNda {
  id: number
  ndaNo: string
  title: string
  template: string
  visitorName: string
  visitorCompany: string
  signerTitle: string
  idNo: string
  signedAt: string
  evidenceHash: string
  validFrom: string
  validTo: string
  status: string
  visitId: number | null
  staffId: number | null
  remark: string
  createTime: string
}

export interface VisitorBlacklist {
  id: number
  visitorName: string
  idNo: string
  phone: string
  company: string
  reason: string
  effectiveFrom: string
  effectiveTo: string
  source: string
  status: string
  remark: string
  createTime: string
}

export interface VisitorHandover {
  id: number
  handoverNo: string
  visitId: number | null
  sampleNo: string
  sampleName: string
  barcode: string
  sampleType: string
  qty: number
  handoverUserName: string
  receiveUserName: string
  handoverAt: string
  status: string
  remark: string
}

export interface VisitorAlert {
  id: number
  visitId: number | null
  alertType: string
  alertTypeText?: string
  level: string
  zoneId: number | null
  zoneName: string
  message: string
  occurredAt: string
  status: string
  handledByName: string
  handledAt: string
  handleRemark: string
}

export interface VisitorStats {
  visiting: number
  pending: number
  approved: number
  todayCheckins: number
  openAlerts: number
}

/** ---------------- B5 生产排程 ---------------- */

/** 排程方案：prd_plan */
export interface ProdPlan {
  id: number
  planNo: string
  name: string
  planDate: string
  status: 'draft' | 'published' | 'confirmed' | 'cancelled'
  statusText?: string
  autoGenerated: boolean
  taskCount: number
  conflictCount: number
  scheduleCount: number
  generatedByName: string
  publishedAt: string
  remark: string
  version: number
  createTime: string
  updateTime: string
  schedules?: ProdSchedule[]
}

/** 排程行：prd_schedule */
export interface ProdSchedule {
  id: number
  scheduleNo: string
  planId: number | null
  planNo: string
  taskId: number | null
  taskNo: string
  taskName: string
  projectId: number | null
  projectNo: string
  resourceType: 'equipment' | 'person' | 'vehicle' | 'material'
  resourceTypeText?: string
  resourceId: number | null
  resourceCode: string
  resourceName: string
  quantity: number
  unit: string
  planStart: string
  planEnd: string
  durationHours: number
  priority: number
  seq: number
  status: 'scheduled' | 'published' | 'confirmed' | 'done' | 'conflict' | 'cancelled'
  statusText?: string
  source: 'auto' | 'manual'
  conflictReason: string
  remark: string
  version: number
  createTime: string
  updateTime: string
}

/** 资源占用窗口（GET /production/resources/occupancy） */
export interface ResourceOccupancy {
  resourceType: string
  resourceTypeText?: string
  resourceId: number | null
  resourceName: string
  resourceCode: string
  occupiedHours: number
  taskCount: number
  windows: {
    scheduleId: number
    scheduleNo: string
    taskId: number | null
    taskNo: string
    taskName: string
    planStart: string
    planEnd: string
    status: string
    statusText?: string
  }[]
}

/** ---------------- B5 项目与甘特 ---------------- */

/** 项目：prj_project */
export interface Project {
  id: number
  projectNo: string
  name: string
  customerId: number | null
  customerName: string
  contractId: number | null
  contractNo: string
  managerId: number | null
  managerName: string
  deptId: number | null
  deptName: string
  startDate: string
  endDate: string
  status: 'draft' | 'planning' | 'executing' | 'accepting' | 'closed' | 'cancelled'
  statusText?: string
  progress: number
  budgetAmount: number
  actualAmount: number
  description: string
  remark: string
  taskCount: number
  version: number
  createTime: string
  updateTime: string
}

/** 项目任务（甘特行）：prj_project_task */
export interface ProjectTask {
  id: number
  taskId: number | null
  taskNo: string
  taskName: string
  seq: number
  groupCode: string
  groupText?: string
  ownerId: number | null
  ownerName: string
  startDate: string
  endDate: string
  progress: number
  milestone: boolean
  weight: number
  status: 'pending' | 'doing' | 'done' | 'delayed'
  dependsOn: string
  source: 'auto' | 'manual'
  remark: string
}

/** 项目甘特数据（GET /project/projects/{id}/gantt） */
export interface ProjectGantt {
  projectId: number
  projectNo: string
  projectName: string
  status: string
  progress: number
  startDate: string
  endDate: string
  items: ProjectTask[]
  milestones: ProjectTask[]
  total: number
  created?: number
}
