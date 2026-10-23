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
  roles: string[]
  perms: string[]
  prefs?: UserPrefs
  menus?: MenuNode[]
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
}

export interface CustomerDetail extends Customer {
  summary?: CustomerSummary
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
  createBy: string | number
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

export interface OaField {
  key: string
  label: string
  type: OaFieldType
  required?: boolean
  options?: string[]
  placeholder?: string
  maxlength?: number | null
  exposeVariable?: boolean
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
