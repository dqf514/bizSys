<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
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
  createPrototypeLoan,
  deletePrototypeLoan,
  exportPrototypeLoans,
  getPrototypeLoan,
  listPrototypeLoans,
  prototypeLoanCounts,
  returnPrototypeLoan,
  updatePrototypeLoan,
} from '@/api/asset'
import type { AssetPrototypeLoan } from '@/api/types'
import { useDeptTree, usePrototypeOptions } from '../composables/useAssetOptions'

defineOptions({ name: 'PrototypeLoanList' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const deptTree = useDeptTree()
const prototypeOpts = usePrototypeOptions()

const searchModel = ref<Record<string, any>>({ q: '', prototypeId: '', deptId: '' })
const searchFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'asset.prototypeLoan.loanNo',
    placeholderKey: 'common.form.placeholderSearch',
    width: 240,
  },
  {
    key: 'prototypeId',
    labelKey: 'asset.prototypeLoan.prototype',
    type: 'select',
    width: 200,
    options: prototypeOpts.opts.value,
  },
  {
    key: 'deptId',
    labelKey: 'asset.prototypeLoan.dept',
    type: 'select',
    width: 180,
    options: deptTree.deptTree.value.map((d) => ({ value: d.id, label: d.name })),
  },
])

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'borrowed', labelKey: 'asset.status.borrowed', count: 0 },
  { value: 'returned', labelKey: 'asset.status.returned', count: 0 },
  { value: 'overdue', labelKey: 'asset.status.overdue', count: 0 },
])

/**
 * 借出单状态有「已逾期」这一计算态（借出中 + 应归还日期早于今天），
 * 后端 status 列只存 borrowed/returned，因此页签统一落到 filters[status]，
 * 逾期页签额外用 range[due_date] 的上界表达。
 */
const statusTab = ref('all')

function yesterday(): string {
  const d = new Date()
  d.setDate(d.getDate() - 1)
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

async function loadCounts() {
  try {
    const data = (await prototypeLoanCounts()) ?? {}
    for (const tab of statusTabs.value) {
      if (tab.value === 'all') continue
      tab.count = data[tab.value] ?? 0
    }
    const allTab = statusTabs.value.find((x) => x.value === 'all')
    if (allTab) allTab.count = (data.borrowed ?? 0) + (data.returned ?? 0)
  } catch {
    /* counts optional */
  }
}

onMounted(() => void loadCounts())

function buildFilters(): Record<string, string | number | boolean | undefined> {
  const filters: Record<string, string | number | boolean | undefined> = {
    prototype_id: searchModel.value.prototypeId || undefined,
    dept_id: searchModel.value.deptId || undefined,
  }
  if (statusTab.value === 'borrowed' || statusTab.value === 'overdue') filters.status = 'borrowed'
  else if (statusTab.value === 'returned') filters.status = 'returned'
  return filters
}

function buildRange(): Record<string, string> {
  if (statusTab.value !== 'overdue') return {}
  return { due_date: `|${yesterday()}` }
}

const list = useListPage<AssetPrototypeLoan>({
  fetch: async (params) => {
    const data = await listPrototypeLoans({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(),
      range: buildRange(),
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) =>
    exportPrototypeLoans({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(),
      range: buildRange(),
    }),
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

function onTabChange(value: string) {
  statusTab.value = value
  list.query.status = ''
  list.query.page = 1
  void list.load()
}

function onReset() {
  searchModel.value = { q: '', prototypeId: '', deptId: '' }
  statusTab.value = 'all'
  list.query.status = 'all'
  list.reset()
}

const columns: ListColumn[] = [
  { prop: 'loanNo', labelKey: 'asset.prototypeLoan.loanNo', width: 150, fixed: 'left', sortable: 'loan_no' },
  { prop: 'prototypeCode', labelKey: 'asset.prototype.code', width: 130 },
  { prop: 'prototypeName', labelKey: 'asset.prototype.name', minWidth: 150 },
  { prop: 'borrowerName', labelKey: 'asset.prototypeLoan.borrower', width: 110 },
  { prop: 'deptName', labelKey: 'asset.prototypeLoan.dept', width: 130 },
  { prop: 'loanDate', labelKey: 'asset.prototypeLoan.loanDate', width: 120, sortable: 'loan_date' },
  { prop: 'dueDate', labelKey: 'asset.prototypeLoan.dueDate', width: 120, sortable: 'due_date' },
  { prop: 'returnDate', labelKey: 'asset.prototypeLoan.returnDate', width: 120 },
  { prop: 'purpose', labelKey: 'asset.prototypeLoan.purpose', minWidth: 160 },
  { prop: 'status', labelKey: 'common.form.status', width: 100, sortable: 'status' },
]

function rowActions(row: AssetPrototypeLoan): ActionItem[] {
  const acts: ActionItem[] = [{ key: 'detail', tip: 'common.action.detail' }]
  if (row.status === 'borrowed') {
    acts.push({ key: 'edit', tip: 'common.action.edit', perm: 'asset:prototypeLoan:edit' })
    acts.push({ key: 'return', tip: 'asset.prototypeLoan.return', icon: 'RefreshLeft', perm: 'asset:prototypeLoan:return' })
    acts.push({ key: 'delete', tip: 'common.action.delete', perm: 'asset:prototypeLoan:delete' })
  }
  return acts
}

function onRowAction(key: string, row: AssetPrototypeLoan) {
  if (key === 'detail') void openDetail(row.id)
  else if (key === 'edit') openEdit(row)
  else if (key === 'return') void doReturn(row)
  else if (key === 'delete') void remove(row)
}

/* ---------- form ---------- */
const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)

const form = reactive({
  prototypeId: null as number | null,
  borrowerName: '',
  deptId: null as number | null,
  loanDate: '',
  dueDate: '',
  purpose: '',
  handlerName: '',
  remark: '',
  version: null as number | null,
})

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('asset.prototypeLoan.create')
  Object.assign(form, {
    prototypeId: null,
    borrowerName: '',
    deptId: null,
    loanDate: '',
    dueDate: '',
    purpose: '',
    handlerName: '',
    remark: '',
    version: null,
  })
  dialogVisible.value = true
}

function openEdit(row: AssetPrototypeLoan) {
  editingId.value = row.id
  dialogTitle.value = t('asset.prototypeLoan.edit')
  Object.assign(form, {
    prototypeId: row.prototypeId,
    borrowerName: row.borrowerName,
    deptId: row.deptId ?? null,
    loanDate: row.loanDate ?? '',
    dueDate: row.dueDate ?? '',
    purpose: row.purpose,
    handlerName: row.handlerName,
    remark: row.remark,
    version: row.version,
  })
  dialogVisible.value = true
}

async function save() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  saving.value = true
  try {
    if (editingId.value) await updatePrototypeLoan(editingId.value, { ...form })
    else await createPrototypeLoan({ ...form })
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function doReturn(row: AssetPrototypeLoan) {
  try {
    await ElMessageBox.confirm(t('asset.prototypeLoan.returnTip'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await returnPrototypeLoan(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function remove(row: AssetPrototypeLoan) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deletePrototypeLoan(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------- detail drawer ---------- */
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<AssetPrototypeLoan | null>(null)

async function openDetail(id: number) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await getPrototypeLoan(id)
  } catch {
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

watch(
  () => route.query.detail,
  (v) => {
    const id = Number(v)
    if (!id) return
    void openDetail(id)
    router.replace({ query: { ...route.query, detail: undefined } })
  },
  { immediate: true },
)
</script>

<template>
  <ListPage :title="t('asset.prototypeLoan.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'asset:prototypeLoan:create'" type="primary" @click="openCreate">
        {{ t('asset.prototypeLoan.create') }}
      </el-button>
      <ExportButton v-permission="'asset:prototypeLoan:list:export'" :export-fn="() => list.exportList()" />
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="onReset"
      />
    </template>

    <template #statusTabs>
      <StatusTabs :tabs="statusTabs" :model-value="statusTab" @update:model-value="onTabChange" />
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
        <template #loanNo="{ row }">
          <el-button link type="primary" @click="openDetail(row.id)">{{ row.loanNo }}</el-button>
        </template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="asset.status" />
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="150" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar
                :actions="rowActions(row as unknown as AssetPrototypeLoan)"
                @select="(k) => onRowAction(k, row as unknown as AssetPrototypeLoan)"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="var(--bs-layout-dialog-lg)" append-to-body>
    <el-form ref="formRef" :model="form" label-width="110px">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item
            :label="t('asset.prototypeLoan.prototype')"
            prop="prototypeId"
            :rules="[{ required: true, message: t('common.form.required') }]"
          >
            <el-select v-model="form.prototypeId" filterable style="width: 100%">
              <el-option v-for="o in prototypeOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.prototypeLoan.borrower')">
            <el-input v-model="form.borrowerName" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.prototypeLoan.dept')">
            <el-tree-select
              v-model="form.deptId"
              :data="deptTree.deptTree.value"
              :props="{ label: 'name', value: 'id', children: 'children' }"
              check-strictly
              clearable
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.prototypeLoan.handler')">
            <el-input v-model="form.handlerName" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.prototypeLoan.loanDate')">
            <el-date-picker v-model="form.loanDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.prototypeLoan.dueDate')">
            <el-date-picker v-model="form.dueDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="t('asset.prototypeLoan.purpose')">
        <el-input v-model="form.purpose" type="textarea" :rows="2" :maxlength="500" />
      </el-form-item>
      <el-form-item :label="t('asset.prototypeLoan.remark')">
        <el-input v-model="form.remark" type="textarea" :rows="2" :maxlength="500" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>

  <el-drawer v-model="detailVisible" size="var(--bs-layout-drawer-md)">
    <template #header>
      <div class="drawer-header">
        <span class="drawer-title">{{ detail?.loanNo || t('asset.common.detail') }}</span>
        <StatusTag v-if="detail" :status="detail.status" i18n-prefix="asset.status" />
      </div>
    </template>
    <div v-loading="detailLoading" class="drawer-body">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="t('asset.prototypeLoan.prototype')">
            {{ detail.prototypeCode }} {{ detail.prototypeName }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('asset.prototypeLoan.borrower')">
            {{ detail.borrowerName || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('asset.prototypeLoan.dept')">{{ detail.deptName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.prototypeLoan.handler')">{{ detail.handlerName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.prototypeLoan.loanDate')">{{ detail.loanDate || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.prototypeLoan.dueDate')">{{ detail.dueDate || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.prototypeLoan.returnDate')">{{ detail.returnDate || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.common.remark')">{{ detail.remark || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.prototypeLoan.purpose')" :span="2">
            {{ detail.purpose || '-' }}
          </el-descriptions-item>
        </el-descriptions>
      </template>
    </div>
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
</style>
