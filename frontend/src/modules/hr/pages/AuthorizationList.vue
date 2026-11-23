<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { useListPage } from '@/composables/useListPage'
import {
  activateAuthorization,
  authorizationCounts,
  createAuthorization,
  expireAuthorization,
  exportAuthorizations,
  getAuthorization,
  getAuthorizationStateAt,
  listAuthorizations,
  resumeAuthorization,
  revokeAuthorization,
  searchAuthorizationUsers,
  submitAuthorization,
  suspendAuthorization,
  updateAuthorization,
} from '@/api/hr'
import type {
  HrAuthorization,
  HrAuthorizationDetail,
  HrAuthorizationEvent,
  HrAuthorizationStateAt,
} from '@/api/types'

defineOptions({ name: 'AuthorizationList' })

const { t } = useI18n()

/* ---------------- 常量 ---------------- */

const AUTH_TYPES = [
  { value: 'test_item', labelKey: 'hr.authorization.type.test_item' },
  { value: 'device', labelKey: 'hr.authorization.type.device' },
  { value: 'report_role', labelKey: 'hr.authorization.type.report_role' },
  { value: 'signer', labelKey: 'hr.authorization.type.signer' },
]

const AUTH_ROLES = [
  { value: 'preparer', labelKey: 'hr.authorization.role.preparer' },
  { value: 'reviewer', labelKey: 'hr.authorization.role.reviewer' },
  { value: 'approver', labelKey: 'hr.authorization.role.approver' },
  { value: 'signer', labelKey: 'hr.authorization.role.signer' },
]

const STATUS_TABS: { value: string; labelKey: string }[] = [
  { value: 'all', labelKey: 'common.action.all' },
  { value: 'draft', labelKey: 'hr.authorization.status.draft' },
  { value: 'approving', labelKey: 'hr.authorization.status.approving' },
  { value: 'confirmed', labelKey: 'hr.authorization.status.confirmed' },
  { value: 'active', labelKey: 'hr.authorization.status.active' },
  { value: 'suspended', labelKey: 'hr.authorization.status.suspended' },
  { value: 'expired', labelKey: 'hr.authorization.status.expired' },
  { value: 'revoked', labelKey: 'hr.authorization.status.revoked' },
  { value: 'rejected', labelKey: 'hr.authorization.status.rejected' },
]

const typeOptions = computed(() => AUTH_TYPES.map((x) => ({ label: t(x.labelKey), value: x.value })))
const roleOptions = computed(() => AUTH_ROLES.map((x) => ({ label: t(x.labelKey), value: x.value })))

function typeLabel(v: unknown) {
  const key = String(v ?? '')
  return AUTH_TYPES.find((x) => x.value === key) ? t(`hr.authorization.type.${key}`) : key || '-'
}

function roleLabel(v: unknown) {
  const key = String(v ?? '')
  return AUTH_ROLES.find((x) => x.value === key) ? t(`hr.authorization.role.${key}`) : key || '-'
}

/* ---------------- 检索 ---------------- */

const searchModel = ref<Record<string, any>>({ q: '', authType: '', roleCode: '' })
const searchFields = computed<SearchField[]>(() => [
  { key: 'q', labelKey: 'hr.authorization.keyword', placeholderKey: 'common.form.placeholderSearch', width: 220 },
  { key: 'authType', labelKey: 'hr.authorization.authType', type: 'select', width: 150, options: typeOptions.value },
  { key: 'roleCode', labelKey: 'hr.authorization.roleCode', type: 'select', width: 140, options: roleOptions.value },
])

/* ---------------- 状态页签 ---------------- */

const statusTabs = ref<StatusTabItem[]>(
  STATUS_TABS.map((s) => ({ value: s.value, labelKey: s.labelKey, count: 0 })),
)

async function loadCounts() {
  try {
    const data = (await authorizationCounts()) ?? {}
    for (const tab of statusTabs.value) {
      tab.count = data[tab.value] ?? 0
    }
  } catch {
    /* counts optional */
  }
}

onMounted(() => {
  void loadCounts()
})

function buildFilters() {
  return {
    auth_type: searchModel.value.authType || undefined,
    role_code: searchModel.value.roleCode || undefined,
  }
}

const list = useListPage<HrAuthorization>({
  fetch: async (params) => {
    const data = await listAuthorizations({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(),
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) =>
    exportAuthorizations({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(),
    }),
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

/* ---------------- 列表列 ---------------- */

const columns: ListColumn[] = [
  { prop: 'authNo', labelKey: 'hr.authorization.authNo', width: 150, fixed: 'left', sortable: 'auth_no' },
  { prop: 'userName', labelKey: 'hr.authorization.userName', width: 110, sortable: 'user_name' },
  { prop: 'deptName', labelKey: 'hr.authorization.deptName', width: 120 },
  { prop: 'authTypeText', labelKey: 'hr.authorization.authType', width: 110, sortable: 'auth_type' },
  { prop: 'roleCodeText', labelKey: 'hr.authorization.roleCode', width: 90 },
  { prop: 'scopeMethod', labelKey: 'hr.authorization.scopeMethod', width: 130 },
  { prop: 'scopeDeviceName', labelKey: 'hr.authorization.scopeDevice', width: 130 },
  { prop: 'validFrom', labelKey: 'hr.authorization.validFrom', width: 150, sortable: 'valid_from' },
  { prop: 'validTo', labelKey: 'hr.authorization.validTo', width: 150, sortable: 'valid_to' },
  { prop: 'statusText', labelKey: 'hr.authorization.statusLabel', width: 100, sortable: 'status' },
]

/* ---------------- 行操作 ---------------- */

function rowActions(row: HrAuthorization): ActionItem[] {
  const s = String(row.status)
  const acts: ActionItem[] = [{ key: 'detail', tip: 'common.action.detail' }]
  if (s === 'draft' || s === 'rejected') {
    acts.push({ key: 'edit', tip: 'common.action.edit', perm: 'hr:authorization:edit' })
    acts.push({ key: 'submit', tip: 'common.action.submitApproval', perm: 'hr:authorization:submit' })
  } else if (s === 'confirmed') {
    acts.push({ key: 'activate', tip: 'hr.authorization.activate', icon: 'CircleCheck', perm: 'hr:authorization:activate' })
    acts.push({ key: 'revoke', tip: 'hr.authorization.revoke', icon: 'CircleClose', danger: true, perm: 'hr:authorization:revoke' })
  } else if (s === 'active') {
    acts.push({ key: 'suspend', tip: 'hr.authorization.suspend', icon: 'VideoPause', perm: 'hr:authorization:activate' })
    acts.push({ key: 'revoke', tip: 'hr.authorization.revoke', icon: 'CircleClose', danger: true, perm: 'hr:authorization:revoke' })
  } else if (s === 'suspended') {
    acts.push({ key: 'resume', tip: 'hr.authorization.resume', icon: 'VideoPlay', perm: 'hr:authorization:activate' })
    acts.push({ key: 'revoke', tip: 'hr.authorization.revoke', icon: 'CircleClose', danger: true, perm: 'hr:authorization:revoke' })
  }
  return acts
}

function onRowAction(key: string, row: HrAuthorization) {
  if (key === 'detail') void openDetail(row.id)
  else if (key === 'edit') openEdit(row)
  else if (key === 'submit') void doSubmit(row)
  else if (key === 'activate') void doAction('activate', row)
  else if (key === 'suspend') void doAction('suspend', row)
  else if (key === 'resume') void doAction('resume', row)
  else if (key === 'revoke') void doAction('revoke', row)
}

/** 需要填写原因的动作 */
const REASON_ACTIONS = new Set(['suspend', 'revoke', 'expire'])

async function doAction(kind: string, row: HrAuthorization) {
  let reason = ''
  if (REASON_ACTIONS.has(kind)) {
    try {
      const res = await ElMessageBox.prompt(
        t(`hr.authorization.reasonTip.${kind}`),
        t(`hr.authorization.${kind}`),
        {
          type: 'warning',
          confirmButtonText: t('common.action.confirm'),
          cancelButtonText: t('common.action.cancel'),
          inputPlaceholder: t('hr.authorization.reasonPlaceholder'),
          inputValidator: (v: string) => (v && v.trim() ? true : t('hr.authorization.reasonRequired')),
        },
      )
      reason = res.value
    } catch {
      return
    }
  } else {
    try {
      await ElMessageBox.confirm(t(`hr.authorization.confirmTip.${kind}`), t('common.action.confirm'), {
        type: 'warning',
      })
    } catch {
      return
    }
  }
  try {
    if (kind === 'activate') await activateAuthorization(row.id, reason)
    else if (kind === 'suspend') await suspendAuthorization(row.id, reason)
    else if (kind === 'resume') await resumeAuthorization(row.id, reason)
    else if (kind === 'revoke') await revokeAuthorization(row.id, reason)
    else if (kind === 'expire') await expireAuthorization(row.id, reason)
    ElMessage.success(t('common.message.updateSuccess'))
    list.refresh()
    if (detailVisible.value && detail.value?.id === row.id) void openDetail(row.id)
  } catch {
    /* http notifies */
  }
}

async function doSubmit(row: HrAuthorization) {
  try {
    await ElMessageBox.confirm(t('hr.authorization.submitTip'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await submitAuthorization(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------------- 表单 ---------------- */

const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)

const form = reactive({
  userId: null as number | null,
  authType: 'test_item',
  roleCode: '',
  scopeMethod: '',
  scopeParams: '',
  scopeDeviceId: null as number | null,
  scopeDeviceName: '',
  scopeDomain: '',
  validFrom: null as string | null,
  validTo: null as string | null,
  remark: '',
})

const userOptions = ref<{ value: number; label: string; sub?: string; deptName?: string }[]>([])
const userLoading = ref(false)

async function searchUsers(q = '') {
  userLoading.value = true
  try {
    userOptions.value = (await searchAuthorizationUsers(q)) ?? []
  } catch {
    userOptions.value = []
  } finally {
    userLoading.value = false
  }
}

function resetForm() {
  Object.assign(form, {
    userId: null,
    authType: 'test_item',
    roleCode: '',
    scopeMethod: '',
    scopeParams: '',
    scopeDeviceId: null,
    scopeDeviceName: '',
    scopeDomain: '',
    validFrom: null,
    validTo: null,
    remark: '',
  })
}

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('hr.authorization.create')
  resetForm()
  void searchUsers('')
  dialogVisible.value = true
}

function openEdit(row: HrAuthorization) {
  editingId.value = row.id
  dialogTitle.value = t('hr.authorization.edit')
  Object.assign(form, {
    userId: row.userId,
    authType: row.authType || 'test_item',
    roleCode: row.roleCode || '',
    scopeMethod: row.scopeMethod || '',
    scopeParams: row.scopeParams || '',
    scopeDeviceId: row.scopeDeviceId,
    scopeDeviceName: row.scopeDeviceName || '',
    scopeDomain: row.scopeDomain || '',
    validFrom: row.validFrom || null,
    validTo: row.validTo || null,
    remark: row.remark || '',
  })
  userOptions.value = [{ value: row.userId, label: row.userName, sub: '', deptName: row.deptName || '' }]
  void searchUsers(row.userName || '')
  dialogVisible.value = true
}

/** 保存：submit=false 只存草稿；submit=true 保存后立即提交授权审批 */
async function save(submit = false) {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  saving.value = true
  try {
    const payload = { ...form, userId: form.userId as number }
    let savedId = editingId.value
    if (editingId.value) await updateAuthorization(editingId.value, payload)
    else savedId = (await createAuthorization(payload))?.id
    ElMessage.success(t('common.message.saveSuccess'))
    if (submit && savedId) {
      await submitAuthorization(savedId)
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
const detail = ref<HrAuthorizationDetail | null>(null)
const replayAt = ref<string>('')
const replayResult = ref<HrAuthorizationStateAt | null>(null)
const replayLoading = ref(false)

async function openDetail(id: number) {
  detailVisible.value = true
  detailLoading.value = true
  replayResult.value = null
  replayAt.value = ''
  try {
    detail.value = await getAuthorization(id)
  } catch {
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

async function runReplay() {
  if (!detail.value || !replayAt.value) return
  replayLoading.value = true
  try {
    replayResult.value = await getAuthorizationStateAt(detail.value.id, replayAt.value)
  } catch {
    replayResult.value = null
  } finally {
    replayLoading.value = false
  }
}

function eventLabel(e: HrAuthorizationEvent) {
  const map: Record<string, string> = {
    create: 'hr.authorization.event.create',
    submit: 'hr.authorization.event.submit',
    approve: 'hr.authorization.event.approve',
    activate: 'hr.authorization.event.activate',
    suspend: 'hr.authorization.event.suspend',
    resume: 'hr.authorization.event.resume',
    revoke: 'hr.authorization.event.revoke',
    expire: 'hr.authorization.event.expire',
  }
  const key = map[e.eventType] ?? 'hr.authorization.event.other'
  return t(key)
}

function eventTagType(e: HrAuthorizationEvent): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  switch (e.toStatus) {
    case 'active':
    case 'confirmed':
      return 'success'
    case 'suspended':
    case 'approving':
      return 'warning'
    case 'revoked':
    case 'rejected':
      return 'danger'
    case 'expired':
      return 'info'
    default:
      return 'info'
  }
}
</script>

<template>
  <ListPage :title="t('hr.authorization.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'hr:authorization:create'" type="primary" @click="openCreate">
        {{ t('hr.authorization.create') }}
      </el-button>
      <ExportButton v-permission="'hr:authorization:export'" :export-fn="() => list.exportList()" />
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '', authType: '', roleCode: '' }; list.reset()"
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
        <template #authNo="{ row }">
          <el-button link type="primary" @click="openDetail(row.id)">{{ row.authNo }}</el-button>
        </template>
        <template #authTypeText="{ row }">{{ typeLabel(row.authType) }}</template>
        <template #roleCodeText="{ row }">{{ roleLabel(row.roleCode) }}</template>
        <template #statusText="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="hr.authorization.status" />
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="150" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar
                :actions="rowActions(row as unknown as HrAuthorization)"
                @select="(k) => onRowAction(k, row as unknown as HrAuthorization)"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <!-- 新建 / 编辑 -->
  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="var(--bs-layout-dialog-md)" append-to-body>
    <el-alert :title="t('hr.authorization.submitTip')" type="info" :closable="false" show-icon />
    <el-form ref="formRef" :model="form" label-width="110px" class="auth-form">
      <el-form-item
        :label="t('hr.authorization.userName')"
        prop="userId"
        :rules="[{ required: true, message: t('common.form.required') }]"
      >
        <el-select
          v-model="form.userId"
          filterable
          remote
          reserve-keyword
          :remote-method="searchUsers"
          :loading="userLoading"
          :placeholder="t('hr.authorization.userPlaceholder')"
          style="width: 100%"
        >
          <el-option v-for="o in userOptions" :key="o.value" :label="o.label" :value="o.value">
            <span>{{ o.label }}</span>
            <span v-if="o.deptName" class="opt-sub">{{ o.deptName }}</span>
            <span v-else-if="o.sub" class="opt-sub">{{ o.sub }}</span>
          </el-option>
        </el-select>
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item
            :label="t('hr.authorization.authType')"
            prop="authType"
            :rules="[{ required: true, message: t('common.form.required') }]"
          >
            <el-select v-model="form.authType" style="width: 100%">
              <el-option v-for="o in typeOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.authorization.roleCode')">
            <el-select v-model="form.roleCode" clearable style="width: 100%">
              <el-option v-for="o in roleOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.authorization.scopeMethod')">
            <el-input v-model="form.scopeMethod" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.authorization.scopeDomain')">
            <el-input v-model="form.scopeDomain" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.authorization.scopeDevice')">
            <el-input v-model="form.scopeDeviceName" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.authorization.scopeDeviceId')">
            <el-input-number v-model="form.scopeDeviceId" :min="1" :controls="false" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.authorization.validFrom')">
            <el-date-picker
              v-model="form.validFrom"
              type="datetime"
              value-format="YYYY-MM-DDTHH:mm:ss"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.authorization.validTo')">
            <el-date-picker
              v-model="form.validTo"
              type="datetime"
              value-format="YYYY-MM-DDTHH:mm:ss"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="t('hr.authorization.scopeParams')">
        <el-input v-model="form.scopeParams" :maxlength="255" />
      </el-form-item>
      <el-form-item :label="t('common.form.remark')">
        <el-input v-model="form.remark" type="textarea" :rows="2" :maxlength="500" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button :loading="saving" @click="save(false)">{{ t('common.action.saveDraft') }}</el-button>
      <el-button
        v-permission="'hr:authorization:submit'"
        type="primary"
        :loading="saving"
        @click="save(true)"
      >
        {{ t('common.action.submitApproval') }}
      </el-button>
    </template>
  </el-dialog>

  <!-- 详情 -->
  <el-drawer v-model="detailVisible" size="var(--bs-layout-drawer-md)">
    <template #header>
      <div class="drawer-header">
        <span class="drawer-title">{{ detail?.authNo || t('hr.authorization.detail') }}</span>
        <StatusTag v-if="detail" :status="detail.status" i18n-prefix="hr.authorization.status" />
      </div>
    </template>
    <div v-loading="detailLoading" class="drawer-body">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="t('hr.authorization.userName')">
            {{ detail.userName || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.authorization.deptName')">
            {{ detail.deptName || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.authorization.authType')">
            {{ typeLabel(detail.authType) }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.authorization.roleCode')">
            {{ roleLabel(detail.roleCode) }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.authorization.scopeMethod')">
            {{ detail.scopeMethod || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.authorization.scopeDomain')">
            {{ detail.scopeDomain || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.authorization.scopeDevice')">
            {{ detail.scopeDeviceName || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.authorization.scopeParams')">
            {{ detail.scopeParams || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.authorization.validFrom')">
            {{ detail.validFrom || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.authorization.validTo')">
            {{ detail.validTo || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.authorization.applicantName')">
            {{ detail.applicantName || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.authorization.approverName')">
            {{ detail.approverName || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.authorization.approvedAt')">
            {{ detail.approvedAt || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.authorization.activatedAt')">
            {{ detail.activatedAt || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.authorization.lastReason')" :span="2">
            {{ detail.lastReason || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('common.form.remark')" :span="2">
            {{ detail.remark || '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <!-- 时点回放 -->
        <section class="drawer-section">
          <h4 class="section-title">{{ t('hr.authorization.stateAt') }}</h4>
          <p class="section-hint">{{ t('hr.authorization.stateAtTip') }}</p>
          <div class="replay-row">
            <el-date-picker
              v-model="replayAt"
              type="datetime"
              value-format="YYYY-MM-DDTHH:mm:ss"
              :placeholder="t('hr.authorization.stateAtPlaceholder')"
              style="flex: 1"
            />
            <el-button :loading="replayLoading" @click="runReplay">
              {{ t('hr.authorization.stateAtRun') }}
            </el-button>
          </div>
          <el-descriptions v-if="replayResult" :column="1" border size="small" class="replay-result">
            <el-descriptions-item :label="t('hr.authorization.statusLabel')">
              <StatusTag
                v-if="replayResult.status"
                :status="replayResult.status"
                i18n-prefix="hr.authorization.status"
              />
              <span v-else>{{ t('hr.authorization.stateAtNotFound') }}</span>
            </el-descriptions-item>
            <el-descriptions-item :label="t('hr.authorization.effectiveAt')">
              {{ replayResult.effectiveAt || '-' }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('hr.authorization.effective')">
              {{ replayResult.effective ? t('common.action.yes') : t('common.action.no') }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('hr.authorization.lastReason')">
              {{ replayResult.reason || '-' }}
            </el-descriptions-item>
          </el-descriptions>
        </section>

        <!-- 变更轨迹 -->
        <section class="drawer-section">
          <h4 class="section-title">{{ t('hr.authorization.timeline') }}</h4>
          <el-timeline v-if="detail.timeline?.length" class="auth-timeline">
            <el-timeline-item
              v-for="e in detail.timeline"
              :key="e.id"
              :timestamp="e.effectiveAt || e.createTime"
              :type="eventTagType(e)"
            >
              <div class="timeline-head">
                <el-tag :type="eventTagType(e)" size="small" effect="light" round>
                  {{ eventLabel(e) }}
                </el-tag>
                <span class="timeline-operator">{{ e.operatorName || '-' }}</span>
              </div>
              <div v-if="e.fromStatus || e.toStatus" class="timeline-status">
                <span>{{ e.fromStatus || '-' }}</span>
                <span class="timeline-arrow">→</span>
                <span>{{ e.toStatus || '-' }}</span>
              </div>
              <div v-if="e.reason" class="timeline-reason">{{ e.reason }}</div>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else :description="t('hr.authorization.timelineEmpty')" :image-size="60" />
        </section>
      </template>
    </div>
  </el-drawer>
</template>

<style scoped>
.auth-form {
  margin-top: var(--bs-space-3);
}

.opt-sub {
  margin-left: var(--bs-space-2);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
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

.section-hint {
  margin: 0;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}

.replay-row {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.replay-result {
  margin-top: var(--bs-space-2);
}

.auth-timeline {
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

.timeline-status {
  margin-top: var(--bs-space-1);
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-sm);
}

.timeline-arrow {
  margin: 0 var(--bs-space-1);
}

.timeline-reason {
  margin-top: var(--bs-space-1);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}
</style>
