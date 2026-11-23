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
  createPosition,
  deletePosition,
  exportPositions,
  getOrgOptions,
  listPositions,
  positionCounts,
  updatePosition,
  type PositionPayload,
} from '@/api/hr'
import { listDepts, userOptions } from '@/api/admin'
import type { HrPosition } from '@/api/types'

defineOptions({ name: 'PositionList' })

const { t } = useI18n()

/* ---------------- 枚举 ---------------- */

const POSITION_TYPES = ['staff', 'manager', 'key']
const KEY_ROLES = ['tech_leader', 'qa_leader', 'signer', 'supervisor', 'sample_manager', 'device_manager']

const positionTypeOptions = computed(() =>
  POSITION_TYPES.map((v) => ({ label: t(`hr.position.type.${v}`), value: v })),
)
const keyRoleOptions = computed(() =>
  KEY_ROLES.map((v) => ({ label: t(`hr.position.keyRoleType.${v}`), value: v })),
)

function positionTypeLabel(v: unknown) {
  const key = String(v ?? '')
  return POSITION_TYPES.includes(key) ? t(`hr.position.type.${key}`) : key || '-'
}

function keyRoleLabel(v: unknown) {
  const key = String(v ?? '')
  return key && KEY_ROLES.includes(key) ? t(`hr.position.keyRoleType.${key}`) : '-'
}

/* ---------------- 部门 / 人员选项 ---------------- */

const deptOptions = ref<{ value: number; label: string }[]>([])
const userOptionsList = ref<{ value: number; label: string; sub?: string }[]>([])

async function loadOptions() {
  try {
    const depts = (await listDepts()) as unknown as { id: number; name: string }[]
    deptOptions.value = (depts ?? []).map((d) => ({ value: d.id, label: d.name }))
  } catch {
    deptOptions.value = []
  }
  try {
    const users = (await userOptions()) ?? []
    userOptionsList.value = users.map((u) => ({ value: u.id, label: u.label, sub: u.sub }))
  } catch {
    userOptionsList.value = []
  }
}

onMounted(() => {
  void loadOptions()
})

/* ---------------- 检索 ---------------- */

const searchModel = ref<Record<string, any>>({ q: '', positionType: '', keyRole: '', deptId: '' })
const searchFields = computed<SearchField[]>(() => [
  { key: 'q', labelKey: 'hr.position.code', placeholderKey: 'common.form.placeholderSearch', width: 220 },
  { key: 'deptId', labelKey: 'hr.position.deptName', type: 'select', width: 170, options: deptOptions.value },
  { key: 'positionType', labelKey: 'hr.position.positionType', type: 'select', width: 140, options: positionTypeOptions.value },
  { key: 'keyRole', labelKey: 'hr.position.keyRole', type: 'select', width: 160, options: keyRoleOptions.value },
])

function buildFilters() {
  return {
    position_type: searchModel.value.positionType || undefined,
    key_role: searchModel.value.keyRole || undefined,
    dept_id: searchModel.value.deptId || undefined,
  }
}

/* ---------------- 状态页签 ---------------- */

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'enabled', labelKey: 'hr.position.statusType.enabled', count: 0 },
  { value: 'disabled', labelKey: 'hr.position.statusType.disabled', count: 0 },
])

async function loadCounts() {
  try {
    const data = (await positionCounts()) ?? {}
    for (const tab of statusTabs.value) tab.count = data[tab.value] ?? 0
  } catch {
    /* counts optional */
  }
}

onMounted(() => {
  void loadCounts()
})

const list = useListPage<HrPosition>({
  fetch: async (params) => {
    const data = await listPositions({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(),
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) =>
    exportPositions({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(),
    }),
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

/* ---------------- 列 ---------------- */

const columns: ListColumn[] = [
  { prop: 'code', labelKey: 'hr.position.code', width: 140, fixed: 'left', sortable: 'code' },
  { prop: 'name', labelKey: 'hr.position.name', minWidth: 160, sortable: 'name' },
  { prop: 'deptName', labelKey: 'hr.position.deptName', width: 150 },
  { prop: 'siteName', labelKey: 'hr.position.siteName', width: 130 },
  { prop: 'positionTypeText', labelKey: 'hr.position.positionType', width: 110, sortable: 'position_type' },
  { prop: 'keyRoleText', labelKey: 'hr.position.keyRole', width: 130, sortable: 'key_role' },
  { prop: 'reportToName', labelKey: 'hr.position.reportTo', width: 140 },
  { prop: 'primaryUserName', labelKey: 'hr.position.primaryUser', width: 120 },
  { prop: 'backupUserName', labelKey: 'hr.position.backupUser', width: 120 },
  { prop: 'statusText', labelKey: 'hr.position.status', width: 90, sortable: 'status' },
]

/* ---------------- 行操作 ---------------- */

function rowActions(): ActionItem[] {
  return [
    { key: 'edit', tip: 'common.action.edit', perm: 'hr:position:edit' },
    { key: 'delete', tip: 'common.action.delete', perm: 'hr:position:edit' },
  ]
}

function onRowAction(key: string, row: HrPosition) {
  if (key === 'edit') openEdit(row)
  else if (key === 'delete') void doDelete(row)
}

async function doDelete(row: HrPosition) {
  try {
    await ElMessageBox.confirm(t('hr.position.deleteConfirm'), t('common.action.delete'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deletePosition(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
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
  code: '',
  name: '',
  deptId: null as number | null,
  siteId: null as number | null,
  positionType: 'staff',
  duty: '',
  requirement: '',
  reportToId: null as number | null,
  keyRole: '',
  primaryUserId: null as number | null,
  backupUserId: null as number | null,
  status: 'enabled',
  remark: '',
})

const positionOptions = ref<{ value: number; label: string }[]>([])

async function loadPositionOptions() {
  try {
    const opts = await getOrgOptions()
    positionOptions.value = (opts?.positions ?? []).map((p) => ({ value: p.value, label: p.label }))
  } catch {
    positionOptions.value = []
  }
}

function resetForm() {
  Object.assign(form, {
    code: '',
    name: '',
    deptId: null,
    siteId: null,
    positionType: 'staff',
    duty: '',
    requirement: '',
    reportToId: null,
    keyRole: '',
    primaryUserId: null,
    backupUserId: null,
    status: 'enabled',
    remark: '',
  })
}

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('hr.position.create')
  resetForm()
  void loadPositionOptions()
  dialogVisible.value = true
}

function openEdit(row: HrPosition) {
  editingId.value = row.id
  dialogTitle.value = t('hr.position.edit')
  Object.assign(form, {
    code: row.code || '',
    name: row.name || '',
    deptId: row.deptId ?? null,
    siteId: row.siteId ?? null,
    positionType: row.positionType || 'staff',
    duty: row.duty || '',
    requirement: row.requirement || '',
    reportToId: row.reportToId ?? null,
    keyRole: row.keyRole || '',
    primaryUserId: row.primaryUserId ?? null,
    backupUserId: row.backupUserId ?? null,
    status: row.status || 'enabled',
    remark: row.remark || '',
  })
  void loadPositionOptions()
  dialogVisible.value = true
}

async function save() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  if (form.primaryUserId && form.primaryUserId === form.backupUserId) {
    ElMessage.warning(t('hr.position.sameAB'))
    return
  }
  saving.value = true
  try {
    const payload: PositionPayload = {
      code: form.code.trim(),
      name: form.name.trim(),
      deptId: form.deptId,
      siteId: form.siteId,
      positionType: form.positionType,
      duty: form.duty,
      requirement: form.requirement,
      reportToId: form.reportToId,
      keyRole: form.keyRole || '',
      primaryUserId: form.primaryUserId,
      backupUserId: form.backupUserId,
      status: form.status,
      remark: form.remark,
    }
    if (editingId.value) await updatePosition(editingId.value, payload)
    else await createPosition(payload)
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <ListPage :title="t('hr.position.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'hr:position:create'" type="primary" @click="openCreate">
        {{ t('hr.position.create') }}
      </el-button>
      <ExportButton v-permission="'hr:position:list'" :export-fn="() => list.exportList()" />
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '', positionType: '', keyRole: '', deptId: '' }; list.reset()"
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
        <template #code="{ row }">
          <el-button link type="primary" @click="openEdit(row as unknown as HrPosition)">
            {{ row.code }}
          </el-button>
        </template>
        <template #positionTypeText="{ row }">{{ positionTypeLabel(row.positionType) }}</template>
        <template #keyRoleText="{ row }">{{ keyRoleLabel(row.keyRole) }}</template>
        <template #statusText="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="hr.position.statusType" />
        </template>
        <template #extraColumns>
          <el-table-column
            :label="t('common.action.operate')"
            width="140"
            fixed="right"
            align="center"
            header-align="center"
          >
            <template #default="{ row }">
              <ActionBar
                :actions="rowActions()"
                @select="(k) => onRowAction(k, row as unknown as HrPosition)"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <!-- 新建 / 编辑岗位 -->
  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="var(--bs-layout-dialog-lg)" append-to-body>
    <el-form ref="formRef" :model="form" label-width="110px" class="pos-form">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item
            :label="t('hr.position.code')"
            prop="code"
            :rules="[{ required: true, message: t('common.form.required') }]"
          >
            <el-input v-model="form.code" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item
            :label="t('hr.position.name')"
            prop="name"
            :rules="[{ required: true, message: t('common.form.required') }]"
          >
            <el-input v-model="form.name" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.position.deptName')">
            <el-select v-model="form.deptId" clearable filterable style="width: 100%">
              <el-option v-for="o in deptOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.position.positionType')">
            <el-select v-model="form.positionType" style="width: 100%">
              <el-option
                v-for="o in positionTypeOptions"
                :key="o.value"
                :label="o.label"
                :value="o.value"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.position.keyRole')">
            <el-select v-model="form.keyRole" clearable style="width: 100%">
              <el-option v-for="o in keyRoleOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.position.reportTo')">
            <el-select v-model="form.reportToId" clearable filterable style="width: 100%">
              <el-option v-for="o in positionOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.position.primaryUser')">
            <el-select v-model="form.primaryUserId" clearable filterable style="width: 100%">
              <el-option v-for="o in userOptionsList" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.position.backupUser')">
            <el-select v-model="form.backupUserId" clearable filterable style="width: 100%">
              <el-option v-for="o in userOptionsList" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.position.status')">
            <el-select v-model="form.status" style="width: 100%">
              <el-option :label="t('hr.position.statusType.enabled')" value="enabled" />
              <el-option :label="t('hr.position.statusType.disabled')" value="disabled" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="t('hr.position.duty')">
        <el-input v-model="form.duty" type="textarea" :rows="3" :maxlength="1000" />
      </el-form-item>
      <el-form-item :label="t('hr.position.requirement')">
        <el-input v-model="form.requirement" type="textarea" :rows="3" :maxlength="1000" />
      </el-form-item>
      <el-form-item :label="t('common.form.remark')">
        <el-input v-model="form.remark" type="textarea" :rows="2" :maxlength="500" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.pos-form {
  margin-top: var(--bs-space-2);
}
</style>
