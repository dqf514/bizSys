<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
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
  listStockOrders,
  stockOrderCounts,
  getStockOrder,
  createStockOrder,
  updateStockOrder,
  confirmStockOrder,
  deleteStockOrder,
  exportStockOrders,
  listPurchaseContracts,
} from '@/api/procurement'
import type { PurchaseContract, StockOrder, StockOrderItem } from '@/api/types'

defineOptions({ name: 'StockOrderList' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const warehouseOpts = useDictOptions('warehouse')

const searchModel = ref<Record<string, any>>({ q: '', orderType: '', sourceType: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'procurement.stock.searchNo', placeholderKey: 'procurement.stock.placeholderNo', width: 220 },
  {
    key: 'orderType',
    labelKey: 'procurement.stock.orderType',
    type: 'select',
    width: 120,
    options: [
      { label: t('procurement.stock.typeIn'), value: 'in' },
      { label: t('procurement.stock.typeOut'), value: 'out' },
    ],
  },
  {
    key: 'sourceType',
    labelKey: 'procurement.stock.sourceType',
    type: 'select',
    width: 120,
    options: [
      { label: t('procurement.stock.sourcePurchase'), value: 'purchase' },
      { label: t('procurement.stock.sourceSample'), value: 'sample' },
    ],
  },
]

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'registered', labelKey: 'common.status.registered', count: 0 },
  { value: 'confirmed', labelKey: 'common.status.confirmed', count: 0 },
])

const counts = ref<Record<string, number>>({})

async function loadCounts() {
  try {
    counts.value = (await stockOrderCounts()) ?? {}
    let all = 0
    for (const tab of statusTabs.value) {
      if (tab.value === 'all') continue
      tab.count = counts.value[tab.value] ?? 0
      all += tab.count
    }
    const allTab = statusTabs.value.find((x) => x.value === 'all')
    if (allTab) allTab.count = all
  } catch {
    /* counts optional */
  }
}

onMounted(() => void loadCounts())

const list = useListPage<StockOrder>({
  fetch: async (params) => {
    const data = await listStockOrders({
      ...params,
      q: searchModel.value.q || undefined,
      filters: {
        order_type: searchModel.value.orderType || undefined,
        source_type: searchModel.value.sourceType || undefined,
      },
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) =>
    exportStockOrders({
      ...params,
      q: searchModel.value.q || undefined,
      filters: {
        order_type: searchModel.value.orderType || undefined,
        source_type: searchModel.value.sourceType || undefined,
      },
    }),
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'orderNo', labelKey: 'procurement.stock.orderNo', width: 150, fixed: 'left', sortable: 'order_no' },
  { prop: 'orderType', labelKey: 'procurement.stock.orderType', width: 90, sortable: 'order_type' },
  { prop: 'sourceType', labelKey: 'procurement.stock.sourceType', width: 90 },
  { prop: 'contractNo', labelKey: 'procurement.stock.contract', width: 160 },
  { prop: 'warehouse', labelKey: 'procurement.stock.warehouse', width: 110 },
  { prop: 'orderDate', labelKey: 'procurement.stock.orderDate', width: 120, sortable: 'order_date' },
  { prop: 'handlerName', labelKey: 'procurement.stock.handlerName', width: 100 },
  { prop: 'status', labelKey: 'procurement.stock.status', width: 100, sortable: 'status' },
  { prop: 'createTime', labelKey: 'procurement.stock.createTime', width: 160, sortable: 'create_time' },
]

function rowActions(row: StockOrder): ActionItem[] {
  const s = String(row.status)
  const acts: ActionItem[] = [{ key: 'detail', tip: 'common.action.detail' }]
  if (s === 'registered') {
    acts.push({ key: 'edit', tip: 'common.action.edit', perm: 'procurement:stock:edit' })
    acts.push({ key: 'confirm', tip: 'procurement.stock.confirm', icon: 'CircleCheck', perm: 'procurement:stock:confirm' })
    acts.push({ key: 'delete', tip: 'common.action.delete', perm: 'procurement:stock:delete' })
  }
  return acts
}

function onRowAction(key: string, row: StockOrder) {
  if (key === 'detail') openDetail(row.id)
  else if (key === 'edit') openEdit(row)
  else if (key === 'confirm') void doConfirm(row)
  else if (key === 'delete') void remove(row)
}

/* ---------- form ---------- */
const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  orderType: 'in' as 'in' | 'out',
  contractId: null as number | null,
  warehouse: '',
  orderDate: '',
  remark: '',
  items: [] as StockOrderItem[],
  version: null as number | null,
})

const contractOpts = ref<{ value: number; label: string }[]>([])
const contractLoading = ref(false)

async function searchContracts(q: string) {
  contractLoading.value = true
  try {
    const data = await listPurchaseContracts({ page: 1, size: 20, status: 'approved', q: q || undefined })
    contractOpts.value = (data.items ?? []).map((c: PurchaseContract) => ({
      value: c.id,
      label: `${c.contractNo} ${c.name}`,
    }))
  } catch {
    contractOpts.value = []
  } finally {
    contractLoading.value = false
  }
}

function blankItem(): StockOrderItem {
  return { itemName: '', spec: '', unit: '', quantity: 1, price: null, remark: '' }
}

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('procurement.stock.create')
  Object.assign(form, {
    orderType: 'in',
    contractId: null,
    warehouse: '',
    orderDate: '',
    remark: '',
    items: [blankItem()],
    version: null,
  })
  contractOpts.value = []
  dialogVisible.value = true
}

function openEdit(row: StockOrder) {
  editingId.value = row.id
  dialogTitle.value = t('procurement.stock.edit')
  Object.assign(form, {
    orderType: row.orderType,
    contractId: row.contractId,
    warehouse: row.warehouse ?? '',
    orderDate: row.orderDate ?? '',
    remark: row.remark ?? '',
    items: (row.items ?? []).map((i) => ({ ...i })),
    version: row.version ?? null,
  })
  contractOpts.value = row.contractId ? [{ value: row.contractId, label: `${row.contractNo} ${row.contractName}` }] : []
  dialogVisible.value = true
}

async function save() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  const items = form.items.filter((i) => i.itemName.trim())
  if (!items.length) {
    ElMessage.warning(t('procurement.item.emptyTip'))
    return
  }
  saving.value = true
  try {
    const payload = {
      orderType: form.orderType,
      contractId: form.contractId,
      warehouse: form.warehouse,
      orderDate: form.orderDate,
      remark: form.remark,
      items,
      version: form.version,
    }
    if (editingId.value) await updateStockOrder(editingId.value, payload)
    else await createStockOrder(payload)
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function doConfirm(row: StockOrder) {
  try {
    await ElMessageBox.confirm(t('procurement.stock.confirmTip'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await confirmStockOrder(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function remove(row: StockOrder) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteStockOrder(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------- detail drawer ---------- */
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<StockOrder | null>(null)

async function openDetail(id: number) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await getStockOrder(id)
  } catch {
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

// 深链互跳：/procurement/stock?detail=<id>
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

function openLinkedContract() {
  if (!detail.value?.contractId) return
  router.push({ path: '/procurement/contracts', query: { detail: detail.value.contractId } })
}

function openLinkedTask() {
  if (!detail.value?.taskId) return
  router.push(`/task/tasks/${detail.value.taskId}`)
}

function openLinkedSample() {
  if (!detail.value?.sampleNo) return
  router.push({ path: '/task/samples', query: { q: detail.value.sampleNo } })
}

function sourceTypeLabel(value: unknown) {
  const v = String(value || 'purchase')
  return v === 'sample' ? t('procurement.stock.sourceSample') : t('procurement.stock.sourcePurchase')
}

function warehouseLabel(value: unknown) {
  const v = String(value ?? '')
  return warehouseOpts.opts.value.find((x) => x.value === v)?.label || v || '-'
}

function fmtAmount(v: unknown) {
  const n = Number(v ?? 0)
  return Number.isFinite(n) && v !== null && v !== '' ? n.toLocaleString() : '-'
}
</script>

<template>
  <ListPage :title="t('procurement.stock.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'procurement:stock:create'" type="primary" @click="openCreate">
        {{ t('procurement.stock.create') }}
      </el-button>
      <ExportButton v-permission="'procurement:stock:list:export'" :export-fn="() => list.exportList()" />
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '', orderType: '', sourceType: '' }; list.reset()"
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
        <template #orderNo="{ row }">
          <el-button link type="primary" @click="openDetail(row.id)">{{ row.orderNo }}</el-button>
        </template>
        <template #orderType="{ row }">
          <StatusTag :status="String(row.orderType)" i18n-prefix="procurement.stock.type" />
        </template>
        <template #sourceType="{ row }">
          {{ sourceTypeLabel(row.sourceType) }}
        </template>
        <template #contractNo="{ row }">{{ row.contractNo || '-' }}</template>
        <template #warehouse="{ row }">{{ warehouseLabel(row.warehouse) }}</template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="common.status" />
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="130" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar :actions="rowActions(row as unknown as StockOrder)" @select="(k) => onRowAction(k, row as unknown as StockOrder)" />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="860px" append-to-body>
    <el-form ref="formRef" :model="form" label-width="110px">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('procurement.stock.orderType')" prop="orderType" :rules="[{ required: true, message: t('common.form.required') }]">
            <el-radio-group v-model="form.orderType" :disabled="!!editingId">
              <el-radio value="in">{{ t('procurement.stock.typeIn') }}</el-radio>
              <el-radio value="out">{{ t('procurement.stock.typeOut') }}</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('procurement.stock.contract')">
            <el-select
              v-model="form.contractId"
              clearable
              filterable
              remote
              :remote-method="searchContracts"
              :loading="contractLoading"
              :placeholder="t('procurement.stock.contractPlaceholder')"
              style="width: 100%"
              @focus="!contractOpts.length && searchContracts('')"
            >
              <el-option v-for="o in contractOpts" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('procurement.stock.warehouse')">
            <el-select v-model="form.warehouse" clearable :placeholder="t('common.form.placeholderSelect')" style="width: 100%">
              <el-option v-for="o in warehouseOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('procurement.stock.orderDate')">
            <el-date-picker v-model="form.orderDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item :label="t('procurement.stock.items')">
        <div class="items-editor">
          <el-table :data="form.items" border size="small">
            <el-table-column :label="t('procurement.item.itemName')" min-width="160">
              <template #default="{ row }"><el-input v-model="row.itemName" :maxlength="255" /></template>
            </el-table-column>
            <el-table-column :label="t('procurement.item.spec')" width="130">
              <template #default="{ row }"><el-input v-model="row.spec" :maxlength="255" /></template>
            </el-table-column>
            <el-table-column :label="t('procurement.item.unit')" width="90">
              <template #default="{ row }"><el-input v-model="row.unit" :maxlength="16" /></template>
            </el-table-column>
            <el-table-column :label="t('procurement.item.quantity')" width="110">
              <template #default="{ row }">
                <el-input-number v-model="row.quantity" :min="0.01" :precision="2" :controls="false" style="width: 100%" />
              </template>
            </el-table-column>
            <el-table-column :label="t('procurement.item.price')" width="120">
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
            {{ t('procurement.item.addItem') }}
          </el-button>
        </div>
      </el-form-item>

      <el-form-item :label="t('procurement.stock.remark')">
        <el-input v-model="form.remark" type="textarea" :rows="2" :maxlength="2000" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>

  <el-drawer v-model="detailVisible" size="720px">
    <template #header>
      <div class="drawer-header">
        <span class="drawer-title">{{ detail?.orderNo || t('procurement.stock.detail') }}</span>
        <template v-if="detail">
          <StatusTag :status="detail.orderType" i18n-prefix="procurement.stock.type" />
          <StatusTag :status="detail.status" i18n-prefix="common.status" />
        </template>
      </div>
    </template>
    <div v-loading="detailLoading" class="drawer-body">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="t('procurement.stock.orderNo')">{{ detail.orderNo }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.stock.warehouse')">{{ warehouseLabel(detail.warehouse) }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.stock.orderDate')">{{ detail.orderDate || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.stock.handlerName')">{{ detail.handlerName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.stock.contract')" :span="2">
            <el-button v-if="detail.contractId" link type="primary" @click="openLinkedContract">
              {{ detail.contractNo }} {{ detail.contractName }}
            </el-button>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item :label="t('procurement.stock.sourceType')">
            {{ sourceTypeLabel(detail.sourceType) }}
          </el-descriptions-item>
          <el-descriptions-item v-if="detail.sourceType === 'sample'" :label="t('procurement.stock.linkedSample')">
            <el-button v-if="detail.sampleNo" link type="primary" @click="openLinkedSample">
              {{ detail.sampleNo }} {{ detail.sampleName }}
            </el-button>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="detail.sourceType === 'sample'" :label="t('procurement.stock.linkedTask')" :span="2">
            <el-button v-if="detail.taskId" link type="primary" @click="openLinkedTask">
              {{ detail.taskNo }} {{ detail.taskName }}
            </el-button>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item :label="t('procurement.stock.remark')" :span="2">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div class="section-title">{{ t('procurement.stock.items') }}</div>
        <el-table :data="detail.items" border stripe size="small">
          <el-table-column :label="t('procurement.item.itemName')" prop="itemName" min-width="140" />
          <el-table-column :label="t('procurement.item.spec')" prop="spec" width="120" />
          <el-table-column :label="t('procurement.item.unit')" prop="unit" width="70" />
          <el-table-column :label="t('procurement.item.quantity')" prop="quantity" width="90" align="right" />
          <el-table-column :label="t('procurement.item.price')" width="110" align="right">
            <template #default="{ row }">{{ fmtAmount(row.price) }}</template>
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

.items-editor {
  width: 100%;
}

.add-item {
  margin-top: var(--bs-space-2);
}
</style>
