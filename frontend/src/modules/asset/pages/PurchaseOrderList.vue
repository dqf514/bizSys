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
  closePurchaseOrder,
  confirmPurchaseOrder,
  createPurchaseOrder,
  deletePurchaseOrder,
  exportPurchaseOrders,
  getPurchaseOrder,
  listPurchaseOrders,
  purchaseOrderCounts,
  updatePurchaseOrder,
} from '@/api/asset'
import type { AssetPurchaseOrder, AssetPurchaseOrderItem } from '@/api/types'
import { useDeptTree, useItemOptions, useSupplierOptions } from '../composables/useAssetOptions'

defineOptions({ name: 'PurchaseOrderList' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const deptTree = useDeptTree()
const itemOpts = useItemOptions()
const supplierOpts = useSupplierOptions()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'asset.po.orderNo',
    placeholderKey: 'common.form.placeholderSearch',
    width: 240,
  },
])

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'draft', labelKey: 'common.status.draft', count: 0 },
  { value: 'confirmed', labelKey: 'common.status.confirmed', count: 0 },
  { value: 'closed', labelKey: 'asset.status.closed', count: 0 },
])

async function loadCounts() {
  try {
    const data = (await purchaseOrderCounts()) ?? {}
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

const list = useListPage<AssetPurchaseOrder>({
  fetch: async (params) => {
    const data = await listPurchaseOrders({ ...params, q: searchModel.value.q || undefined })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) => exportPurchaseOrders({ ...params, q: searchModel.value.q || undefined }),
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'orderNo', labelKey: 'asset.po.orderNo', width: 150, fixed: 'left', sortable: 'order_no' },
  { prop: 'title', labelKey: 'asset.po.title', minWidth: 180 },
  { prop: 'supplierName', labelKey: 'asset.po.supplier', minWidth: 160 },
  { prop: 'deptName', labelKey: 'asset.po.dept', width: 130 },
  { prop: 'orderDate', labelKey: 'asset.po.orderDate', width: 120, sortable: 'order_date' },
  { prop: 'arriveDate', labelKey: 'asset.po.arriveDate', width: 130 },
  { prop: 'totalAmount', labelKey: 'asset.po.totalAmount', width: 130, align: 'right' },
  { prop: 'handlerName', labelKey: 'asset.po.handler', width: 110 },
  { prop: 'status', labelKey: 'common.form.status', width: 100, sortable: 'status' },
  { prop: 'createTime', labelKey: 'common.form.createTime', width: 160, sortable: 'create_time' },
]

function fmtNumber(v: unknown) {
  const n = Number(v ?? 0)
  return Number.isFinite(n) ? n.toLocaleString() : '-'
}

function rowActions(row: AssetPurchaseOrder): ActionItem[] {
  const s = String(row.status)
  const acts: ActionItem[] = [{ key: 'detail', tip: 'common.action.detail' }]
  if (s === 'draft') {
    acts.push({ key: 'edit', tip: 'common.action.edit', perm: 'asset:purchaseOrder:edit' })
    acts.push({ key: 'confirm', tip: 'asset.po.confirm', icon: 'CircleCheck', perm: 'asset:purchaseOrder:confirm' })
    acts.push({ key: 'delete', tip: 'common.action.delete', perm: 'asset:purchaseOrder:delete' })
  } else if (s === 'confirmed') {
    acts.push({ key: 'close', tip: 'asset.po.close', icon: 'CircleClose', perm: 'asset:purchaseOrder:close' })
  }
  return acts
}

function onRowAction(key: string, row: AssetPurchaseOrder) {
  if (key === 'detail') void openDetail(row.id)
  else if (key === 'edit') openEdit(row)
  else if (key === 'confirm') void doConfirm(row)
  else if (key === 'close') void doClose(row)
  else if (key === 'delete') void remove(row)
}

/* ---------- form ---------- */
const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  title: '',
  supplierId: null as number | null,
  deptId: null as number | null,
  orderDate: '',
  arriveDate: '',
  totalAmount: null as number | null,
  handlerName: '',
  remark: '',
  items: [] as AssetPurchaseOrderItem[],
  version: null as number | null,
})

function blankItem(): AssetPurchaseOrderItem {
  return { itemId: null, itemCode: '', itemName: '', spec: '', unit: '', quantity: 1, price: null, remark: '' }
}

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('asset.po.create')
  Object.assign(form, {
    title: '',
    supplierId: null,
    deptId: null,
    orderDate: '',
    arriveDate: '',
    totalAmount: null,
    handlerName: '',
    remark: '',
    items: [blankItem()],
    version: null,
  })
  void supplierOpts.search('')
  dialogVisible.value = true
}

function openEdit(row: AssetPurchaseOrder) {
  editingId.value = row.id
  dialogTitle.value = t('asset.po.edit')
  Object.assign(form, {
    title: row.title,
    supplierId: row.supplierId ?? null,
    deptId: row.deptId ?? null,
    orderDate: row.orderDate ?? '',
    arriveDate: row.arriveDate ?? '',
    totalAmount: row.totalAmount,
    handlerName: row.handlerName,
    remark: row.remark,
    items: (row.items ?? []).map((i) => ({ ...i })),
    version: row.version,
  })
  dialogVisible.value = true
}

/** 选择存货后自动带出名称/规格/单位/单价 */
function onItemPick(row: AssetPurchaseOrderItem, itemId: number | null) {
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
    if (editingId.value) await updatePurchaseOrder(editingId.value, payload)
    else await createPurchaseOrder(payload)
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function doConfirm(row: AssetPurchaseOrder) {
  try {
    await ElMessageBox.confirm(t('asset.po.confirmTip'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await confirmPurchaseOrder(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doClose(row: AssetPurchaseOrder) {
  try {
    await ElMessageBox.confirm(t('asset.po.closeTip'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await closePurchaseOrder(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function remove(row: AssetPurchaseOrder) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deletePurchaseOrder(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------- detail drawer ---------- */
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<(AssetPurchaseOrder & { receipts?: { id: number; receiptNo: string; status: string }[] }) | null>(
  null,
)

async function openDetail(id: number) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await getPurchaseOrder(id)
  } catch {
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

// 深链互跳：/asset/purchase-orders?detail=<id>
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
  <ListPage :title="t('asset.po.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'asset:purchaseOrder:create'" type="primary" @click="openCreate">
        {{ t('asset.po.create') }}
      </el-button>
      <ExportButton v-permission="'asset:purchaseOrder:list:export'" :export-fn="() => list.exportList()" />
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '' }; list.reset()"
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
        <template #totalAmount="{ row }">{{ fmtNumber(row.totalAmount) }}</template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="asset.status" />
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="130" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar
                :actions="rowActions(row as unknown as AssetPurchaseOrder)"
                @select="(k) => onRowAction(k, row as unknown as AssetPurchaseOrder)"
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
          <el-form-item :label="t('asset.po.title')" prop="title" :rules="[{ required: true, message: t('common.form.required') }]">
            <el-input v-model="form.title" :maxlength="255" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.po.supplier')" prop="supplierId" :rules="[{ required: true, message: t('common.form.required') }]">
            <el-select
              v-model="form.supplierId"
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
          <el-form-item :label="t('asset.po.dept')">
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
          <el-form-item :label="t('asset.po.handler')">
            <el-input v-model="form.handlerName" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.po.orderDate')">
            <el-date-picker v-model="form.orderDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.po.arriveDate')">
            <el-date-picker v-model="form.arriveDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.po.totalAmount')">
            <el-input-number v-model="form.totalAmount" :min="0" :precision="2" :controls="false" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item :label="t('asset.po.items')">
        <div class="items-editor">
          <el-table :data="form.items" border size="small">
            <el-table-column :label="t('asset.po.itemName')" min-width="200">
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
            <el-table-column :label="t('asset.common.spec')" width="140">
              <template #default="{ row }"><el-input v-model="row.spec" :maxlength="255" /></template>
            </el-table-column>
            <el-table-column :label="t('asset.common.unit')" width="90">
              <template #default="{ row }"><el-input v-model="row.unit" :maxlength="16" /></template>
            </el-table-column>
            <el-table-column :label="t('asset.po.itemQty')" width="120">
              <template #default="{ row }">
                <el-input-number v-model="row.quantity" :min="0.01" :precision="2" :controls="false" style="width: 100%" />
              </template>
            </el-table-column>
            <el-table-column :label="t('asset.common.price')" width="120">
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

      <el-form-item :label="t('asset.po.remark')">
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
        <span class="drawer-title">{{ detail?.orderNo || t('asset.common.detail') }}</span>
        <StatusTag v-if="detail" :status="detail.status" i18n-prefix="asset.status" />
      </div>
    </template>
    <div v-loading="detailLoading" class="drawer-body">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="t('asset.po.title')" :span="2">{{ detail.title }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.po.supplier')">{{ detail.supplierName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.po.dept')">{{ detail.deptName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.po.orderDate')">{{ detail.orderDate || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.po.arriveDate')">{{ detail.arriveDate || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.po.totalAmount')">{{ fmtNumber(detail.totalAmount) }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.po.handler')">{{ detail.handlerName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.po.remark')" :span="2">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div class="section-title">{{ t('asset.po.items') }}</div>
        <el-table :data="detail.items" border stripe size="small">
          <el-table-column :label="t('asset.po.itemName')" prop="itemName" min-width="140" />
          <el-table-column :label="t('asset.common.spec')" prop="spec" width="120" />
          <el-table-column :label="t('asset.common.unit')" prop="unit" width="70" />
          <el-table-column :label="t('asset.po.itemQty')" prop="quantity" width="90" align="right" />
          <el-table-column :label="t('asset.common.price')" width="110" align="right">
            <template #default="{ row }">{{ fmtNumber(row.price) }}</template>
          </el-table-column>
        </el-table>

        <template v-if="detail.receipts?.length">
          <div class="section-title">{{ t('asset.receipt.title') }}</div>
          <el-table :data="detail.receipts" border stripe size="small">
            <el-table-column :label="t('asset.receipt.receiptNo')" prop="receiptNo" min-width="140" />
            <el-table-column :label="t('common.form.status')" width="120">
              <template #default="{ row }">
                <StatusTag :status="String(row.status)" i18n-prefix="asset.status" />
              </template>
            </el-table-column>
          </el-table>
        </template>
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
