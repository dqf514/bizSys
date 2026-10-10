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
  prefix: string
  dateFormat: string
  seqLen: number
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

export interface FlowNode {
  seq: number
  nodeName: string
  approverType: 'USER' | 'ROLE'
  approverValue: string | number
  approverName?: string
}

export interface FlowDef {
  id: number
  code: string
  name: string
  bizType: string
  enabled: boolean | number
  nodes: FlowNode[]
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
  | 'assigning'
  | 'assigned'
  | 'in_progress'
  | 'finished'
  | 'closed'
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
  reportCount: number
  sampleCount: number
  createTime: string
  updateTime: string
  items?: TaskItem[]
  samples?: TaskSample[]
  logs?: TaskLog[]
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

export type ApprovalAction = 'start' | 'agree' | 'reject' | 'withdraw' | 'add_sign' | 'transfer'

export interface ApprovalTask {
  id: number
  instanceId: number
  bizType: string
  bizId: number
  title: string
  status: string
  nodeName: string
  comment: string
  initiatorName: string
  assigneeName: string
  createTime: string
  actedAt: string | null
}

export interface TimelineRecord {
  action: ApprovalAction
  operatorName: string
  nodeName: string
  comment: string
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
  snapshot: Record<string, unknown> | null
  timeline?: TimelineRecord[]
}

/** Finance module — camelCase per backend convention */
export type SettlementStatus = 'pending' | 'invoicing' | 'invoiced' | 'paid'

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
