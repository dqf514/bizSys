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
import { useDictOptions } from '@/composables/useDict'
import {
  createPrototype,
  deletePrototype,
  exportPrototypes,
  getPrototype,
  listPrototypes,
  prototypeCounts,
  updatePrototype,
} from '@/api/asset'
import type { AssetPrototype, AssetPrototypeLoan } from '@/api/types'
import { useDeptTree, useLocationOptions } from '../composables/useAssetOptions'

defineOptions({ name: 'PrototypeList' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const deptTree = useDeptTree()
const locationOpts = useLocationOptions()
const kindDict = useDictOptions('prototype_kind')

const searchModel = ref<Record<string, any>>({ q: '', kind: '', deptId: '' })
const searchFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'asset.prototype.name',
    placeholderKey: 'common.form.placeholderSearch',
    width: 240,
  },
  {
    key: 'kind',
    labelKey: 'asset.prototype.kind',
    type: 'select',
    width: 160,
    options: kindDict.opts.value,
  },
  {
    key: 'deptId',
    labelKey: 'asset.prototype.dept',
    type: 'select',
    width: 180,
    options: deptTree.deptTree.value.map((d) => ({ value: d.id, label: d.name })),
  },
])

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'in_stock', labelKey: 'asset.status.in_stock', count: 0 },
  { value: 'loaned', labelKey: 'asset.status.loaned', count: 0 },
  { value: 'maintenance', labelKey: 'asset.status.maintenance', count: 0 },
  { value: 'scrapped', labelKey: 'asset.status.scrapped', count: 0 },
])

async function loadCounts() {
  try {
    const data = (await prototypeCounts()) ?? {}
    for (const tab of statusTabs.value) {
      if (tab.value === 'all') continue
      tab.count = data[tab.value] ?? 0
    }
    const allTab = statusTabs.value.find((x) => x.value === 'all')
    if (allTab) allTab.count = data.all ?? 0
  } catch {
    /* counts optional */
  }
}

onMounted(() => void loadCounts())

function buildFilters() {
  return {
    kind: searchModel.value.kind || undefined,
    dept_id: searchModel.value.deptId || undefined,
  }
}

const list = useListPage<AssetPrototype>({
  fetch: async (params) => {
    const data = await listPrototypes({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(),
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) =>
    exportPrototypes({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(),
    }),
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'code', labelKey: 'asset.prototype.code', width: 130, fixed: 'left', sortable: 'code' },
  { prop: 'name', labelKey: 'asset.prototype.name', minWidth: 160, sortable: 'name' },
  { prop: 'kind', labelKey: 'asset.prototype.kind', width: 110 },
  { prop: 'model', labelKey: 'asset.prototype.model', width: 120 },
  { prop: 'vin', labelKey: 'asset.prototype.vin', width: 140 },
  { prop: 'deptName', labelKey: 'asset.prototype.dept', width: 130 },
  { prop: 'locationName', labelKey: 'asset.prototype.location', width: 140 },
  { prop: 'purchaseDate', labelKey: 'asset.prototype.purchaseDate', width: 120, sortable: 'create_time' },
  { prop: 'value', labelKey: 'asset.prototype.value', width: 120, align: 'right', sortable: 'value' },
  { prop: 'status', labelKey: 'common.form.status', width: 100, sortable: 'status' },
]

function kindLabel(value: unknown) {
  const v = String(value ?? '')
  return kindDict.opts.value.find((o) => o.value === v)?.label || v || '-'
}

function rowActions(_row: AssetPrototype): ActionItem[] {
  return [
    { key: 'detail', tip: 'common.action.detail' },
    { key: 'edit', tip: 'common.action.edit', perm: 'asset:prototype:edit' },
    { key: 'delete', tip: 'common.action.delete', perm: 'asset:prototype:delete' },
  ]
}

function onRowAction(key: string, row: AssetPrototype) {
  if (key === 'detail') void openDetail(row.id)
  else if (key === 'edit') openEdit(row)
  else if (key === 'delete') void remove(row)
}

/* ---------- form ---------- */
const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)

const STATUS_OPTIONS = ['in_stock', 'loaned', 'maintenance', 'scrapped'] as const

const form = reactive({
  code: '',
  name: '',
  kind: '',
  model: '',
  vin: '',
  deptId: null as number | null,
  locationId: null as number | null,
  purchaseDate: '',
  value: null as number | null,
  remark: '',
  status: 'in_stock' as string,
  version: null as number | null,
})

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('asset.prototype.create')
  Object.assign(form, {
    code: '',
    name: '',
    kind: '',
    model: '',
    vin: '',
    deptId: null,
    locationId: null,
    purchaseDate: '',
    value: null,
    remark: '',
    status: 'in_stock',
    version: null,
  })
  dialogVisible.value = true
}

function openEdit(row: AssetPrototype) {
  editingId.value = row.id
  dialogTitle.value = t('asset.prototype.edit')
  Object.assign(form, {
    code: row.code,
    name: row.name,
    kind: row.kind,
    model: row.model,
    vin: row.vin,
    deptId: row.deptId ?? null,
    locationId: row.locationId ?? null,
    purchaseDate: row.purchaseDate ?? '',
    value: row.value ?? null,
    remark: row.remark,
    status: row.status,
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
    if (editingId.value) await updatePrototype(editingId.value, { ...form })
    else await createPrototype({ ...form })
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function remove(row: AssetPrototype) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deletePrototype(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------- detail drawer ---------- */
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<(AssetPrototype & { loans?: AssetPrototypeLoan[] }) | null>(null)

async function openDetail(id: number) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await getPrototype(id)
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
  <ListPage :title="t('asset.prototype.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'asset:prototype:create'" type="primary" @click="openCreate">
        {{ t('asset.prototype.create') }}
      </el-button>
      <ExportButton v-permission="'asset:prototype:list:export'" :export-fn="() => list.exportList()" />
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '', kind: '', deptId: '' }; list.reset()"
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
          <el-button link type="primary" @click="openDetail(row.id)">{{ row.code }}</el-button>
        </template>
        <template #kind="{ row }">{{ kindLabel(row.kind) }}</template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="asset.status" />
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="120" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar
                :actions="rowActions(row as unknown as AssetPrototype)"
                @select="(k) => onRowAction(k, row as unknown as AssetPrototype)"
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
        <el-col :span="8">
          <el-form-item
            :label="t('asset.prototype.code')"
            prop="code"
            :rules="[{ required: true, message: t('common.form.required') }]"
          >
            <el-input v-model="form.code" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item
            :label="t('asset.prototype.name')"
            prop="name"
            :rules="[{ required: true, message: t('common.form.required') }]"
          >
            <el-input v-model="form.name" :maxlength="128" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.prototype.kind')">
            <el-select v-model="form.kind" clearable style="width: 100%">
              <el-option v-for="o in kindDict.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.prototype.model')">
            <el-input v-model="form.model" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.prototype.vin')">
            <el-input v-model="form.vin" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.prototype.dept')">
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
        <el-col :span="8">
          <el-form-item :label="t('asset.prototype.location')">
            <el-select v-model="form.locationId" clearable filterable style="width: 100%">
              <el-option v-for="o in locationOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.prototype.purchaseDate')">
            <el-date-picker v-model="form.purchaseDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.prototype.value')">
            <el-input-number v-model="form.value" :min="0" :precision="2" :controls="false" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('common.form.status')">
            <el-select v-model="form.status" style="width: 100%">
              <el-option v-for="s in STATUS_OPTIONS" :key="s" :label="t(`asset.status.${s}`)" :value="s" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="t('asset.prototype.remark')">
        <el-input v-model="form.remark" type="textarea" :rows="2" :maxlength="500" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>

  <el-drawer v-model="detailVisible" size="var(--bs-layout-drawer-lg)">
    <template #header>
      <div class="drawer-header">
        <span class="drawer-title">{{ detail?.code || t('asset.common.detail') }}</span>
        <StatusTag v-if="detail" :status="detail.status" i18n-prefix="asset.status" />
      </div>
    </template>
    <div v-loading="detailLoading" class="drawer-body">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="t('asset.prototype.name')">{{ detail.name }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.prototype.kind')">{{ detail.kindText || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.prototype.model')">{{ detail.model || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.prototype.vin')">{{ detail.vin || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.prototype.dept')">{{ detail.deptName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.prototype.location')">{{ detail.locationName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.prototype.purchaseDate')">{{ detail.purchaseDate || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.prototype.value')">{{ detail.value ?? '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.prototype.remark')" :span="2">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div class="section-title">{{ t('asset.prototype.loanTitle') }}</div>
        <el-table :data="detail.loans ?? []" border stripe size="small">
          <el-table-column :label="t('asset.prototypeLoan.loanNo')" prop="loanNo" width="140" />
          <el-table-column :label="t('asset.prototypeLoan.borrower')" prop="borrowerName" width="110" />
          <el-table-column :label="t('asset.prototypeLoan.loanDate')" prop="loanDate" width="110" />
          <el-table-column :label="t('asset.prototypeLoan.dueDate')" prop="dueDate" width="110" />
          <el-table-column :label="t('asset.prototypeLoan.returnDate')" prop="returnDate" width="110" />
          <el-table-column :label="t('common.form.status')" width="100">
            <template #default="{ row }">
              <StatusTag :status="String(row.status)" i18n-prefix="asset.status" />
            </template>
          </el-table-column>
        </el-table>
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

.section-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}
</style>
