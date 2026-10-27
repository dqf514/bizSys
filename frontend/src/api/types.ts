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
  createTime: string
  updateTime: string
  items?: TaskItem[]
  samples?: TaskSample[]
  logs?: TaskLog[]
  flow?: TaskFlowInfo | null
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
