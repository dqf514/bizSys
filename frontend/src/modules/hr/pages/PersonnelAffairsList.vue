<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { useListPage } from '@/composables/useListPage'
import {
  createDelegate,
  createEmployment,
  deleteDelegate,
  effectEmployment,
  employeeOptions,
  employmentCounts,
  getEmployment,
  getOrgOptions,
  listDelegates,
  listEmployments,
  submitEmployment,
  updateDelegate,
  updateEmployment,
  withdrawEmployment,
  type DelegatePayload,
  type EmploymentPayload,
} from '@/api/hr'
import { listRoles, userOptions } from '@/api/admin'
import { useAuthStore } from '@/stores/auth'
import type { HrDelegate, HrEmployeeOption, HrEmployment, HrEmploymentDetail } from '@/api/types'

defineOptions({ name: 'PersonnelAffairsList' })

const { t } = useI18n()
const auth = useAuthStore()

/* ---------------- 枚举 ---------------- */

const EVENT_TYPES = ['onboard', 'transfer', 'resign', 'rehire']
const EMPLOYMENT_STATUSES = ['draft', 'approving', 'approved', 'effective', 'rejected']
const DELEGATE_SCOPES = ['position', 'auth', 'task']

const eventTypeOptions = computed(() =>
  EVENT_TYPES.map((v) => ({ label: t(`hr.employment.eventTypeType.${v}`), value: v })),
)
const delegateScopeOptions = computed(() =>
  DELEGATE_SCOPES.map((v) => ({ label: t(`hr.delegate.scopeType.${v}`), value: v })),
)

function eventTypeLabel(v: unknown) {
  const key = String(v ?? '')
  return EVENT_TYPES.includes(key) ? t(`hr.employment.eventTypeType.${key}`) : key || '-'
}

function scopeLabel(v: unknown) {
  const key = String(v ?? '')
  return DELEGATE_SCOPES.includes(key) ? t(`hr.delegate.scopeType.${key}`) : key || '-'
}

/* ---------------- 选项 ---------------- */

const deptOptions = ref<{ value: number; label: string }[]>([])
const positionOptions = ref<{ value: number; label: string }[]>([])
const employeeList = ref<HrEmployeeOption[]>([])
const userOptionsList = ref<{ value: number; label: string }[]>([])
const roleOptions = ref<{ value: number; label: string }[]>([])

async function loadOptions() {
  try {
    const opts = await getOrgOptions()
    deptOptions.value = (opts?.depts ?? []).map((d) => ({ value: d.value, label: d.label }))
    positionOptions.value = (opts?.positions ?? []).map((p) => ({ value: p.value, label: p.label }))
  } catch {
    deptOptions.value = []
    positionOptions.value = []
  }
  try {
    const opts = await employeeOptions()
    employeeList.value = opts?.all ?? []
  } catch {
    employeeList.value = []
  }
  try {
    const users = (await userOptions()) ?? []
    userOptionsList.value = users.map((u) => ({ value: u.id, label: u.label }))
  } catch {
    userOptionsList.value = []
  }
  if (auth.hasPerm('admin:role:list')) {
    try {
      const res = await listRoles({ page: 1, size: 100 })
      roleOptions.value = (res?.items ?? []).map((r) => ({ value: r.id, label: r.name }))
    } catch {
      roleOptions.value = []
    }
  }
}

onMounted(() => {
  void loadOptions()
})

/* ---------------- 检索 ---------------- */

const searchModel = ref<Record<string, any>>({ q: '', eventType: '' })
const searchFields = computed<SearchField[]>(() => [
  { key: 'q', labelKey: 'hr.employment.empNo', placeholderKey: 'common.form.placeholderSearch', width: 220 },
  { key: 'eventType', labelKey: 'hr.employment.eventType', type: 'select', width: 140, options: eventTypeOptions.value },
])

function buildFilters() {
  return { event_type: searchModel.value.eventType || undefined }
}

/* ---------------- 状态页签 ---------------- */

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  ...EMPLOYMENT_STATUSES.map((s) => ({ value: s, labelKey: `hr.employment.statusType.${s}`, count: 0 })),
])

async function loadCounts() {
  try {
    const data = (await employmentCounts()) ?? {}
    for (const tab of statusTabs.value) tab.count = data[tab.value] ?? 0
  } catch {
    /* counts optional */
  }
}

onMounted(() => {
  void loadCounts()
})

const list = useListPage<HrEmployment>({
  fetch: async (params) => {
    const data = await listEmployments({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(),
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

/* ---------------- 列 ---------------- */

const columns: ListColumn[] = [
  { prop: 'empNo', labelKey: 'hr.employment.empNo', width: 140, fixed: 'left', sortable: 'emp_no' },
  { prop: 'eventTypeText', labelKey: 'hr.employment.eventType', width: 90, sortable: 'event_type' },
  { prop: 'userName', labelKey: 'hr.employment.employee', width: 110 },
  { prop: 'deptName', labelKey: 'hr.employment.deptName', width: 140 },
  { prop: 'newDeptName', labelKey: 'hr.employment.newDeptName', width: 140 },
  { prop: 'positionName', labelKey: 'hr.employment.positionName', width: 130 },
  { prop: 'newPositionName', labelKey: 'hr.employment.newPositionName', width: 130 },
  { prop: 'effectiveDate', labelKey: 'hr.employment.effectiveDate', width: 110, sortable: 'effective_date' },
  { prop: 'statusText', labelKey: 'hr.employment.status', width: 90, sortable: 'status' },
  { prop: 'reason', labelKey: 'hr.employment.reason', minWidth: 160 },
]

/* ---------------- 行操作 ---------------- */

function rowActions(row: HrEmployment): ActionItem[] {
  const s = String(row.status)
  const acts: ActionItem[] = [{ key: 'detail', tip: 'common.action.detail' }]
  if (s === 'draft' || s === 'rejected') {
    acts.push({ key: 'edit', tip: 'common.action.edit', perm: 'hr:employment:edit' })
    acts.push({ key: 'submit', tip: 'common.action.submitApproval', perm: 'hr:employment:submit' })
  } else if (s === 'approving') {
    acts.push({ key: 'withdraw', tip: 'common.action.withdraw', perm: 'hr:employment:submit' })
  } else if (s === 'approved') {
    acts.push({ key: 'effect', tip: 'hr.employment.effect', icon: 'CircleCheck', perm: 'hr:employment:effect' })
  }
  return acts
}

function onRowAction(key: string, row: HrEmployment) {
  if (key === 'detail') void openDetail(row.id)
  else if (key === 'edit') openEdit(row)
  else if (key === 'submit') void doSubmit(row)
  else if (key === 'withdraw') void doWithdraw(row)
  else if (key === 'effect') void doEffect(row)
}

async function doSubmit(row: HrEmployment) {
  try {
    await ElMessageBox.confirm(t('hr.employment.submitTip'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await submitEmployment(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doWithdraw(row: HrEmployment) {
  try {
    await ElMessageBox.confirm(t('common.action.withdraw'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await withdrawEmployment(row.id)
    ElMessage.success(t('common.message.updateSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doEffect(row: HrEmployment) {
  try {
    await ElMessageBox.confirm(t('hr.employment.effectConfirm'), t('hr.employment.effect'), {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    const res = await effectEmployment(row.id)
    const notes = res?.effect?.notes ?? []
    if (notes.length) {
      await ElMessageBox.alert(notes.join('\n'), t('hr.employment.effectResult'), {
        confirmButtonText: t('common.action.confirm'),
      })
    } else {
      ElMessage.success(t('common.message.updateSuccess'))
    }
    list.refresh()
    if (detailVisible.value && detail.value?.id === row.id) void openDetail(row.id)
  } catch {
    /* http notifies */
  }
}

/* ---------------- 人事事务表单 ---------------- */

const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)

const form = reactive({
  employeeId: null as number | null,
  eventType: 'onboard',
  newDeptId: null as number | null,
  newPositionId: null as number | null,
  effectiveDate: null as string | null,
  reason: '',
  remark: '',
  createAccount: false,
  username: '',
  password: '',
  roleIds: [] as number[],
})

function resetForm() {
  Object.assign(form, {
    employeeId: null,
    eventType: 'onboard',
    newDeptId: null,
    newPositionId: null,
    effectiveDate: null,
    reason: '',
    remark: '',
    createAccount: false,
    username: '',
    password: '',
    roleIds: [],
  })
}

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('hr.employment.create')
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: HrEmployment) {
  editingId.value = row.id
  dialogTitle.value = t('hr.employment.edit')
  Object.assign(form, {
    employeeId: row.employeeId,
    eventType: row.eventType || 'onboard',
    newDeptId: row.newDeptId ?? null,
    newPositionId: row.newPositionId ?? null,
    effectiveDate: row.effectiveDate || null,
    reason: row.reason || '',
    remark: row.remark || '',
    createAccount: row.createAccount === 1,
    username: row.accountUsername || '',
    password: '',
    roleIds: [],
  })
  dialogVisible.value = true
}

async function save(submit = false) {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  if (!form.employeeId) {
    ElMessage.warning(t('hr.employment.employee'))
    return
  }
  if (form.eventType === 'transfer' && !form.newDeptId) {
    ElMessage.warning(t('hr.employment.newDeptRequired'))
    return
  }
  saving.value = true
  try {
    const payload: EmploymentPayload = {
      employeeId: form.employeeId,
      eventType: form.eventType,
      newDeptId: form.eventType === 'transfer' ? form.newDeptId : null,
      newPositionId: form.eventType === 'transfer' ? form.newPositionId : null,
      effectiveDate: form.effectiveDate || null,
      reason: form.reason,
      remark: form.remark,
      createAccount: form.eventType === 'onboard' && form.createAccount,
      username: form.username,
      password: form.password,
      roleIds: form.roleIds,
    }
    let savedId = editingId.value
    if (editingId.value) await updateEmployment(editingId.value, payload)
    else savedId = (await createEmployment(payload))?.id
    ElMessage.success(t('common.message.saveSuccess'))
    if (submit && savedId) {
      await submitEmployment(savedId)
      ElMessage.success(t('common.message.submitSuccess'))
    }
    dialogVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

/* ---------------- 详情抽屉 ---------------- */

const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<HrEmploymentDetail | null>(null)

async function openDetail(id: number) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await getEmployment(id)
  } catch {
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

function eventLabel(e: { eventType: string }) {
  const map: Record<string, string> = {
    create: 'hr.employment.eventLabel.create',
    update: 'hr.employment.eventLabel.update',
    submit: 'hr.employment.eventLabel.submit',
    approve: 'hr.employment.eventLabel.approve',
    reject: 'hr.employment.eventLabel.reject',
    withdraw: 'hr.employment.eventLabel.withdraw',
    effect: 'hr.employment.eventLabel.effect',
  }
  return t(map[e.eventType] ?? 'hr.employment.eventLabel.other')
}

/* ---------------- 代理人（抽屉内维护） ---------------- */

const delegateVisible = ref(false)
const delegateLoading = ref(false)
const delegateItems = ref<HrDelegate[]>([])
const delegateSearch = ref('')
const delegateDialogVisible = ref(false)
const delegateSaving = ref(false)
const delegateEditingId = ref<number | null>(null)

const delegateForm = reactive({
  principalId: null as number | null,
  agentId: null as number | null,
  scope: 'position',
  positionId: null as number | null,
  reason: '',
  effectiveFrom: null as string | null,
  effectiveTo: null as string | null,
  autoTakeover: false,
  remark: '',
})

async function loadDelegates() {
  delegateLoading.value = true
  try {
    const res = await listDelegates({ page: 1, size: 100, q: delegateSearch.value || undefined })
    delegateItems.value = res?.items ?? []
  } catch {
    delegateItems.value = []
  } finally {
    delegateLoading.value = false
  }
}

function openDelegates() {
  delegateVisible.value = true
  void loadDelegates()
}

function openDelegateCreate() {
  delegateEditingId.value = null
  Object.assign(delegateForm, {
    principalId: null,
    agentId: null,
    scope: 'position',
    positionId: null,
    reason: '',
    effectiveFrom: null,
    effectiveTo: null,
    autoTakeover: false,
    remark: '',
  })
  delegateDialogVisible.value = true
}

function openDelegateEdit(row: HrDelegate) {
  delegateEditingId.value = row.id
  Object.assign(delegateForm, {
    principalId: row.principalId,
    agentId: row.agentId,
    scope: row.scope || 'position',
    positionId: row.positionId ?? null,
    reason: row.reason || '',
    effectiveFrom: row.effectiveFrom || null,
    effectiveTo: row.effectiveTo || null,
    autoTakeover: row.autoTakeover === 1,
    remark: row.remark || '',
  })
  delegateDialogVisible.value = true
}

async function saveDelegate() {
  if (!delegateForm.principalId || !delegateForm.agentId) {
    ElMessage.warning(t('hr.delegate.principal'))
    return
  }
  if (delegateForm.principalId === delegateForm.agentId) {
    ElMessage.warning(t('hr.delegate.sameUser'))
    return
  }
  delegateSaving.value = true
  try {
    const payload: DelegatePayload = {
      principalId: delegateForm.principalId,
      agentId: delegateForm.agentId,
      scope: delegateForm.scope,
      positionId: delegateForm.scope === 'position' ? delegateForm.positionId : null,
      reason: delegateForm.reason,
      effectiveFrom: delegateForm.effectiveFrom || null,
      effectiveTo: delegateForm.effectiveTo || null,
      autoTakeover: delegateForm.autoTakeover ? 1 : 0,
      remark: delegateForm.remark,
    }
    if (delegateEditingId.value) await updateDelegate(delegateEditingId.value, payload)
    else await createDelegate(payload)
    ElMessage.success(t('common.message.saveSuccess'))
    delegateDialogVisible.value = false
    void loadDelegates()
  } catch {
    /* http notifies */
  } finally {
    delegateSaving.value = false
  }
}

async function doDeleteDelegate(row: HrDelegate) {
  try {
    await ElMessageBox.confirm(t('hr.delegate.deleteConfirm'), t('common.action.delete'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteDelegate(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    void loadDelegates()
  } catch {
    /* http notifies */
  }
}

const delegateColumns: ListColumn[] = [
  { prop: 'principalName', labelKey: 'hr.delegate.principal', width: 120 },
  { prop: 'agentName', labelKey: 'hr.delegate.agent', width: 120 },
  { prop: 'scopeText', labelKey: 'hr.delegate.scope', width: 100 },
  { prop: 'effectiveFrom', labelKey: 'hr.delegate.effectiveFrom', width: 150 },
  { prop: 'effectiveTo', labelKey: 'hr.delegate.effectiveTo', width: 150 },
  { prop: 'status', labelKey: 'common.form.status', width: 100 },
  { prop: 'reason', labelKey: 'hr.delegate.reason', minWidth: 160 },
]
</script>


<template>
  <ListPage :title="t('hr.employment.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'hr:employment:create'" type="primary" @click="openCreate">
        {{ t('hr.employment.create') }}
      </el-button>
      <el-button v-permission="'hr:delegate:list'" @click="openDelegates">
        {{ t('hr.delegate.title') }}
      </el-button>
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '', eventType: '' }; list.reset()"
      />
    </template>

    <template #statusTabs>
      <StatusTabs
        :tabs="statusTabs"
        :model-value="String(list.query.status)"
        @update:model-value="list.setStatus($event)"
      />
    </template>

    <template #table>
      <ListTable
        :columns="columns"
        :data="list.items.value as unknown as Record<string, unknown>[]"
        :loading="list.loading.value"
        :total="list.total.value"
        :page="Number(list.query.page)"
        :size="Number(list.query.size)"
        row-key="id"
        @update:page="list.setPage"
        @update:size="list.setSize"
        @sort-change="list.onSortChange"
      >
        <template #empNo="{ row }">
          <el-button link type="primary" @click="openDetail(row.id)">{{ row.empNo }}</el-button>
        </template>
        <template #eventTypeText="{ row }">{{ eventTypeLabel(row.eventType) }}</template>
        <template #statusText="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="hr.employment.statusType" />
        </template>
        <template #extraColumns>
          <el-table-column
            :label="t('common.action.operate')"
            width="180"
            fixed="right"
            align="center"
            header-align="center"
          >
            <template #default="{ row }">
              <ActionBar
                :actions="rowActions(row as unknown as HrEmployment)"
                @select="(k) => onRowAction(k, row as unknown as HrEmployment)"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <!-- 新建 / 编辑人事事务 -->
  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="var(--bs-layout-dialog-lg)" append-to-body>
    <el-alert :title="t('hr.employment.submitTip')" type="info" :closable="false" show-icon />
    <el-form ref="formRef" :model="form" label-width="110px" class="pa-form">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('hr.employment.eventType')" prop="eventType">
            <el-select v-model="form.eventType" style="width: 100%">
              <el-option
                v-for="o in eventTypeOptions"
                :key="o.value"
                :label="o.label"
                :value="o.value"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.employment.employee')" prop="employeeId">
            <el-select v-model="form.employeeId" filterable style="width: 100%">
              <el-option
                v-for="o in employeeList"
                :key="o.value"
                :label="o.label"
                :value="o.value"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.employment.newDeptName')">
            <el-select v-model="form.newDeptId" clearable filterable style="width: 100%">
              <el-option v-for="o in deptOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.employment.newPositionName')">
            <el-select v-model="form.newPositionId" clearable filterable style="width: 100%">
              <el-option v-for="o in positionOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.employment.effectiveDate')">
            <el-date-picker
              v-model="form.effectiveDate"
              type="date"
              value-format="YYYY-MM-DD"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="t('hr.employment.reason')">
        <el-input v-model="form.reason" type="textarea" :rows="2" :maxlength="500" />
      </el-form-item>
      <template v-if="form.eventType === 'onboard'">
        <el-form-item>
          <el-checkbox v-model="form.createAccount">{{ t('hr.employment.createAccount') }}</el-checkbox>
        </el-form-item>
        <template v-if="form.createAccount">
          <el-row :gutter="12">
            <el-col :span="12">
              <el-form-item :label="t('hr.employment.accountUsername')">
                <el-input v-model="form.username" :maxlength="64" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('hr.employment.accountPassword')">
                <el-input v-model="form.password" :maxlength="128" show-password />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item v-if="roleOptions.length" :label="t('hr.employment.accountRoles')">
            <el-select v-model="form.roleIds" multiple style="width: 100%">
              <el-option v-for="o in roleOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
          <el-alert :title="t('hr.employment.passwordTip')" type="warning" :closable="false" show-icon />
        </template>
      </template>
      <el-form-item :label="t('common.form.remark')">
        <el-input v-model="form.remark" type="textarea" :rows="2" :maxlength="500" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button :loading="saving" @click="save(false)">{{ t('common.action.saveDraft') }}</el-button>
      <el-button
        v-permission="'hr:employment:submit'"
        type="primary"
        :loading="saving"
        @click="save(true)"
      >
        {{ t('common.action.submitApproval') }}
      </el-button>
    </template>
  </el-dialog>

  <!-- 人事事务详情 -->
  <el-drawer v-model="detailVisible" size="var(--bs-layout-drawer-lg)">
    <template #header>
      <div class="drawer-header">
        <span class="drawer-title">{{ detail?.empNo || t('hr.employment.detail') }}</span>
        <StatusTag v-if="detail" :status="detail.status" i18n-prefix="hr.employment.statusType" />
      </div>
    </template>
    <div v-loading="detailLoading" class="drawer-body">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="t('hr.employment.eventType')">
            {{ eventTypeLabel(detail.eventType) }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.employment.employee')">
            {{ detail.employee?.name || detail.userName || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.employment.deptName')">
            {{ detail.deptName || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.employment.newDeptName')">
            {{ detail.newDeptName || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.employment.positionName')">
            {{ detail.positionName || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.employment.newPositionName')">
            {{ detail.newPositionName || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.employment.effectiveDate')">
            {{ detail.effectiveDate || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.employment.applicantName')">
            {{ detail.applicantName || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.employment.approverName')">
            {{ detail.approverName || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.employment.approvedAt')">
            {{ detail.approvedAt || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.employment.reason')" :span="2">
            {{ detail.reason || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('common.form.remark')" :span="2">
            {{ detail.remark || '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <section v-if="detail.effect?.notes?.length" class="drawer-section">
          <h4 class="section-title">{{ t('hr.employment.effectResult') }}</h4>
          <ul class="effect-notes">
            <li v-for="(n, i) in detail.effect.notes" :key="i">{{ n }}</li>
          </ul>
        </section>

        <section class="drawer-section">
          <h4 class="section-title">{{ t('hr.employment.timeline') }}</h4>
          <el-timeline v-if="detail.timeline?.length" class="pa-timeline">
            <el-timeline-item
              v-for="e in detail.timeline"
              :key="e.id"
              :timestamp="e.effectiveAt"
              :type="e.toStatus === 'effective' ? 'success' : 'info'"
            >
              <div class="timeline-head">
                <el-tag size="small" effect="light" round>{{ eventLabel(e) }}</el-tag>
                <span class="timeline-operator">{{ e.operatorName || '-' }}</span>
              </div>
              <div v-if="e.reason" class="timeline-reason">{{ e.reason }}</div>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else :description="t('hr.employment.timelineEmpty')" :image-size="60" />
        </section>
      </template>
    </div>
  </el-drawer>

  <!-- 代理人 -->
  <el-drawer v-model="delegateVisible" size="var(--bs-layout-drawer-lg)">
    <template #header>
      <div class="drawer-header">
        <span class="drawer-title">{{ t('hr.delegate.title') }}</span>
      </div>
    </template>
    <div class="drawer-body">
      <el-alert :title="t('hr.delegate.tip')" type="info" :closable="false" show-icon />
      <div class="delegate-toolbar">
        <el-input
          v-model="delegateSearch"
          :placeholder="t('common.form.placeholderSearch')"
          clearable
          @keyup.enter="loadDelegates"
          @clear="loadDelegates"
        />
        <el-button @click="loadDelegates">{{ t('common.action.search') }}</el-button>
        <el-button v-permission="'hr:delegate:edit'" type="primary" @click="openDelegateCreate">
          {{ t('hr.delegate.create') }}
        </el-button>
      </div>
      <ListTable
        :columns="delegateColumns"
        :data="delegateItems as unknown as Record<string, unknown>[]"
        :loading="delegateLoading"
        :total="delegateItems.length"
        :page="1"
        :size="delegateItems.length || 1"
        row-key="id"
      >
        <template #scopeText="{ row }">{{ scopeLabel(row.scope) }}</template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="hr.delegate.statusType" />
        </template>
        <template #extraColumns>
          <el-table-column
            :label="t('common.action.operate')"
            width="130"
            align="center"
            header-align="center"
          >
            <template #default="{ row }">
              <ActionBar
                :actions="[
                  { key: 'edit', tip: 'common.action.edit', perm: 'hr:delegate:edit' },
                  { key: 'delete', tip: 'common.action.delete', perm: 'hr:delegate:edit' },
                ]"
                @select="(k) => (k === 'edit' ? openDelegateEdit(row) : doDeleteDelegate(row))"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </div>
  </el-drawer>

  <!-- 代理人表单 -->
  <el-dialog
    v-model="delegateDialogVisible"
    :title="delegateEditingId ? t('hr.delegate.edit') : t('hr.delegate.create')"
    width="var(--bs-layout-dialog-md)"
    append-to-body
  >
    <el-form :model="delegateForm" label-width="110px" class="pa-form">
      <el-form-item :label="t('hr.delegate.principal')">
        <el-select v-model="delegateForm.principalId" filterable style="width: 100%">
          <el-option v-for="o in userOptionsList" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('hr.delegate.agent')">
        <el-select v-model="delegateForm.agentId" filterable style="width: 100%">
          <el-option v-for="o in userOptionsList" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('hr.delegate.scope')">
        <el-select v-model="delegateForm.scope" style="width: 100%">
          <el-option v-for="o in delegateScopeOptions" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="delegateForm.scope === 'position'" :label="t('hr.delegate.position')">
        <el-select v-model="delegateForm.positionId" clearable filterable style="width: 100%">
          <el-option v-for="o in positionOptions" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('hr.delegate.effectiveFrom')">
            <el-date-picker
              v-model="delegateForm.effectiveFrom"
              type="datetime"
              value-format="YYYY-MM-DDTHH:mm:ss"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.delegate.effectiveTo')">
            <el-date-picker
              v-model="delegateForm.effectiveTo"
              type="datetime"
              value-format="YYYY-MM-DDTHH:mm:ss"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item>
        <el-checkbox v-model="delegateForm.autoTakeover">
          {{ t('hr.delegate.autoTakeover') }}
        </el-checkbox>
      </el-form-item>
      <el-form-item :label="t('hr.delegate.reason')">
        <el-input v-model="delegateForm.reason" type="textarea" :rows="2" :maxlength="500" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="delegateDialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="delegateSaving" @click="saveDelegate">
        {{ t('common.action.save') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.pa-form {
  margin-top: var(--bs-space-2);
}

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

.drawer-section {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.section-title {
  margin: 0;
  font-size: var(--bs-typography-font-size-md);
  font-weight: 600;
}

.effect-notes {
  margin: 0;
  padding-left: var(--bs-space-4);
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-sm);
}

.pa-timeline {
  padding-left: var(--bs-space-1);
}

.timeline-head {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.timeline-operator {
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-sm);
}

.timeline-reason {
  margin-top: var(--bs-space-1);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}

.delegate-toolbar {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}
</style>
