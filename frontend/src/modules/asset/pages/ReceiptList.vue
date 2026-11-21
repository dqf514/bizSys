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
  acceptReceipt,
  createReceipt,
  deleteReceipt,
  exportReceipts,
  getReceipt,
  listPurchaseOrders,
  listReceipts,
  receiptCounts,
  updateReceipt,
} from '@/api/asset'
import type { AssetReceipt, AssetReceiptItem } from '@/api/types'
import {
  useItemOptions,
  useLocationOptions,
  useSupplierOptions,
  useWarehouseOptions,
} from '../composables/useAssetOptions'

defineOptions({ name: 'ReceiptList' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const itemOpts = useItemOptions()
const locationOpts = useLocationOptions()
const supplierOpts = useSupplierOptions()
const warehouseOpts = useWarehouseOptions()

const searchModel = ref<Record<string, any>>({ q: '', warehouseId: '' })
const searchFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'asset.receipt.receiptNo',
    placeholderKey: 'common.form.placeholderSearch',
    width: 240,
  },
  {
    key: 'warehouseId',
    labelKey: 'asset.receipt.warehouse',
    type: 'select',
    width: 200,
    options: warehouseOpts.opts.value,
  },
])

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'draft', labelKey: 'common.status.draft', count: 0 },
  { value: 'accepted', labelKey: 'asset.status.accepted', count: 0 },
  { value: 'partial', labelKey: 'asset.status.partial', count: 0 },
  { value: 'rejected', labelKey: 'asset.status.rejected', count: 0 },
])

async function loadCounts() {
  try {
    const data = (await receiptCounts()) ?? {}
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

const list = useListPage<AssetReceipt>({
  fetch: async (params) => {
    const data = await listReceipts({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(),
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) =>
    exportReceipts({
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
  { prop: 'receiptNo', labelKey: 'asset.receipt.receiptNo', width: 150, fixed: 'left', sortable: 'receipt_no' },
  { prop: 'orderNo', labelKey: 'asset.receipt.order', width: 150 },
  { prop: 'supplierName', labelKey: 'asset.receipt.supplier', minWidth: 160 },
  { prop: 'warehouseName', labelKey: 'asset.receipt.warehouse', width: 140 },
  { prop: 'arriveDate', labelKey: 'asset.receipt.arriveDate', width: 120, sortable: 'arrive_date' },
  { prop: 'totalQty', labelKey: 'asset.receipt.totalQty', width: 110, align: 'right' },
  { prop: 'qualifiedQty', labelKey: 'asset.receipt.qualifiedQty', width: 110, align: 'right' },
  { prop: 'inspectorName', labelKey: 'asset.receipt.inspector', width: 110 },
  { prop: 'status', labelKey: 'common.form.status', width: 110, sortable: 'status' },
  { prop: 'createTime', labelKey: 'common.form.createTime', width: 160, sortable: 'create_time' },
]

function rowActions(row: AssetReceipt): ActionItem[] {
  const s = String(row.status)
  const acts: ActionItem[] = [{ key: 'detail', tip: 'common.action.detail' }]
  if (s === 'draft') {
    acts.push({ key: 'edit', tip: 'common.action.edit', perm: 'asset:receipt:edit' })
    acts.push({ key: 'accept', tip: 'asset.receipt.accept', icon: 'CircleCheck', perm: 'asset:receipt:accept' })
    acts.push({ key: 'delete', tip: 'common.action.delete', perm: 'asset:receipt:delete' })
  }
  return acts
}

function onRowAction(key: string, row: AssetReceipt) {
  if (key === 'detail') void openDetail(row.id)
  else if (key === 'edit') openEdit(row)
  else if (key === 'accept') void doAccept(row)
  else if (key === 'delete') void remove(row)
}

/* ---------- form ---------- */
const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  orderId: null as number | null,
  warehouseId: null as number | null,
  supplierId: null as number | null,
  arriveDate: '',
  inspectorName: '',
  remark: '',
  items: [] as AssetReceiptItem[],
  version: null as number | null,
})

const orderOpts = ref<{ value: number; label: string }[]>([])
const orderLoading = ref(false)

async function searchOrders(q: string) {
  orderLoading.value = true
  try {
    const data = await listPurchaseOrders({ page: 1, size: 30, status: 'confirmed', q: q || undefined })
    orderOpts.value = (data.items ?? []).map((o) => ({ value: o.id, label: `${o.orderNo} ${o.title}` }))
  } catch {
    orderOpts.value = []
  } finally {
    orderLoading.value = false
  }
}

function blankItem(): AssetReceiptItem {
  return {
    itemId: null,
    itemCode: '',
    itemName: '',
    spec: '',
    unit: '',
    quantity: 1,
    qualifiedQty: 1,
    locationId: null,
    locationCode: '',
    price: null,
    remark: '',
  }
}

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('asset.receipt.create')
  Object.assign(form, {
    orderId: null,
    warehouseId: null,
    supplierId: null,
    arriveDate: '',
    inspectorName: '',
    remark: '',
    items: [blankItem()],
    version: null,
  })
  void supplierOpts.search('')
  void searchOrders('')
  dialogVisible.value = true
}

function openEdit(row: AssetReceipt) {
  editingId.value = row.id
  dialogTitle.value = t('asset.receipt.edit')
  Object.assign(form, {
    orderId: row.orderId ?? null,
    warehouseId: row.warehouseId ?? null,
    supplierId: row.supplierId ?? null,
    arriveDate: row.arriveDate ?? '',
    inspectorName: row.inspectorName,
    remark: row.remark,
    items: (row.items ?? []).map((i) => ({ ...i })),
    version: row.version,
  })
  orderOpts.value = row.orderId
    ? [{ value: row.orderId, label: `${row.orderNo}` }]
    : []
  dialogVisible.value = true
}

function onItemPick(row: AssetReceiptItem, itemId: number | null) {
  if (!itemId) return
  const opt = itemOpts.items.value.find((o) => o.id === itemId)
  if (!opt) return
  row.itemId = opt.id
  row.itemCode = opt.code
  row.itemName = opt.name
  row.spec = opt.spec
  row.unit = opt.unit
  if (row.price === null || row.price === undefined) row.price = opt.unitPrice
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
    if (editingId.value) await updateReceipt(editingId.value, payload)
    else await createReceipt(payload)
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function doAccept(row: AssetReceipt) {
  try {
    await ElMessageBox.confirm(t('asset.receipt.acceptTip'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await acceptReceipt(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function remove(row: AssetReceipt) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteReceipt(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------- detail drawer ---------- */
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<AssetReceipt | null>(null)

async function openDetail(id: number) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await getReceipt(id)
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
  <ListPage :title="t('asset.receipt.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'asset:receipt:create'" type="primary" @click="openCreate">
        {{ t('asset.receipt.create') }}
      </el-button>
      <ExportButton v-permission="'asset:receipt:list:export'" :export-fn="() => list.exportList()" />
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
        <template #receiptNo="{ row }">
          <el-button link type="primary" @click="openDetail(row.id)">{{ row.receiptNo }}</el-button>
        </template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="asset.status" />
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="130" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar
                :actions="rowActions(row as unknown as AssetReceipt)"
                @select="(k) => onRowAction(k, row as unknown as AssetReceipt)"
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
        <el-col :span="12">
          <el-form-item :label="t('asset.receipt.order')">
            <el-select
              v-model="form.orderId"
              clearable
              filterable
              remote
              :remote-method="(q: string) => searchOrders(q)"
              :loading="orderLoading"
              :placeholder="t('common.form.placeholderSelect')"
              style="width: 100%"
            >
              <el-option v-for="o in orderOpts" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.receipt.warehouse')">
            <el-select v-model="form.warehouseId" clearable style="width: 100%">
              <el-option v-for="o in warehouseOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.receipt.supplier')">
            <el-select
              v-model="form.supplierId"
              clearable
              filterable
              remote
              :remote-method="(q: string) => supplierOpts.search(q)"
              :loading="supplierOpts.loading.value"
              style="width: 100%"
            >
              <el-option v-for="o in supplierOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.receipt.arriveDate')">
            <el-date-picker v-model="form.arriveDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.receipt.inspector')">
            <el-input v-model="form.inspectorName" :maxlength="64" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item :label="t('asset.receipt.items')">
        <div class="items-editor">
          <el-table :data="form.items" border size="small">
            <el-table-column :label="t('asset.receipt.itemName')" min-width="190">
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
            <el-table-column :label="t('asset.receipt.arrivalQty')" width="110">
              <template #default="{ row }">
                <el-input-number v-model="row.quantity" :min="0" :precision="2" :controls="false" style="width: 100%" />
              </template>
            </el-table-column>
            <el-table-column :label="t('asset.receipt.qualified')" width="110">
              <template #default="{ row }">
                <el-input-number v-model="row.qualifiedQty" :min="0" :precision="2" :controls="false" style="width: 100%" />
              </template>
            </el-table-column>
            <el-table-column :label="t('asset.receipt.location')" width="170">
              <template #default="{ row }">
                <el-select v-model="row.locationId" clearable filterable style="width: 100%">
                  <el-option v-for="o in locationOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column :label="t('asset.common.price')" width="110">
              <template #default="{ row }">
                <el-input-number v-model="row.price" :min="0" :precision="2" :controls="false" style="width: 100%" />
              </template>
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

      <el-form-item :label="t('asset.receipt.remark')">
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
        <span class="drawer-title">{{ detail?.receiptNo || t('asset.common.detail') }}</span>
        <StatusTag v-if="detail" :status="detail.status" i18n-prefix="asset.status" />
      </div>
    </template>
    <div v-loading="detailLoading" class="drawer-body">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="t('asset.receipt.order')">{{ detail.orderNo || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.receipt.supplier')">{{ detail.supplierName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.receipt.warehouse')">{{ detail.warehouseName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.receipt.arriveDate')">{{ detail.arriveDate || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.receipt.totalQty')">{{ detail.totalQty }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.receipt.qualifiedQty')">{{ detail.qualifiedQty }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.receipt.inspector')">{{ detail.inspectorName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.receipt.remark')" :span="2">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div class="section-title">{{ t('asset.receipt.items') }}</div>
        <el-table :data="detail.items" border stripe size="small">
          <el-table-column :label="t('asset.receipt.itemName')" prop="itemName" min-width="140" />
          <el-table-column :label="t('asset.receipt.arrivalQty')" prop="quantity" width="100" align="right" />
          <el-table-column :label="t('asset.receipt.qualified')" prop="qualifiedQty" width="100" align="right" />
          <el-table-column :label="t('asset.receipt.location')" prop="locationCode" width="120" />
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
