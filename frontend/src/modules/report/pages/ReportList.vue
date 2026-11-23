<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import ReportUploadDialog from '../components/ReportUploadDialog.vue'
import ReportDetailDrawer from '../components/ReportDetailDrawer.vue'
import { useListPage } from '@/composables/useListPage'
import {
  listReports,
  reportCounts,
  submitReport,
  sealApplyReport,
  sealReport,
  downloadReport,
  exportReports,
  verifyReportSeal,
} from '@/api/report'
import { useFlowCapability } from '@/composables/useFlowCapability'
import type { Report, SealVerifyResult } from '@/api/types'

defineOptions({ name: 'ReportList' })

const { t } = useI18n()
const { load: loadFlowCaps, flowEnabled } = useFlowCapability()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'report.report.searchQ', placeholderKey: 'report.report.placeholderQ', width: 260 },
]

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'uploaded', labelKey: 'report.report.status.uploaded', count: 0 },
  { value: 'approving', labelKey: 'report.report.status.approving', count: 0 },
  { value: 'approved', labelKey: 'report.report.status.approved', count: 0 },
  { value: 'rejected', labelKey: 'report.report.status.rejected', count: 0 },
  { value: 'sealing', labelKey: 'report.report.status.sealing', count: 0 },
  { value: 'seal_approved', labelKey: 'report.report.status.seal_approved', count: 0 },
  { value: 'sealed', labelKey: 'report.report.status.sealed', count: 0 },
])

const counts = ref<Record<string, number>>({})

async function loadCounts() {
  try {
    counts.value = (await reportCounts()) ?? {}
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

onMounted(() => {
  void loadCounts()
  void loadFlowCaps()
})

const list = useListPage<Report>({
  fetch: async (params) => {
    const data = await listReports({
      ...params,
      q: searchModel.value.q || undefined,
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) =>
    exportReports({
      ...params,
      q: searchModel.value.q || undefined,
    }),
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'reportNo', labelKey: 'report.report.reportNo', width: 150, fixed: 'left', sortable: 'report_no' },
  { prop: 'taskNo', labelKey: 'report.report.taskNo', width: 140 },
  { prop: 'contractNo', labelKey: 'report.report.contractNo', width: 140 },
  { prop: 'itemName', labelKey: 'report.report.itemName', minWidth: 130 },
  { prop: 'customerName', labelKey: 'report.report.customerName', minWidth: 140 },
  { prop: 'fileName', labelKey: 'report.report.fileName', minWidth: 160, sortable: 'file_name' },
  { prop: 'status', labelKey: 'common.form.status', width: 110, sortable: 'status' },
  { prop: 'createBy', labelKey: 'report.report.createBy', width: 100 },
  { prop: 'createTime', labelKey: 'report.report.createTime', width: 160, sortable: 'create_time' },
]

/** 行内动作随状态变化；超出 3 个收进「更多」 */
function rowActions(row: Report): ActionItem[] {
  const acts: ActionItem[] = [{ key: 'detail', tip: 'common.action.detail' }]
  if (row.status === 'uploaded' || row.status === 'rejected') {
    acts.push({ key: 'submit', tip: 'report.report.submit', perm: 'report:submit' })
  }
  // F5：用章流程启用时，先「用章申请」再「签章」；流程停用则由有权人直接签章
  if (row.status === 'approved') {
    if (flowEnabled('report_seal')) {
      acts.push({ key: 'sealApply', tip: 'report.report.sealApply', perm: 'report:seal:apply' })
    } else {
      acts.push({ key: 'seal', tip: 'report.report.seal', perm: 'report:seal' })
    }
  }
  if (row.status === 'seal_approved') {
    acts.push({ key: 'seal', tip: 'report.report.seal', perm: 'report:seal' })
  }
  acts.push({ key: 'downloadRaw', tip: 'report.report.downloadRaw', icon: 'Download' })
  if (row.pdfReady) acts.push({ key: 'downloadPdf', tip: 'report.report.downloadPdf', icon: 'Document' })
  // B9-C2：签章后锁定的报告可验签（签名 + 内容哈希比对）
  if (row.status === 'sealed') {
    acts.push({ key: 'verify', tip: 'report.report.verifySeal', icon: 'CircleCheck', perm: 'report:seal' })
  }
  return acts
}

function onRowAction(key: string, row: Report) {
  if (key === 'detail') openDetail(row)
  else if (key === 'submit') void doSubmit(row)
  else if (key === 'sealApply') void doSealApply(row)
  else if (key === 'seal') void doSeal(row)
  else if (key === 'verify') void doVerifySeal(row)
  else if (key === 'downloadRaw') doDownload(row, false)
  else if (key === 'downloadPdf') doDownload(row, true)
}

/* ---------- upload dialog ---------- */
const uploadVisible = ref(false)

/* ---------- row actions ---------- */
async function doSubmit(row: Report) {
  try {
    await ElMessageBox.confirm(t('report.report.submitConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await submitReport(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doSeal(row: Report) {
  try {
    await ElMessageBox.confirm(t('report.report.sealConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await sealReport(row.id)
    ElMessage.success(t('common.message.saveSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doSealApply(row: Report) {
  try {
    await ElMessageBox.confirm(t('report.report.sealApplyConfirm'), t('common.action.confirm'), {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await sealApplyReport(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

function doDownload(row: Report, pdf: boolean) {
  const name = pdf ? row.fileName.replace(/\.[^.]+$/, '') + '.pdf' : row.fileName
  void downloadReport(row.id, pdf, name)
}

/* ---------- detail drawer ---------- */
const detailVisible = ref(false)
const detailId = ref<number | null>(null)

function openDetail(row: Report) {
  detailId.value = row.id
  detailVisible.value = true
}

/* ---------- 签章验签（B9-C2） ---------- */
const verifyVisible = ref(false)
const verifyLoading = ref(false)
const verifyResult = ref<SealVerifyResult | null>(null)

async function doVerifySeal(row: Report) {
  verifyVisible.value = true
  verifyLoading.value = true
  verifyResult.value = null
  try {
    verifyResult.value = await verifyReportSeal(row.id)
  } catch {
    verifyResult.value = null
  } finally {
    verifyLoading.value = false
  }
}
</script>

<template>
  <ListPage :title="t('report.report.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'report:create'" type="primary" @click="uploadVisible = true">
        {{ t('report.report.upload') }}
      </el-button>
      <ExportButton v-permission="'report:export'" :export-fn="() => list.exportList()" />
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
        <template #reportNo="{ row }">
          <el-button link type="primary" @click="openDetail(row as unknown as Report)">
            {{ row.reportNo }}
          </el-button>
        </template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="report.report.status" />
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="130" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar :actions="rowActions(row as unknown as Report)" @select="(k) => onRowAction(k, row as unknown as Report)" />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <ReportUploadDialog v-model="uploadVisible" @uploaded="list.refresh()" />

  <ReportDetailDrawer v-model="detailVisible" :report-id="detailId" />

  <!-- 签章验签 -->
  <el-dialog v-model="verifyVisible" :title="t('report.report.verifySeal')" width="var(--bs-layout-dialog-md)" append-to-body>
    <div v-loading="verifyLoading">
      <template v-if="verifyResult">
        <el-alert
          :type="verifyResult.signatureValid && verifyResult.contentMatch ? 'success' : 'error'"
          :title="
            verifyResult.signatureValid && verifyResult.contentMatch
              ? t('report.report.sealVerifyOk')
              : t('report.report.sealVerifyBad')
          "
          :closable="false"
          show-icon
        />
        <el-descriptions :column="1" border size="small" class="verify-desc">
          <el-descriptions-item :label="t('report.report.reportNo')">
            {{ verifyResult.reportNo || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('report.report.sealSignatureValid')">
            {{ verifyResult.signatureValid ? t('common.action.yes') : t('common.action.no') }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('report.report.sealContentMatch')">
            <template v-if="verifyResult.contentUnavailable">
              {{ t('report.report.sealContentUnavailable') }}
            </template>
            <template v-else>
              {{ verifyResult.contentMatch ? t('common.action.yes') : t('common.action.no') }}
            </template>
          </el-descriptions-item>
          <el-descriptions-item :label="t('report.report.sealAlg')">
            {{ verifyResult.alg || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('report.report.sealBy')">
            {{ verifyResult.sealedBy || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('report.report.sealAt')">
            {{ verifyResult.sealedAt || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('report.report.sealContentHash')">
            <span class="hash-text">{{ verifyResult.contentHash || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item :label="t('report.report.sealReason')">
            {{ verifyResult.reason || '-' }}
          </el-descriptions-item>
        </el-descriptions>
      </template>
      <el-empty v-else :description="t('report.report.sealVerifyEmpty')" :image-size="60" />
    </div>
  </el-dialog>
</template>

<style scoped>
.verify-desc {
  margin-top: var(--bs-space-3);
}

.hash-text {
  font-family: var(--bs-typography-font-family-mono);
  font-size: var(--bs-typography-font-size-xs);
  word-break: break-all;
}
</style>
