<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import ReportUploadDialog from '../components/ReportUploadDialog.vue'
import ReportDetailDrawer from '../components/ReportDetailDrawer.vue'
import { useListPage } from '@/composables/useListPage'
import {
  listReports,
  submitReport,
  sealReport,
  downloadReport,
  exportReports,
} from '@/api/report'
import type { Report } from '@/api/types'

defineOptions({ name: 'ReportList' })

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'report.report.searchQ', placeholderKey: 'report.report.placeholderQ', width: 260 },
]

const statusTabs: StatusTabItem[] = [
  { value: 'uploaded', labelKey: 'report.report.status.uploaded' },
  { value: 'approving', labelKey: 'report.report.status.approving' },
  { value: 'approved', labelKey: 'report.report.status.approved' },
  { value: 'rejected', labelKey: 'report.report.status.rejected' },
  { value: 'sealed', labelKey: 'report.report.status.sealed' },
  { value: 'all', labelKey: 'common.action.all' },
]

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
})

const columns: ListColumn[] = [
  { prop: 'reportNo', labelKey: 'report.report.reportNo', width: 150, fixed: 'left' },
  { prop: 'taskNo', labelKey: 'report.report.taskNo', width: 140 },
  { prop: 'contractNo', labelKey: 'report.report.contractNo', width: 140 },
  { prop: 'itemName', labelKey: 'report.report.itemName', minWidth: 130 },
  { prop: 'customerName', labelKey: 'report.report.customerName', minWidth: 140 },
  { prop: 'fileName', labelKey: 'report.report.fileName', minWidth: 160 },
  { prop: 'status', labelKey: 'common.form.status', width: 110 },
  { prop: 'createBy', labelKey: 'report.report.createBy', width: 100 },
  { prop: 'createTime', labelKey: 'report.report.createTime', width: 160 },
]

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
          <el-table-column :label="t('common.action.operate')" width="330" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openDetail(row as unknown as Report)">
                {{ t('common.action.detail') }}
              </el-button>
              <el-button
                v-if="row.status === 'uploaded' || row.status === 'rejected'"
                v-permission="'report:submit'"
                link
                type="warning"
                @click="doSubmit(row as unknown as Report)"
              >
                {{ t('report.report.submit') }}
              </el-button>
              <el-button
                v-if="row.status === 'approved'"
                v-permission="'report:seal'"
                link
                type="danger"
                @click="doSeal(row as unknown as Report)"
              >
                {{ t('report.report.seal') }}
              </el-button>
              <el-button link type="primary" @click="doDownload(row as unknown as Report, false)">
                {{ t('report.report.downloadRaw') }}
              </el-button>
              <el-button
                v-if="row.pdfReady"
                link
                type="success"
                @click="doDownload(row as unknown as Report, true)"
              >
                {{ t('report.report.downloadPdf') }}
              </el-button>
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <ReportUploadDialog v-model="uploadVisible" @uploaded="list.refresh()" />

  <ReportDetailDrawer v-model="detailVisible" :report-id="detailId" />
</template>
