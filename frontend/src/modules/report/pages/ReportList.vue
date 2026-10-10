<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import RemoteSelect, { type RemoteOption } from '@/components/form/RemoteSelect.vue'
import ApprovalTimeline from '@/components/approval/ApprovalTimeline.vue'
import { useListPage } from '@/composables/useListPage'
import {
  listReports,
  reportItemOptions,
  uploadReport,
  submitReport,
  sealReport,
  getReport,
  downloadReport,
  exportReports,
} from '@/api/report'
import type { Report, ReportDetail } from '@/api/types'

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
  { prop: 'itemName', labelKey: 'report.report.itemName', minWidth: 130 },
  { prop: 'customerName', labelKey: 'report.report.customerName', minWidth: 140 },
  { prop: 'fileName', labelKey: 'report.report.fileName', minWidth: 160 },
  { prop: 'status', labelKey: 'common.form.status', width: 110 },
  { prop: 'createBy', labelKey: 'report.report.createBy', width: 100 },
  { prop: 'createTime', labelKey: 'report.report.createTime', width: 160 },
]

/* ---------- upload dialog ---------- */
const uploadVisible = ref(false)
const uploadSaving = ref(false)
const uploadForm = reactive({ itemId: null as number | null })
const pickedFile = ref<File | null>(null)
const fileInputRef = ref<HTMLInputElement>()

async function fetchItemOptions(q: string): Promise<RemoteOption[]> {
  try {
    const options = await reportItemOptions(q)
    return (options ?? []).map((x) => ({ id: x.value, label: x.label, sub: x.sub }))
  } catch {
    return []
  }
}

function openUpload() {
  uploadForm.itemId = null
  pickedFile.value = null
  uploadVisible.value = true
}

function pickFile() {
  fileInputRef.value?.click()
}

function onFilePicked(e: Event) {
  const input = e.target as HTMLInputElement
  pickedFile.value = input.files?.[0] ?? null
  input.value = ''
}

async function saveUpload() {
  if (!uploadForm.itemId || !pickedFile.value) {
    ElMessage.warning(pickedFile.value ? t('common.form.required') : t('report.report.noFile'))
    return
  }
  uploadSaving.value = true
  try {
    await uploadReport(uploadForm.itemId, pickedFile.value)
    ElMessage.success(t('common.message.createSuccess'))
    uploadVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    uploadSaving.value = false
  }
}

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
const detailLoading = ref(false)
const detail = ref<ReportDetail | null>(null)

async function openDetail(row: Report) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await getReport(row.id)
  } catch {
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}
</script>

<template>
  <ListPage :title="t('report.report.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'report:create'" type="primary" @click="openUpload">
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

  <el-dialog v-model="uploadVisible" :title="t('report.report.upload')" width="560px" append-to-body>
    <el-form label-width="110px">
      <el-form-item :label="t('report.report.selectItem')" required>
        <RemoteSelect v-model="uploadForm.itemId" :fetch="fetchItemOptions" />
        <div class="form-tip">{{ t('report.report.selectItemTip') }}</div>
      </el-form-item>
      <el-form-item :label="t('report.report.selectFile')" required>
        <div class="file-pick">
          <el-button @click="pickFile">{{ t('report.report.selectFile') }}</el-button>
          <span v-if="pickedFile" class="file-name bs-truncate">{{ pickedFile.name }}</span>
        </div>
        <div class="form-tip">{{ t('report.report.fileTip') }}</div>
      </el-form-item>
    </el-form>
    <input ref="fileInputRef" type="file" accept=".pdf,.doc,.docx" class="hidden-input" @change="onFilePicked" />
    <template #footer>
      <el-button @click="uploadVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="uploadSaving" @click="saveUpload">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>

  <el-drawer v-model="detailVisible" :title="t('report.report.detail')" size="640px">
    <div v-loading="detailLoading" class="drawer-body">
      <template v-if="detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item :label="t('report.report.reportNo')">{{ detail.reportNo }}</el-descriptions-item>
          <el-descriptions-item :label="t('report.report.taskNo')">{{ detail.taskNo }}</el-descriptions-item>
          <el-descriptions-item :label="t('report.report.itemName')">{{ detail.itemName }}</el-descriptions-item>
          <el-descriptions-item :label="t('report.report.customerName')">{{ detail.customerName }}</el-descriptions-item>
          <el-descriptions-item :label="t('report.report.fileName')">{{ detail.fileName }}</el-descriptions-item>
          <el-descriptions-item :label="t('common.form.status')">
            <StatusTag :status="detail.status" i18n-prefix="report.report.status" />
          </el-descriptions-item>
          <el-descriptions-item :label="t('report.report.createBy')">{{ detail.createBy || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('report.report.createTime')">{{ detail.createTime || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('report.report.sealBy')">{{ detail.sealBy || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('report.report.sealTime')">{{ detail.sealTime || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('report.report.remark')" :span="2">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div class="section-title">{{ t('report.report.timeline') }}</div>
        <ApprovalTimeline :records="detail.timeline ?? []" />
      </template>
    </div>
  </el-drawer>
</template>

<style scoped>
.drawer-body {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}

.section-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.form-tip {
  width: 100%;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}

.file-pick {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  width: 100%;
}

.file-name {
  flex: 1;
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-sm);
}

.hidden-input {
  display: none;
}
</style>
