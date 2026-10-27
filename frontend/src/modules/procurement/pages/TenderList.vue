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
import ApprovalTimeline from '@/components/approval/ApprovalTimeline.vue'
import { useListPage } from '@/composables/useListPage'
import { useDictOptions } from '@/composables/useDict'
import {
  listTenders,
  tenderCounts,
  getTender,
  createTender,
  updateTender,
  deleteTender,
  publishTender,
  terminateTender,
  startEvaluation,
  reviewRegistration,
  upsertTenderEval,
  awardTender,
  generateTenderContract,
  exportTenders,
  downloadRegistrationAttachment,
  downloadBidProposal,
  listPurchaseRequests,
} from '@/api/procurement'
import type { PurchaseRequest, TenderBid, TenderProject, TenderProjectDetail, TenderRegistration } from '@/api/types'

defineOptions({ name: 'TenderList' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const methodOpts = useDictOptions('tender_method')

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'procurement.tender.searchName', placeholderKey: 'procurement.tender.placeholderName', width: 240 },
]

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'draft', labelKey: 'common.status.draft', count: 0 },
  { value: 'published', labelKey: 'common.status.published', count: 0 },
  { value: 'evaluating', labelKey: 'common.status.evaluating', count: 0 },
  { value: 'awarding', labelKey: 'common.status.awarding', count: 0 },
  { value: 'awarded', labelKey: 'common.status.awarded', count: 0 },
  { value: 'terminated', labelKey: 'common.status.terminated', count: 0 },
])

const counts = ref<Record<string, number>>({})

async function loadCounts() {
  try {
    counts.value = (await tenderCounts()) ?? {}
    for (const tab of statusTabs.value) {
      tab.count = counts.value[tab.value] ?? 0
    }
  } catch {
    /* counts optional */
  }
}

onMounted(() => void loadCounts())

const list = useListPage<TenderProject>({
  fetch: async (params) => {
    const data = await listTenders({ ...params, q: searchModel.value.q || undefined })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) => exportTenders({ ...params, q: searchModel.value.q || undefined }),
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'tenderNo', labelKey: 'procurement.tender.tenderNo', width: 150, fixed: 'left', sortable: 'tender_no' },
  { prop: 'name', labelKey: 'procurement.tender.name', minWidth: 200, fixed: 'left', sortable: 'name' },
  { prop: 'requestNo', labelKey: 'procurement.tender.linkedRequest', width: 140 },
  { prop: 'tenderMethod', labelKey: 'procurement.tender.tenderMethod', width: 110 },
  { prop: 'budgetAmount', labelKey: 'procurement.tender.budgetAmount', width: 110, sortable: 'budget_amount' },
  { prop: 'bidDeadline', labelKey: 'procurement.tender.bidDeadline', width: 160, sortable: 'bid_deadline' },
  { prop: 'winnerName', labelKey: 'procurement.tender.winner', width: 160 },
  { prop: 'status', labelKey: 'procurement.tender.status', width: 110, sortable: 'status' },
  { prop: 'createTime', labelKey: 'procurement.tender.createTime', width: 160, sortable: 'create_time' },
]

function rowActions(row: TenderProject): ActionItem[] {
  const s = String(row.status)
  const acts: ActionItem[] = [{ key: 'detail', tip: 'common.action.detail' }]
  if (s === 'draft') {
    acts.push({ key: 'edit', tip: 'common.action.edit', perm: 'procurement:tender:edit' })
    acts.push({ key: 'publish', tip: 'procurement.tender.publish', icon: 'Promotion', perm: 'procurement:tender:publish' })
    acts.push({ key: 'delete', tip: 'common.action.delete', perm: 'procurement:tender:delete' })
  }
  if (s === 'published') {
    acts.push({ key: 'evaluate', tip: 'procurement.tender.startEvaluation', icon: 'EditPen', perm: 'procurement:tender:evaluate' })
  }
  if (s === 'published' || s === 'evaluating') {
    acts.push({ key: 'terminate', tip: 'procurement.tender.terminate', icon: 'CircleClose', danger: true, perm: 'procurement:tender:terminate' })
  }
  return acts
}

function onRowAction(key: string, row: TenderProject) {
  if (key === 'detail') openDetail(row.id)
  else if (key === 'edit') openEdit(row)
  else if (key === 'publish') void doPublish(row)
  else if (key === 'evaluate') void doStartEvaluation(row)
  else if (key === 'terminate') void doTerminate(row)
  else if (key === 'delete') void remove(row)
}

/* ---------- form ---------- */
const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  name: '',
  requestId: null as number | null,
  tenderMethod: 'public',
  budgetAmount: null as number | null,
  regDeadline: '',
  bidDeadline: '',
  openTime: '',
  announcement: '',
  version: null as number | null,
})

const reqOpts = ref<{ value: number; label: string }[]>([])
const reqLoading = ref(false)

async function searchRequests(q: string) {
  reqLoading.value = true
  try {
    const data = await listPurchaseRequests({ page: 1, size: 20, q: q || undefined })
    reqOpts.value = (data.items ?? []).map((x: PurchaseRequest) => ({
      value: x.id,
      label: `${x.requestNo || '-'} ${x.title}`,
    }))
  } catch {
    reqOpts.value = []
  } finally {
    reqLoading.value = false
  }
}

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('procurement.tender.create')
  Object.assign(form, {
    name: '',
    requestId: null,
    tenderMethod: 'public',
    budgetAmount: null,
    regDeadline: '',
    bidDeadline: '',
    openTime: '',
    announcement: '',
    version: null,
  })
  reqOpts.value = []
  dialogVisible.value = true
}

function openEdit(row: TenderProject) {
  editingId.value = row.id
  dialogTitle.value = t('procurement.tender.edit')
  Object.assign(form, {
    name: row.name,
    requestId: row.requestId,
    tenderMethod: row.tenderMethod || 'public',
    budgetAmount: row.budgetAmount === null ? null : Number(row.budgetAmount),
    regDeadline: row.regDeadline ?? '',
    bidDeadline: row.bidDeadline ?? '',
    openTime: row.openTime ?? '',
    announcement: row.announcement ?? '',
    version: row.version ?? null,
  })
  reqOpts.value = row.requestId ? [{ value: row.requestId, label: row.requestNo || `#${row.requestId}` }] : []
  dialogVisible.value = true
}

async function save() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  saving.value = true
  try {
    const payload = {
      name: form.name,
      requestId: form.requestId,
      tenderMethod: form.tenderMethod,
      budgetAmount: form.budgetAmount,
      regDeadline: form.regDeadline || null,
      bidDeadline: form.bidDeadline || null,
      openTime: form.openTime || null,
      announcement: form.announcement,
      version: form.version,
    }
    if (editingId.value) await updateTender(editingId.value, payload)
    else await createTender(payload)
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function doPublish(row: TenderProject) {
  try {
    await ElMessageBox.confirm(t('procurement.tender.publishConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await publishTender(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doStartEvaluation(row: TenderProject) {
  try {
    await ElMessageBox.confirm(t('procurement.tender.startEvaluationConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await startEvaluation(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
    if (detail.value?.id === row.id) void openDetail(row.id)
  } catch {
    /* http notifies */
  }
}

async function doTerminate(row: TenderProject) {
  try {
    await ElMessageBox.confirm(t('procurement.tender.terminateConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await terminateTender(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function remove(row: TenderProject) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteTender(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------- detail drawer ---------- */
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<TenderProjectDetail | null>(null)

async function openDetail(id: number) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await getTender(id)
  } catch {
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

// 深链互跳：/procurement/tenders?detail=<id>
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

/* ---------- registration review ---------- */
async function doReview(reg: TenderRegistration, approve: boolean) {
  let comment = ''
  try {
    const { value } = await ElMessageBox.prompt(
      t('procurement.tender.reviewComment'),
      approve ? t('procurement.tender.approve') : t('procurement.tender.reject'),
      { inputPlaceholder: t('procurement.tender.reviewComment'), confirmButtonText: t('common.action.confirm'), cancelButtonText: t('common.action.cancel') },
    )
    comment = value ?? ''
  } catch {
    return
  }
  if (!detail.value) return
  try {
    await reviewRegistration(detail.value.id, reg.id, { approve, comment })
    ElMessage.success(t('common.message.saveSuccess'))
    void openDetail(detail.value.id)
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------- eval ---------- */
const evalForms = reactive<Record<number, { score: number | null; comment: string; recommend: boolean }>>({})

function evalForm(bid: TenderBid) {
  let f = evalForms[bid.id]
  if (!f) {
    f = { score: null, comment: '', recommend: false }
    evalForms[bid.id] = f
  }
  return f
}

const evalSaving = ref(0)

async function saveEval(bid: TenderBid) {
  if (!detail.value) return
  const f = evalForm(bid)
  if (f.score === null) return
  evalSaving.value = bid.id
  try {
    await upsertTenderEval(detail.value.id, { bidId: bid.id, score: f.score, comment: f.comment, recommend: f.recommend })
    ElMessage.success(t('common.message.saveSuccess'))
    void openDetail(detail.value.id)
  } catch {
    /* http notifies */
  } finally {
    evalSaving.value = 0
  }
}

/* ---------- award / contract ---------- */
async function doAward(bid: TenderBid) {
  if (!detail.value) return
  try {
    await ElMessageBox.confirm(t('procurement.tender.awardConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await awardTender(detail.value.id, bid.id)
    ElMessage.success(t('common.message.submitSuccess'))
    void openDetail(detail.value.id)
    list.refresh()
  } catch {
    /* http notifies */
  }
}

const genSaving = ref(false)

async function doGenerateContract() {
  if (!detail.value) return
  genSaving.value = true
  try {
    const c = await generateTenderContract(detail.value.id)
    ElMessage.success(t('common.message.saveSuccess'))
    detailVisible.value = false
    list.refresh()
    router.push({ path: '/procurement/contracts', query: { detail: c.id } })
  } catch {
    /* http notifies */
  } finally {
    genSaving.value = false
  }
}

function openLinkedContract() {
  if (!detail.value?.contractId) return
  router.push({ path: '/procurement/contracts', query: { detail: detail.value.contractId } })
}

function methodLabel(value: unknown) {
  const v = String(value ?? '')
  return methodOpts.opts.value.find((x) => x.value === v)?.label || v || '-'
}

function fmtAmount(v: unknown) {
  const n = Number(v ?? 0)
  return Number.isFinite(n) && v !== null && v !== '' ? n.toLocaleString() : '-'
}
</script>

<template>
  <ListPage :title="t('procurement.tender.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'procurement:tender:create'" type="primary" @click="openCreate">
        {{ t('procurement.tender.create') }}
      </el-button>
      <ExportButton v-permission="'procurement:tender:list:export'" :export-fn="() => list.exportList()" />
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
        <template #tenderNo="{ row }">
          <el-button link type="primary" @click="openDetail(row.id)">{{ row.tenderNo || '-' }}</el-button>
        </template>
        <template #tenderMethod="{ row }">{{ methodLabel(row.tenderMethod) }}</template>
        <template #budgetAmount="{ row }">{{ fmtAmount(row.budgetAmount) }}</template>
        <template #requestNo="{ row }">{{ row.requestNo || '-' }}</template>
        <template #winnerName="{ row }">{{ row.winnerName || '-' }}</template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="common.status" />
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="150" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar :actions="rowActions(row as unknown as TenderProject)" @select="(k) => onRowAction(k, row as unknown as TenderProject)" />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="720px" append-to-body>
    <el-form ref="formRef" :model="form" label-width="110px">
      <el-form-item :label="t('procurement.tender.name')" prop="name" :rules="[{ required: true, message: t('common.form.required') }]">
        <el-input v-model="form.name" :maxlength="255" />
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('procurement.tender.linkedRequest')">
            <el-select
              v-model="form.requestId"
              clearable
              filterable
              remote
              :remote-method="searchRequests"
              :loading="reqLoading"
              :placeholder="t('procurement.tender.requestPlaceholder')"
              style="width: 100%"
              @focus="!reqOpts.length && searchRequests('')"
            >
              <el-option v-for="o in reqOpts" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('procurement.tender.tenderMethod')">
            <el-select v-model="form.tenderMethod" style="width: 100%">
              <el-option v-for="o in methodOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('procurement.tender.budgetAmount')">
            <el-input-number v-model="form.budgetAmount" :min="0" :precision="2" :controls="false" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('procurement.tender.openTime')">
            <el-date-picker v-model="form.openTime" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('procurement.tender.regDeadline')">
            <el-date-picker v-model="form.regDeadline" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('procurement.tender.bidDeadline')">
            <el-date-picker v-model="form.bidDeadline" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="t('procurement.tender.announcement')">
        <el-input v-model="form.announcement" type="textarea" :rows="4" :maxlength="8000" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>

  <el-drawer v-model="detailVisible" size="860px">
    <template #header>
      <div class="drawer-header">
        <span class="drawer-title">{{ detail?.name || t('procurement.tender.detail') }}</span>
        <StatusTag v-if="detail" :status="detail.status" i18n-prefix="common.status" />
      </div>
    </template>
    <div v-loading="detailLoading" class="drawer-body">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="t('procurement.tender.tenderNo')">{{ detail.tenderNo || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.tender.tenderMethod')">{{ methodLabel(detail.tenderMethod) }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.tender.linkedRequest')">{{ detail.requestNo || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.tender.budgetAmount')">{{ fmtAmount(detail.budgetAmount) }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.tender.regDeadline')">{{ detail.regDeadline || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.tender.bidDeadline')">{{ detail.bidDeadline || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.tender.openTime')">{{ detail.openTime || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.tender.createTime')">{{ detail.createTime }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.tender.announcement')" :span="2">
            <span class="pre-wrap">{{ detail.announcement || '-' }}</span>
          </el-descriptions-item>
        </el-descriptions>

        <div class="section-title">{{ t('procurement.tender.registrations') }}</div>
        <el-table v-if="detail.registrations.length" :data="detail.registrations" border stripe size="small">
          <el-table-column :label="t('procurement.partner.companyName')" prop="companyName" min-width="150" />
          <el-table-column :label="t('procurement.partner.contactName')" prop="contactName" width="90" />
          <el-table-column :label="t('procurement.partner.phone')" prop="contactPhone" width="120" />
          <el-table-column :label="t('procurement.tender.attachment')" width="90" align="center">
            <template #default="{ row }">
              <el-button v-if="row.hasAttachment" link type="primary" @click="downloadRegistrationAttachment(row.id)">
                {{ t('procurement.tender.download') }}
              </el-button>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column :label="t('procurement.tender.status')" width="90" align="center">
            <template #default="{ row }">
              <StatusTag :status="String(row.status)" i18n-prefix="common.status" />
            </template>
          </el-table-column>
          <el-table-column :label="t('common.action.operate')" width="130" align="center">
            <template #default="{ row }">
              <template v-if="row.status === 'pending'">
                <el-button v-permission="'procurement:tender:review'" link type="success" @click="doReview(row, true)">
                  {{ t('procurement.tender.approve') }}
                </el-button>
                <el-button v-permission="'procurement:tender:review'" link type="danger" @click="doReview(row, false)">
                  {{ t('procurement.tender.reject') }}
                </el-button>
              </template>
              <span v-else class="muted">{{ row.reviewName || '-' }}</span>
            </template>
          </el-table-column>
        </el-table>
        <div v-else class="muted">{{ t('procurement.tender.noRegistrations') }}</div>

        <div class="section-title">{{ t('procurement.tender.bids') }}</div>
        <div v-if="detail.bids.length" class="bid-list">
          <div v-for="bid in detail.bids" :key="bid.id" class="bid-card">
            <div class="bid-head">
              <span class="bid-company">{{ bid.companyName }}</span>
              <el-tag v-if="bid.isWinner" type="success" size="small" effect="dark" round>{{ t('procurement.tender.isWinner') }}</el-tag>
              <span class="bid-price">{{ fmtAmount(bid.price) }}</span>
              <span v-if="bid.avgScore !== null" class="muted">{{ t('procurement.tender.avgScore') }} {{ bid.avgScore }}</span>
              <el-button v-if="bid.hasProposal" link type="primary" @click="downloadBidProposal(bid.id)">
                {{ t('procurement.tender.proposal') }}
              </el-button>
              <el-button
                v-if="detail.status === 'evaluating'"
                v-permission="'procurement:tender:award'"
                type="primary"
                size="small"
                @click="doAward(bid)"
              >
                {{ t('procurement.tender.award') }}
              </el-button>
            </div>
            <div v-if="bid.comment" class="muted">{{ bid.comment }}</div>
            <div v-if="bid.evals.length" class="eval-list">
              <div v-for="e in bid.evals" :key="e.id" class="eval-row">
                <span>{{ e.evaluatorName }}</span>
                <span>{{ e.score }}</span>
                <el-tag v-if="e.recommend" type="warning" size="small" round>{{ t('procurement.tender.recommend') }}</el-tag>
                <span class="muted">{{ e.comment }}</span>
              </div>
            </div>
            <div v-if="detail.status === 'evaluating'" v-permission="'procurement:tender:evaluate'" class="eval-form">
              <el-input-number
                v-model="evalForm(bid).score"
                :min="0"
                :max="100"
                :precision="1"
                :placeholder="t('procurement.tender.score')"
                style="width: 140px"
              />
              <el-input v-model="evalForm(bid).comment" :placeholder="t('procurement.tender.evalComment')" :maxlength="500" style="width: 240px" />
              <el-checkbox v-model="evalForm(bid).recommend">{{ t('procurement.tender.recommend') }}</el-checkbox>
              <el-button size="small" type="primary" :loading="evalSaving === bid.id" @click="saveEval(bid)">
                {{ t('procurement.tender.saveEval') }}
              </el-button>
            </div>
          </div>
        </div>
        <div v-else class="muted">{{ t('procurement.tender.noBids') }}</div>

        <template v-if="detail.status === 'awarded'">
          <div class="section-title">{{ t('procurement.tender.winner') }}</div>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item :label="t('procurement.tender.winner')">{{ detail.winnerName }}</el-descriptions-item>
            <el-descriptions-item :label="t('procurement.tender.winnerAmount')">{{ fmtAmount(detail.winnerAmount) }}</el-descriptions-item>
          </el-descriptions>
          <div class="link-row">
            <template v-if="detail.contractId">
              <el-button link type="primary" @click="openLinkedContract">
                {{ detail.contractNo || `#${detail.contractId}` }}
              </el-button>
              <StatusTag :status="detail.contractStatus || ''" i18n-prefix="common.status" />
            </template>
            <el-button
              v-else
              v-permission="'procurement:contract:create'"
              type="primary"
              size="small"
              :loading="genSaving"
              @click="doGenerateContract"
            >
              {{ t('procurement.tender.generateContract') }}
            </el-button>
          </div>
        </template>
        <el-alert
          v-else-if="detail.status === 'awarding'"
          :title="t('procurement.tender.awardingTip')"
          type="warning"
          :closable="false"
          show-icon
        />

        <div class="section-title">{{ t('procurement.tender.timeline') }}</div>
        <ApprovalTimeline :records="detail.timeline ?? []" />
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

.muted {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.pre-wrap {
  white-space: pre-wrap;
}

.link-row {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.bid-list {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.bid-card {
  border: 1px solid var(--bs-color-border-default);
  border-radius: var(--bs-radius-md);
  padding: var(--bs-space-2) var(--bs-space-3);
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.bid-head {
  display: flex;
  align-items: center;
  gap: var(--bs-space-3);
  flex-wrap: wrap;
}

.bid-company {
  font-weight: 600;
}

.bid-price {
  font-weight: 600;
  color: var(--bs-color-primary);
}

.eval-list {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-1);
}

.eval-row {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  font-size: var(--bs-typography-font-size-sm);
}

.eval-form {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  flex-wrap: wrap;
}
</style>
