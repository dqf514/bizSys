<script setup lang="ts">
/**
 * B8 作业申请流程：作业许可申请（叉车 / 吊装 / 高处 / 动火）。
 * 列表（状态页签 + 检索）→ 发起（选类型 → 动态表单）→ 详情（表单回显 + 审批时间线）→ 撤销。
 * 单据落在 OA 域（oa_instance，category=work_apply），模板与流程均由 OA 设计器/审批引擎驱动。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { resolveComponent } from 'vue'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import ApprovalTimeline from '@/components/approval/ApprovalTimeline.vue'
import FormRenderer from '@/modules/oa/components/FormRenderer.vue'
import { useListPage } from '@/composables/useListPage'
import { useAuthStore } from '@/stores/auth'
import {
  cancelWorkApply,
  createWorkApply,
  getWorkApply,
  listWorkApplies,
  workApplyCatalog,
  workApplyCounts,
  type WorkApply,
  type WorkApplyCatalogItem,
  type WorkApplyDetail,
} from '@/api/oa'
import type { ApprovalAction, TimelineRecord } from '@/api/types'

defineOptions({ name: 'WorkApplyList' })

const { t } = useI18n()
const auth = useAuthStore()

/* ---------- 模板目录（4 类作业许可） ---------- */
const catalog = ref<WorkApplyCatalogItem[]>([])

function typeName(item: WorkApplyCatalogItem) {
  const short = item.key.replace(/^work_apply_/, '')
  return t(`oa.workApply.types.${short}`, item.name)
}

function iconOf(name: string) {
  if (!name) return null
  const comp = resolveComponent(name)
  return comp ? (comp as never) : null
}

async function loadCatalog() {
  try {
    catalog.value = (await workApplyCatalog()) ?? []
  } catch {
    catalog.value = []
  }
}

/* ---------- 列表 ---------- */
const activeStatus = ref('all')
const counts = ref<Record<string, number>>({})

const statusTabs = computed<StatusTabItem[]>(() => [
  { value: 'all', labelKey: 'common.action.all', count: counts.value.all ?? 0 },
  { value: 'running', label: t('oa.status.running'), count: counts.value.running ?? 0 },
  { value: 'approved', label: t('oa.status.approved'), count: counts.value.approved ?? 0 },
  { value: 'rejected', label: t('oa.status.rejected'), count: counts.value.rejected ?? 0 },
  { value: 'withdrawn', label: t('oa.status.withdrawn'), count: counts.value.withdrawn ?? 0 },
  { value: 'terminated', label: t('oa.status.terminated'), count: counts.value.terminated ?? 0 },
])

async function loadCounts() {
  try {
    counts.value = { ...((await workApplyCounts()) ?? {}) }
  } catch {
    /* counts optional */
  }
}

const searchModel = ref<Record<string, any>>({ q: '', formKey: '' })

const searchFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'oa.workApply.searchQ',
    placeholderKey: 'oa.workApply.placeholderQ',
    width: 240,
  },
  {
    key: 'formKey',
    labelKey: 'oa.workApply.formType',
    type: 'select',
    width: 180,
    options: catalog.value.map((c) => ({ label: typeName(c), value: c.key })),
  },
])

const list = useListPage<WorkApply>({
  fetch: async (params) => {
    const data = await listWorkApplies({
      page: Number(params.page),
      size: Number(params.size),
      sort: (params.sort as string) || undefined,
      q: searchModel.value.q || undefined,
      status: activeStatus.value === 'all' ? '' : activeStatus.value,
      ...(searchModel.value.formKey ? { 'filters[form_key]': searchModel.value.formKey } : {}),
    })
    return { items: data.items, total: data.total ?? 0 }
  },
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'displayNo', labelKey: 'oa.workApply.columns.displayNo', width: 150, fixed: 'left', sortable: 'display_no' },
  { prop: 'formName', labelKey: 'oa.workApply.columns.formName', minWidth: 130 },
  { prop: 'applicantName', labelKey: 'oa.workApply.columns.applicantName', width: 110 },
  { prop: 'location', labelKey: 'oa.workApply.columns.location', minWidth: 160 },
  { prop: 'workTime', labelKey: 'oa.workApply.columns.time', minWidth: 180 },
  { prop: 'status', labelKey: 'oa.workApply.columns.status', width: 100 },
  { prop: 'createTime', labelKey: 'oa.workApply.columns.createTime', width: 165, sortable: 'create_time' },
]

function switchStatus(v: string) {
  activeStatus.value = v
  list.query.page = 1
  list.refresh()
}

function summaryOf(row: Record<string, unknown>): WorkApply['data'] {
  const d = row.data
  return (d && typeof d === 'object' ? d : {}) as WorkApply['data']
}

function rowActions(row: WorkApply): ActionItem[] {
  const actions: ActionItem[] = [{ key: 'detail', tip: 'common.action.detail' }]
  if (row.status === 'running' && row.applicantId === auth.user?.id) {
    actions.push({
      key: 'cancel',
      tip: 'oa.workApply.cancel',
      danger: true,
      confirm: 'oa.workApply.cancelConfirm',
    })
  }
  return actions
}

function onRowAction(key: string, row: WorkApply) {
  if (key === 'detail') {
    void openDetail(row)
    return
  }
  if (key === 'cancel') {
    void doCancel(row)
  }
}

/* ---------- 发起作业申请 ---------- */
const createVisible = ref(false)
const createStep = ref<1 | 2>(1)
const currentType = ref<WorkApplyCatalogItem | null>(null)
const formData = ref<Record<string, unknown>>({})
const rendererRef = ref<InstanceType<typeof FormRenderer> | null>(null)
const submitting = ref(false)

function draftKeyOf(type: WorkApplyCatalogItem) {
  return `oa.draft.${auth.user?.id ?? 'anon'}.${type.key}`
}

function openCreate() {
  createStep.value = 1
  currentType.value = null
  formData.value = {}
  createVisible.value = true
  if (!catalog.value.length) void loadCatalog()
}

function pickType(item: WorkApplyCatalogItem) {
  currentType.value = item
  let restored = false
  try {
    const raw = localStorage.getItem(draftKeyOf(item))
    if (raw) {
      const draft = JSON.parse(raw) as { data?: Record<string, unknown> }
      if (draft.data && Object.keys(draft.data).length) {
        formData.value = { ...draft.data }
        restored = true
      }
    }
  } catch {
    /* 草稿损坏时按新单处理 */
  }
  if (!restored) formData.value = { applicant: auth.user?.id }
  createStep.value = 2
}

function backToTypes() {
  createStep.value = 1
  currentType.value = null
  formData.value = {}
}

/** 保存草稿：落到本地（OA 单据无服务端草稿态），下次进入同类型自动恢复 */
function saveDraft() {
  if (!currentType.value) return
  try {
    localStorage.setItem(draftKeyOf(currentType.value), JSON.stringify({ data: formData.value }))
    ElMessage.success(t('oa.workApply.draftSaved'))
  } catch {
    /* storage 不可用时静默跳过 */
  }
}

async function submitApply() {
  if (!currentType.value) return
  const ok = await rendererRef.value?.validate()
  if (!ok) {
    ElMessage.warning(t('oa.workApply.fillRequired'))
    return
  }
  submitting.value = true
  try {
    await createWorkApply(currentType.value.key, formData.value)
    try {
      localStorage.removeItem(draftKeyOf(currentType.value))
    } catch {
      /* ignore */
    }
    ElMessage.success(t('oa.workApply.submitSuccess'))
    createVisible.value = false
    createStep.value = 1
    currentType.value = null
    formData.value = {}
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    submitting.value = false
  }
}

/* ---------- 详情抽屉 ---------- */
const drawerVisible = ref(false)
const detail = ref<WorkApplyDetail | null>(null)
const detailLoading = ref(false)

async function openDetail(row: WorkApply) {
  detail.value = null
  drawerVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await getWorkApply(row.id)
  } catch {
    /* http notifies */
  } finally {
    detailLoading.value = false
  }
}

const timeline = computed<TimelineRecord[]>(() =>
  (detail.value?.timeline ?? []).map((r) => ({ ...r, action: r.action as ApprovalAction })),
)

const canCancel = computed(
  () => detail.value?.status === 'running' && detail.value.applicantId === auth.user?.id,
)

async function doCancel(row: WorkApply) {
  try {
    await ElMessageBox.confirm(t('oa.workApply.cancelConfirm'), {
      type: 'warning',
      confirmButtonText: t('common.action.confirm'),
      cancelButtonText: t('common.action.cancel'),
    })
  } catch {
    return
  }
  try {
    await cancelWorkApply(row.id)
    ElMessage.success(t('oa.workApply.cancelDone'))
    if (detail.value?.id === row.id) drawerVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  }
}

onMounted(() => {
  void loadCatalog()
  void loadCounts()
})
</script>

<template>
  <ListPage :title="t('oa.workApply.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'oa:workapply:create'" type="primary" @click="openCreate">
        {{ t('oa.workApply.create') }}
      </el-button>
      <el-button @click="list.refresh()">{{ t('common.action.refresh') }}</el-button>
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '', formKey: '' }; list.reset()"
      />
    </template>

    <template #statusTabs>
      <StatusTabs :tabs="statusTabs" :model-value="activeStatus" @update:model-value="switchStatus" />
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
        <template #displayNo="{ row }">
          <el-button link type="primary" @click="openDetail(row as unknown as WorkApply)">
            {{ row.displayNo }}
          </el-button>
        </template>
        <template #formName="{ row }">{{ row.formName }}</template>
        <template #applicantName="{ row }">{{ row.applicantName || '-' }}</template>
        <template #location="{ row }">{{ summaryOf(row).work_location || '-' }}</template>
        <template #workTime="{ row }">{{ summaryOf(row).work_time || '-' }}</template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="oa.status" />
        </template>
        <template #createTime="{ row }">{{ row.createTime }}</template>
        <template #extraColumns>
          <el-table-column
            :label="t('common.action.operate')"
            width="110"
            fixed="right"
            align="center"
            header-align="center"
          >
            <template #default="{ row }">
              <ActionBar
                :actions="rowActions(row as unknown as WorkApply)"
                @select="(key: string) => onRowAction(key, row as unknown as WorkApply)"
              />
            </template>
          </el-table-column>
        </template>
        <template #cardFooter="{ row }">
          <div class="card-actions">
            <ActionBar
              :actions="rowActions(row as unknown as WorkApply)"
              @select="(key: string) => onRowAction(key, row as unknown as WorkApply)"
            />
          </div>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <!-- 新建作业申请：选类型 → 填表单 -->
  <el-dialog v-model="createVisible" :title="t('oa.workApply.createTitle')" fullscreen append-to-body>
    <div v-if="createStep === 1" class="type-picker">
      <div class="picker-tip">{{ t('oa.workApply.catalogTip') }}</div>
      <div v-if="catalog.length" class="type-grid">
        <div
          v-for="item in catalog"
          :key="item.key"
          class="type-card"
          role="button"
          tabindex="0"
          @click="pickType(item)"
          @keyup.enter="pickType(item)"
        >
          <div class="type-icon">
            <el-icon :size="22"><component :is="iconOf(item.icon) || 'Document'" /></el-icon>
          </div>
          <div class="type-body">
            <div class="type-name">{{ typeName(item) }}</div>
            <div class="type-desc">{{ item.description || '-' }}</div>
          </div>
        </div>
      </div>
      <el-empty v-else :description="t('oa.workApply.noCatalog')" />
    </div>

    <div v-else class="form-body">
      <div class="form-head">
        <el-button link @click="backToTypes">{{ t('oa.workApply.prevStep') }}</el-button>
        <span class="form-title">{{ currentType ? typeName(currentType) : '' }}</span>
      </div>
      <FormRenderer
        v-if="currentType"
        ref="rendererRef"
        v-model="formData"
        :fields="currentType.fields ?? []"
      />
    </div>

    <template #footer>
      <div class="dialog-footer">
        <div class="footer-left">
          <el-button v-if="createStep === 2" @click="saveDraft">{{ t('common.action.saveDraft') }}</el-button>
        </div>
        <div>
          <el-button @click="createVisible = false">{{ t('common.action.cancel') }}</el-button>
          <el-button v-if="createStep === 2" type="primary" :loading="submitting" @click="submitApply">
            {{ t('common.action.submitApproval') }}
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>

  <!-- 详情 -->
  <el-drawer
    v-model="drawerVisible"
    :title="detail ? `${detail.displayNo} ${detail.formName}` : t('oa.workApply.detail')"
    size="var(--bs-layout-drawer-md)"
  >
    <div v-if="detail" class="drawer-body" v-loading="detailLoading">
      <el-descriptions :column="2" border>
        <el-descriptions-item :label="t('oa.workApply.columns.displayNo')">
          {{ detail.displayNo }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('oa.workApply.columns.formName')">
          {{ detail.formName }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('oa.workApply.columns.applicantName')">
          {{ detail.applicantName || '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('oa.workApply.columns.status')">
          <StatusTag :status="detail.status" i18n-prefix="oa.status" />
        </el-descriptions-item>
        <el-descriptions-item :label="t('oa.workApply.columns.createTime')">
          {{ detail.createTime }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('oa.workApply.columns.time')">
          {{ detail.data?.work_time || '-' }}
        </el-descriptions-item>
      </el-descriptions>

      <div class="section-title">{{ t('oa.workApply.formData') }}</div>
      <FormRenderer :fields="detail.schema?.fields ?? []" :model-value="detail.formData" disabled />

      <div class="section-title">{{ t('approval.approval.timeline') }}</div>
      <ApprovalTimeline :records="timeline" :loading="detailLoading" />

      <div v-if="canCancel" class="drawer-actions">
        <el-button type="danger" @click="doCancel(detail)">{{ t('oa.workApply.cancel') }}</el-button>
      </div>
    </div>
  </el-drawer>
</template>

<style scoped>
.type-picker {
  max-width: var(--bs-layout-content-max-width);
  margin: 0 auto;
  width: 100%;
}

.picker-tip {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
  margin-bottom: var(--bs-space-3);
}

.type-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--bs-space-3);
}

.type-card {
  display: flex;
  align-items: center;
  gap: var(--bs-space-3);
  padding: var(--bs-space-3);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
  cursor: pointer;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.type-card:hover {
  border-color: var(--bs-color-primary);
  box-shadow: var(--bs-shadow-elevation2);
}

.type-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-fill-light);
  color: var(--bs-color-primary);
  flex-shrink: 0;
}

.type-body {
  flex: 1;
  min-width: 0;
}

.type-name {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.type-desc {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.form-body {
  max-width: var(--bs-layout-form-max-width);
  margin: 0 auto;
  width: 100%;
}

.form-head {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  margin-bottom: var(--bs-space-3);
}

.form-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.dialog-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.footer-left {
  display: flex;
  gap: var(--bs-space-2);
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

.drawer-actions {
  display: flex;
  justify-content: flex-end;
}

.card-actions {
  display: flex;
  justify-content: flex-end;
  padding: var(--bs-space-2) 0;
}
</style>
