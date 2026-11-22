<script setup lang="ts">
/** 访客登记与审批（B3）：多渠道预约登记 → 逐级审批 → 下发通行凭证 → 签入签出。 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
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
  approveVisitorVisit,
  cancelVisitorVisit,
  checkInVisitorVisit,
  checkOutVisitorVisit,
  createVisitorVisit,
  exportVisitorVisits,
  getVisitorVisit,
  listVisitorVisits,
  listVisitorZones,
  visitorVisitCounts,
} from '@/api/visitor'
import type { VisitorVisit, VisitorZone } from '@/api/types'

defineOptions({ name: 'VisitList' })

const { t } = useI18n()
const typeOpts = useDictOptions('visitor_type')
const sourceOpts = useDictOptions('visitor_source')

const searchModel = ref<Record<string, any>>({ q: '', visitor_type: '', source: '' })
const searchFields = computed<SearchField[]>(() => [
  { key: 'q', labelKey: 'visitor.visit.searchName', placeholderKey: 'visitor.visit.placeholderName', width: 260 },
  {
    key: 'visitor_type',
    labelKey: 'visitor.visit.visitorType',
    type: 'select',
    options: typeOpts.opts.value,
    width: 170,
  },
  {
    key: 'source',
    labelKey: 'visitor.visit.source',
    type: 'select',
    options: sourceOpts.opts.value,
    width: 170,
  },
])

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'pending', labelKey: 'visitor.visit.statusPending', count: 0 },
  { value: 'approved', labelKey: 'visitor.visit.statusApproved', count: 0 },
  { value: 'visiting', labelKey: 'visitor.visit.statusVisiting', count: 0 },
  { value: 'left', labelKey: 'visitor.visit.statusLeft', count: 0 },
  { value: 'overdue', labelKey: 'visitor.visit.statusOverdue', count: 0 },
  { value: 'rejected', labelKey: 'visitor.visit.statusRejected', count: 0 },
])

const counts = ref<Record<string, number>>({})

async function loadCounts() {
  try {
    counts.value = (await visitorVisitCounts()) ?? {}
    for (const tab of statusTabs.value) {
      if (tab.value === 'all') continue
      tab.count = counts.value[tab.value] ?? 0
    }
    const allTab = statusTabs.value.find((x) => x.value === 'all')
    if (allTab) allTab.count = counts.value.all ?? 0
  } catch {
    /* counts optional */
  }
}

onMounted(() => void loadCounts())

function buildFilters(params: Record<string, unknown>) {
  return {
    ...((params.filters as Record<string, unknown>) || {}),
    visitor_type: searchModel.value.visitor_type || undefined,
    source: searchModel.value.source || undefined,
  }
}

const list = useListPage<VisitorVisit>({
  fetch: async (params) => {
    const data = await listVisitorVisits({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(params),
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) =>
    exportVisitorVisits({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(params),
    }),
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'visitNo', labelKey: 'visitor.visit.no', width: 170, fixed: 'left' },
  { prop: 'visitorName', labelKey: 'visitor.visit.visitorName', width: 110 },
  { prop: 'visitorCompany', labelKey: 'visitor.visit.visitorCompany', minWidth: 150 },
  { prop: 'visitorTypeText', labelKey: 'visitor.visit.visitorType', width: 110 },
  { prop: 'hostName', labelKey: 'visitor.visit.hostName', width: 100 },
  { prop: 'zoneNames', labelKey: 'visitor.visit.zoneNames', minWidth: 140 },
  { prop: 'planStart', labelKey: 'visitor.visit.planStart', width: 160 },
  { prop: 'credentialNo', labelKey: 'visitor.visit.credentialNo', width: 165 },
  { prop: 'status', labelKey: 'visitor.visit.status', width: 105, sortable: 'status' },
  { prop: 'createTime', labelKey: 'visitor.visit.createTime', width: 160, sortable: 'create_time' },
]

function rowActions(row: VisitorVisit): ActionItem[] {
  const s = String(row.status)
  const acts: ActionItem[] = [{ key: 'detail', tip: 'common.action.detail' }]
  if (s === 'pending') {
    acts.push({ key: 'approve', tip: 'visitor.visit.approve', perm: 'visitor:visit:review' })
    acts.push({ key: 'reject', tip: 'visitor.visit.reject', perm: 'visitor:visit:review' })
    acts.push({ key: 'cancel', tip: 'visitor.visit.cancel', danger: true, perm: 'visitor:visit:review' })
  }
  if (s === 'approved') {
    acts.push({ key: 'checkin', tip: 'visitor.visit.checkin', perm: 'visitor:visit:checkin' })
  }
  if (s === 'visiting' || s === 'overdue') {
    acts.push({ key: 'checkout', tip: 'visitor.visit.checkout', perm: 'visitor:visit:checkin' })
  }
  return acts
}

/* ---------------- 详情 ---------------- */
const detailVisible = ref(false)
const detail = ref<VisitorVisit | null>(null)

async function openDetail(row: VisitorVisit) {
  try {
    detail.value = await getVisitorVisit(row.id)
    detailVisible.value = true
  } catch {
    /* http notifies */
  }
}

/* ---------------- 审批 ---------------- */
const reviewVisible = ref(false)
const reviewTarget = ref<VisitorVisit | null>(null)
const reviewForm = ref<{ action: 'approve' | 'reject'; level: string; comment: string }>({
  action: 'approve',
  level: '',
  comment: '',
})

function openReview(row: VisitorVisit, action: 'approve' | 'reject') {
  reviewTarget.value = row
  const pending = String(row.requiredLevels || '')
    .split(',')
    .filter((lv) => lv && !String(row.approvedLevels || '').split(',').includes(lv))[0]
  reviewForm.value = { action, level: pending || '', comment: '' }
  reviewVisible.value = true
}

async function submitReview() {
  const target = reviewTarget.value
  if (!target) return
  try {
    await approveVisitorVisit(target.id, {
      level: reviewForm.value.level || undefined,
      action: reviewForm.value.action,
      comment: reviewForm.value.comment,
    })
    ElMessage.success(t('common.message.submitSuccess'))
    reviewVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------------- 登记来访 ---------------- */
const zones = ref<VisitorZone[]>([])
const createVisible = ref(false)
const createForm = ref<Record<string, any>>({
  visitor_name: '',
  visitor_company: '',
  visitor_type: 'customer',
  id_no: '',
  phone: '',
  plate_no: '',
  host_name: '',
  host_dept_name: '',
  purpose: '',
  source: 'web',
  zone_ids: [] as number[],
  escort_names: '',
  plan_start: '',
  plan_end: '',
  remark: '',
})

async function loadZones() {
  try {
    const data = await listVisitorZones({ page: 1, size: 200, status: 'enabled' })
    zones.value = data.items ?? []
  } catch {
    /* optional */
  }
}

function openCreate() {
  createForm.value = {
    visitor_name: '',
    visitor_company: '',
    visitor_type: 'customer',
    id_no: '',
    phone: '',
    plate_no: '',
    host_name: '',
    host_dept_name: '',
    purpose: '',
    source: 'web',
    zone_ids: [],
    escort_names: '',
    plan_start: '',
    plan_end: '',
    remark: '',
  }
  createVisible.value = true
  void loadZones()
}

async function submitCreate() {
  const f = createForm.value
  if (!f.visitor_name) {
    ElMessage.warning(t('common.form.required'))
    return
  }
  try {
    await createVisitorVisit({
      visitor_name: f.visitor_name,
      visitor_company: f.visitor_company,
      visitor_type: f.visitor_type,
      id_no: f.id_no,
      phone: f.phone,
      plate_no: f.plate_no,
      host_name: f.host_name,
      host_dept_name: f.host_dept_name,
      purpose: f.purpose,
      source: f.source,
      zone_ids: (f.zone_ids as number[]).join(','),
      escort_names: f.escort_names,
      plan_start: f.plan_start ? `${f.plan_start} 00:00:00` : null,
      plan_end: f.plan_end ? `${f.plan_end} 23:59:59` : null,
      remark: f.remark,
    })
    ElMessage.success(t('common.message.createSuccess'))
    createVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------------- 签入 / 签出 / 取消 ---------------- */
const checkVisible = ref(false)
const checkTarget = ref<VisitorVisit | null>(null)
const checkForm = ref<{ method: string; device_id: string }>({ method: 'qrcode', device_id: '' })

function openCheckin(row: VisitorVisit) {
  checkTarget.value = row
  checkForm.value = { method: 'qrcode', device_id: '' }
  checkVisible.value = true
}

async function submitCheckin() {
  const target = checkTarget.value
  if (!target) return
  try {
    await checkInVisitorVisit(target.id, {
      method: checkForm.value.method,
      device_id: checkForm.value.device_id,
    })
    ElMessage.success(t('common.message.submitSuccess'))
    checkVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doCheckout(row: VisitorVisit) {
  try {
    await checkOutVisitorVisit(row.id, { method: 'qrcode' })
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doCancel(row: VisitorVisit) {
  try {
    await cancelVisitorVisit(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

function onRowAction(key: string, row: VisitorVisit) {
  if (key === 'detail') void openDetail(row)
  else if (key === 'approve') openReview(row, 'approve')
  else if (key === 'reject') openReview(row, 'reject')
  else if (key === 'cancel') void doCancel(row)
  else if (key === 'checkin') openCheckin(row)
  else if (key === 'checkout') void doCheckout(row)
}

function levelText(level: string) {
  return t(`visitor.visit.level${level.charAt(0).toUpperCase()}${level.slice(1)}`)
}
</script>

<template>
  <ListPage :title="t('visitor.visit.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'visitor:visit:create'" type="primary" @click="openCreate">
        {{ t('visitor.visit.create') }}
      </el-button>
      <ExportButton v-permission="'visitor:visit:export'" :export-fn="() => list.exportList()" />
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '', visitor_type: '', source: '' }; list.reset()"
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
        <template #visitNo="{ row }">
          <el-button link type="primary" @click="openDetail(row as unknown as VisitorVisit)">
            {{ row.visitNo }}
          </el-button>
        </template>
        <template #visitorTypeText="{ row }">
          {{ row.visitorTypeText || row.visitorType || '-' }}
        </template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="visitor.visit.status" />
        </template>
        <template #extraColumns>
          <el-table-column
            :label="t('common.action.operate')"
            width="130"
            fixed="right"
            align="center"
            header-align="center"
          >
            <template #default="{ row }">
              <ActionBar
                :actions="rowActions(row as unknown as VisitorVisit)"
                @select="(k) => onRowAction(k, row as unknown as VisitorVisit)"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-drawer v-model="detailVisible" :size="'var(--bs-layout-drawer-md)'" :title="t('visitor.visit.detail')">
    <el-descriptions v-if="detail" :column="2" border>
      <el-descriptions-item :label="t('visitor.visit.no')">{{ detail.visitNo }}</el-descriptions-item>
      <el-descriptions-item :label="t('visitor.visit.status')">
        <StatusTag :status="detail.status" i18n-prefix="visitor.visit.status" />
      </el-descriptions-item>
      <el-descriptions-item :label="t('visitor.visit.visitorName')">
        {{ detail.visitorName }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('visitor.visit.visitorCompany')">
        {{ detail.visitorCompany || '-' }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('visitor.visit.visitorType')">
        {{ detail.visitorTypeText || detail.visitorType }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('visitor.visit.idNo')">{{ detail.idNo || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('visitor.visit.phone')">{{ detail.phone || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('visitor.visit.plateNo')">{{ detail.plateNo || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('visitor.visit.hostName')">{{ detail.hostName || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('visitor.visit.hostDeptName')">
        {{ detail.hostDeptName || '-' }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('visitor.visit.source')">
        {{ detail.sourceText || detail.source }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('visitor.visit.zoneNames')">
        {{ detail.zoneNames || '-' }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('visitor.visit.escortNames')">
        {{ detail.escortNames || '-' }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('visitor.visit.planStart')">{{ detail.planStart || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('visitor.visit.planEnd')">{{ detail.planEnd || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('visitor.visit.checkinAt')">{{ detail.checkinAt || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('visitor.visit.checkoutAt')">{{ detail.checkoutAt || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('visitor.visit.credentialNo')">
        {{ detail.credentialNo || '-' }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('visitor.visit.purpose')" :span="2">
        {{ detail.purpose || '-' }}
      </el-descriptions-item>
    </el-descriptions>

    <template v-if="detail?.approvals?.length">
      <h4 class="drawer-section">{{ t('visitor.visit.approvals') }}</h4>
      <el-timeline>
        <el-timeline-item
          v-for="a in detail.approvals"
          :key="a.id"
          :timestamp="a.decidedAt"
          :type="a.action === 'approve' ? 'success' : 'danger'"
        >
          {{ levelText(a.level) }} · {{ a.approverName }}
          <div class="drawer-muted">{{ a.comment }}</div>
        </el-timeline-item>
      </el-timeline>
    </template>

    <template v-if="detail?.handovers?.length">
      <h4 class="drawer-section">{{ t('visitor.visit.handovers') }}</h4>
      <el-table :data="detail.handovers" size="small" border>
        <el-table-column prop="handoverNo" :label="t('visitor.handover.handoverNo')" />
        <el-table-column prop="sampleNo" :label="t('visitor.handover.sampleNo')" />
        <el-table-column prop="handoverUserName" :label="t('visitor.handover.handoverUserName')" />
        <el-table-column prop="receiveUserName" :label="t('visitor.handover.receiveUserName')" />
        <el-table-column prop="handoverAt" :label="t('visitor.handover.handoverAt')" />
      </el-table>
    </template>
  </el-drawer>

  <el-dialog v-model="reviewVisible" :width="'var(--bs-layout-dialog-sm)'" :title="t('visitor.visit.approvalTitle')">
    <el-form label-position="top">
      <el-form-item :label="t('visitor.visit.level')">
        <el-input :model-value="levelText(reviewForm.level)" disabled />
      </el-form-item>
      <el-form-item :label="t('visitor.visit.comment')">
        <el-input v-model="reviewForm.comment" type="textarea" :rows="3" :maxlength="1000" show-word-limit />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="reviewVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button
        :type="reviewForm.action === 'approve' ? 'primary' : 'danger'"
        @click="submitReview"
      >
        {{ reviewForm.action === 'approve' ? t('visitor.visit.approve') : t('visitor.visit.reject') }}
      </el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="checkVisible" :width="'var(--bs-layout-dialog-sm)'" :title="t('visitor.visit.checkin')">
    <el-form label-position="top">
      <el-form-item :label="t('visitor.credential.method')">
        <el-select v-model="checkForm.method" style="width: 100%">
          <el-option label="QR Code" value="qrcode" />
          <el-option label="Face" value="face" />
          <el-option label="IC Card" value="ic" />
          <el-option label="Plate" value="plate" />
          <el-option label="Manual" value="manual" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('visitor.credential.deviceId')">
        <el-input v-model="checkForm.device_id" :maxlength="64" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="checkVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="submitCheckin">{{ t('common.action.confirm') }}</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="createVisible" :width="'var(--bs-layout-dialog-md)'" :title="t('visitor.visit.createTitle')">
    <el-form label-position="top">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('visitor.visit.visitorName')" required>
            <el-input v-model="createForm.visitor_name" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('visitor.visit.visitorCompany')">
            <el-input v-model="createForm.visitor_company" :maxlength="128" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('visitor.visit.visitorType')">
            <el-select v-model="createForm.visitor_type" style="width: 100%" clearable>
              <el-option
                v-for="o in typeOpts.opts.value"
                :key="o.value"
                :label="o.label"
                :value="o.value"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('visitor.visit.source')">
            <el-select v-model="createForm.source" style="width: 100%" clearable>
              <el-option
                v-for="o in sourceOpts.opts.value"
                :key="o.value"
                :label="o.label"
                :value="o.value"
              />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('visitor.visit.idNo')">
            <el-input v-model="createForm.id_no" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('visitor.visit.phone')">
            <el-input v-model="createForm.phone" :maxlength="32" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('visitor.visit.hostName')">
            <el-input v-model="createForm.host_name" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('visitor.visit.hostDeptName')">
            <el-input v-model="createForm.host_dept_name" :maxlength="128" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="t('visitor.visit.selectZones')">
        <el-select v-model="createForm.zone_ids" multiple style="width: 100%" collapse-tags>
          <el-option v-for="z in zones" :key="z.id" :label="z.name" :value="z.id" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('visitor.visit.escortNames')">
        <el-input v-model="createForm.escort_names" :maxlength="500" />
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('visitor.visit.planStart')">
            <el-date-picker v-model="createForm.plan_start" type="date" value-format="YYYY-MM-DD" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('visitor.visit.planEnd')">
            <el-date-picker v-model="createForm.plan_end" type="date" value-format="YYYY-MM-DD" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="t('visitor.visit.purpose')">
        <el-input v-model="createForm.purpose" :maxlength="255" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="createVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="submitCreate">{{ t('common.action.submitApproval') }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.drawer-section {
  margin: var(--bs-space-4) 0 var(--bs-space-2);
  font-size: var(--bs-typography-font-size-lg);
}

.drawer-muted {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}
</style>
