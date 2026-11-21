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
import { useDictOptions } from '@/composables/useDict'
import {
  createLedger,
  deleteLedger,
  exportLedger,
  ledgerCounts,
  listLedger,
  updateLedger,
} from '@/api/asset'
import type { AssetLedger } from '@/api/types'
import {
  useDeptTree,
  useItemOptions,
  useLocationOptions,
  useWarehouseOptions,
} from '../composables/useAssetOptions'

defineOptions({ name: 'StockLedgerList' })

const { t } = useI18n()
const deptTree = useDeptTree()
const itemOpts = useItemOptions()
const locationOpts = useLocationOptions()
const warehouseOpts = useWarehouseOptions()
const reasonDict = useDictOptions('stock_reason')

const searchModel = ref<Record<string, any>>({ q: '', reason: '', happenRange: [] as string[] })
const searchFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'asset.ledger.item',
    placeholderKey: 'common.form.placeholderSearch',
    width: 220,
  },
  {
    key: 'reason',
    labelKey: 'asset.ledger.reason',
    type: 'select',
    width: 160,
    options: reasonDict.opts.value,
  },
  {
    key: 'happenRange',
    labelKey: 'asset.ledger.happenAt',
    type: 'daterange',
    width: 240,
  },
])

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'in', labelKey: 'asset.status.in', count: 0 },
  { value: 'out', labelKey: 'asset.status.out', count: 0 },
])

/** 台账没有 status 列，方向页签落到 filters[direction] */
const directionTab = ref('all')

async function loadCounts() {
  try {
    const data = (await ledgerCounts()) ?? {}
    for (const tab of statusTabs.value) {
      if (tab.value === 'all') continue
      tab.count = data[tab.value] ?? 0
    }
    const allTab = statusTabs.value.find((x) => x.value === 'all')
    if (allTab) allTab.count = (data.in ?? 0) + (data.out ?? 0)
  } catch {
    /* counts optional */
  }
}

onMounted(() => void loadCounts())

function buildFilters() {
  return {
    direction: directionTab.value === 'all' ? undefined : directionTab.value,
    reason: searchModel.value.reason || undefined,
  }
}

function buildRange(): Record<string, string> {
  const range = searchModel.value.happenRange
  return range && range.length === 2 ? { happen_at: range.join('|') } : {}
}

const list = useListPage<AssetLedger>({
  fetch: async (params) => {
    const data = await listLedger({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(),
      range: buildRange(),
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) =>
    exportLedger({
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
  directionTab.value = value
  list.setStatus(value)
}

function onReset() {
  searchModel.value = { q: '', reason: '', happenRange: [] }
  directionTab.value = 'all'
  list.reset()
}

const columns: ListColumn[] = [
  { prop: 'happenAt', labelKey: 'asset.ledger.happenAt', width: 160, sortable: 'create_time' },
  { prop: 'direction', labelKey: 'asset.ledger.direction', width: 90 },
  { prop: 'itemCode', labelKey: 'asset.ledger.item', width: 130 },
  { prop: 'itemName', labelKey: 'asset.common.name', minWidth: 160 },
  { prop: 'warehouseName', labelKey: 'asset.ledger.warehouse', width: 140 },
  { prop: 'locationCode', labelKey: 'asset.ledger.location', width: 120 },
  { prop: 'quantity', labelKey: 'asset.ledger.quantity', width: 100, align: 'right' },
  { prop: 'unitPrice', labelKey: 'asset.ledger.unitPrice', width: 110, align: 'right' },
  { prop: 'amount', labelKey: 'asset.ledger.amount', width: 120, align: 'right' },
  { prop: 'reason', labelKey: 'asset.ledger.reason', width: 120 },
  { prop: 'bizType', labelKey: 'asset.ledger.bizType', width: 120 },
  { prop: 'operatorName', labelKey: 'asset.ledger.operator', width: 110 },
  { prop: 'deptName', labelKey: 'asset.ledger.dept', width: 130 },
]

const BIZ_LABELS: Record<string, string> = {
  purchase: 'asset.ledger.bizPurchase',
  receipt: 'asset.ledger.bizReceipt',
  count: 'asset.ledger.bizCount',
  borrow: 'asset.ledger.bizBorrow',
  return: 'asset.ledger.bizReturn',
  scrap: 'asset.ledger.bizScrap',
  manual: 'asset.ledger.bizManual',
}

function bizTypeLabel(value: unknown) {
  const key = BIZ_LABELS[String(value ?? 'manual')] ?? 'asset.ledger.bizManual'
  return t(key)
}

function reasonLabel(value: unknown) {
  const v = String(value ?? '')
  return reasonDict.opts.value.find((o) => o.value === v)?.label || v || '-'
}

function rowActions(row: AssetLedger): ActionItem[] {
  if (!row.editable) return []
  return [
    { key: 'edit', tip: 'common.action.edit', perm: 'asset:ledger:edit' },
    { key: 'delete', tip: 'common.action.delete', perm: 'asset:ledger:delete' },
  ]
}

function onRowAction(key: string, row: AssetLedger) {
  if (key === 'edit') openEdit(row)
  else if (key === 'delete') void remove(row)
}

/* ---------- form ---------- */
const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  direction: 'in' as 'in' | 'out',
  itemId: null as number | null,
  warehouseId: null as number | null,
  locationId: null as number | null,
  quantity: 1,
  unitPrice: null as number | null,
  reason: 'manual',
  deptId: null as number | null,
  happenAt: '',
  remark: '',
  version: null as number | null,
})

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('asset.ledger.create')
  Object.assign(form, {
    direction: 'in',
    itemId: null,
    warehouseId: null,
    locationId: null,
    quantity: 1,
    unitPrice: null,
    reason: 'manual',
    deptId: null,
    happenAt: '',
    remark: '',
    version: null,
  })
  dialogVisible.value = true
}

function openEdit(row: AssetLedger) {
  editingId.value = row.id
  dialogTitle.value = t('asset.ledger.edit')
  Object.assign(form, {
    direction: row.direction === 'out' ? 'out' : 'in',
    itemId: row.itemId ?? null,
    warehouseId: row.warehouseId ?? null,
    locationId: row.locationId ?? null,
    quantity: row.quantity,
    unitPrice: row.unitPrice,
    reason: row.reason || 'manual',
    deptId: row.deptId ?? null,
    happenAt: (row.happenAt ?? '').slice(0, 10),
    remark: row.remark,
    version: row.version,
  })
  dialogVisible.value = true
}

function onItemPick(itemId: number | null) {
  if (!itemId) return
  const opt = itemOpts.items.value.find((o) => o.id === itemId)
  if (!opt) return
  if (form.unitPrice === null || form.unitPrice === undefined) form.unitPrice = opt.unitPrice
}

async function save() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  saving.value = true
  try {
    if (editingId.value) await updateLedger(editingId.value, { ...form })
    else await createLedger({ ...form })
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function remove(row: AssetLedger) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteLedger(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}
</script>

<template>
  <ListPage :title="t('asset.ledger.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'asset:ledger:create'" type="primary" @click="openCreate">
        {{ t('asset.ledger.create') }}
      </el-button>
      <ExportButton v-permission="'asset:ledger:list:export'" :export-fn="() => list.exportList()" />
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
      <StatusTabs
        :tabs="statusTabs"
        :model-value="String(list.query.status)"
        @update:model-value="onTabChange"
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
        <template #direction="{ row }">
          <StatusTag :status="String(row.direction)" i18n-prefix="asset.status" />
        </template>
        <template #reason="{ row }">{{ reasonLabel(row.reason) }}</template>
        <template #bizType="{ row }">{{ bizTypeLabel(row.bizType) }}</template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="110" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar
                :actions="rowActions(row as unknown as AssetLedger)"
                @select="(k) => onRowAction(k, row as unknown as AssetLedger)"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="var(--bs-layout-dialog-md)" append-to-body>
    <el-form ref="formRef" :model="form" label-width="110px">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('asset.ledger.direction')">
            <el-radio-group v-model="form.direction">
              <el-radio value="in">{{ t('asset.status.in') }}</el-radio>
              <el-radio value="out">{{ t('asset.status.out') }}</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.ledger.item')" prop="itemId" :rules="[{ required: true, message: t('common.form.required') }]">
            <el-select
              v-model="form.itemId"
              filterable
              :placeholder="t('asset.common.selectItem')"
              style="width: 100%"
              @change="onItemPick"
            >
              <el-option v-for="o in itemOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.ledger.warehouse')">
            <el-select v-model="form.warehouseId" clearable style="width: 100%">
              <el-option v-for="o in warehouseOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.ledger.location')">
            <el-select v-model="form.locationId" clearable filterable style="width: 100%">
              <el-option v-for="o in locationOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.ledger.quantity')" prop="quantity" :rules="[{ required: true, message: t('common.form.required') }]">
            <el-input-number v-model="form.quantity" :min="0.01" :precision="2" :controls="false" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.ledger.unitPrice')">
            <el-input-number v-model="form.unitPrice" :min="0" :precision="2" :controls="false" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.ledger.happenAt')">
            <el-date-picker v-model="form.happenAt" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.common.dept')">
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
      </el-row>
      <el-form-item :label="t('asset.ledger.remark')">
        <el-input v-model="form.remark" type="textarea" :rows="2" :maxlength="500" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>
</template>
