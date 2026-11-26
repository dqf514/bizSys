<script setup lang="ts">
/**
 * B6 设备台账 / 能耗采集 / 设备预警。
 *
 * 页面结构：统计卡片 + 三个页签（设备台账 / 能耗数据 / 设备预警）。
 * 列表一律走 `components/list/ListTable.vue`（内部适配 ResponsiveTable，窄屏自动降级为卡片流）。
 * 页面根用 `.bs-page .bs-page--fill`，el-tabs 需要撑满剩余高度，表格才能拿到确定高度。
 */
import { computed, onActivated, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import PageHeader from '@/components/common/PageHeader.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { useListPage } from '@/composables/useListPage'
import {
  createEquipment,
  createEquipmentAlert,
  createEquipmentMetric,
  deleteEquipment,
  equipmentAlertCounts,
  equipmentCounts,
  getEquipment,
  handleEquipmentAlert,
  listEquipmentAlerts,
  listEquipmentMetrics,
  listEquipments,
  scanEquipmentAlerts,
  updateEquipment,
} from '@/api/asset'
import type { Equipment, EquipmentAlert, EquipmentDetail, EquipmentMetric } from '@/api/asset'
import { useDeptTree, useSupplierOptions } from '../composables/useAssetOptions'

defineOptions({ name: 'EquipmentList' })

const { t } = useI18n()
const deptTree = useDeptTree()
const suppliers = useSupplierOptions()

const activeTab = ref('ledger')

/* ---------------- 口径常量 ---------------- */

const STATUS_OPTIONS = ['idle', 'running', 'maintenance', 'fault', 'scrapped'] as const
const CATEGORY_OPTIONS = ['wind_tunnel', 'cfd', 'machining', 'test', 'other'] as const
const SHIFT_OPTIONS = ['morning', 'day', 'night'] as const
const SOURCE_OPTIONS = ['manual', 'schedule'] as const
const RULE_OPTIONS = [
  'maintain_overdue',
  'energy_abnormal',
  'low_utilization',
  'fault',
  'status_abnormal',
] as const
const LEVEL_OPTIONS = ['info', 'warning', 'critical'] as const
const HANDLE_STATUS_OPTIONS = ['processing', 'closed'] as const

function statusOptions() {
  return STATUS_OPTIONS.map((s) => ({ value: s, label: t(`asset.equipment.statusOptions.${s}`) }))
}

function categoryOptions() {
  return CATEGORY_OPTIONS.map((s) => ({ value: s, label: t(`asset.equipment.categoryOptions.${s}`) }))
}

function shiftOptions() {
  return SHIFT_OPTIONS.map((s) => ({ value: s, label: t(`asset.equipment.metric.shiftOptions.${s}`) }))
}

function sourceOptions() {
  return SOURCE_OPTIONS.map((s) => ({ value: s, label: t(`asset.equipment.metric.sourceOptions.${s}`) }))
}

function ruleOptions() {
  return RULE_OPTIONS.map((s) => ({ value: s, label: t(`asset.equipment.alert.ruleOptions.${s}`) }))
}

function levelOptions() {
  return LEVEL_OPTIONS.map((s) => ({ value: s, label: t(`asset.equipment.alert.levelOptions.${s}`) }))
}

function handleStatusOptions() {
  return HANDLE_STATUS_OPTIONS.map((s) => ({
    value: s,
    label: t(`asset.equipment.alert.statusOptions.${s}`),
  }))
}

/* ---------------- 统计卡片 ---------------- */

const counts = ref<Record<string, number>>({
  all: 0,
  idle: 0,
  running: 0,
  maintenance: 0,
  fault: 0,
  scrapped: 0,
})

async function loadCounts() {
  try {
    const data = await equipmentCounts()
    counts.value = { ...counts.value, ...(data as unknown as Record<string, number>) }
  } catch {
    /* 统计卡允许为空 */
  }
}

const statCards = computed(() => [
  { key: 'all', label: t('asset.equipment.stat.total'), value: counts.value.all ?? 0, tone: 'total' },
  {
    key: 'running',
    label: t('asset.equipment.stat.running'),
    value: counts.value.running ?? 0,
    tone: 'ok',
  },
  {
    key: 'maintenance',
    label: t('asset.equipment.stat.maintenance'),
    value: counts.value.maintenance ?? 0,
    tone: 'warn',
  },
  { key: 'fault', label: t('asset.equipment.stat.fault'), value: counts.value.fault ?? 0, tone: 'danger' },
])

/* ---------------- 下拉选项 ---------------- */

const equipmentOptions = ref<{ value: number; label: string }[]>([])
const workshopOptions = ref<{ value: string; label: string }[]>([])

async function loadEquipmentOptions() {
  try {
    const data = await listEquipments({ page: 1, size: 200 })
    const items = data.items ?? []
    equipmentOptions.value = items.map((e) => ({
      value: e.id,
      label: `${e.equipmentNo} ${e.name}`,
    }))
    const workshops = Array.from(new Set(items.map((e) => e.workshop).filter(Boolean)))
    workshopOptions.value = workshops.map((w) => ({ value: w, label: w }))
  } catch {
    equipmentOptions.value = []
    workshopOptions.value = []
  }
}

/* ---------------- 页签一：设备台账 ---------------- */

const ledgerSearch = ref<Record<string, any>>({ q: '', status: '', category: '', workshop: '' })

const ledgerFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'asset.equipment.keyword',
    placeholderKey: 'common.form.placeholderSearch',
    width: 220,
  },
  {
    key: 'status',
    labelKey: 'asset.equipment.status',
    type: 'select',
    width: 150,
    options: statusOptions(),
  },
  {
    key: 'category',
    labelKey: 'asset.equipment.category',
    type: 'select',
    width: 160,
    options: categoryOptions(),
  },
  {
    key: 'workshop',
    labelKey: 'asset.equipment.workshop',
    type: 'select',
    width: 160,
    options: workshopOptions.value,
  },
])

const ledger = useListPage<Equipment>({
  autoLoad: false,
  fetch: async (params) => {
    const data = await listEquipments({
      ...params,
      q: ledgerSearch.value.q || undefined,
      status: ledgerSearch.value.status || 'all',
      filters: {
        category: ledgerSearch.value.category || undefined,
        workshop: ledgerSearch.value.workshop || undefined,
      },
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  onLoaded: () => {
    void loadCounts()
  },
})

const ledgerColumns: ListColumn[] = [
  {
    prop: 'equipmentNo',
    labelKey: 'asset.equipment.equipmentNo',
    width: 140,
    fixed: 'left',
    sortable: 'equipment_no',
  },
  { prop: 'name', labelKey: 'asset.equipment.name', minWidth: 160, sortable: 'name' },
  { prop: 'category', labelKey: 'asset.equipment.category', width: 120 },
  { prop: 'model', labelKey: 'asset.equipment.model', width: 130 },
  { prop: 'workshop', labelKey: 'asset.equipment.workshop', width: 130 },
  { prop: 'location', labelKey: 'asset.equipment.location', minWidth: 140 },
  { prop: 'ownerName', labelKey: 'asset.equipment.owner', width: 110 },
  { prop: 'status', labelKey: 'asset.equipment.status', width: 110, sortable: 'status' },
  {
    prop: 'nextMaintainDate',
    labelKey: 'asset.equipment.nextMaintainDate',
    width: 130,
    sortable: 'next_maintain_date',
  },
]

function ledgerActions(row: Equipment): ActionItem[] {
  const acts: ActionItem[] = [{ key: 'detail', tip: 'common.action.detail' }]
  acts.push({ key: 'edit', tip: 'common.action.edit', perm: 'asset:equipment:edit' })
  if (row.status !== 'scrapped') {
    acts.push({
      key: 'metric',
      tip: 'asset.equipment.metric.register',
      icon: 'DataLine',
      perm: 'asset:equipment:metric:create',
    })
  }
  acts.push({ key: 'delete', tip: 'common.action.delete', perm: 'asset:equipment:delete' })
  return acts
}

function onLedgerAction(key: string, row: Equipment) {
  if (key === 'detail') void openDetail(row.id)
  else if (key === 'edit') openEdit(row)
  else if (key === 'metric') openMetricDialog(row.id)
  else if (key === 'delete') void removeEquipment(row)
}

/* ---------------- 页签二：能耗数据 ---------------- */

const metricSearch = ref<Record<string, any>>({ q: '', equipmentId: '', statDate: [] as string[] })

const metricFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'asset.equipment.keyword',
    placeholderKey: 'common.form.placeholderSearch',
    width: 200,
  },
  {
    key: 'equipmentId',
    labelKey: 'asset.equipment.name',
    type: 'select',
    width: 220,
    options: equipmentOptions.value,
  },
  {
    key: 'statDate',
    labelKey: 'asset.equipment.metric.statDate',
    type: 'daterange',
    width: 260,
  },
])

const metric = useListPage<EquipmentMetric>({
  autoLoad: false,
  fetch: async (params) => {
    const range = metricSearch.value.statDate
    const data = await listEquipmentMetrics({
      ...params,
      q: metricSearch.value.q || undefined,
      filters: {
        equipment_id: metricSearch.value.equipmentId || undefined,
      },
      range: {
        stat_date: Array.isArray(range) && range.length === 2 ? range.join('|') : '',
      },
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
})

const metricColumns: ListColumn[] = [
  { prop: 'equipmentName', labelKey: 'asset.equipment.name', minWidth: 160 },
  { prop: 'equipmentNo', labelKey: 'asset.equipment.equipmentNo', width: 130 },
  {
    prop: 'statDate',
    labelKey: 'asset.equipment.metric.statDate',
    width: 120,
    sortable: 'stat_date',
  },
  { prop: 'shift', labelKey: 'asset.equipment.metric.shift', width: 100 },
  {
    prop: 'runHours',
    labelKey: 'asset.equipment.metric.runHours',
    width: 110,
    align: 'right',
    sortable: 'run_hours',
  },
  {
    prop: 'downtimeHours',
    labelKey: 'asset.equipment.metric.downtimeHours',
    width: 110,
    align: 'right',
  },
  {
    prop: 'energy',
    labelKey: 'asset.equipment.metric.energy',
    width: 130,
    align: 'right',
    sortable: 'energy',
  },
  {
    prop: 'outputQty',
    labelKey: 'asset.equipment.metric.outputQty',
    width: 100,
    align: 'right',
  },
  { prop: 'source', labelKey: 'asset.equipment.metric.source', width: 120 },
]

/* ---------------- 页签三：设备预警 ---------------- */

const alertSearch = ref<Record<string, any>>({ q: '', equipmentId: '', ruleType: '', level: '' })

const alertFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'asset.equipment.keyword',
    placeholderKey: 'common.form.placeholderSearch',
    width: 200,
  },
  {
    key: 'equipmentId',
    labelKey: 'asset.equipment.name',
    type: 'select',
    width: 220,
    options: equipmentOptions.value,
  },
  {
    key: 'ruleType',
    labelKey: 'asset.equipment.alert.ruleType',
    type: 'select',
    width: 150,
    options: ruleOptions(),
  },
  {
    key: 'level',
    labelKey: 'asset.equipment.alert.level',
    type: 'select',
    width: 130,
    options: levelOptions(),
  },
])

const alertTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'open', labelKey: 'asset.equipment.alert.statusOptions.open', count: 0 },
  { value: 'processing', labelKey: 'asset.equipment.alert.statusOptions.processing', count: 0 },
  { value: 'closed', labelKey: 'asset.equipment.alert.statusOptions.closed', count: 0 },
])

async function loadAlertCounts() {
  try {
    const data = await equipmentAlertCounts()
    const map = (data ?? {}) as unknown as Record<string, number>
    for (const tab of alertTabs.value) {
      tab.count = map[tab.value] ?? 0
    }
  } catch {
    /* 计数允许为空 */
  }
}

const alert = useListPage<EquipmentAlert>({
  autoLoad: false,
  fetch: async (params) => {
    const data = await listEquipmentAlerts({
      ...params,
      q: alertSearch.value.q || undefined,
      filters: {
        equipment_id: alertSearch.value.equipmentId || undefined,
        rule_type: alertSearch.value.ruleType || undefined,
        level: alertSearch.value.level || undefined,
      },
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  onLoaded: () => {
    void loadAlertCounts()
  },
})

const alertColumns: ListColumn[] = [
  {
    prop: 'alertNo',
    labelKey: 'asset.equipment.alert.alertNo',
    width: 150,
    fixed: 'left',
    sortable: 'alert_no',
  },
  { prop: 'equipmentName', labelKey: 'asset.equipment.name', minWidth: 150 },
  {
    prop: 'ruleType',
    labelKey: 'asset.equipment.alert.ruleType',
    width: 130,
    sortable: 'rule_type',
  },
  { prop: 'level', labelKey: 'asset.equipment.alert.level', width: 110, sortable: 'level' },
  { prop: 'title', labelKey: 'asset.equipment.alert.title', minWidth: 180 },
  {
    prop: 'triggeredAt',
    labelKey: 'asset.equipment.alert.triggeredAt',
    width: 160,
    sortable: 'triggered_at',
  },
  { prop: 'status', labelKey: 'asset.equipment.alert.status', width: 110, sortable: 'status' },
  { prop: 'handlerName', labelKey: 'asset.equipment.alert.handler', width: 110 },
]

function alertActions(row: EquipmentAlert): ActionItem[] {
  const acts: ActionItem[] = []
  if (row.status !== 'closed') {
    acts.push({
      key: 'handle',
      tip: 'asset.equipment.alert.handle',
      icon: 'CircleCheck',
      perm: 'asset:equipment:alert:handle',
    })
  }
  return acts
}

function onAlertAction(key: string, row: EquipmentAlert) {
  if (key === 'handle') openHandleDialog(row)
}

/* ---------------- 设备表单 ---------------- */

const formVisible = ref(false)
const formSaving = ref(false)
const formRef = ref<FormInstance>()
const editingId = ref<number | null>(null)

const form = reactive({
  equipmentNo: '',
  name: '',
  category: 'other',
  model: '',
  spec: '',
  workshop: '',
  location: '',
  vendorId: null as number | null,
  purchaseDate: '',
  commissionDate: '',
  originalValue: 0,
  status: 'idle',
  ownerName: '',
  deptId: null as number | null,
  maintainCycleDays: 0,
  lastMaintainDate: '',
  nextMaintainDate: '',
  runHours: 0,
  remark: '',
  version: null as number | null,
})

function resetForm() {
  Object.assign(form, {
    equipmentNo: '',
    name: '',
    category: 'other',
    model: '',
    spec: '',
    workshop: '',
    location: '',
    vendorId: null,
    purchaseDate: '',
    commissionDate: '',
    originalValue: 0,
    status: 'idle',
    ownerName: '',
    deptId: null,
    maintainCycleDays: 0,
    lastMaintainDate: '',
    nextMaintainDate: '',
    runHours: 0,
    remark: '',
    version: null,
  })
}

function openCreate() {
  editingId.value = null
  resetForm()
  formVisible.value = true
}

function openEdit(row: Equipment) {
  editingId.value = row.id
  Object.assign(form, {
    equipmentNo: row.equipmentNo,
    name: row.name,
    category: row.category,
    model: row.model,
    spec: row.spec,
    workshop: row.workshop,
    location: row.location,
    vendorId: row.vendorId ?? null,
    purchaseDate: row.purchaseDate ?? '',
    commissionDate: row.commissionDate ?? '',
    originalValue: row.originalValue ?? 0,
    status: row.status,
    ownerName: row.ownerName,
    deptId: row.deptId ?? null,
    maintainCycleDays: row.maintainCycleDays,
    lastMaintainDate: row.lastMaintainDate ?? '',
    nextMaintainDate: row.nextMaintainDate ?? '',
    runHours: row.runHours ?? 0,
    remark: row.remark,
    version: row.version ?? null,
  })
  formVisible.value = true
}

async function saveForm() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  formSaving.value = true
  try {
    if (editingId.value) await updateEquipment(editingId.value, { ...form })
    else await createEquipment({ ...form })
    ElMessage.success(t('common.message.saveSuccess'))
    formVisible.value = false
    ledger.refresh()
    void loadEquipmentOptions()
  } catch {
    /* http 层已提示 */
  } finally {
    formSaving.value = false
  }
}

async function removeEquipment(row: Equipment) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await deleteEquipment(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    ledger.refresh()
    void loadEquipmentOptions()
  } catch {
    /* http 层已提示 */
  }
}

/* ---------------- 能耗登记 ---------------- */

const metricVisible = ref(false)
const metricSaving = ref(false)

const metricForm = reactive({
  equipmentId: null as number | null,
  statDate: '',
  shift: 'day',
  runHours: 0,
  downtimeHours: 0,
  energy: 0,
  outputQty: 0,
  source: 'manual',
  remark: '',
})

function openMetricDialog(equipmentId?: number) {
  Object.assign(metricForm, {
    equipmentId: equipmentId ?? null,
    statDate: '',
    shift: 'day',
    runHours: 0,
    downtimeHours: 0,
    energy: 0,
    outputQty: 0,
    source: 'manual',
    remark: '',
  })
  metricVisible.value = true
}

async function submitMetric() {
  const equipmentId = metricForm.equipmentId
  if (!equipmentId) {
    ElMessage.warning(t('common.form.required'))
    return
  }
  metricSaving.value = true
  try {
    await createEquipmentMetric({ ...metricForm, equipmentId })
    ElMessage.success(t('common.message.saveSuccess'))
    metricVisible.value = false
    metric.refresh()
    ledger.refresh()
  } catch {
    /* http 层已提示 */
  } finally {
    metricSaving.value = false
  }
}

/* ---------------- 预警登记 ---------------- */

const alertVisible = ref(false)
const alertSaving = ref(false)

const alertForm = reactive({
  equipmentId: null as number | null,
  ruleType: 'status_abnormal',
  level: 'warning',
  title: '',
  content: '',
  remark: '',
})

function openAlertDialog() {
  Object.assign(alertForm, {
    equipmentId: null,
    ruleType: 'status_abnormal',
    level: 'warning',
    title: '',
    content: '',
    remark: '',
  })
  alertVisible.value = true
}

async function submitAlert() {
  const equipmentId = alertForm.equipmentId
  if (!equipmentId) {
    ElMessage.warning(t('common.form.required'))
    return
  }
  alertSaving.value = true
  try {
    await createEquipmentAlert({ ...alertForm, equipmentId })
    ElMessage.success(t('asset.equipment.message.registerSuccess'))
    alertVisible.value = false
    alert.refresh()
  } catch {
    /* http 层已提示 */
  } finally {
    alertSaving.value = false
  }
}

/* ---------------- 预警处理 ---------------- */

const handleVisible = ref(false)
const handleSaving = ref(false)
const handleRow = ref<EquipmentAlert | null>(null)
const handleForm = reactive({ status: 'processing', handleResult: '' })

function openHandleDialog(row: EquipmentAlert) {
  handleRow.value = row
  Object.assign(handleForm, { status: 'processing', handleResult: '' })
  handleVisible.value = true
}

async function submitHandle() {
  if (!handleRow.value) return
  handleSaving.value = true
  try {
    await handleEquipmentAlert(handleRow.value.id, { ...handleForm })
    ElMessage.success(t('asset.equipment.message.handleSuccess'))
    handleVisible.value = false
    alert.refresh()
  } catch {
    /* http 层已提示 */
  } finally {
    handleSaving.value = false
  }
}

const scanning = ref(false)

async function scanAlerts() {
  scanning.value = true
  try {
    const res = await scanEquipmentAlerts()
    ElMessage.success(
      t('asset.equipment.message.scanDone', { created: res?.created ?? 0, skipped: res?.skipped ?? 0 }),
    )
    alert.refresh()
  } catch {
    /* http 层已提示 */
  } finally {
    scanning.value = false
  }
}

/* ---------------- 详情抽屉 ---------------- */

const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<EquipmentDetail | null>(null)

async function openDetail(id: number) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await getEquipment(id)
  } catch {
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

/* ---------------- 加载与切换 ---------------- */

onMounted(() => {
  void ledger.load()
  void loadCounts()
  void loadEquipmentOptions()
})

let firstActivation = true
onActivated(() => {
  if (firstActivation) {
    firstActivation = false
    return
  }
  if (activeTab.value === 'metric') void metric.load()
  else if (activeTab.value === 'alert') void alert.load()
  else void ledger.load()
})

const metricLoaded = ref(false)
const alertLoaded = ref(false)

watch(activeTab, (tab) => {
  if (tab === 'metric' && !metricLoaded.value) {
    metricLoaded.value = true
    void metric.load()
  }
  if (tab === 'alert' && !alertLoaded.value) {
    alertLoaded.value = true
    void alert.load()
  }
})
</script>

<template>
  <div class="bs-page bs-page--fill equipment-page">
    <PageHeader :title="t('asset.equipment.title')">
      <template #actions>
        <el-button v-permission="'asset:equipment:create'" type="primary" @click="openCreate">
          {{ t('asset.equipment.create') }}
        </el-button>
      </template>
    </PageHeader>

    <div class="stat-row">
      <div v-for="card in statCards" :key="card.key" class="stat-card" :class="`stat-card--${card.tone}`">
        <div class="stat-label">{{ card.label }}</div>
        <div class="stat-value">{{ card.value }}</div>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="equipment-tabs">
      <!-- 设备台账 -->
      <el-tab-pane :label="t('asset.equipment.tabs.ledger')" name="ledger">
        <div class="tab-pane">
          <div class="pane-search">
            <SearchBar
              v-model="ledgerSearch"
              :fields="ledgerFields"
              @search="ledger.search()"
              @reset="ledgerSearch = { q: '', status: '', category: '', workshop: '' }; ledger.reset()"
            />
          </div>
          <div class="pane-table">
            <ListTable
              :columns="ledgerColumns"
              :data="ledger.items.value as unknown as Record<string, unknown>[]"
              :loading="ledger.loading.value"
              :total="ledger.total.value"
              :page="Number(ledger.query.page)"
              :size="Number(ledger.query.size)"
              row-key="id"
              @update:page="ledger.setPage"
              @update:size="ledger.setSize"
              @sort-change="ledger.onSortChange"
            >
              <template #equipmentNo="{ row }">
                <el-button link type="primary" @click="openDetail(row.id)">{{ row.equipmentNo }}</el-button>
              </template>
              <template #category="{ row }">{{ row.categoryText || '-' }}</template>
              <template #status="{ row }">
                <StatusTag :status="String(row.status)" i18n-prefix="asset.equipment.statusOptions" />
              </template>
              <template #extraColumns>
                <el-table-column
                  :label="t('common.action.operate')"
                  width="170"
                  fixed="right"
                  align="center"
                  header-align="center"
                >
                  <template #default="{ row }">
                    <ActionBar
                      :actions="ledgerActions(row as unknown as Equipment)"
                      @select="(k) => onLedgerAction(k, row as unknown as Equipment)"
                    />
                  </template>
                </el-table-column>
              </template>
            </ListTable>
          </div>
        </div>
      </el-tab-pane>

      <!-- 能耗数据 -->
      <el-tab-pane :label="t('asset.equipment.tabs.metric')" name="metric">
        <div class="tab-pane">
          <div class="pane-search">
            <SearchBar
              v-model="metricSearch"
              :fields="metricFields"
              @search="metric.search()"
              @reset="metricSearch = { q: '', equipmentId: '', statDate: [] }; metric.reset()"
            />
          </div>
          <div class="pane-toolbar">
            <el-button
              v-permission="'asset:equipment:metric:create'"
              type="primary"
              @click="openMetricDialog()"
            >
              {{ t('asset.equipment.metric.register') }}
            </el-button>
          </div>
          <div class="pane-table">
            <ListTable
              :columns="metricColumns"
              :data="metric.items.value as unknown as Record<string, unknown>[]"
              :loading="metric.loading.value"
              :total="metric.total.value"
              :page="Number(metric.query.page)"
              :size="Number(metric.query.size)"
              row-key="id"
              @update:page="metric.setPage"
              @update:size="metric.setSize"
              @sort-change="metric.onSortChange"
            >
              <template #shift="{ row }">{{ row.shiftText || '-' }}</template>
              <template #source="{ row }">{{ row.sourceText || '-' }}</template>
            </ListTable>
          </div>
        </div>
      </el-tab-pane>

      <!-- 设备预警 -->
      <el-tab-pane :label="t('asset.equipment.tabs.alert')" name="alert">
        <div class="tab-pane">
          <div class="pane-toolbar pane-toolbar--tabs">
            <StatusTabs
              :tabs="alertTabs"
              :model-value="String(alert.query.status)"
              @update:model-value="alert.setStatus($event)"
            />
          </div>
          <div class="pane-search">
            <SearchBar
              v-model="alertSearch"
              :fields="alertFields"
              @search="alert.search()"
              @reset="alertSearch = { q: '', equipmentId: '', ruleType: '', level: '' }; alert.reset()"
            />
          </div>
          <div class="pane-toolbar">
            <el-button v-permission="'asset:equipment:alert:create'" :loading="scanning" @click="scanAlerts">
              {{ t('asset.equipment.alert.scan') }}
            </el-button>
            <el-button v-permission="'asset:equipment:alert:create'" @click="openAlertDialog">
              {{ t('asset.equipment.alert.register') }}
            </el-button>
            <span class="pane-tip">{{ t('asset.equipment.alert.scanTip') }}</span>
          </div>
          <div class="pane-table">
            <ListTable
              :columns="alertColumns"
              :data="alert.items.value as unknown as Record<string, unknown>[]"
              :loading="alert.loading.value"
              :total="alert.total.value"
              :page="Number(alert.query.page)"
              :size="Number(alert.query.size)"
              row-key="id"
              @update:page="alert.setPage"
              @update:size="alert.setSize"
              @sort-change="alert.onSortChange"
            >
              <template #ruleType="{ row }">{{ row.ruleTypeText || '-' }}</template>
              <template #level="{ row }">
                <StatusTag :status="String(row.level)" i18n-prefix="asset.equipment.alert.levelOptions" />
              </template>
              <template #status="{ row }">
                <StatusTag :status="String(row.status)" i18n-prefix="asset.equipment.alert.statusOptions" />
              </template>
              <template #extraColumns>
                <el-table-column
                  :label="t('common.action.operate')"
                  width="120"
                  fixed="right"
                  align="center"
                  header-align="center"
                >
                  <template #default="{ row }">
                    <ActionBar
                      :actions="alertActions(row as unknown as EquipmentAlert)"
                      @select="(k) => onAlertAction(k, row as unknown as EquipmentAlert)"
                    />
                  </template>
                </el-table-column>
              </template>
            </ListTable>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>

  <!-- 设备表单 -->
  <el-dialog
    v-model="formVisible"
    :title="editingId ? t('asset.equipment.edit') : t('asset.equipment.create')"
    width="var(--bs-layout-dialog-lg)"
    append-to-body
  >
    <el-form ref="formRef" :model="form" label-width="120px">
      <el-row :gutter="12">
        <el-col :span="8">
          <el-form-item
            :label="t('asset.equipment.equipmentNo')"
            prop="equipmentNo"
            :rules="[{ required: true, message: t('common.form.required') }]"
          >
            <el-input v-model="form.equipmentNo" :maxlength="32" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item
            :label="t('asset.equipment.name')"
            prop="name"
            :rules="[{ required: true, message: t('common.form.required') }]"
          >
            <el-input v-model="form.name" :maxlength="128" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.equipment.category')">
            <el-select v-model="form.category" style="width: 100%">
              <el-option v-for="o in categoryOptions()" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.equipment.model')">
            <el-input v-model="form.model" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.equipment.spec')">
            <el-input v-model="form.spec" :maxlength="255" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.equipment.workshop')">
            <el-input v-model="form.workshop" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.equipment.location')">
            <el-input v-model="form.location" :maxlength="128" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.equipment.vendor')">
            <el-select
              v-model="form.vendorId"
              filterable
              remote
              clearable
              :remote-method="(q: string) => suppliers.search(q)"
              :loading="suppliers.loading.value"
              style="width: 100%"
            >
              <el-option
                v-for="o in suppliers.opts.value"
                :key="o.value"
                :label="o.label"
                :value="o.value"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.equipment.dept')">
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
          <el-form-item :label="t('asset.equipment.owner')">
            <el-input v-model="form.ownerName" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.equipment.purchaseDate')">
            <el-date-picker
              v-model="form.purchaseDate"
              type="date"
              value-format="YYYY-MM-DD"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.equipment.commissionDate')">
            <el-date-picker
              v-model="form.commissionDate"
              type="date"
              value-format="YYYY-MM-DD"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.equipment.originalValue')">
            <el-input-number
              v-model="form.originalValue"
              :min="0"
              :precision="2"
              :controls="false"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.equipment.status')">
            <el-select v-model="form.status" style="width: 100%">
              <el-option v-for="o in statusOptions()" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.equipment.maintainCycleDays')">
            <el-input-number
              v-model="form.maintainCycleDays"
              :min="0"
              :max="3650"
              :controls="false"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.equipment.lastMaintainDate')">
            <el-date-picker
              v-model="form.lastMaintainDate"
              type="date"
              value-format="YYYY-MM-DD"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.equipment.nextMaintainDate')">
            <el-date-picker
              v-model="form.nextMaintainDate"
              type="date"
              value-format="YYYY-MM-DD"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('asset.equipment.runHours')">
            <el-input-number
              v-model="form.runHours"
              :min="0"
              :precision="2"
              :controls="false"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="t('asset.equipment.remark')">
        <el-input v-model="form.remark" type="textarea" :rows="2" :maxlength="500" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="formVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="formSaving" @click="saveForm">
        {{ t('common.action.save') }}
      </el-button>
    </template>
  </el-dialog>

  <!-- 能耗登记 -->
  <el-dialog
    v-model="metricVisible"
    :title="t('asset.equipment.metric.register')"
    width="var(--bs-layout-dialog-sm)"
    append-to-body
  >
    <el-alert :title="t('asset.equipment.metric.registerTip')" type="info" :closable="false" />
    <el-form :model="metricForm" label-width="110px" style="margin-top: var(--bs-space-3)">
      <el-form-item :label="t('asset.equipment.name')" required>
        <el-select v-model="metricForm.equipmentId" filterable style="width: 100%">
          <el-option
            v-for="o in equipmentOptions"
            :key="o.value"
            :label="o.label"
            :value="o.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('asset.equipment.metric.statDate')">
        <el-date-picker
          v-model="metricForm.statDate"
          type="date"
          value-format="YYYY-MM-DD"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item :label="t('asset.equipment.metric.shift')">
        <el-select v-model="metricForm.shift" style="width: 100%">
          <el-option v-for="o in shiftOptions()" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('asset.equipment.metric.runHours')">
        <el-input-number
          v-model="metricForm.runHours"
          :min="0"
          :precision="2"
          :controls="false"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item :label="t('asset.equipment.metric.downtimeHours')">
        <el-input-number
          v-model="metricForm.downtimeHours"
          :min="0"
          :precision="2"
          :controls="false"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item :label="t('asset.equipment.metric.energy')">
        <el-input-number
          v-model="metricForm.energy"
          :min="0"
          :precision="2"
          :controls="false"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item :label="t('asset.equipment.metric.outputQty')">
        <el-input-number
          v-model="metricForm.outputQty"
          :min="0"
          :precision="2"
          :controls="false"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item :label="t('asset.equipment.metric.source')">
        <el-select v-model="metricForm.source" style="width: 100%">
          <el-option v-for="o in sourceOptions()" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('common.form.remark')">
        <el-input v-model="metricForm.remark" type="textarea" :rows="2" :maxlength="255" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="metricVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="metricSaving" @click="submitMetric">
        {{ t('common.action.confirm') }}
      </el-button>
    </template>
  </el-dialog>

  <!-- 预警登记 -->
  <el-dialog
    v-model="alertVisible"
    :title="t('asset.equipment.alert.registerTitle')"
    width="var(--bs-layout-dialog-sm)"
    append-to-body
  >
    <el-form :model="alertForm" label-width="110px">
      <el-form-item :label="t('asset.equipment.name')" required>
        <el-select v-model="alertForm.equipmentId" filterable style="width: 100%">
          <el-option
            v-for="o in equipmentOptions"
            :key="o.value"
            :label="o.label"
            :value="o.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('asset.equipment.alert.ruleType')">
        <el-select v-model="alertForm.ruleType" style="width: 100%">
          <el-option v-for="o in ruleOptions()" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('asset.equipment.alert.level')">
        <el-select v-model="alertForm.level" style="width: 100%">
          <el-option v-for="o in levelOptions()" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('asset.equipment.alert.title')">
        <el-input v-model="alertForm.title" :maxlength="128" />
      </el-form-item>
      <el-form-item :label="t('asset.equipment.alert.content')">
        <el-input v-model="alertForm.content" type="textarea" :rows="3" :maxlength="500" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="alertVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="alertSaving" @click="submitAlert">
        {{ t('common.action.confirm') }}
      </el-button>
    </template>
  </el-dialog>

  <!-- 预警处理 -->
  <el-dialog
    v-model="handleVisible"
    :title="t('asset.equipment.alert.handleTitle')"
    width="var(--bs-layout-dialog-sm)"
    append-to-body
  >
    <el-form :model="handleForm" label-width="110px">
      <el-form-item :label="t('asset.equipment.name')">
        {{ handleRow?.equipmentName || '-' }}
      </el-form-item>
      <el-form-item :label="t('asset.equipment.alert.ruleType')">
        {{ handleRow?.ruleTypeText || '-' }}
      </el-form-item>
      <el-form-item :label="t('asset.equipment.alert.status')">
        <el-radio-group v-model="handleForm.status">
          <el-radio v-for="o in handleStatusOptions()" :key="o.value" :value="o.value">
            {{ o.label }}
          </el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item :label="t('asset.equipment.alert.handleResult')">
        <el-input
          v-model="handleForm.handleResult"
          type="textarea"
          :rows="3"
          :maxlength="500"
          :placeholder="t('asset.equipment.alert.handleResultPlaceholder')"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="handleVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="handleSaving" @click="submitHandle">
        {{ t('common.action.confirm') }}
      </el-button>
    </template>
  </el-dialog>

  <!-- 设备详情 -->
  <el-drawer v-model="detailVisible" size="var(--bs-layout-drawer-lg)">
    <template #header>
      <div class="drawer-header">
        <span class="drawer-title">{{ detail?.equipmentNo || t('asset.equipment.detailTitle') }}</span>
        <StatusTag
          v-if="detail"
          :status="detail.status"
          i18n-prefix="asset.equipment.statusOptions"
        />
      </div>
    </template>
    <div v-loading="detailLoading" class="drawer-body">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="t('asset.equipment.name')">{{ detail.name }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.equipment.category')">
            {{ detail.categoryText || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('asset.equipment.model')">{{ detail.model || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.equipment.spec')">{{ detail.spec || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.equipment.workshop')">{{ detail.workshop || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.equipment.location')">{{ detail.location || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.equipment.vendor')">{{ detail.vendorName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.equipment.dept')">{{ detail.deptName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.equipment.owner')">{{ detail.ownerName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.equipment.purchaseDate')">
            {{ detail.purchaseDate || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('asset.equipment.commissionDate')">
            {{ detail.commissionDate || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('asset.equipment.originalValue')">
            {{ detail.originalValue ?? '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('asset.equipment.runHours')">{{ detail.runHours ?? '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.equipment.maintainCycleDays')">
            {{ detail.maintainCycleDays }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('asset.equipment.lastMaintainDate')">
            {{ detail.lastMaintainDate || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('asset.equipment.nextMaintainDate')">
            {{ detail.nextMaintainDate || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('common.form.remark')" :span="2">
            {{ detail.remark || '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <div class="section-title">{{ t('asset.equipment.detail.metrics') }}</div>
        <el-table :data="detail.metrics ?? []" border stripe size="small">
          <el-table-column
            :label="t('asset.equipment.metric.statDate')"
            prop="statDate"
            width="110"
          />
          <el-table-column :label="t('asset.equipment.metric.shift')" prop="shiftText" width="90" />
          <el-table-column
            :label="t('asset.equipment.metric.runHours')"
            prop="runHours"
            width="100"
            align="right"
          />
          <el-table-column
            :label="t('asset.equipment.metric.energy')"
            prop="energy"
            width="110"
            align="right"
          />
          <el-table-column
            :label="t('asset.equipment.metric.outputQty')"
            prop="outputQty"
            width="90"
            align="right"
          />
        </el-table>

        <div class="section-title">{{ t('asset.equipment.detail.alerts') }}</div>
        <el-table :data="detail.alerts ?? []" border stripe size="small">
          <el-table-column
            :label="t('asset.equipment.alert.alertNo')"
            prop="alertNo"
            width="140"
          />
          <el-table-column :label="t('asset.equipment.alert.ruleType')" prop="ruleTypeText" width="120" />
          <el-table-column :label="t('asset.equipment.alert.level')" prop="levelText" width="90" />
          <el-table-column :label="t('asset.equipment.alert.status')" prop="statusText" width="90" />
          <el-table-column :label="t('asset.equipment.alert.triggeredAt')" prop="triggeredAt" min-width="150" />
        </el-table>
      </template>
    </div>
  </el-drawer>
</template>

<style scoped>
.stat-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--bs-space-2);
  flex-shrink: 0;
}

.stat-card {
  padding: var(--bs-space-3);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
}

.stat-label {
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-secondary);
}

.stat-value {
  margin-top: var(--bs-space-1);
  font-size: var(--bs-typography-font-size-xl);
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.stat-card--ok .stat-value {
  color: var(--bs-color-semantic-success);
}

.stat-card--warn .stat-value {
  color: var(--bs-color-semantic-warning);
}

.stat-card--danger .stat-value {
  color: var(--bs-color-semantic-danger);
}

.equipment-tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.equipment-tabs :deep(.el-tabs__header) {
  flex-shrink: 0;
  margin-bottom: var(--bs-space-2);
}

.equipment-tabs :deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.equipment-tabs :deep(.el-tab-pane) {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.tab-pane {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.pane-search {
  flex-shrink: 0;
  padding: var(--bs-space-2) var(--bs-layout-content-padding);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
}

.pane-toolbar {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  flex-shrink: 0;
}

.pane-toolbar--tabs {
  padding: 0 var(--bs-layout-content-padding);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
}

.pane-toolbar--tabs :deep(.status-tabs) {
  border-bottom: none;
}

.pane-tip {
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-muted);
}

.pane-table {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

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
