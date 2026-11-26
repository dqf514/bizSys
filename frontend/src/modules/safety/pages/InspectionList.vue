<script setup lang="ts">
/** 安全巡检管理（B8 / CSV 24）：巡检计划 → 巡检记录（异常自动生成隐患）→ 隐患整改闭环。 */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import PageHeader from '@/components/common/PageHeader.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import { useListPage } from '@/composables/useListPage'
import type { ListQuery } from '@/api/types'
import {
  closeSafetyInspection,
  createSafetyHazard,
  createSafetyInspection,
  createSafetyPlan,
  deleteSafetyInspection,
  deleteSafetyPlan,
  getSafetyBoard,
  listSafetyHazards,
  listSafetyInspections,
  listSafetyPlans,
  rectifySafetyHazard,
  safetyHazardCounts,
  safetyInspectionCounts,
  safetyPlanCounts,
  submitSafetyInspection,
  updateSafetyInspection,
  updateSafetyPlan,
  verifySafetyHazard,
  type SafetyBoard,
  type SafetyHazard,
  type SafetyInspection,
  type SafetyInspectionItem,
  type SafetyPlan,
} from '@/api/safety'

defineOptions({ name: 'InspectionList' })

const { t } = useI18n()

type TagType = 'primary' | 'success' | 'info' | 'warning' | 'danger'

/* ---------------- 统计看板 ---------------- */
const board = ref<SafetyBoard | null>(null)

async function loadBoard() {
  try {
    board.value = await getSafetyBoard()
  } catch {
    /* http 层已提示 */
  }
}

/* ---------------- 枚举选项 ---------------- */
const planTypeOptions = computed(() => [
  { label: t('safety.plan.typeDaily'), value: 'daily' },
  { label: t('safety.plan.typeWeekly'), value: 'weekly' },
  { label: t('safety.plan.typeMonthly'), value: 'monthly' },
  { label: t('safety.plan.typeSpecial'), value: 'special' },
])
const planStatusOptions = computed(() => [
  { label: t('safety.plan.statusActive'), value: 'active' },
  { label: t('safety.plan.statusPaused'), value: 'paused' },
  { label: t('safety.plan.statusFinished'), value: 'finished' },
])
const resultOptions = computed(() => [
  { label: t('safety.inspection.resultNormal'), value: 'normal' },
  { label: t('safety.inspection.resultAbnormal'), value: 'abnormal' },
])
const levelOptions = computed(() => [
  { label: t('safety.hazard.levelLow'), value: 'low' },
  { label: t('safety.hazard.levelMedium'), value: 'medium' },
  { label: t('safety.hazard.levelHigh'), value: 'high' },
  { label: t('safety.hazard.levelCritical'), value: 'critical' },
])
const hazardSourceOptions = computed(() => [
  { label: t('safety.hazard.sourceInspection'), value: 'inspection' },
  { label: t('safety.hazard.sourceManual'), value: 'manual' },
])

/* ---------------- 状态 / 等级：标签色与文案 ---------------- */
const PLAN_STATUS_TAG: Record<string, TagType> = {
  active: 'success',
  paused: 'warning',
  finished: 'info',
}
const RESULT_TAG: Record<string, TagType> = { normal: 'success', abnormal: 'danger' }
const LEVEL_TAG: Record<string, TagType> = {
  low: 'info',
  medium: 'warning',
  high: 'danger',
  critical: 'danger',
}
const HAZARD_STATUS_TAG: Record<string, TagType> = {
  open: 'danger',
  rectifying: 'warning',
  verified: 'primary',
  closed: 'success',
}
const INSPECTION_STATUS_TAG: Record<string, TagType> = {
  draft: 'info',
  submitted: 'primary',
  closed: 'success',
}

function planStatusTag(v: unknown): TagType {
  return PLAN_STATUS_TAG[String(v)] ?? 'info'
}
function resultTag(v: unknown): TagType {
  return RESULT_TAG[String(v)] ?? 'info'
}
function levelTag(v: unknown): TagType {
  return LEVEL_TAG[String(v)] ?? 'info'
}
function hazardStatusTag(v: unknown): TagType {
  return HAZARD_STATUS_TAG[String(v)] ?? 'info'
}
function inspectionStatusTag(v: unknown): TagType {
  return INSPECTION_STATUS_TAG[String(v)] ?? 'info'
}

function planStatusLabel(v: unknown): string {
  const key = String(v)
  if (key === 'active') return t('safety.plan.statusActive')
  if (key === 'paused') return t('safety.plan.statusPaused')
  if (key === 'finished') return t('safety.plan.statusFinished')
  return key
}
function resultLabel(v: unknown): string {
  return String(v) === 'abnormal'
    ? t('safety.inspection.resultAbnormal')
    : t('safety.inspection.resultNormal')
}
function inspectionStatusLabel(v: unknown): string {
  const key = String(v)
  if (key === 'draft') return t('safety.inspection.statusDraft')
  if (key === 'submitted') return t('safety.inspection.statusSubmitted')
  if (key === 'closed') return t('safety.inspection.statusClosed')
  return key
}
function levelLabel(v: unknown): string {
  const key = String(v)
  if (key === 'low') return t('safety.hazard.levelLow')
  if (key === 'medium') return t('safety.hazard.levelMedium')
  if (key === 'high') return t('safety.hazard.levelHigh')
  if (key === 'critical') return t('safety.hazard.levelCritical')
  return key
}
function hazardStatusLabel(v: unknown): string {
  const key = String(v)
  if (key === 'open') return t('safety.hazard.statusOpen')
  if (key === 'rectifying') return t('safety.hazard.statusRectifying')
  if (key === 'verified') return t('safety.hazard.statusVerified')
  if (key === 'closed') return t('safety.hazard.statusClosed')
  return key
}

/* ---------------- 巡检计划 ---------------- */
const planSearch = ref<Record<string, unknown>>({ q: '', plan_type: '' })
const planFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'safety.plan.keyword',
    placeholderKey: 'safety.plan.searchPlaceholder',
    width: 260,
  },
  {
    key: 'plan_type',
    labelKey: 'safety.plan.type',
    type: 'select',
    options: planTypeOptions.value,
    width: 160,
  },
])
const planTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'active', labelKey: 'safety.plan.statusActive', count: 0 },
  { value: 'paused', labelKey: 'safety.plan.statusPaused', count: 0 },
  { value: 'finished', labelKey: 'safety.plan.statusFinished', count: 0 },
])

async function loadPlanCounts() {
  try {
    const counts = (await safetyPlanCounts()) ?? {}
    for (const tab of planTabs.value) {
      tab.count = counts[tab.value] ?? 0
    }
  } catch {
    /* 计数失败不影响列表 */
  }
}

const {
  items: planItems,
  total: planTotal,
  loading: planLoading,
  query: planQuery,
  load: loadPlans,
  search: searchPlans,
  reset: resetPlans,
  setStatus: setPlanStatus,
  setPage: setPlanPage,
  setSize: setPlanSize,
  onSortChange: onPlanSort,
} = useListPage<SafetyPlan>({
  fetch: async (params) => {
    const merged: ListQuery = { ...(params as ListQuery) }
    merged.q = (planSearch.value.q as string) || undefined
    merged.filters = {
      ...((merged.filters as Record<string, unknown>) || {}),
      plan_type: (planSearch.value.plan_type as string) || undefined,
    }
    const data = await listSafetyPlans(merged)
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  defaultStatus: 'all',
  onLoaded: () => void loadPlanCounts(),
})

const planColumns: ListColumn[] = [
  { prop: 'planNo', labelKey: 'safety.plan.no', width: 165, fixed: 'left' },
  { prop: 'name', labelKey: 'safety.plan.name', minWidth: 170 },
  { prop: 'planTypeText', labelKey: 'safety.plan.type', width: 100 },
  { prop: 'targetArea', labelKey: 'safety.plan.area', minWidth: 140 },
  { prop: 'cycleDays', labelKey: 'safety.plan.cycle', width: 110 },
  { prop: 'nextDate', labelKey: 'safety.plan.nextDate', width: 120 },
  { prop: 'ownerName', labelKey: 'safety.plan.owner', width: 110 },
  { prop: 'status', labelKey: 'safety.plan.status', width: 100 },
]

/* ---------------- 巡检记录 ---------------- */
const inspectionSearch = ref<Record<string, unknown>>({ q: '', result: '' })
const inspectionFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'safety.inspection.keyword',
    placeholderKey: 'safety.inspection.searchPlaceholder',
    width: 260,
  },
  {
    key: 'result',
    labelKey: 'safety.inspection.result',
    type: 'select',
    options: resultOptions.value,
    width: 150,
  },
])
const inspectionTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'draft', labelKey: 'safety.inspection.statusDraft', count: 0 },
  { value: 'submitted', labelKey: 'safety.inspection.statusSubmitted', count: 0 },
  { value: 'closed', labelKey: 'safety.inspection.statusClosed', count: 0 },
])

async function loadInspectionCounts() {
  try {
    const counts = (await safetyInspectionCounts()) ?? {}
    for (const tab of inspectionTabs.value) {
      tab.count = counts[tab.value] ?? 0
    }
  } catch {
    /* 计数失败不影响列表 */
  }
}

const {
  items: inspectionItems,
  total: inspectionTotal,
  loading: inspectionLoading,
  query: inspectionQuery,
  load: loadInspections,
  search: searchInspections,
  reset: resetInspections,
  setStatus: setInspectionStatus,
  setPage: setInspectionPage,
  setSize: setInspectionSize,
  onSortChange: onInspectionSort,
} = useListPage<SafetyInspection>({
  fetch: async (params) => {
    const merged: ListQuery = { ...(params as ListQuery) }
    merged.q = (inspectionSearch.value.q as string) || undefined
    merged.filters = {
      ...((merged.filters as Record<string, unknown>) || {}),
      result: (inspectionSearch.value.result as string) || undefined,
    }
    const data = await listSafetyInspections(merged)
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  defaultStatus: 'all',
  autoLoad: false,
  onLoaded: () => void loadInspectionCounts(),
})

const inspectionColumns: ListColumn[] = [
  { prop: 'recordNo', labelKey: 'safety.inspection.no', width: 165, fixed: 'left' },
  { prop: 'planName', labelKey: 'safety.inspection.plan', minWidth: 160 },
  { prop: 'area', labelKey: 'safety.inspection.area', minWidth: 130 },
  { prop: 'inspectDate', labelKey: 'safety.inspection.date', width: 120 },
  { prop: 'inspectorName', labelKey: 'safety.inspection.inspector', width: 110 },
  { prop: 'result', labelKey: 'safety.inspection.result', width: 100 },
  { prop: 'abnormalCount', labelKey: 'safety.inspection.abnormalCount', width: 110 },
  { prop: 'status', labelKey: 'safety.inspection.status', width: 100 },
]

/* ---------------- 隐患 ---------------- */
const hazardSearch = ref<Record<string, unknown>>({ q: '', level: '' })
const hazardFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'safety.hazard.keyword',
    placeholderKey: 'safety.hazard.searchPlaceholder',
    width: 260,
  },
  {
    key: 'level',
    labelKey: 'safety.hazard.level',
    type: 'select',
    options: levelOptions.value,
    width: 150,
  },
])
const hazardTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'open', labelKey: 'safety.hazard.statusOpen', count: 0 },
  { value: 'rectifying', labelKey: 'safety.hazard.statusRectifying', count: 0 },
  { value: 'verified', labelKey: 'safety.hazard.statusVerified', count: 0 },
  { value: 'closed', labelKey: 'safety.hazard.statusClosed', count: 0 },
])

async function loadHazardCounts() {
  try {
    const counts = (await safetyHazardCounts()) ?? {}
    for (const tab of hazardTabs.value) {
      tab.count = counts[tab.value] ?? 0
    }
  } catch {
    /* 计数失败不影响列表 */
  }
}

const {
  items: hazardItems,
  total: hazardTotal,
  loading: hazardLoading,
  query: hazardQuery,
  load: loadHazards,
  search: searchHazards,
  reset: resetHazards,
  setStatus: setHazardStatus,
  setPage: setHazardPage,
  setSize: setHazardSize,
  onSortChange: onHazardSort,
} = useListPage<SafetyHazard>({
  fetch: async (params) => {
    const merged: ListQuery = { ...(params as ListQuery) }
    merged.q = (hazardSearch.value.q as string) || undefined
    merged.filters = {
      ...((merged.filters as Record<string, unknown>) || {}),
      level: (hazardSearch.value.level as string) || undefined,
    }
    const data = await listSafetyHazards(merged)
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  defaultStatus: 'all',
  autoLoad: false,
  onLoaded: () => void loadHazardCounts(),
})

const hazardColumns: ListColumn[] = [
  { prop: 'hazardNo', labelKey: 'safety.hazard.no', width: 165, fixed: 'left' },
  { prop: 'description', labelKey: 'safety.hazard.description', minWidth: 220 },
  { prop: 'level', labelKey: 'safety.hazard.level', width: 100 },
  { prop: 'responsibleName', labelKey: 'safety.hazard.responsible', width: 110 },
  { prop: 'deadline', labelKey: 'safety.hazard.deadline', width: 140 },
  { prop: 'status', labelKey: 'safety.hazard.status', width: 110 },
]

/* ---------------- 页签懒加载 ---------------- */
const activeTab = ref('plan')
const loadedTabs = ref<Record<string, boolean>>({ plan: true, inspection: false, hazard: false })

watch(activeTab, (v) => {
  if (loadedTabs.value[v]) return
  loadedTabs.value[v] = true
  if (v === 'inspection') {
    void loadInspections()
    void loadInspectionCounts()
  } else if (v === 'hazard') {
    void loadHazards()
    void loadHazardCounts()
  }
})

onMounted(() => {
  void loadBoard()
  void loadPlanCounts()
})

/* ---------------- 计划：新增 / 编辑 ---------------- */
const planVisible = ref(false)
const planMode = ref<'create' | 'edit'>('create')
const planTarget = ref<SafetyPlan | null>(null)
const planForm = ref<Record<string, any>>({
  plan_no: '',
  name: '',
  plan_type: 'daily',
  target_area: '',
  check_items: '',
  cycle_days: 1,
  next_date: '',
  owner_name: '',
  dept_name: '',
  status: 'active',
  remark: '',
})

function openPlanCreate() {
  planMode.value = 'create'
  planTarget.value = null
  planForm.value = {
    plan_no: '',
    name: '',
    plan_type: 'daily',
    target_area: '',
    check_items: '',
    cycle_days: 1,
    next_date: '',
    owner_name: '',
    dept_name: '',
    status: 'active',
    remark: '',
  }
  planVisible.value = true
}

function openPlanEdit(row: SafetyPlan) {
  planMode.value = 'edit'
  planTarget.value = row
  planForm.value = {
    plan_no: row.planNo,
    name: row.name,
    plan_type: row.planType,
    target_area: row.targetArea,
    check_items: (row.checkItems || []).join('\n'),
    cycle_days: row.cycleDays,
    next_date: row.nextDate,
    owner_name: row.ownerName,
    dept_name: row.deptName,
    status: row.status,
    remark: row.remark,
  }
  planVisible.value = true
}

async function submitPlan() {
  const f = planForm.value
  if (!String(f.name || '').trim()) {
    ElMessage.warning(t('common.form.required'))
    return
  }
  const payload = {
    planNo: String(f.plan_no || '').trim(),
    name: String(f.name).trim(),
    planType: f.plan_type,
    targetArea: String(f.target_area || ''),
    checkItems: String(f.check_items || '')
      .split('\n')
      .map((x: string) => x.trim())
      .filter(Boolean),
    cycleDays: Number(f.cycle_days) || 1,
    nextDate: f.next_date || null,
    ownerName: String(f.owner_name || ''),
    deptName: String(f.dept_name || ''),
    status: f.status,
    remark: String(f.remark || ''),
  }
  try {
    if (planMode.value === 'create') {
      await createSafetyPlan(payload)
      ElMessage.success(t('common.message.createSuccess'))
    } else if (planTarget.value) {
      await updateSafetyPlan(planTarget.value.id, payload)
      ElMessage.success(t('common.message.updateSuccess'))
    }
    planVisible.value = false
    void loadPlans()
    void loadBoard()
  } catch {
    /* http 层已提示 */
  }
}

async function doDeletePlan(row: SafetyPlan) {
  try {
    await deleteSafetyPlan(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    void loadPlans()
  } catch {
    /* http 层已提示 */
  }
}

function planActions(_row: SafetyPlan): ActionItem[] {
  return [
    { key: 'edit', tip: 'common.action.edit', perm: 'safety:inspection:edit' },
    {
      key: 'delete',
      tip: 'common.action.delete',
      perm: 'safety:inspection:delete',
      confirm: 'safety.plan.deleteConfirm',
    },
  ]
}

/* ---------------- 巡检记录：登记 / 编辑 / 提交 ---------------- */
const planOptions = ref<SafetyPlan[]>([])

async function loadPlanOptions() {
  try {
    const data = await listSafetyPlans({ page: 1, size: 200, status: 'all' })
    planOptions.value = data.items ?? []
  } catch {
    /* 计划下拉拉取失败不阻断登记 */
  }
}

const inspectionVisible = ref(false)
const inspectionMode = ref<'create' | 'edit' | 'submit'>('create')
/** 已提交 / 已闭环的记录不可改，仅查看 */
const inspectionReadonly = ref(false)
const inspectionTarget = ref<SafetyInspection | null>(null)
const inspectionForm = ref<Record<string, any>>({
  record_no: '',
  plan_id: null as number | null,
  area: '',
  inspect_date: '',
  inspector_name: '',
  summary: '',
  remark: '',
  items: [] as SafetyInspectionItem[],
})

function applyPlanItems(planId: number | null) {
  const plan = planOptions.value.find((p) => p.id === planId)
  inspectionForm.value.area = plan?.targetArea || ''
  inspectionForm.value.items = (plan?.checkItems || []).map((item) => ({
    item,
    result: 'normal',
    note: '',
  }))
}

function openInspectionCreate() {
  inspectionMode.value = 'create'
  inspectionReadonly.value = false
  inspectionTarget.value = null
  inspectionForm.value = {
    record_no: '',
    plan_id: null,
    area: '',
    inspect_date: '',
    inspector_name: '',
    summary: '',
    remark: '',
    items: [],
  }
  inspectionVisible.value = true
  void loadPlanOptions()
}

function openInspectionEdit(row: SafetyInspection) {
  inspectionMode.value = 'edit'
  inspectionReadonly.value = row.status !== 'draft'
  inspectionTarget.value = row
  inspectionForm.value = {
    record_no: row.recordNo,
    plan_id: row.planId,
    area: row.area,
    inspect_date: row.inspectDate,
    inspector_name: row.inspectorName,
    summary: row.summary,
    remark: row.remark,
    items: (row.items || []).map((it) => ({ ...it })),
  }
  inspectionVisible.value = true
  void loadPlanOptions()
}

function openInspectionSubmit(row: SafetyInspection) {
  inspectionMode.value = 'submit'
  inspectionReadonly.value = false
  inspectionTarget.value = row
  inspectionForm.value = {
    record_no: row.recordNo,
    plan_id: row.planId,
    area: row.area,
    inspect_date: row.inspectDate,
    inspector_name: row.inspectorName,
    summary: row.summary,
    remark: row.remark,
    items: (row.items || []).map((it) => ({ ...it })),
  }
  inspectionVisible.value = true
}

function inspectionPayload() {
  const f = inspectionForm.value
  return {
    recordNo: String(f.record_no || '').trim(),
    planId: f.plan_id,
    planName:
      planOptions.value.find((p) => p.id === f.plan_id)?.name || inspectionTarget.value?.planName || '',
    area: String(f.area || ''),
    inspectDate: f.inspect_date || null,
    inspectorName: String(f.inspector_name || ''),
    itemsJson: (f.items || []) as SafetyInspectionItem[],
    summary: String(f.summary || ''),
    remark: String(f.remark || ''),
  }
}

async function saveInspection(submit: boolean) {
  const f = inspectionForm.value
  if (submit && !(f.items || []).length) {
    ElMessage.warning(t('safety.inspection.noItems'))
    return
  }
  try {
    if (inspectionMode.value === 'create') {
      const created = await createSafetyInspection({
        ...inspectionPayload(),
        status: 'draft',
      })
      if (submit) await submitSafetyInspection(created.id)
      ElMessage.success(t('common.message.createSuccess'))
    } else if (inspectionTarget.value) {
      await updateSafetyInspection(inspectionTarget.value.id, inspectionPayload())
      if (submit) await submitSafetyInspection(inspectionTarget.value.id)
      ElMessage.success(t('common.message.updateSuccess'))
    }
    inspectionVisible.value = false
    void loadInspections()
    void loadBoard()
  } catch {
    /* http 层已提示 */
  }
}

async function doDeleteInspection(row: SafetyInspection) {
  try {
    await deleteSafetyInspection(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    void loadInspections()
  } catch {
    /* http 层已提示 */
  }
}

async function doCloseInspection(row: SafetyInspection) {
  try {
    await closeSafetyInspection(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    void loadInspections()
    void loadBoard()
  } catch {
    /* http 层已提示 */
  }
}

function inspectionActions(row: SafetyInspection): ActionItem[] {
  const acts: ActionItem[] = []
  if (row.status === 'draft') {
    acts.push({ key: 'edit', tip: 'common.action.edit', perm: 'safety:inspection:edit' })
    acts.push({
      key: 'submit',
      tip: 'safety.inspection.submitAction',
      perm: 'safety:inspection:submit',
    })
    acts.push({
      key: 'delete',
      tip: 'common.action.delete',
      perm: 'safety:inspection:delete',
      confirm: 'safety.inspection.deleteConfirm',
    })
  }
  if (row.status === 'submitted') {
    acts.push({
      key: 'close',
      tip: 'safety.inspection.closeAction',
      perm: 'safety:inspection:submit',
    })
  }
  return acts
}

/* ---------------- 隐患：上报 / 整改 / 验证 ---------------- */
const hazardVisible = ref(false)
const hazardForm = ref<Record<string, any>>({
  description: '',
  level: 'medium',
  source: 'manual',
  responsible_name: '',
  deadline: '',
  remark: '',
})

function openHazardCreate() {
  hazardForm.value = {
    description: '',
    level: 'medium',
    source: 'manual',
    responsible_name: '',
    deadline: '',
    remark: '',
  }
  hazardVisible.value = true
}

async function submitHazard() {
  const f = hazardForm.value
  if (!String(f.description || '').trim()) {
    ElMessage.warning(t('common.form.required'))
    return
  }
  try {
    await createSafetyHazard({
      description: String(f.description).trim(),
      level: f.level,
      source: f.source,
      responsibleName: String(f.responsible_name || ''),
      deadline: f.deadline || null,
      remark: String(f.remark || ''),
    })
    ElMessage.success(t('common.message.createSuccess'))
    hazardVisible.value = false
    void loadHazards()
    void loadBoard()
  } catch {
    /* http 层已提示 */
  }
}

const rectifyVisible = ref(false)
const rectifyTarget = ref<SafetyHazard | null>(null)
const rectifyForm = ref({ measure: '' })

function openRectify(row: SafetyHazard) {
  rectifyTarget.value = row
  rectifyForm.value = { measure: row.measure || '' }
  rectifyVisible.value = true
}

async function submitRectify() {
  const target = rectifyTarget.value
  if (!target) return
  if (!String(rectifyForm.value.measure || '').trim()) {
    ElMessage.warning(t('common.form.required'))
    return
  }
  try {
    await rectifySafetyHazard(target.id, { measure: rectifyForm.value.measure.trim() })
    ElMessage.success(t('common.message.submitSuccess'))
    rectifyVisible.value = false
    void loadHazards()
    void loadBoard()
  } catch {
    /* http 层已提示 */
  }
}

const verifyVisible = ref(false)
const verifyTarget = ref<SafetyHazard | null>(null)
const verifyForm = ref<{ verify_result: string; pass: boolean }>({ verify_result: '', pass: true })

function openVerify(row: SafetyHazard) {
  verifyTarget.value = row
  verifyForm.value = { verify_result: row.verifyResult || '', pass: true }
  verifyVisible.value = true
}

async function submitVerify() {
  const target = verifyTarget.value
  if (!target) return
  try {
    await verifySafetyHazard(target.id, {
      verifyResult: verifyForm.value.verify_result,
      pass: verifyForm.value.pass,
    })
    ElMessage.success(t('common.message.submitSuccess'))
    verifyVisible.value = false
    void loadHazards()
    void loadBoard()
  } catch {
    /* http 层已提示 */
  }
}

function hazardActions(row: SafetyHazard): ActionItem[] {
  const acts: ActionItem[] = []
  if (row.status === 'open' || row.status === 'rectifying') {
    acts.push({
      key: 'rectify',
      tip: 'safety.hazard.rectifyAction',
      perm: 'safety:hazard:rectify',
    })
  }
  if (row.status === 'verified') {
    acts.push({
      key: 'verify',
      tip: 'safety.hazard.verifyAction',
      perm: 'safety:hazard:verify',
    })
  }
  return acts
}

function onRowAction(key: string, row: Record<string, unknown>) {
  if (key === 'edit') {
    if (activeTab.value === 'plan') openPlanEdit(row as unknown as SafetyPlan)
    else openInspectionEdit(row as unknown as SafetyInspection)
  } else if (key === 'delete') {
    if (activeTab.value === 'plan') void doDeletePlan(row as unknown as SafetyPlan)
    else void doDeleteInspection(row as unknown as SafetyInspection)
  } else if (key === 'submit') {
    openInspectionSubmit(row as unknown as SafetyInspection)
  } else if (key === 'close') {
    void doCloseInspection(row as unknown as SafetyInspection)
  } else if (key === 'rectify') {
    openRectify(row as unknown as SafetyHazard)
  } else if (key === 'verify') {
    openVerify(row as unknown as SafetyHazard)
  }
}
</script>

<template>
  <div class="bs-page bs-page--fill safety-page">
    <PageHeader :title="t('safety.title')">
      <template #actions>
        <el-button v-permission="'safety:inspection:create'" type="primary" @click="openPlanCreate">
          {{ t('safety.plan.create') }}
        </el-button>
        <el-button v-permission="'safety:inspection:create'" @click="openInspectionCreate">
          {{ t('safety.inspection.create') }}
        </el-button>
        <el-button v-permission="'safety:hazard:create'" @click="openHazardCreate">
          {{ t('safety.hazard.create') }}
        </el-button>
      </template>
    </PageHeader>

    <div class="safety-stats">
      <div class="stat-card">
        <div class="stat-label">{{ t('safety.stats.planCount') }}</div>
        <div class="stat-value">{{ board?.planTotal ?? 0 }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ t('safety.stats.monthInspections') }}</div>
        <div class="stat-value">{{ board?.monthInspections ?? 0 }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ t('safety.stats.openHazards') }}</div>
        <div class="stat-value">{{ board?.openHazards ?? 0 }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ t('safety.stats.overdueHazards') }}</div>
        <div class="stat-value" :class="{ 'is-danger': (board?.overdueHazards ?? 0) > 0 }">
          {{ board?.overdueHazards ?? 0 }}
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ t('safety.stats.completion') }}</div>
        <div class="stat-value">{{ board?.completion?.rate ?? 0 }}%</div>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="safety-tabs">
      <!-- 巡检计划 -->
      <el-tab-pane :label="t('safety.plan.tab')" name="plan">
        <div class="pane">
          <SearchBar
            v-model="planSearch"
            :fields="planFields"
            @search="searchPlans()"
            @reset="planSearch = { q: '', plan_type: '' }; resetPlans()"
          />
          <StatusTabs
            :tabs="planTabs"
            :model-value="String(planQuery.status)"
            @update:model-value="setPlanStatus($event)"
          />
          <div class="pane-table">
            <ListTable
              :columns="planColumns"
              :data="planItems as unknown as Record<string, unknown>[]"
              :loading="planLoading"
              :total="planTotal"
              :page="Number(planQuery.page)"
              :size="Number(planQuery.size)"
              row-key="id"
              @update:page="setPlanPage"
              @update:size="setPlanSize"
              @sort-change="onPlanSort"
            >
              <template #planNo="{ row }">
                <el-button link type="primary" @click="openPlanEdit(row as unknown as SafetyPlan)">
                  {{ row.planNo }}
                </el-button>
              </template>
              <template #status="{ row }">
                <el-tag :type="planStatusTag(row.status)" size="small" effect="light" round>
                  {{ planStatusLabel(row.status) }}
                </el-tag>
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
                      :actions="planActions(row as unknown as SafetyPlan)"
                      @select="(k) => onRowAction(k, row as unknown as Record<string, unknown>)"
                    />
                  </template>
                </el-table-column>
              </template>
            </ListTable>
          </div>
        </div>
      </el-tab-pane>

      <!-- 巡检记录 -->
      <el-tab-pane :label="t('safety.inspection.tab')" name="inspection">
        <div class="pane">
          <SearchBar
            v-model="inspectionSearch"
            :fields="inspectionFields"
            @search="searchInspections()"
            @reset="inspectionSearch = { q: '', result: '' }; resetInspections()"
          />
          <StatusTabs
            :tabs="inspectionTabs"
            :model-value="String(inspectionQuery.status)"
            @update:model-value="setInspectionStatus($event)"
          />
          <div class="pane-table">
            <ListTable
              :columns="inspectionColumns"
              :data="inspectionItems as unknown as Record<string, unknown>[]"
              :loading="inspectionLoading"
              :total="inspectionTotal"
              :page="Number(inspectionQuery.page)"
              :size="Number(inspectionQuery.size)"
              row-key="id"
              @update:page="setInspectionPage"
              @update:size="setInspectionSize"
              @sort-change="onInspectionSort"
            >
              <template #recordNo="{ row }">
                <el-button
                  link
                  type="primary"
                  @click="openInspectionEdit(row as unknown as SafetyInspection)"
                >
                  {{ row.recordNo }}
                </el-button>
              </template>
              <template #result="{ row }">
                <el-tag :type="resultTag(row.result)" size="small" effect="light" round>
                  {{ resultLabel(row.result) }}
                </el-tag>
              </template>
              <template #status="{ row }">
                <el-tag :type="inspectionStatusTag(row.status)" size="small" effect="light" round>
                  {{ inspectionStatusLabel(row.status) }}
                </el-tag>
              </template>
              <template #extraColumns>
                <el-table-column
                  :label="t('common.action.operate')"
                  width="140"
                  fixed="right"
                  align="center"
                  header-align="center"
                >
                  <template #default="{ row }">
                    <ActionBar
                      :actions="inspectionActions(row as unknown as SafetyInspection)"
                      @select="(k) => onRowAction(k, row as unknown as Record<string, unknown>)"
                    />
                  </template>
                </el-table-column>
              </template>
            </ListTable>
          </div>
        </div>
      </el-tab-pane>

      <!-- 隐患整改 -->
      <el-tab-pane :label="t('safety.hazard.tab')" name="hazard">
        <div class="pane">
          <SearchBar
            v-model="hazardSearch"
            :fields="hazardFields"
            @search="searchHazards()"
            @reset="hazardSearch = { q: '', level: '' }; resetHazards()"
          />
          <StatusTabs
            :tabs="hazardTabs"
            :model-value="String(hazardQuery.status)"
            @update:model-value="setHazardStatus($event)"
          />
          <div class="pane-table">
            <ListTable
              :columns="hazardColumns"
              :data="hazardItems as unknown as Record<string, unknown>[]"
              :loading="hazardLoading"
              :total="hazardTotal"
              :page="Number(hazardQuery.page)"
              :size="Number(hazardQuery.size)"
              row-key="id"
              @update:page="setHazardPage"
              @update:size="setHazardSize"
              @sort-change="onHazardSort"
            >
              <template #level="{ row }">
                <el-tag :type="levelTag(row.level)" size="small" effect="light" round>
                  {{ levelLabel(row.level) }}
                </el-tag>
              </template>
              <template #deadline="{ row }">
                <span>
                  {{ row.deadline || '-' }}
                  <el-tag v-if="row.overdue" type="danger" size="small" effect="light" round>
                    {{ t('safety.hazard.overdue') }}
                  </el-tag>
                </span>
              </template>
              <template #status="{ row }">
                <el-tag :type="hazardStatusTag(row.status)" size="small" effect="light" round>
                  {{ hazardStatusLabel(row.status) }}
                </el-tag>
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
                      :actions="hazardActions(row as unknown as SafetyHazard)"
                      @select="(k) => onRowAction(k, row as unknown as Record<string, unknown>)"
                    />
                  </template>
                </el-table-column>
              </template>
            </ListTable>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 计划：新增 / 编辑 -->
    <el-dialog
      v-model="planVisible"
      width="var(--bs-layout-dialog-md)"
      :title="planMode === 'create' ? t('safety.plan.createTitle') : t('safety.plan.editTitle')"
    >
      <el-form label-position="top">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item :label="t('safety.plan.no')">
              <el-input v-model="planForm.plan_no" :maxlength="32" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('safety.plan.name')" required>
              <el-input
                v-model="planForm.name"
                :placeholder="t('safety.plan.placeholderName')"
                :maxlength="128"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item :label="t('safety.plan.type')">
              <el-select v-model="planForm.plan_type" style="width: 100%">
                <el-option v-for="o in planTypeOptions" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('safety.plan.status')">
              <el-select v-model="planForm.status" style="width: 100%">
                <el-option v-for="o in planStatusOptions" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item :label="t('safety.plan.area')">
              <el-input
                v-model="planForm.target_area"
                :placeholder="t('safety.plan.placeholderArea')"
                :maxlength="128"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('safety.plan.cycle')">
              <el-input-number v-model="planForm.cycle_days" :min="1" :max="365" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item :label="t('safety.plan.nextDate')">
              <el-date-picker
                v-model="planForm.next_date"
                type="date"
                value-format="YYYY-MM-DD"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('safety.plan.owner')">
              <el-input v-model="planForm.owner_name" :maxlength="64" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="t('safety.plan.dept')">
          <el-input v-model="planForm.dept_name" :maxlength="128" />
        </el-form-item>
        <el-form-item :label="t('safety.plan.items')">
          <el-input
            v-model="planForm.check_items"
            type="textarea"
            :rows="4"
            :placeholder="t('safety.plan.itemsTip')"
          />
        </el-form-item>
        <el-form-item :label="t('common.form.remark')">
          <el-input v-model="planForm.remark" type="textarea" :rows="2" :maxlength="500" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="planVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" @click="submitPlan">{{ t('common.action.confirm') }}</el-button>
      </template>
    </el-dialog>

    <!-- 巡检记录：登记 / 编辑 / 提交 -->
    <el-dialog
      v-model="inspectionVisible"
      width="var(--bs-layout-dialog-md)"
      :title="
        inspectionReadonly
          ? t('safety.inspection.detail')
          : inspectionMode === 'create'
            ? t('safety.inspection.createTitle')
            : inspectionMode === 'edit'
              ? t('safety.inspection.editTitle')
              : t('safety.inspection.submitAction')
      "
    >
      <el-alert
        v-if="inspectionMode === 'submit'"
        :title="t('safety.inspection.submitTip')"
        type="info"
        :closable="false"
        show-icon
      />
      <el-form label-position="top" :disabled="inspectionReadonly">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item :label="t('safety.inspection.plan')">
              <el-select
                v-model="inspectionForm.plan_id"
                style="width: 100%"
                clearable
                :placeholder="t('safety.inspection.noPlan')"
                @change="applyPlanItems"
              >
                <el-option v-for="p in planOptions" :key="p.id" :label="p.name" :value="p.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('safety.inspection.no')">
              <el-input v-model="inspectionForm.record_no" :maxlength="32" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item :label="t('safety.inspection.area')">
              <el-input
                v-model="inspectionForm.area"
                :placeholder="t('safety.inspection.placeholderArea')"
                :maxlength="128"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('safety.inspection.date')">
              <el-date-picker
                v-model="inspectionForm.inspect_date"
                type="date"
                value-format="YYYY-MM-DD"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="t('safety.inspection.inspector')">
          <el-input
            v-model="inspectionForm.inspector_name"
            :placeholder="t('safety.inspection.placeholderInspector')"
            :maxlength="64"
          />
        </el-form-item>

        <el-form-item :label="t('safety.inspection.items')">
          <div class="inspection-items">
            <div v-for="(it, idx) in inspectionForm.items" :key="idx" class="inspection-item">
              <span class="inspection-item-name">{{ it.item }}</span>
              <el-radio-group v-model="it.result" size="small">
                <el-radio value="normal">{{ t('safety.inspection.normalLabel') }}</el-radio>
                <el-radio value="abnormal">{{ t('safety.inspection.abnormalLabel') }}</el-radio>
              </el-radio-group>
              <el-input
                v-model="it.note"
                size="small"
                :placeholder="t('safety.inspection.itemNote')"
                class="inspection-item-note"
              />
            </div>
            <el-empty v-if="!inspectionForm.items.length" :description="t('safety.inspection.noItems')" />
          </div>
        </el-form-item>

        <el-form-item :label="t('safety.inspection.summary')">
          <el-input v-model="inspectionForm.summary" type="textarea" :rows="2" :maxlength="500" />
        </el-form-item>
        <el-form-item :label="t('common.form.remark')">
          <el-input v-model="inspectionForm.remark" type="textarea" :rows="2" :maxlength="500" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="inspectionVisible = false">{{ t('common.action.cancel') }}</el-button>
        <template v-if="!inspectionReadonly">
          <el-button v-if="inspectionMode !== 'submit'" @click="saveInspection(false)">
            {{ t('common.action.saveDraft') }}
          </el-button>
          <el-button type="primary" @click="saveInspection(true)">
            {{ t('safety.inspection.submitAction') }}
          </el-button>
        </template>
      </template>
    </el-dialog>

    <!-- 隐患上报 -->
    <el-dialog v-model="hazardVisible" width="var(--bs-layout-dialog-sm)" :title="t('safety.hazard.createTitle')">
      <el-form label-position="top">
        <el-form-item :label="t('safety.hazard.description')" required>
          <el-input
            v-model="hazardForm.description"
            type="textarea"
            :rows="3"
            :placeholder="t('safety.hazard.placeholderDesc')"
            :maxlength="500"
          />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item :label="t('safety.hazard.level')">
              <el-select v-model="hazardForm.level" style="width: 100%">
                <el-option v-for="o in levelOptions" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('safety.hazard.source')">
              <el-select v-model="hazardForm.source" style="width: 100%">
                <el-option v-for="o in hazardSourceOptions" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item :label="t('safety.hazard.responsible')">
              <el-input
                v-model="hazardForm.responsible_name"
                :placeholder="t('safety.hazard.placeholderResponsible')"
                :maxlength="64"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('safety.hazard.deadline')">
              <el-date-picker
                v-model="hazardForm.deadline"
                type="date"
                value-format="YYYY-MM-DD"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="t('common.form.remark')">
          <el-input v-model="hazardForm.remark" type="textarea" :rows="2" :maxlength="255" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="hazardVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" @click="submitHazard">{{ t('common.action.confirm') }}</el-button>
      </template>
    </el-dialog>

    <!-- 隐患整改 -->
    <el-dialog
      v-model="rectifyVisible"
      width="var(--bs-layout-dialog-sm)"
      :title="t('safety.hazard.rectifyTitle')"
    >
      <el-alert :title="t('safety.hazard.rectifyTip')" type="info" :closable="false" show-icon />
      <el-form label-position="top">
        <el-form-item :label="t('safety.hazard.measure')" required>
          <el-input
            v-model="rectifyForm.measure"
            type="textarea"
            :rows="4"
            :placeholder="t('safety.hazard.placeholderMeasure')"
            :maxlength="500"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rectifyVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" @click="submitRectify">{{ t('common.action.confirm') }}</el-button>
      </template>
    </el-dialog>

    <!-- 隐患验证 -->
    <el-dialog
      v-model="verifyVisible"
      width="var(--bs-layout-dialog-sm)"
      :title="t('safety.hazard.verifyTitle')"
    >
      <el-form label-position="top">
        <el-form-item :label="t('safety.hazard.verifyResult')">
          <el-input
            v-model="verifyForm.verify_result"
            type="textarea"
            :rows="3"
            :placeholder="t('safety.hazard.placeholderVerify')"
            :maxlength="500"
          />
        </el-form-item>
        <el-form-item :label="t('common.status.approved')">
          <el-radio-group v-model="verifyForm.pass">
            <el-radio :value="true">{{ t('safety.hazard.pass') }}</el-radio>
            <el-radio :value="false">{{ t('safety.hazard.notPass') }}</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="verifyVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" @click="submitVerify">{{ t('common.action.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.safety-page {
  height: 100%;
  min-height: 0;
}

.safety-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
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
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.stat-value {
  margin-top: var(--bs-space-1);
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.stat-value.is-danger {
  color: var(--bs-color-semantic-danger);
}

.safety-tabs {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.safety-tabs :deep(.el-tabs__header) {
  flex: none;
  margin-bottom: var(--bs-space-2);
}

.safety-tabs :deep(.el-tabs__content) {
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
}

.safety-tabs :deep(.el-tab-pane) {
  height: 100%;
  min-height: 0;
}

.pane {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  height: 100%;
  min-height: 0;
}

.pane-table {
  flex: 1 1 auto;
  min-height: 0;
}

.inspection-items {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  width: 100%;
}

.inspection-item {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  flex-wrap: wrap;
}

.inspection-item-name {
  min-width: 140px;
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-default);
}

.inspection-item-note {
  flex: 1 1 200px;
  min-width: 160px;
}
</style>
