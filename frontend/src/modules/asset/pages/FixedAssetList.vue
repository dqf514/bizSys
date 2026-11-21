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
  assetCounts,
  createFixedAsset,
  deleteFixedAsset,
  depreciateAsset,
  exportAssets,
  getFixedAsset,
  listAssets,
  updateFixedAsset,
} from '@/api/asset'
import type { AssetDepreciation, AssetDisposal, AssetFixedAsset } from '@/api/types'
import { useDeptTree } from '../composables/useAssetOptions'

defineOptions({ name: 'FixedAssetList' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const deptTree = useDeptTree()
const categoryDict = useDictOptions('asset_category')
const methodDict = useDictOptions('depreciation_method')

const searchModel = ref<Record<string, any>>({ q: '', category: '', deptId: '' })
const searchFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'asset.asset.name',
    placeholderKey: 'common.form.placeholderSearch',
    width: 240,
  },
  {
    key: 'category',
    labelKey: 'asset.asset.category',
    type: 'select',
    width: 160,
    options: categoryDict.opts.value,
  },
  {
    key: 'deptId',
    labelKey: 'asset.asset.dept',
    type: 'select',
    width: 180,
    options: deptTree.deptTree.value.map((d) => ({ value: d.id, label: d.name })),
  },
])

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'in_use', labelKey: 'asset.status.in_use', count: 0 },
  { value: 'idle', labelKey: 'asset.status.idle', count: 0 },
  { value: 'repaired', labelKey: 'asset.status.repaired', count: 0 },
  { value: 'scrapped', labelKey: 'asset.status.scrapped', count: 0 },
])

async function loadCounts() {
  try {
    const data = (await assetCounts()) ?? {}
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
    category: searchModel.value.category || undefined,
    dept_id: searchModel.value.deptId || undefined,
  }
}

const list = useListPage<AssetFixedAsset>({
  fetch: async (params) => {
    const data = await listAssets({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(),
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) =>
    exportAssets({
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
  { prop: 'assetNo', labelKey: 'asset.asset.assetNo', width: 140, fixed: 'left', sortable: 'asset_no' },
  { prop: 'name', labelKey: 'asset.asset.name', minWidth: 160, sortable: 'name' },
  { prop: 'category', labelKey: 'asset.asset.category', width: 110 },
  { prop: 'model', labelKey: 'asset.asset.model', width: 120 },
  { prop: 'deptName', labelKey: 'asset.asset.dept', width: 130 },
  { prop: 'custodianName', labelKey: 'asset.asset.custodian', width: 110 },
  { prop: 'purchaseDate', labelKey: 'asset.asset.purchaseDate', width: 120 },
  { prop: 'originalValue', labelKey: 'asset.asset.originalValue', width: 120, align: 'right', sortable: 'original_value' },
  { prop: 'accumDepreciation', labelKey: 'asset.asset.accumDepreciation', width: 130, align: 'right' },
  { prop: 'netValue', labelKey: 'asset.asset.netValue', width: 120, align: 'right' },
  { prop: 'status', labelKey: 'common.form.status', width: 100, sortable: 'status' },
]

function categoryLabel(value: unknown) {
  const v = String(value ?? '')
  return categoryDict.opts.value.find((o) => o.value === v)?.label || v || '-'
}

function rowActions(row: AssetFixedAsset): ActionItem[] {
  const acts: ActionItem[] = [{ key: 'detail', tip: 'common.action.detail' }]
  acts.push({ key: 'edit', tip: 'common.action.edit', perm: 'asset:asset:edit' })
  if (row.status !== 'scrapped') {
    acts.push({ key: 'depreciate', tip: 'asset.asset.depreciate', icon: 'TrendCharts', perm: 'asset:depreciation:create' })
  }
  acts.push({ key: 'delete', tip: 'common.action.delete', perm: 'asset:asset:delete' })
  return acts
}

function onRowAction(key: string, row: AssetFixedAsset) {
  if (key === 'detail') void openDetail(row.id)
  else if (key === 'edit') openEdit(row)
  else if (key === 'depreciate') openDepreciate(row)
  else if (key === 'delete') void remove(row)
}

/* ---------- form ---------- */
const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)

const STATUS_OPTIONS = ['in_use', 'idle', 'repaired', 'scrapped'] as const

const form = reactive({
  assetNo: '',
  name: '',
  category: '',
  model: '',
  spec: '',
  deptId: null as number | null,
  custodianName: '',
  location: '',
  purchaseDate: '',
  originalValue: null as number | null,
  salvageRate: 0.05,
  usefulLifeMonths: 60,
  remark: '',
  status: 'in_use' as string,
  version: null as number | null,
})

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('asset.asset.create')
  Object.assign(form, {
    assetNo: '',
    name: '',
    category: '',
    model: '',
    spec: '',
    deptId: null,
    custodianName: '',
    location: '',
    purchaseDate: '',
    originalValue: null,
    salvageRate: 0.05,
    usefulLifeMonths: 60,
    remark: '',
    status: 'in_use',
    version: null,
  })
  dialogVisible.value = true
}

function openEdit(row: AssetFixedAsset) {
  editingId.value = row.id
  dialogTitle.value = t('asset.asset.edit')
  Object.assign(form, {
    assetNo: row.assetNo,
    name: row.name,
    category: row.category,
    model: row.model,
    spec: row.spec,
    deptId: row.deptId ?? null,
    custodianName: row.custodianName,
    location: row.location,
    purchaseDate: row.purchaseDate ?? '',
    originalValue: row.originalValue ?? null,
    salvageRate: row.salvageRate,
    usefulLifeMonths: row.usefulLifeMonths,
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
    if (editingId.value) await updateFixedAsset(editingId.value, { ...form })
    else await createFixedAsset({ ...form })
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function remove(row: AssetFixedAsset) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteFixedAsset(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------- depreciate ---------- */
const depVisible = ref(false)
const depSaving = ref(false)
const depRow = ref<AssetFixedAsset | null>(null)
const depForm = reactive({ period: '', method: 'straight_line', remark: '' })

function openDepreciate(row: AssetFixedAsset) {
  depRow.value = row
  Object.assign(depForm, { period: '', method: 'straight_line', remark: '' })
  depVisible.value = true
}

async function submitDepreciate() {
  if (!depRow.value) return
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(depForm.period)) {
    ElMessage.warning(t('common.form.required'))
    return
  }
  depSaving.value = true
  try {
    await depreciateAsset(depRow.value.id, { ...depForm })
    ElMessage.success(t('common.message.submitSuccess'))
    depVisible.value = false
    list.refresh()
    if (detailVisible.value && detail.value?.id === depRow.value.id) void openDetail(depRow.value.id)
  } catch {
    /* http notifies */
  } finally {
    depSaving.value = false
  }
}

/* ---------- detail drawer ---------- */
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<(AssetFixedAsset & { depreciations?: AssetDepreciation[]; disposals?: AssetDisposal[] }) | null>(null)

async function openDetail(id: number) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await getFixedAsset(id)
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
  <ListPage :title="t('asset.asset.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'asset:asset:create'" type="primary" @click="openCreate">
        {{ t('asset.asset.create') }}
      </el-button>
      <ExportButton v-permission="'asset:asset:list:export'" :export-fn="() => list.exportList()" />
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '', category: '', deptId: '' }; list.reset()"
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
        <template #assetNo="{ row }">
          <el-button link type="primary" @click="openDetail(row.id)">{{ row.assetNo }}</el-button>
        </template>
        <template #category="{ row }">{{ categoryLabel(row.category) }}</template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="asset.status" />
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="150" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar
                :actions="rowActions(row as unknown as AssetFixedAsset)"
                @select="(k) => onRowAction(k, row as unknown as AssetFixedAsset)"
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
            :label="t('asset.asset.assetNo')"
            prop="assetNo"
            :rules="[{ required: true, message: t('common.form.required') }]"
          >
            <el-input v-model="form.assetNo" :maxlength="32" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item
            :label="t('asset.asset.name')"
            prop="name"
            :rules="[{ required: true, message: t('common.form.required') }]"
          >
            <el-input v-model="form.name" :maxlength="128" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.asset.category')">
            <el-select v-model="form.category" clearable style="width: 100%">
              <el-option v-for="o in categoryDict.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.asset.model')">
            <el-input v-model="form.model" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.asset.spec')">
            <el-input v-model="form.spec" :maxlength="255" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.asset.dept')">
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
          <el-form-item :label="t('asset.asset.custodian')">
            <el-input v-model="form.custodianName" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.asset.location')">
            <el-input v-model="form.location" :maxlength="255" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.asset.purchaseDate')">
            <el-date-picker v-model="form.purchaseDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.asset.originalValue')">
            <el-input-number v-model="form.originalValue" :min="0" :precision="2" :controls="false" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.asset.salvageRate')">
            <el-input-number
              v-model="form.salvageRate"
              :min="0"
              :max="1"
              :step="0.05"
              :precision="2"
              :controls="false"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.asset.usefulLifeMonths')">
            <el-input-number v-model="form.usefulLifeMonths" :min="1" :max="1200" :controls="false" style="width: 100%" />
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
      <el-form-item :label="t('asset.asset.remark')">
        <el-input v-model="form.remark" type="textarea" :rows="2" :maxlength="500" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="depVisible" :title="t('asset.asset.depreciateTitle')" width="var(--bs-layout-dialog-sm)" append-to-body>
    <el-form :model="depForm" label-width="110px">
      <el-form-item :label="t('asset.asset.name')">{{ depRow?.name }}</el-form-item>
      <el-form-item :label="t('asset.asset.netValue')">{{ depRow?.netValue ?? '-' }}</el-form-item>
      <el-form-item :label="t('asset.asset.period')">
        <el-date-picker v-model="depForm.period" type="month" value-format="YYYY-MM" style="width: 100%" />
      </el-form-item>
      <el-form-item :label="t('asset.asset.method')">
        <el-select v-model="depForm.method" style="width: 100%">
          <el-option v-for="o in methodDict.opts.value" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('common.form.remark')">
        <el-input v-model="depForm.remark" type="textarea" :rows="2" :maxlength="500" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="depVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="depSaving" @click="submitDepreciate">{{ t('common.action.confirm') }}</el-button>
    </template>
  </el-dialog>

  <el-drawer v-model="detailVisible" size="var(--bs-layout-drawer-lg)">
    <template #header>
      <div class="drawer-header">
        <span class="drawer-title">{{ detail?.assetNo || t('asset.common.detail') }}</span>
        <StatusTag v-if="detail" :status="detail.status" i18n-prefix="asset.status" />
      </div>
    </template>
    <div v-loading="detailLoading" class="drawer-body">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="t('asset.asset.name')">{{ detail.name }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.asset.category')">{{ detail.categoryText || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.asset.model')">{{ detail.model || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.asset.spec')">{{ detail.spec || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.asset.dept')">{{ detail.deptName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.asset.custodian')">{{ detail.custodianName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.asset.location')">{{ detail.location || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.asset.purchaseDate')">{{ detail.purchaseDate || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.asset.originalValue')">{{ detail.originalValue ?? '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.asset.salvageRate')">{{ detail.salvageRate }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.asset.usefulLifeMonths')">{{ detail.usefulLifeMonths }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.asset.accumDepreciation')">{{ detail.accumDepreciation }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.asset.netValue')">{{ detail.netValue }}</el-descriptions-item>
          <el-descriptions-item :label="t('common.form.remark')" :span="2">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div class="section-title">{{ t('asset.asset.depreciationTitle') }}</div>
        <el-table :data="detail.depreciations ?? []" border stripe size="small">
          <el-table-column :label="t('asset.asset.depreciationPeriod')" prop="period" width="100" />
          <el-table-column :label="t('asset.asset.depreciationAmount')" prop="amount" width="110" align="right" />
          <el-table-column :label="t('asset.asset.accumAmount')" prop="accumAmount" width="120" align="right" />
          <el-table-column :label="t('asset.asset.netValue')" prop="netValue" width="120" align="right" />
          <el-table-column :label="t('asset.asset.method')" prop="methodText" width="130" />
          <el-table-column :label="t('asset.common.operator')" prop="operatorName" min-width="100" />
        </el-table>

        <div class="section-title">{{ t('asset.disposal.title') }}</div>
        <el-table :data="detail.disposals ?? []" border stripe size="small">
          <el-table-column :label="t('asset.disposal.disposalNo')" prop="disposalNo" min-width="150" />
          <el-table-column :label="t('asset.disposal.disposalType')" prop="disposalTypeText" width="100" />
          <el-table-column :label="t('asset.disposal.disposalAmount')" prop="disposalAmount" width="110" align="right" />
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
