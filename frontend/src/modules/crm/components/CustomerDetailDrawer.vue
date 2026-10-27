<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type FormInstance, type UploadFile } from 'element-plus'
import { useI18n } from 'vue-i18n'
import StatusTag from '@/components/common/StatusTag.vue'
import CountUp from '@/components/common/CountUp.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import SettlementDetailDrawer from '@/modules/finance/components/SettlementDetailDrawer.vue'
import PartnerAccountFormDialog from './PartnerAccountFormDialog.vue'
import PartnerAccountResetDialog from './PartnerAccountResetDialog.vue'
import { useDictOptions } from '@/composables/useDict'
import { useAuthStore } from '@/stores/auth'
import {
  getCustomer,
  listPartnerContacts,
  createPartnerContact,
  updatePartnerContact,
  deletePartnerContact,
  listPartnerAttachments,
  uploadPartnerAttachment,
  downloadPartnerAttachment,
  deletePartnerAttachment,
  customerProcurement,
  listPartnerAccounts,
  reviewPartnerAccount,
  deletePartnerAccount,
} from '@/api/crm'
import { listContracts } from '@/api/contract'
import { listTasks } from '@/api/task'
import { listSettlements } from '@/api/finance'
import type {
  Contract,
  CustomerDetail,
  PartnerAccount,
  PartnerAttachment,
  PartnerContact,
  PartnerProcurement,
  Settlement,
  Task,
} from '@/api/types'

defineOptions({ name: 'CustomerDetailDrawer' })

const props = defineProps<{
  modelValue: boolean
  customerId: number | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
}>()

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()

const loading = ref(false)
const detail = ref<CustomerDetail | null>(null)

const typeOpts = useDictOptions('customer_type')
const gradeOpts = useDictOptions('customer_grade')
const supplyOpts = useDictOptions('supply_category')
const attCatOpts = useDictOptions('partner_attachment_category')

const isSupplier = computed(() => (detail.value?.partnerType ?? 'customer') !== 'customer')
// 采购 tab 需要采购合同列表权限，无权限隐藏
const canViewProcurement = computed(() => auth.hasPerm('procurement:contract:list'))
// 门户账号 tab 沿用合作方账号管理权限
const canViewAccounts = computed(() => auth.hasPerm('procurement:partner:list'))

function attCatLabel(value: unknown) {
  const v = String(value ?? '')
  return attCatOpts.opts.value.find((x) => x.value === v)?.label || v || '-'
}

function supplyLabel(value: unknown) {
  const v = String(value ?? '')
  return supplyOpts.opts.value.find((x) => x.value === v)?.label || v || '-'
}

function typeLabel(value: unknown) {
  const v = String(value ?? '')
  return typeOpts.opts.value.find((x) => x.value === v)?.label || v || '-'
}

function gradeLabel(value: unknown) {
  const v = String(value ?? '')
  return gradeOpts.opts.value.find((x) => x.value === v)?.label || v || '-'
}

function fmtMoney(v: number | string | undefined | null) {
  const n = Number(v ?? 0)
  return Number.isFinite(n) ? n.toLocaleString() : String(v ?? '-')
}

function toNum(v: number | string | undefined | null) {
  const n = Number(v ?? 0)
  return Number.isFinite(n) ? n : 0
}

async function load() {
  if (!props.customerId) return
  loading.value = true
  try {
    detail.value = await getCustomer(props.customerId)
    // 供应商类型默认落采购 tab（有权限时），否则合同 tab
    activeTab.value = isSupplier.value && canViewProcurement.value ? 'procurement' : 'contracts'
  } catch {
    detail.value = null
  } finally {
    loading.value = false
  }
}

/* ---------- related records (lazy per tab) ---------- */
const activeTab = ref('contracts')
const contracts = ref<Contract[]>([])
const tasks = ref<Task[]>([])
const settlements = ref<Settlement[]>([])
const procurement = ref<PartnerProcurement>({ contracts: [], requests: [] })
const relatedLoading = ref(false)
const loadedTabs = new Set<string>()

async function loadRelated(tab: string) {
  if (!props.customerId || loadedTabs.has(tab)) return
  loadedTabs.add(tab)
  relatedLoading.value = true
  try {
    if (tab === 'contracts') {
      const data = await listContracts({ page: 1, size: 100, filters: { customer_id: props.customerId } })
      contracts.value = data.items ?? []
    } else if (tab === 'tasks') {
      const data = await listTasks({ page: 1, size: 100, filters: { customer_id: props.customerId } })
      tasks.value = data.items ?? []
    } else if (tab === 'settlements') {
      const data = await listSettlements({ page: 1, size: 100, filters: { customer_id: props.customerId } })
      settlements.value = data.items ?? []
      settlementTotal.value = data.total ?? settlements.value.length
    } else if (tab === 'procurement') {
      procurement.value = await customerProcurement(props.customerId)
    }
  } catch {
    /* keep empty */
  } finally {
    relatedLoading.value = false
  }
}

/* ---------- tab badges ---------- */
// 合同/任务/采购数取自详情 summary；结算数 summary 未提供，用一次轻量 count 查询
const contractTotal = computed(() => toNum(detail.value?.summary?.contractCount))
const taskTotal = computed(() => toNum(detail.value?.summary?.taskCount))
const purchaseTotal = computed(() => toNum(detail.value?.summary?.purchaseContractCount))
const settlementTotal = ref(0)

async function loadSettlementCount() {
  if (!props.customerId) return
  try {
    const data = await listSettlements({ page: 1, size: 1, filters: { customer_id: props.customerId } })
    settlementTotal.value = data.total ?? 0
  } catch {
    settlementTotal.value = 0
  }
}

watch(activeTab, (tab) => void loadRelated(tab))

watch(
  () => [props.modelValue, props.customerId],
  ([visible]) => {
    if (visible) {
      detail.value = null
      contracts.value = []
      tasks.value = []
      settlements.value = []
      procurement.value = { contracts: [], requests: [] }
      settlementTotal.value = 0
      contacts.value = []
      attachments.value = []
      attCategory.value = ''
      portalAccounts.value = []
      loadedTabs.clear()
      activeTab.value = 'contracts'
      void load().then(() => {
        void loadRelated(activeTab.value)
      })
      void loadSettlementCount()
      void loadContacts()
      void loadAttachments()
      void loadAccounts()
    }
  },
)

const settleDrawerVisible = ref(false)
const settleDrawerId = ref<number | null>(null)

function openContract(row: Contract) {
  router.push(`/contract/contracts/${row.id}`)
}

function openTask(row: Task) {
  router.push(`/task/tasks/${row.id}`)
}

function openSettlement(row: Settlement) {
  settleDrawerId.value = row.id
  settleDrawerVisible.value = true
}

function openPurchaseContract(id: number) {
  router.push({ path: '/procurement/contracts', query: { detail: id } })
}

function openPurchaseRequest(id: number) {
  router.push({ path: '/procurement/requests', query: { detail: id } })
}

/* ---------- 联系人 ---------- */
const contacts = ref<PartnerContact[]>([])
const contactTotal = computed(() => contacts.value.length)
const contactDialogVisible = ref(false)
const contactSaving = ref(false)
const contactFormRef = ref<FormInstance>()
const editingContactId = ref<number | null>(null)
const contactForm = reactive({
  name: '',
  position: '',
  phone: '',
  email: '',
  isPrimary: false,
  remark: '',
})

async function loadContacts() {
  if (!props.customerId) return
  try {
    const data = await listPartnerContacts(props.customerId)
    contacts.value = data.items ?? []
  } catch {
    contacts.value = []
  }
}

function openContactCreate() {
  editingContactId.value = null
  Object.assign(contactForm, { name: '', position: '', phone: '', email: '', isPrimary: false, remark: '' })
  contactDialogVisible.value = true
}

function openContactEdit(row: PartnerContact) {
  editingContactId.value = row.id ?? null
  Object.assign(contactForm, {
    name: row.name,
    position: row.position,
    phone: row.phone,
    email: row.email,
    isPrimary: row.isPrimary,
    remark: row.remark,
  })
  contactDialogVisible.value = true
}

async function saveContact() {
  if (!contactFormRef.value || !props.customerId) return
  const ok = await contactFormRef.value.validate().catch(() => false)
  if (!ok) return
  contactSaving.value = true
  try {
    const payload = { ...contactForm }
    if (editingContactId.value) await updatePartnerContact(editingContactId.value, payload)
    else await createPartnerContact(props.customerId, payload)
    ElMessage.success(t('common.message.saveSuccess'))
    contactDialogVisible.value = false
    void loadContacts()
  } catch {
    /* http notifies */
  } finally {
    contactSaving.value = false
  }
}

async function removeContact(row: PartnerContact) {
  try {
    await ElMessageBox.confirm(t('crm.contact.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deletePartnerContact(row.id!)
    ElMessage.success(t('common.message.deleteSuccess'))
    void loadContacts()
  } catch {
    /* http notifies */
  }
}

function contactRowActions(): ActionItem[] {
  return [
    { key: 'edit', tip: 'common.action.edit', perm: 'crm:customer:edit' },
    { key: 'delete', tip: 'common.action.delete', perm: 'crm:customer:edit' },
  ]
}

function onContactAction(key: string, row: PartnerContact) {
  if (key === 'edit') openContactEdit(row)
  else if (key === 'delete') void removeContact(row)
}

/* ---------- 附件 ---------- */
const attachments = ref<PartnerAttachment[]>([])
const attachmentTotal = computed(() => attachments.value.length)
const attCategory = ref('')
const uploadDialogVisible = ref(false)
const uploadSaving = ref(false)
const uploadForm = reactive({ category: 'license', remark: '' })
const uploadFile = ref<File | null>(null)
const uploadFileName = ref('')

async function loadAttachments() {
  if (!props.customerId) return
  try {
    const data = await listPartnerAttachments(props.customerId, attCategory.value)
    attachments.value = data.items ?? []
  } catch {
    attachments.value = []
  }
}

function openUpload() {
  Object.assign(uploadForm, { category: 'license', remark: '' })
  uploadFile.value = null
  uploadFileName.value = ''
  uploadDialogVisible.value = true
}

function onPickFile(f: UploadFile) {
  uploadFile.value = f.raw ?? null
  uploadFileName.value = f.name
}

async function doUpload() {
  if (!props.customerId || !uploadFile.value) return
  uploadSaving.value = true
  try {
    await uploadPartnerAttachment(props.customerId, uploadFile.value, uploadForm.category, uploadForm.remark)
    ElMessage.success(t('crm.attachment.uploadSuccess'))
    uploadDialogVisible.value = false
    void loadAttachments()
  } catch {
    /* http notifies */
  } finally {
    uploadSaving.value = false
  }
}

function fmtSize(v: number) {
  const n = Number(v ?? 0)
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${n} B`
}

async function removeAttachment(row: PartnerAttachment) {
  try {
    await ElMessageBox.confirm(t('crm.attachment.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deletePartnerAttachment(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    void loadAttachments()
  } catch {
    /* http notifies */
  }
}

function attachmentRowActions(): ActionItem[] {
  return [
    { key: 'download', tip: 'common.action.download', perm: 'crm:customer:list' },
    { key: 'delete', tip: 'common.action.delete', perm: 'crm:customer:edit' },
  ]
}

function onAttachmentAction(key: string, row: PartnerAttachment) {
  if (key === 'download') void downloadPartnerAttachment(row.id, row.fileName)
  else if (key === 'delete') void removeAttachment(row)
}

/* ---------- 门户账号（绑定到本单位的合作方账号） ---------- */
const portalAccounts = ref<PartnerAccount[]>([])
const accountTotal = computed(() => portalAccounts.value.length)

async function loadAccounts() {
  if (!props.customerId || !canViewAccounts.value) return
  try {
    const data = await listPartnerAccounts({ page: 1, size: 100, filters: { customer_id: props.customerId } })
    portalAccounts.value = data.items ?? []
  } catch {
    portalAccounts.value = []
  }
}

function accountRowActions(row: PartnerAccount): ActionItem[] {
  const acts: ActionItem[] = []
  if (row.status === 'pending' || row.status === 'rejected' || row.status === 'disabled') {
    acts.push({ key: 'approve', tip: 'crm.account.approve', icon: 'CircleCheck', perm: 'procurement:partner:review' })
  }
  if (row.status === 'pending') {
    acts.push({ key: 'reject', tip: 'crm.account.reject', icon: 'CircleClose', danger: true, perm: 'procurement:partner:review' })
  }
  if (row.status === 'enabled') {
    acts.push({ key: 'disable', tip: 'crm.account.disable', icon: 'CircleClose', danger: true, perm: 'procurement:partner:review' })
  }
  acts.push({ key: 'edit', tip: 'crm.account.edit', icon: 'EditPen', perm: 'procurement:partner:edit' })
  acts.push({ key: 'resetPwd', tip: 'crm.account.resetPwd', icon: 'Key', perm: 'procurement:partner:edit' })
  acts.push({ key: 'delete', tip: 'crm.account.delete', icon: 'Delete', danger: true, perm: 'procurement:partner:delete' })
  return acts
}

function onAccountAction(key: string, row: PartnerAccount) {
  if (key === 'approve') void approveAccount(row)
  else if (key === 'reject') void rejectAccount(row)
  else if (key === 'disable') void disableAccount(row)
  else if (key === 'edit') openAccountForm(row)
  else if (key === 'resetPwd') openAccountReset(row)
  else if (key === 'delete') void deleteAccount(row)
}

/* ---------- 门户账号：编辑/重置密码/删除 ---------- */
const accountFormVisible = ref(false)
const accountFormTarget = ref<PartnerAccount | null>(null)
const accountResetVisible = ref(false)
const accountResetTarget = ref<PartnerAccount | null>(null)

function openAccountForm(row: PartnerAccount) {
  accountFormTarget.value = row
  accountFormVisible.value = true
}

function openAccountReset(row: PartnerAccount) {
  accountResetTarget.value = row
  accountResetVisible.value = true
}

async function deleteAccount(row: PartnerAccount) {
  try {
    await ElMessageBox.confirm(
      t('crm.account.deleteConfirm', { name: row.companyName || row.username }),
      t('common.action.confirm'),
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await deletePartnerAccount(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    void loadAccounts()
  } catch {
    /* http notifies */
  }
}

/* ---------- 门户注册地址（空态引导） ---------- */
const portalRegisterUrl = `${window.location.origin}/portal/register`

async function copyPortalUrl() {
  try {
    await navigator.clipboard.writeText(portalRegisterUrl)
    ElMessage.success(t('common.message.copySuccess'))
  } catch {
    ElMessage.warning(t('common.message.copyFail'))
  }
}

async function approveAccount(row: PartnerAccount) {
  try {
    await ElMessageBox.confirm(
      t('crm.account.approveBindConfirm', { name: row.companyName || row.username }),
      t('common.action.confirm'),
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await reviewPartnerAccount(row.id, { approve: true, customerId: props.customerId })
    ElMessage.success(t('common.message.saveSuccess'))
    void loadAccounts()
  } catch {
    /* http notifies */
  }
}

async function rejectAccount(row: PartnerAccount) {
  let comment = ''
  try {
    const { value } = await ElMessageBox.prompt(
      t('crm.account.rejectConfirm'),
      t('crm.account.reject'),
      { inputPlaceholder: t('crm.account.reviewComment'), confirmButtonText: t('common.action.confirm'), cancelButtonText: t('common.action.cancel') },
    )
    comment = value ?? ''
  } catch {
    return
  }
  try {
    await reviewPartnerAccount(row.id, { approve: false, comment })
    ElMessage.success(t('common.message.saveSuccess'))
    void loadAccounts()
  } catch {
    /* http notifies */
  }
}

async function disableAccount(row: PartnerAccount) {
  try {
    await ElMessageBox.confirm(t('crm.account.disableConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await reviewPartnerAccount(row.id, { approve: false })
    ElMessage.success(t('common.message.saveSuccess'))
    void loadAccounts()
  } catch {
    /* http notifies */
  }
}

</script>

<template>
  <el-drawer
    :model-value="props.modelValue"
    size="720px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template #header>
      <div class="drawer-header">
        <span class="drawer-title">{{ detail?.name || t('crm.customer.detail') }}</span>
        <template v-if="detail">
          <el-tag size="small" effect="plain">{{ gradeLabel(detail.grade) }}</el-tag>
          <el-tag size="small" type="warning" effect="plain">
            {{ t(`crm.customer.partnerType${(detail.partnerType || 'customer').charAt(0).toUpperCase()}${(detail.partnerType || 'customer').slice(1)}`) }}
          </el-tag>
          <StatusTag :status="detail.status" i18n-prefix="common.status" />
        </template>
      </div>
    </template>

    <div v-loading="loading" class="drawer-body">
      <template v-if="detail">
        <div class="section-title">{{ t('crm.detail.basicInfo') }}</div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="t('crm.customer.customerNo')">{{ detail.customerNo }}</el-descriptions-item>
          <el-descriptions-item :label="t('crm.customer.customerType')">{{ typeLabel(detail.customerType) }}</el-descriptions-item>
          <el-descriptions-item :label="t('crm.customer.contactPerson')">{{ detail.contactPerson || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('crm.customer.contactPhone')">{{ detail.contactPhone || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('crm.customer.taxNo')">{{ detail.taxNo || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('crm.customer.payOrg')">{{ detail.payOrg || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('crm.customer.bankName')">{{ detail.bankName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('crm.customer.bankAccount')">{{ detail.bankAccount || '-' }}</el-descriptions-item>
          <template v-if="detail.partnerType !== 'customer'">
            <el-descriptions-item :label="t('crm.customer.supplyCategory')">
              {{ supplyLabel(detail.supplyCategory) }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('crm.customer.supplierRating')">
              {{ detail.supplierRating || '-' }}
            </el-descriptions-item>
          </template>
          <el-descriptions-item :label="t('crm.customer.address')" :span="2">
            {{ [detail.country, detail.province, detail.city, detail.address].filter(Boolean).join(' ') || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('crm.customer.remark')" :span="2">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div v-if="detail.summary" class="stat-strip bs-stagger">
          <div class="stat-card">
            <div class="stat-label">{{ t('crm.detail.contractCount') }}</div>
            <div class="stat-value"><CountUp :value="toNum(detail.summary.contractCount)" /></div>
          </div>
          <div class="stat-card">
            <div class="stat-label">{{ t('crm.detail.contractTotal') }}</div>
            <div class="stat-value"><CountUp :value="toNum(detail.summary.contractTotal)" /></div>
          </div>
          <div class="stat-card">
            <div class="stat-label">{{ t('crm.detail.taskCount') }}</div>
            <div class="stat-value"><CountUp :value="toNum(detail.summary.taskCount)" /></div>
          </div>
          <div class="stat-card">
            <div class="stat-label">{{ t('crm.detail.settledTotal') }}</div>
            <div class="stat-value"><CountUp :value="toNum(detail.summary.settledTotal)" /></div>
          </div>
          <div class="stat-card">
            <div class="stat-label">{{ t('crm.detail.paidTotal') }}</div>
            <div class="stat-value stat-paid"><CountUp :value="toNum(detail.summary.paidTotal)" /></div>
          </div>
          <template v-if="isSupplier">
            <div class="stat-card">
              <div class="stat-label">{{ t('crm.detail.purchaseContractCount') }}</div>
              <div class="stat-value"><CountUp :value="toNum(detail.summary.purchaseContractCount)" /></div>
            </div>
            <div class="stat-card">
              <div class="stat-label">{{ t('crm.detail.purchaseTotal') }}</div>
              <div class="stat-value"><CountUp :value="toNum(detail.summary.purchaseTotal)" /></div>
            </div>
          </template>
        </div>

        <el-tabs v-model="activeTab">
          <el-tab-pane v-if="canViewProcurement" name="procurement">
            <template #label>
              {{ t('crm.detail.procurement') }}
              <span v-if="purchaseTotal" class="bs-tab-count">({{ purchaseTotal }})</span>
            </template>
            <div v-loading="relatedLoading" class="tab-stack">
              <div class="section-title">{{ t('crm.detail.purchaseContracts') }}</div>
              <el-table :data="procurement.contracts" border stripe size="small">
                <el-table-column :label="t('procurement.contract.contractNo')" prop="contractNo" width="150">
                  <template #default="{ row }">
                    <el-button link type="primary" @click="openPurchaseContract(row.id)">
                      {{ row.contractNo || '-' }}
                    </el-button>
                  </template>
                </el-table-column>
                <el-table-column :label="t('procurement.contract.name')" prop="name" min-width="150" />
                <el-table-column :label="t('procurement.contract.amount')" prop="amount" width="110" align="right">
                  <template #default="{ row }">{{ fmtMoney(row.amount) }}</template>
                </el-table-column>
                <el-table-column :label="t('common.form.status')" prop="status" width="110">
                  <template #default="{ row }">
                    <StatusTag :status="String(row.status)" i18n-prefix="common.status" />
                  </template>
                </el-table-column>
                <el-table-column :label="t('procurement.contract.signDate')" prop="signDate" width="110" />
              </el-table>
              <div class="section-title">{{ t('crm.detail.purchaseRequests') }}</div>
              <el-table :data="procurement.requests" border stripe size="small">
                <el-table-column :label="t('procurement.request.requestNo')" prop="requestNo" width="150">
                  <template #default="{ row }">
                    <el-button link type="primary" @click="openPurchaseRequest(row.id)">
                      {{ row.requestNo || '-' }}
                    </el-button>
                  </template>
                </el-table-column>
                <el-table-column :label="t('procurement.request.requestTitle')" prop="title" min-width="150" />
                <el-table-column :label="t('common.form.status')" prop="status" width="110">
                  <template #default="{ row }">
                    <StatusTag :status="String(row.status)" i18n-prefix="common.status" />
                  </template>
                </el-table-column>
                <el-table-column :label="t('procurement.contract.createTime')" prop="createTime" width="160" />
              </el-table>
            </div>
          </el-tab-pane>

          <el-tab-pane name="contracts">
            <template #label>
              {{ t('crm.detail.contracts') }}
              <span v-if="contractTotal" class="bs-tab-count">({{ contractTotal }})</span>
            </template>
            <el-table v-loading="relatedLoading" :data="contracts" border stripe size="small">
              <el-table-column :label="t('contract.contract.contractNo')" prop="contractNo" width="150" sortable>
                <template #default="{ row }">
                  <el-button link type="primary" @click="openContract(row as unknown as Contract)">
                    {{ row.contractNo }}
                  </el-button>
                </template>
              </el-table-column>
              <el-table-column :label="t('contract.contract.name')" prop="name" min-width="160" sortable />
              <el-table-column :label="t('contract.contract.amount')" prop="amount" width="120" sortable align="right">
                <template #default="{ row }">{{ fmtMoney(row.amount) }}</template>
              </el-table-column>
              <el-table-column :label="t('common.form.status')" prop="status" width="110" sortable>
                <template #default="{ row }">
                  <StatusTag :status="String(row.status)" i18n-prefix="contract.contract.status" />
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane name="tasks">
            <template #label>
              {{ t('crm.detail.tasks') }}
              <span v-if="taskTotal" class="bs-tab-count">({{ taskTotal }})</span>
            </template>
            <el-table v-loading="relatedLoading" :data="tasks" border stripe size="small">
              <el-table-column :label="t('task.task.taskNo')" prop="taskNo" width="150" sortable>
                <template #default="{ row }">
                  <el-button link type="primary" @click="openTask(row as unknown as Task)">
                    {{ row.taskNo }}
                  </el-button>
                </template>
              </el-table-column>
              <el-table-column :label="t('task.task.taskName')" prop="taskName" min-width="160" sortable />
              <el-table-column :label="t('common.form.status')" prop="status" width="110" sortable>
                <template #default="{ row }">
                  <StatusTag :status="String(row.status)" i18n-prefix="task.task.status" />
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane name="settlements">
            <template #label>
              {{ t('crm.detail.settlements') }}
              <span v-if="settlementTotal" class="bs-tab-count">({{ settlementTotal }})</span>
            </template>
            <el-table v-loading="relatedLoading" :data="settlements" border stripe size="small">
              <el-table-column :label="t('finance.settlement.settlementNo')" prop="settlementNo" width="150" sortable>
                <template #default="{ row }">
                  <el-button link type="primary" @click="openSettlement(row as unknown as Settlement)">
                    {{ row.settlementNo }}
                  </el-button>
                </template>
              </el-table-column>
              <el-table-column :label="t('finance.settlement.amount')" prop="amount" width="120" sortable align="right">
                <template #default="{ row }">{{ fmtMoney(row.amount) }}</template>
              </el-table-column>
              <el-table-column :label="t('common.form.status')" prop="status" width="110" sortable>
                <template #default="{ row }">
                  <StatusTag :status="String(row.status)" i18n-prefix="finance.settlement.status" />
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane name="contacts">
            <template #label>
              {{ t('crm.detail.contacts') }}
              <span v-if="contactTotal" class="bs-tab-count">({{ contactTotal }})</span>
            </template>
            <div class="tab-toolbar">
              <el-button v-permission="'crm:customer:edit'" size="small" type="primary" plain @click="openContactCreate">
                {{ t('crm.contact.add') }}
              </el-button>
            </div>
            <el-table :data="contacts" border stripe size="small">
              <el-table-column :label="t('crm.contact.name')" prop="name" min-width="100">
                <template #default="{ row }">
                  {{ row.name }}
                  <el-tag v-if="row.isPrimary" size="small" type="warning" effect="plain" class="primary-tag">
                    {{ t('crm.contact.primaryTag') }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column :label="t('crm.contact.position')" prop="position" width="110" />
              <el-table-column :label="t('crm.contact.phone')" prop="phone" width="130" />
              <el-table-column :label="t('crm.contact.email')" prop="email" min-width="140" />
              <el-table-column :label="t('crm.contact.remark')" prop="remark" min-width="100" show-overflow-tooltip />
              <el-table-column :label="t('common.action.operate')" width="90" fixed="right" align="center" header-align="center">
                <template #default="{ row }">
                  <ActionBar
                    :actions="contactRowActions()"
                    @select="(key: string) => onContactAction(key, row as unknown as PartnerContact)"
                  />
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane name="attachments">
            <template #label>
              {{ t('crm.detail.attachments') }}
              <span v-if="attachmentTotal" class="bs-tab-count">({{ attachmentTotal }})</span>
            </template>
            <div class="tab-toolbar tab-toolbar-split">
              <el-select
                v-model="attCategory"
                clearable
                :placeholder="t('crm.attachment.category')"
                style="width: 160px"
                @change="loadAttachments"
              >
                <el-option v-for="o in attCatOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
              <el-button v-permission="'crm:customer:edit'" size="small" type="primary" plain @click="openUpload">
                {{ t('crm.attachment.upload') }}
              </el-button>
            </div>
            <el-table :data="attachments" border stripe size="small">
              <el-table-column :label="t('crm.attachment.fileName')" prop="fileName" min-width="170" show-overflow-tooltip />
              <el-table-column :label="t('crm.attachment.category')" width="110">
                <template #default="{ row }">{{ attCatLabel(row.category) }}</template>
              </el-table-column>
              <el-table-column :label="t('crm.attachment.size')" width="90" align="right">
                <template #default="{ row }">{{ fmtSize(row.size) }}</template>
              </el-table-column>
              <el-table-column :label="t('crm.attachment.uploader')" prop="uploaderName" width="90" />
              <el-table-column :label="t('crm.attachment.uploadTime')" prop="createTime" width="150" />
              <el-table-column :label="t('common.action.operate')" width="90" fixed="right" align="center" header-align="center">
                <template #default="{ row }">
                  <ActionBar
                    :actions="attachmentRowActions()"
                    @select="(key: string) => onAttachmentAction(key, row as unknown as PartnerAttachment)"
                  />
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
          <el-tab-pane v-if="canViewAccounts" name="accounts">
            <template #label>
              {{ t('crm.detail.portalAccounts') }}
              <span v-if="accountTotal" class="bs-tab-count">({{ accountTotal }})</span>
            </template>
            <el-table :data="portalAccounts" border stripe size="small">
              <el-table-column :label="t('crm.account.username')" prop="username" width="130" />
              <el-table-column :label="t('crm.account.contactName')" prop="contactName" width="100" />
              <el-table-column :label="t('crm.account.phone')" prop="phone" width="130" />
              <el-table-column :label="t('crm.account.email')" prop="email" min-width="140" show-overflow-tooltip />
              <el-table-column :label="t('crm.account.status')" width="90">
                <template #default="{ row }">
                  <StatusTag :status="String(row.status)" i18n-prefix="common.status" />
                </template>
              </el-table-column>
              <el-table-column :label="t('crm.account.createTime')" prop="createTime" width="150" />
              <el-table-column :label="t('crm.account.reviewInfo')" min-width="150">
                <template #default="{ row }">
                  {{ [row.reviewName, row.reviewAt].filter(Boolean).join(' · ') || '-' }}
                </template>
              </el-table-column>
              <el-table-column :label="t('common.action.operate')" width="90" fixed="right" align="center" header-align="center">
                <template #default="{ row }">
                  <ActionBar
                    :actions="accountRowActions(row as unknown as PartnerAccount)"
                    @select="(key: string) => onAccountAction(key, row as unknown as PartnerAccount)"
                  />
                </template>
              </el-table-column>
              <template #empty>
                <div class="account-empty">
                  <p>{{ t('crm.account.emptyTip') }}</p>
                  <p class="portal-url-row">
                    <span>{{ t('crm.account.portalRegisterTip') }}：{{ portalRegisterUrl }}</span>
                    <el-button size="small" text type="primary" @click="copyPortalUrl">
                      {{ t('common.action.copy') }}
                    </el-button>
                  </p>
                </div>
              </template>
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </template>
    </div>

    <PartnerAccountFormDialog
      v-model="accountFormVisible"
      :account="accountFormTarget"
      @saved="loadAccounts"
    />
    <PartnerAccountResetDialog
      v-model="accountResetVisible"
      :account="accountResetTarget"
      @saved="loadAccounts"
    />

    <el-dialog
      v-model="contactDialogVisible"
      :title="editingContactId ? t('crm.contact.edit') : t('crm.contact.add')"
      width="520px"
      append-to-body
    >
      <el-form ref="contactFormRef" :model="contactForm" label-width="100px">
        <el-form-item :label="t('crm.contact.name')" prop="name" :rules="[{ required: true, message: t('common.form.required') }]">
          <el-input v-model="contactForm.name" :maxlength="64" />
        </el-form-item>
        <el-form-item :label="t('crm.contact.position')" prop="position">
          <el-input v-model="contactForm.position" :maxlength="64" />
        </el-form-item>
        <el-form-item :label="t('crm.contact.phone')" prop="phone">
          <el-input v-model="contactForm.phone" :maxlength="32" />
        </el-form-item>
        <el-form-item :label="t('crm.contact.email')" prop="email">
          <el-input v-model="contactForm.email" :maxlength="128" />
        </el-form-item>
        <el-form-item :label="t('crm.contact.isPrimary')" prop="isPrimary">
          <el-switch v-model="contactForm.isPrimary" />
        </el-form-item>
        <el-form-item :label="t('crm.contact.remark')" prop="remark">
          <el-input v-model="contactForm.remark" type="textarea" :rows="2" :maxlength="500" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="contactDialogVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="contactSaving" @click="saveContact">{{ t('common.action.save') }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="uploadDialogVisible" :title="t('crm.attachment.upload')" width="520px" append-to-body>
      <el-form label-width="100px">
        <el-form-item :label="t('crm.attachment.category')" required>
          <el-select v-model="uploadForm.category" style="width: 100%">
            <el-option v-for="o in attCatOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('crm.attachment.fileName')" required>
          <el-upload :auto-upload="false" :limit="1" :show-file-list="false" :on-change="onPickFile">
            <el-button>{{ t('crm.attachment.pickFile') }}</el-button>
            <span v-if="uploadFileName" class="picked-file">{{ uploadFileName }}</span>
            <span v-else class="picked-file picked-empty">{{ t('crm.attachment.noFile') }}</span>
          </el-upload>
        </el-form-item>
        <el-form-item :label="t('crm.attachment.remark')">
          <el-input v-model="uploadForm.remark" type="textarea" :rows="2" :maxlength="500" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadDialogVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="uploadSaving" :disabled="!uploadFile" @click="doUpload">
          {{ t('common.action.upload') }}
        </el-button>
      </template>
    </el-dialog>

    <SettlementDetailDrawer v-model="settleDrawerVisible" :settlement-id="settleDrawerId" />
  </el-drawer>
</template>

<style scoped>
.drawer-header {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.drawer-title {
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
}

.drawer-body {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}

.section-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.stat-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--bs-space-2);
}

.stat-card {
  padding: var(--bs-space-2) var(--bs-space-3);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-app);
}

.stat-label {
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-secondary);
}

.stat-value {
  margin-top: var(--bs-space-1);
  font-size: var(--bs-typography-font-size-xl);
  font-weight: 700;
  line-height: 1.2;
}

.stat-paid {
  color: var(--bs-color-semantic-success);
}

.tab-stack {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.tab-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: var(--bs-space-2);
}

.tab-toolbar-split {
  justify-content: space-between;
}

.primary-tag {
  margin-left: var(--bs-space-1);
}

.picked-file {
  margin-left: var(--bs-space-2);
  font-size: var(--bs-typography-font-size-sm);
}

.picked-empty {
  color: var(--bs-color-fg-secondary);
}

.account-empty {
  padding: var(--bs-space-4) var(--bs-space-3);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
  text-align: center;
}

.account-empty p {
  margin: 0 0 var(--bs-space-2);
}

.portal-url-row {
  display: inline-flex;
  align-items: center;
  gap: var(--bs-space-1);
  word-break: break-all;
}
</style>
