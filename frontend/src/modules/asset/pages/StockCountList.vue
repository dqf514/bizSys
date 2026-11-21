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
  createStockCount,
  deleteStockCount,
  exportStockCounts,
  finishStockCount,
  getStockCount,
  listStockCounts,
  startStockCount,
  stockCountCounts,
  updateStockCount,
} from '@/api/asset'
import type { AssetStockCount, AssetStockCountItem } from '@/api/types'
import { useItemOptions, useLocationOptions, useWarehouseOptions } from '../composables/useAssetOptions'

defineOptions({ name: 'StockCountList' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const itemOpts = useItemOptions()
const locationOpts = useLocationOptions()
const warehouseOpts = useWarehouseOptions()

const searchModel = ref<Record<string, any>>({ q: '', warehouseId: '' })
const searchFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'asset.count.countNo',
    placeholderKey: 'common.form.placeholderSearch',
    width: 240,
  },
  {
    key: 'warehouseId',
    labelKey: 'asset.count.warehouse',
    type: 'select',
    width: 200,
    options: warehouseOpts.opts.value,
  },
])

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'draft', labelKey: 'common.status.draft', count: 0 },
  { value: 'counting', labelKey: 'asset.status.counting', count: 0 },
  { value: 'finished', labelKey: 'common.status.finished', count: 0 },
])

async function loadCounts() {
  try {
    const data = (await stockCountCounts()) ?? {}
    for (const tab of statusTabs.value) {
      if (tab.value === 'all') continue
      tab.count = data[tab.value] ?? 0
    }
    const allTab = statusTabs.value.find((x) => x.value === 'all')
    if (allTab) {
      allTab.count = statusTabs.value.reduce((sum, x) => sum + (x.value === 'all' ? 0 : (x.count ?? 0)), 0)
    }
  } catch {
    /* counts optional */
  }
}

onMounted(() => void loadCounts())

function buildFilters() {
  return { warehouse_id: searchModel.value.warehouseId || undefined }
}

const list = useListPage<AssetStockCount>({
  fetch: async (params) => {
    const data = await listStockCounts({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(),
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) =>
    exportStockCounts({
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
  { prop: 'countNo', labelKey: 'asset.count.countNo', width: 150, fixed: 'left', sortable: 'count_no' },
  { prop: 'warehouseName', labelKey: 'asset.count.warehouse', minWidth: 150 },
  { prop: 'countDate', labelKey: 'asset.count.countDate', width: 120, sortable: 'count_date' },
  { prop: 'totalQty', labelKey: 'asset.count.totalQty', width: 110, align: 'right' },
  { prop: 'diffCount', labelKey: 'asset.count.diffCount', width: 110, align: 'right' },
  { prop: 'operatorName', labelKey: 'asset.count.operator', width: 110 },
  { prop: 'status', labelKey: 'common.form.status', width: 100, sortable: 'status' },
  { prop: 'createTime', labelKey: 'common.form.createTime', width: 160, sortable: 'create_time' },
]

function rowActions(row: AssetStockCount): ActionItem[] {
  const s = String(row.status)
  const acts: ActionItem[] = [{ key: 'detail', tip: 'common.action.detail' }]
  if (s === 'draft') {
    acts.push({ key: 'edit', tip: 'common.action.edit', perm: 'asset:count:edit' })
    acts.push({ key: 'start', tip: 'asset.count.start', icon: 'VideoPlay', perm: 'asset:count:start' })
    acts.push({ key: 'delete', tip: 'common.action.delete', perm: 'asset:count:delete' })
  } else if (s === 'counting') {
    acts.push({ key: 'finish', tip: 'asset.count.finish', icon: 'CircleCheck', perm: 'asset:count:finish' })
  }
  return acts
}

function onRowAction(key: string, row: AssetStockCount) {
  if (key === 'detail') void openDetail(row.id)
  else if (key === 'edit') openEdit(row)
  else if (key === 'start') void doStart(row)
  else if (key === 'finish') void doFinish(row)
  else if (key === 'delete') void remove(row)
}

/* ---------- form ---------- */
const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  warehouseId: null as number | null,
  countDate: '',
  operatorName: '',
  remark: '',
  items: [] as AssetStockCountItem[],
  version: null as number | null,
})

function blankItem(): AssetStockCountItem {
  return {
    itemId: null,
    itemCode: '',
    itemName: '',
    unit: '',
    locationId: null,
    locationCode: '',
    bookQty: 0,
    actualQty: 0,
    diffQty: 0,
    price: null,
    diffAmount: 0,
    reason: '',
  }
}

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('asset.count.create')
  Object.assign(form, {
    warehouseId: null,
    countDate: '',
    operatorName: '',
    remark: '',
    items: [blankItem()],
    version: null,
  })
  dialogVisible.value = true
}

function openEdit(row: AssetStockCount) {
  editingId.value = row.id
  dialogTitle.value = t('asset.count.edit')
  Object.assign(form, {
    warehouseId: row.warehouseId ?? null,
    countDate: row.countDate ?? '',
    operatorName: row.operatorName,
    remark: row.remark,
    items: (row.items ?? []).map((i) => ({ ...i })),
    version: row.version,
  })
  dialogVisible.value = true
}

function onItemPick(row: AssetStockCountItem, itemId: number | null) {
  if (!itemId) return
  const opt = itemOpts.items.value.find((o) => o.id === itemId)
  if (!opt) return
  row.itemId = opt.id
  row.itemCode = opt.code
  row.itemName = opt.name
  row.unit = opt.unit
  row.price = opt.unitPrice
}

async function save() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  const items = form.items.filter((i) => i.itemName.trim())
  if (!items.length) {
    ElMessage.warning(t('asset.common.emptyItems'))
    return
  }
  saving.value = true
  try {
    const payload = { ...form, items }
    if (editingId.value) await updateStockCount(editingId.value, payload)
    else await createStockCount(payload)
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function doStart(row: AssetStockCount) {
  try {
    await ElMessageBox.confirm(t('asset.count.startTip'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await startStockCount(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doFinish(row: AssetStockCount) {
  try {
    await ElMessageBox.confirm(t('asset.count.finishTip'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await finishStockCount(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function remove(row: AssetStockCount) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteStockCount(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------- detail drawer ---------- */
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<AssetStockCount | null>(null)

async function openDetail(id: number) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await getStockCount(id)
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
  <ListPage :title="t('asset.count.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'asset:count:create'" type="primary" @click="openCreate">
        {{ t('asset.count.create') }}
      </el-button>
      <ExportButton v-permission="'asset:count:list:export'" :export-fn="() => list.exportList()" />
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '', warehouseId: '' }; list.reset()"
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
        <template #countNo="{ row }">
          <el-button link type="primary" @click="openDetail(row.id)">{{ row.countNo }}</el-button>
        </template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="asset.status" />
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="130" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar
                :actions="rowActions(row as unknown as AssetStockCount)"
                @select="(k) => onRowAction(k, row as unknown as AssetStockCount)"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="var(--bs-layout-dialog-xl)" append-to-body>
    <el-form ref="formRef" :model="form" label-width="110px">
      <el-row :gutter="12">
        <el-col :span="8">
          <el-form-item :label="t('asset.count.warehouse')">
            <el-select v-model="form.warehouseId" clearable style="width: 100%">
              <el-option v-for="o in warehouseOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.count.countDate')">
            <el-date-picker v-model="form.countDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.count.operator')">
            <el-input v-model="form.operatorName" :maxlength="64" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item :label="t('asset.count.items')">
        <div class="items-editor">
          <el-table :data="form.items" border size="small">
            <el-table-column :label="t('asset.count.itemName')" min-width="190">
              <template #default="{ row }">
                <el-select
                  v-model="row.itemId"
                  filterable
                  clearable
                  :placeholder="t('asset.common.selectItem')"
                  style="width: 100%"
                  @change="(v: number | null) => onItemPick(row, v)"
                >
                  <el-option v-for="o in itemOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column :label="t('asset.common.location')" width="170">
              <template #default="{ row }">
                <el-select v-model="row.locationId" clearable filterable style="width: 100%">
                  <el-option v-for="o in locationOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column :label="t('asset.count.bookQty')" width="110">
              <template #default="{ row }">
                <el-input-number v-model="row.bookQty" :min="0" :precision="2" :controls="false" style="width: 100%" />
              </template>
            </el-table-column>
            <el-table-column :label="t('asset.count.actualQty')" width="110">
              <template #default="{ row }">
                <el-input-number v-model="row.actualQty" :min="0" :precision="2" :controls="false" style="width: 100%" />
              </template>
            </el-table-column>
            <el-table-column :label="t('asset.count.reason')" min-width="140">
              <template #default="{ row }"><el-input v-model="row.reason" :maxlength="255" /></template>
            </el-table-column>
            <el-table-column :label="t('common.action.operate')" width="70" align="center">
              <template #default="{ $index }">
                <el-button link type="danger" @click="form.items.splice($index, 1)">{{ t('common.action.delete') }}</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-button class="add-item" size="small" @click="form.items.push(blankItem())">
            {{ t('asset.common.addItem') }}
          </el-button>
        </div>
      </el-form-item>

      <el-form-item :label="t('asset.count.remark')">
        <el-input v-model="form.remark" type="textarea" :rows="2" :maxlength="2000" />
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
        <span class="drawer-title">{{ detail?.countNo || t('asset.common.detail') }}</span>
        <StatusTag v-if="detail" :status="detail.status" i18n-prefix="asset.status" />
      </div>
    </template>
    <div v-loading="detailLoading" class="drawer-body">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="t('asset.count.warehouse')">{{ detail.warehouseName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.count.countDate')">{{ detail.countDate || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.count.totalQty')">{{ detail.totalQty }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.count.diffCount')">{{ detail.diffCount }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.count.operator')">{{ detail.operatorName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.count.remark')">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div class="section-title">{{ t('asset.count.items') }}</div>
        <el-table :data="detail.items" border stripe size="small">
          <el-table-column :label="t('asset.count.itemName')" prop="itemName" min-width="140" />
          <el-table-column :label="t('asset.common.location')" prop="locationCode" width="120" />
          <el-table-column :label="t('asset.count.bookQty')" prop="bookQty" width="100" align="right" />
          <el-table-column :label="t('asset.count.actualQty')" prop="actualQty" width="100" align="right" />
          <el-table-column :label="t('asset.count.diffQty')" prop="diffQty" width="100" align="right" />
          <el-table-column :label="t('asset.count.reason')" prop="reason" min-width="120" />
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

.items-editor {
  width: 100%;
}

.add-item {
  margin-top: var(--bs-space-2);
}
</style>
