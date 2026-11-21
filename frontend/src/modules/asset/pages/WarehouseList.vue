<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import PageHeader from '@/components/common/PageHeader.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import {
  createLocation,
  createWarehouse,
  deleteLocation,
  deleteWarehouse,
  getWarehouse,
  listWarehouses,
  updateLocation,
  updateWarehouse,
  warehouseStats,
} from '@/api/asset'
import type { AssetLocation, AssetWarehouse, AssetWarehouseStats } from '@/api/types'
import { useDeptTree } from '../composables/useAssetOptions'

defineOptions({ name: 'WarehouseList' })

const { t } = useI18n()
const deptTree = useDeptTree()

const stats = ref<AssetWarehouseStats | null>(null)
const warehouses = ref<AssetWarehouse[]>([])
const keyword = ref('')
const loading = ref(false)
const currentId = ref<number | null>(null)
const locations = ref<AssetLocation[]>([])
const locationLoading = ref(false)

const statCards = computed(() => [
  { key: 'statWarehouse', label: t('asset.warehouse.statWarehouse'), value: stats.value?.warehouseCount ?? 0 },
  { key: 'statLocation', label: t('asset.warehouse.statLocation'), value: stats.value?.locationCount ?? 0 },
  { key: 'statBatch', label: t('asset.warehouse.statBatch'), value: stats.value?.batchCount ?? 0 },
  { key: 'statAmount', label: t('asset.warehouse.statAmount'), value: stats.value?.stockAmount ?? 0, money: true },
])

function fmtNumber(v: unknown) {
  const n = Number(v ?? 0)
  return Number.isFinite(n) ? n.toLocaleString() : '0'
}

async function loadStats() {
  try {
    stats.value = await warehouseStats()
  } catch {
    stats.value = null
  }
}

async function loadWarehouses() {
  loading.value = true
  try {
    const data = await listWarehouses({ page: 1, size: 200, q: keyword.value || undefined })
    warehouses.value = data.items ?? []
    if (!warehouses.value.length) {
      currentId.value = null
      locations.value = []
      return
    }
    const stillThere = warehouses.value.some((w) => w.id === currentId.value)
    const first = warehouses.value[0]
    if (!stillThere && first) await selectWarehouse(first.id)
  } catch {
    warehouses.value = []
  } finally {
    loading.value = false
  }
}

async function selectWarehouse(id: number) {
  currentId.value = id
  locationLoading.value = true
  try {
    const data = await getWarehouse(id)
    locations.value = data.locations ?? []
  } catch {
    locations.value = []
  } finally {
    locationLoading.value = false
  }
}

async function refreshAll() {
  await Promise.all([loadStats(), loadWarehouses()])
}

onMounted(() => void refreshAll())

function onSearch() {
  void loadWarehouses()
}

function resetSearch() {
  keyword.value = ''
  void loadWarehouses()
}

/* ---------- warehouse actions ---------- */
function warehouseActions(_row: AssetWarehouse): ActionItem[] {
  return [
    { key: 'edit', tip: 'common.action.edit', perm: 'asset:warehouse:edit' },
    { key: 'delete', tip: 'common.action.delete', perm: 'asset:warehouse:delete' },
  ]
}

function onWarehouseAction(key: string, row: AssetWarehouse) {
  if (key === 'edit') openWarehouseEdit(row)
  else if (key === 'delete') void removeWarehouse(row)
}

const whDialogVisible = ref(false)
const whDialogTitle = ref('')
const whFormRef = ref<FormInstance>()
const whSaving = ref(false)
const whEditingId = ref<number | null>(null)
const whForm = reactive({
  code: '',
  name: '',
  deptId: null as number | null,
  address: '',
  managerName: '',
  phone: '',
  capacity: null as number | null,
  remark: '',
  status: 'enabled',
  version: null as number | null,
})

function openWarehouseCreate() {
  whEditingId.value = null
  whDialogTitle.value = t('asset.warehouse.create')
  Object.assign(whForm, {
    code: '',
    name: '',
    deptId: null,
    address: '',
    managerName: '',
    phone: '',
    capacity: null,
    remark: '',
    status: 'enabled',
    version: null,
  })
  whDialogVisible.value = true
}

function openWarehouseEdit(row: AssetWarehouse) {
  whEditingId.value = row.id
  whDialogTitle.value = t('asset.warehouse.edit')
  Object.assign(whForm, {
    code: row.code,
    name: row.name,
    deptId: row.deptId ?? null,
    address: row.address,
    managerName: row.managerName,
    phone: row.phone,
    capacity: row.capacity ?? null,
    remark: row.remark,
    status: row.status,
    version: row.version,
  })
  whDialogVisible.value = true
}

async function saveWarehouse() {
  if (!whFormRef.value) return
  const ok = await whFormRef.value.validate().catch(() => false)
  if (!ok) return
  whSaving.value = true
  try {
    if (whEditingId.value) await updateWarehouse(whEditingId.value, { ...whForm })
    else await createWarehouse({ ...whForm })
    ElMessage.success(t('common.message.saveSuccess'))
    whDialogVisible.value = false
    await refreshAll()
  } catch {
    /* http notifies */
  } finally {
    whSaving.value = false
  }
}

async function removeWarehouse(row: AssetWarehouse) {
  try {
    await ElMessageBox.confirm(t('asset.warehouse.deleteTip'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteWarehouse(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    if (currentId.value === row.id) currentId.value = null
    await refreshAll()
  } catch {
    /* http notifies */
  }
}

/* ---------- location actions ---------- */
const locDialogVisible = ref(false)
const locDialogTitle = ref('')
const locFormRef = ref<FormInstance>()
const locSaving = ref(false)
const locEditingId = ref<number | null>(null)
const locForm = reactive({
  warehouseId: null as number | null,
  code: '',
  name: '',
  area: '',
  capacity: null as number | null,
  remark: '',
  status: 'enabled',
  version: null as number | null,
})

function openLocationCreate() {
  if (!currentId.value) return
  locEditingId.value = null
  locDialogTitle.value = t('asset.warehouse.addLocation')
  Object.assign(locForm, {
    warehouseId: currentId.value,
    code: '',
    name: '',
    area: '',
    capacity: null,
    remark: '',
    status: 'enabled',
    version: null,
  })
  locDialogVisible.value = true
}

function openLocationEdit(row: AssetLocation) {
  locEditingId.value = row.id
  locDialogTitle.value = t('asset.warehouse.editLocation')
  Object.assign(locForm, {
    warehouseId: row.warehouseId,
    code: row.code,
    name: row.name,
    area: row.area,
    capacity: row.capacity,
    remark: row.remark,
    status: row.status,
    version: row.version,
  })
  locDialogVisible.value = true
}

async function saveLocation() {
  if (!locFormRef.value) return
  const ok = await locFormRef.value.validate().catch(() => false)
  if (!ok) return
  locSaving.value = true
  try {
    if (locEditingId.value) await updateLocation(locEditingId.value, { ...locForm })
    else await createLocation({ ...locForm })
    ElMessage.success(t('common.message.saveSuccess'))
    locDialogVisible.value = false
    if (currentId.value) await selectWarehouse(currentId.value)
    await Promise.all([loadStats(), loadWarehouses()])
  } catch {
    /* http notifies */
  } finally {
    locSaving.value = false
  }
}

async function removeLocation(row: AssetLocation) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteLocation(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    if (currentId.value) await selectWarehouse(currentId.value)
    await Promise.all([loadStats(), loadWarehouses()])
  } catch {
    /* http notifies */
  }
}
</script>

<template>
  <div class="bs-page bs-page--fill warehouse-page">
    <PageHeader :title="t('asset.warehouse.title')">
      <template #actions>
        <el-button @click="refreshAll">
          <el-icon><Refresh /></el-icon>
          <span>{{ t('common.action.refresh') }}</span>
        </el-button>
        <el-button v-permission="'asset:warehouse:create'" type="primary" @click="openWarehouseCreate">
          {{ t('asset.warehouse.create') }}
        </el-button>
      </template>
    </PageHeader>

    <div class="stat-row">
      <div v-for="card in statCards" :key="card.key" class="stat-card">
        <div class="stat-label">{{ card.label }}</div>
        <div class="stat-value">{{ fmtNumber(card.value) }}</div>
      </div>
    </div>

    <div class="master-detail">
      <section class="bs-page-card master-panel">
        <div class="panel-header">
          <span class="panel-title">{{ t('asset.warehouse.title') }}</span>
          <el-input
            v-model="keyword"
            :placeholder="t('common.form.placeholderSearch')"
            clearable
            class="panel-search"
            @keyup.enter="onSearch"
            @clear="resetSearch"
          />
        </div>
        <div v-loading="loading" class="panel-body">
          <div
            v-for="w in warehouses"
            :key="w.id"
            class="master-item"
            :class="{ active: w.id === currentId }"
            @click="selectWarehouse(w.id)"
          >
            <div class="master-item-head">
              <div>
                <span class="master-code">{{ w.code }}</span>
                <span class="master-name">{{ w.name }}</span>
              </div>
              <ActionBar
                :actions="warehouseActions(w)"
                @select="(k) => onWarehouseAction(k, w)"
              />
            </div>
            <div class="master-item-meta">{{ w.deptName || '-' }}</div>
            <div class="master-item-summary">
              <span>{{ t('asset.warehouse.locationCount') }}: {{ w.locationCount }}</span>
              <span>{{ t('asset.warehouse.qtyOnHand') }}: {{ fmtNumber(w.qtyOnHand) }}</span>
              <span>{{ t('asset.warehouse.stockAmount') }}: {{ fmtNumber(w.stockAmount) }}</span>
            </div>
          </div>
          <el-empty v-if="!loading && !warehouses.length" :description="t('common.table.empty')" />
        </div>
      </section>

      <section class="bs-page-card detail-panel">
        <div class="panel-header">
          <span class="panel-title">{{ t('asset.warehouse.locationTitle') }}</span>
          <el-button
            v-permission="'asset:warehouse:create'"
            type="primary"
            size="small"
            :disabled="!currentId"
            @click="openLocationCreate"
          >
            {{ t('asset.warehouse.addLocation') }}
          </el-button>
        </div>
        <div v-loading="locationLoading" class="panel-body panel-body--table">
          <el-table :data="locations" border stripe size="small" height="100%">
            <el-table-column :label="t('asset.warehouse.locationCode')" prop="code" width="130" />
            <el-table-column :label="t('asset.warehouse.locationName')" prop="name" min-width="140" />
            <el-table-column :label="t('asset.warehouse.area')" prop="area" width="110" />
            <el-table-column :label="t('asset.warehouse.capacity')" prop="capacity" width="100" align="right" />
            <el-table-column :label="t('asset.warehouse.used')" prop="used" width="100" align="right" />
            <el-table-column :label="t('asset.common.stockQty')" prop="qtyOnHand" width="110" align="right" />
            <el-table-column :label="t('common.form.status')" width="100">
              <template #default="{ row }">
                <StatusTag :status="String(row.status)" i18n-prefix="asset.status" />
              </template>
            </el-table-column>
            <el-table-column :label="t('common.action.operate')" width="110" fixed="right" align="center">
              <template #default="{ row }">
                <ActionBar
                  :actions="[
                    { key: 'edit', tip: 'common.action.edit', perm: 'asset:warehouse:edit' },
                    { key: 'delete', tip: 'common.action.delete', perm: 'asset:warehouse:delete' },
                  ]"
                  @select="(k) => (k === 'edit' ? openLocationEdit(row) : removeLocation(row))"
                />
              </template>
            </el-table-column>
          </el-table>
        </div>
      </section>
    </div>

    <el-dialog v-model="whDialogVisible" :title="whDialogTitle" width="var(--bs-layout-dialog-md)" append-to-body>
      <el-form ref="whFormRef" :model="whForm" label-width="120px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item :label="t('asset.warehouse.code')" prop="code" :rules="[{ required: true, message: t('common.form.required') }]">
              <el-input v-model="whForm.code" :maxlength="32" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.warehouse.name')" prop="name" :rules="[{ required: true, message: t('common.form.required') }]">
              <el-input v-model="whForm.name" :maxlength="128" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.warehouse.dept')">
              <el-tree-select
                v-model="whForm.deptId"
                :data="deptTree.deptTree.value"
                :props="{ label: 'name', value: 'id', children: 'children' }"
                check-strictly
                clearable
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.warehouse.manager')">
              <el-input v-model="whForm.managerName" :maxlength="64" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.warehouse.phone')">
              <el-input v-model="whForm.phone" :maxlength="32" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.warehouse.capacity')">
              <el-input-number v-model="whForm.capacity" :min="0" :precision="0" :controls="false" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item :label="t('asset.warehouse.address')">
              <el-input v-model="whForm.address" :maxlength="255" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item :label="t('common.form.status')">
              <el-radio-group v-model="whForm.status">
                <el-radio value="enabled">{{ t('common.form.enabled') }}</el-radio>
                <el-radio value="disabled">{{ t('common.form.disabled') }}</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="t('common.form.remark')">
          <el-input v-model="whForm.remark" type="textarea" :rows="2" :maxlength="500" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="whDialogVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="whSaving" @click="saveWarehouse">{{ t('common.action.save') }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="locDialogVisible" :title="locDialogTitle" width="var(--bs-layout-dialog-sm)" append-to-body>
      <el-form ref="locFormRef" :model="locForm" label-width="110px">
        <el-form-item :label="t('asset.warehouse.locationCode')" prop="code" :rules="[{ required: true, message: t('common.form.required') }]">
          <el-input v-model="locForm.code" :maxlength="32" />
        </el-form-item>
        <el-form-item :label="t('asset.warehouse.locationName')">
          <el-input v-model="locForm.name" :maxlength="128" />
        </el-form-item>
        <el-form-item :label="t('asset.warehouse.area')">
          <el-input v-model="locForm.area" :maxlength="64" />
        </el-form-item>
        <el-form-item :label="t('asset.warehouse.capacity')">
          <el-input-number v-model="locForm.capacity" :min="0" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item :label="t('common.form.status')">
          <el-radio-group v-model="locForm.status">
            <el-radio value="enabled">{{ t('common.form.enabled') }}</el-radio>
            <el-radio value="disabled">{{ t('common.form.disabled') }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="t('common.form.remark')">
          <el-input v-model="locForm.remark" type="textarea" :rows="2" :maxlength="500" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="locDialogVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="locSaving" @click="saveLocation">{{ t('common.action.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.warehouse-page {
  gap: var(--bs-layout-section-gap);
}

.stat-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--bs-space-3);
  flex-shrink: 0;
}

.stat-card {
  background: var(--bs-color-bg-surface);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  padding: var(--bs-space-3);
}

.stat-label {
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-xs);
}

.stat-value {
  margin-top: var(--bs-space-2);
  font-size: 24px;
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.master-detail {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(280px, 340px) 1fr;
  gap: var(--bs-layout-section-gap);
}

.master-panel,
.detail-panel {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  min-height: 0;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bs-space-2);
  flex-shrink: 0;
}

.panel-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.panel-search {
  max-width: 180px;
}

.panel-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.panel-body--table {
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.master-item {
  padding: var(--bs-space-2) var(--bs-space-3);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  margin-bottom: var(--bs-space-2);
  cursor: pointer;
}

.master-item:hover {
  border-color: var(--bs-color-border-default);
}

.master-item.active {
  border-color: var(--bs-color-primary);
  background: var(--bs-color-brand-primary-soft);
}

.master-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bs-space-2);
}

.master-code {
  font-family: var(--bs-typography-font-family-mono);
  color: var(--bs-color-fg-muted);
  margin-right: var(--bs-space-2);
}

.master-name {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.master-item-meta {
  margin-top: var(--bs-space-1);
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-sm);
}

.master-item-summary {
  margin-top: var(--bs-space-2);
  display: flex;
  gap: var(--bs-space-3);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}
</style>
