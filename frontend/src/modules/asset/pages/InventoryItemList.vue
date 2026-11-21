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
  createItem,
  deleteItem,
  exportItems,
  itemCounts,
  listItems,
  updateItem,
} from '@/api/asset'
import type { AssetItem } from '@/api/types'
import { useDeptTree, useLocationOptions, useSupplierOptions, useWarehouseOptions } from '../composables/useAssetOptions'

defineOptions({ name: 'InventoryItemList' })

const { t } = useI18n()
const deptTree = useDeptTree()
const warehouseOpts = useWarehouseOptions()
const locationOpts = useLocationOptions()
const supplierOpts = useSupplierOptions()
const categoryDict = useDictOptions('stock_category')

const searchModel = ref<Record<string, any>>({ q: '', category: '', lowStock: '' })
const searchFields = computed<SearchField[]>(() => [
  { key: 'q', labelKey: 'asset.item.name', placeholderKey: 'common.form.placeholderSearch', width: 220 },
  {
    key: 'category',
    labelKey: 'asset.item.category',
    type: 'select',
    width: 160,
    options: categoryDict.opts.value,
  },
  {
    key: 'lowStock',
    labelKey: 'asset.item.lowStockOnly',
    type: 'select',
    width: 140,
    options: [
      { label: t('common.action.yes'), value: '1' },
      { label: t('common.action.no'), value: '' },
    ],
  },
])

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'enabled', labelKey: 'common.status.enabled', count: 0 },
  { value: 'disabled', labelKey: 'common.status.disabled', count: 0 },
])

async function loadCounts() {
  try {
    const data = (await itemCounts()) ?? {}
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
  return {
    category: searchModel.value.category || undefined,
    low_stock: searchModel.value.lowStock === '1' ? '1' : undefined,
  }
}

const list = useListPage<AssetItem>({
  fetch: async (params) => {
    const data = await listItems({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(),
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) =>
    exportItems({
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
  { prop: 'code', labelKey: 'asset.item.code', width: 140, fixed: 'left', sortable: 'code' },
  { prop: 'name', labelKey: 'asset.item.name', minWidth: 160, sortable: 'name' },
  { prop: 'spec', labelKey: 'asset.item.spec', minWidth: 140 },
  { prop: 'unit', labelKey: 'asset.item.unit', width: 80 },
  { prop: 'category', labelKey: 'asset.item.category', width: 110 },
  { prop: 'unitPrice', labelKey: 'asset.item.unitPrice', width: 110, align: 'right', sortable: 'unit_price' },
  { prop: 'safetyStock', labelKey: 'asset.item.safetyStock', width: 110, align: 'right' },
  { prop: 'qtyOnHand', labelKey: 'asset.item.qtyOnHand', width: 110, align: 'right' },
  { prop: 'lowStock', labelKey: 'asset.item.lowStock', width: 110 },
  { prop: 'supplierName', labelKey: 'asset.item.supplier', minWidth: 140 },
  { prop: 'status', labelKey: 'common.form.status', width: 100, sortable: 'status' },
  { prop: 'createTime', labelKey: 'common.form.createTime', width: 160, sortable: 'create_time' },
]

function categoryLabel(value: unknown) {
  const v = String(value ?? '')
  return categoryDict.opts.value.find((x) => x.value === v)?.label || v || '-'
}

function rowActions(_row: AssetItem): ActionItem[] {
  return [
    { key: 'edit', tip: 'common.action.edit', perm: 'asset:item:edit' },
    { key: 'delete', tip: 'common.action.delete', perm: 'asset:item:delete' },
  ]
}

function onRowAction(key: string, row: AssetItem) {
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
  code: '',
  name: '',
  spec: '',
  unit: '',
  category: '',
  unitPrice: null as number | null,
  safetyStock: 0,
  maxStock: 0,
  defaultWarehouseId: null as number | null,
  defaultLocationId: null as number | null,
  supplierId: null as number | null,
  manufacturer: '',
  deptId: null as number | null,
  remark: '',
  status: 'enabled',
  version: null as number | null,
})

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('asset.item.create')
  Object.assign(form, {
    code: '',
    name: '',
    spec: '',
    unit: '',
    category: '',
    unitPrice: null,
    safetyStock: 0,
    maxStock: 0,
    defaultWarehouseId: null,
    defaultLocationId: null,
    supplierId: null,
    manufacturer: '',
    deptId: null,
    remark: '',
    status: 'enabled',
    version: null,
  })
  void supplierOpts.search('')
  dialogVisible.value = true
}

function openEdit(row: AssetItem) {
  editingId.value = row.id
  dialogTitle.value = t('asset.item.edit')
  Object.assign(form, {
    code: row.code,
    name: row.name,
    spec: row.spec,
    unit: row.unit,
    category: row.category,
    unitPrice: row.unitPrice,
    safetyStock: row.safetyStock,
    maxStock: row.maxStock,
    defaultWarehouseId: row.defaultWarehouseId ?? null,
    defaultLocationId: row.defaultLocationId ?? null,
    supplierId: row.supplierId ?? null,
    manufacturer: row.manufacturer,
    deptId: row.deptId ?? null,
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
    if (editingId.value) await updateItem(editingId.value, { ...form })
    else await createItem({ ...form })
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function remove(row: AssetItem) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteItem(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}
</script>

<template>
  <ListPage :title="t('asset.item.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'asset:item:create'" type="primary" @click="openCreate">
        {{ t('asset.item.create') }}
      </el-button>
      <ExportButton v-permission="'asset:item:list:export'" :export-fn="() => list.exportList()" />
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '', category: '', lowStock: '' }; list.reset()"
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
          <el-button link type="primary" @click="openEdit(row as unknown as AssetItem)">{{ row.code }}</el-button>
        </template>
        <template #category="{ row }">{{ categoryLabel(row.category) }}</template>
        <template #lowStock="{ row }">
          <el-tag v-if="row.lowStock" type="warning" size="small" effect="light" round>
            {{ t('asset.common.lowStock') }}
          </el-tag>
          <span v-else>{{ t('asset.common.normalStock') }}</span>
        </template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="asset.status" />
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="110" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar
                :actions="rowActions(row as unknown as AssetItem)"
                @select="(k) => onRowAction(k, row as unknown as AssetItem)"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="var(--bs-layout-dialog-lg)" append-to-body>
    <el-form ref="formRef" :model="form" label-width="120px">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('asset.item.code')" prop="code" :rules="[{ required: true, message: t('common.form.required') }]">
            <el-input v-model="form.code" :maxlength="32" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.item.name')" prop="name" :rules="[{ required: true, message: t('common.form.required') }]">
            <el-input v-model="form.name" :maxlength="128" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.item.spec')">
            <el-input v-model="form.spec" :maxlength="255" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.item.unit')">
            <el-input v-model="form.unit" :maxlength="16" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.item.category')">
            <el-select v-model="form.category" clearable style="width: 100%">
              <el-option v-for="o in categoryDict.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.item.unitPrice')">
            <el-input-number v-model="form.unitPrice" :min="0" :precision="2" :controls="false" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.item.safetyStock')">
            <el-input-number v-model="form.safetyStock" :min="0" :precision="2" :controls="false" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.item.maxStock')">
            <el-input-number v-model="form.maxStock" :min="0" :precision="2" :controls="false" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.item.defaultWarehouse')">
            <el-select v-model="form.defaultWarehouseId" clearable style="width: 100%">
              <el-option v-for="o in warehouseOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.item.defaultLocation')">
            <el-select v-model="form.defaultLocationId" clearable style="width: 100%">
              <el-option v-for="o in locationOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.item.supplier')">
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
          <el-form-item :label="t('asset.item.manufacturer')">
            <el-input v-model="form.manufacturer" :maxlength="128" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.item.dept')">
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
          <el-form-item :label="t('common.form.status')">
            <el-radio-group v-model="form.status">
              <el-radio value="enabled">{{ t('common.form.enabled') }}</el-radio>
              <el-radio value="disabled">{{ t('common.form.disabled') }}</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="t('asset.item.remark')">
        <el-input v-model="form.remark" type="textarea" :rows="2" :maxlength="500" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>
</template>
