<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import StatusTag from '@/components/common/StatusTag.vue'
import ApprovalTimeline from '@/components/approval/ApprovalTimeline.vue'
import { getContract, downloadAttachment, voidContract } from '@/api/contract'
import { getTimeline } from '@/api/approval'
import { listTasks } from '@/api/task'
import { listReports } from '@/api/report'
import type { Attachment, Contract, Report, Task, TimelineRecord } from '@/api/types'

defineOptions({ name: 'ContractDetail' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const detail = ref<Contract | null>(null)
const attachments = ref<Attachment[]>([])
const records = ref<TimelineRecord[]>([])
const loading = ref(false)
const timelineLoading = ref(false)
const activeTab = ref('basic')

/* ---------- 任务与报告（页签首次激活时加载） ---------- */
const tasks = ref<Task[]>([])
const reports = ref<Report[]>([])
const tasksLoading = ref(false)
const reportsLoading = ref(false)
let tasksReportsLoaded = false

async function loadTasksReports() {
  const id = Number(route.params.id)
  if (!id) return
  tasksLoading.value = true
  reportsLoading.value = true
  try {
    const data = await listTasks({ page: 1, size: 100, filters: { contract_id: id } })
    tasks.value = data.items ?? []
  } catch {
    tasks.value = []
  } finally {
    tasksLoading.value = false
  }
  try {
    const data = await listReports({ page: 1, size: 100, filters: { contract_id: id } })
    reports.value = data.items ?? []
  } catch {
    reports.value = []
  } finally {
    reportsLoading.value = false
  }
}

watch(activeTab, (tab) => {
  if (tab === 'tasksReports' && !tasksReportsLoaded) {
    tasksReportsLoaded = true
    void loadTasksReports()
  }
})

function openTask(row: Task) {
  router.push(`/task/tasks/${row.id}`)
}

async function load() {
  const id = Number(route.params.id)
  if (!id) return
  loading.value = true
  try {
    const data = await getContract(id)
    detail.value = data
    attachments.value = data.attachments ?? []
    if (data.flowInstanceId || data.status === 'approving' || data.status === 'approved') {
      timelineLoading.value = true
      try {
        const tl = await getTimeline('contract', id)
        records.value = tl.records ?? []
      } catch {
        records.value = []
      } finally {
        timelineLoading.value = false
      }
    }
  } catch {
    detail.value = null
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())

async function doVoid() {
  if (!detail.value) return
  try {
    await ElMessageBox.confirm(t('contract.contract.voidConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await voidContract(detail.value.id)
    ElMessage.success(t('common.message.submitSuccess'))
    void load()
  } catch {
    /* http notifies */
  }
}
</script>

<template>
  <div class="contract-detail" v-loading="loading">
    <div class="detail-header">
      <h2 class="detail-title">
        {{ detail?.name || t('contract.contract.detail') }}
        <StatusTag v-if="detail" :status="detail.status" i18n-prefix="contract.contract.status" />
      </h2>
      <div class="header-actions">
        <el-button
          v-if="detail && ['draft', 'rejected', 'approved'].includes(detail.status)"
          v-permission="'contract:edit'"
          type="danger"
          plain
          @click="doVoid"
        >
          {{ t('contract.contract.void') }}
        </el-button>
        <el-button @click="router.push('/contract/contracts')">{{ t('common.action.back') }}</el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane :label="t('contract.contract.tabBasic')" name="basic">
        <el-descriptions v-if="detail" :column="2" border>
          <el-descriptions-item :label="t('contract.contract.contractNo')">{{ detail.contractNo }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.name')">{{ detail.name }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.customerName')">{{ detail.customerName }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.contractType')">{{ detail.contractType || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.amount')">{{ detail.amount }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.subjectType')">{{ detail.subjectType || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.startDate')">{{ detail.startDate }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.endDate')">{{ detail.endDate }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.payCycle')">{{ detail.payCycle || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.delivery')">{{ detail.delivery || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.sealType')">{{ detail.sealType || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.handlerName')">{{ detail.handlerName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.frameworkNo')">{{ detail.frameworkNo || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.paymentOrg')">{{ detail.paymentOrg || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.remark')" :span="2">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>
      </el-tab-pane>

      <el-tab-pane :label="t('contract.contract.tabAttachments')" name="attachments">
        <div class="file-list">
          <div v-for="f in attachments" :key="String(f.id)" class="file-row">
            <span>{{ f.fileName }}</span>
            <el-button link type="primary" @click="downloadAttachment(f.id, f.fileName)">
              {{ t('common.action.download') }}
            </el-button>
          </div>
          <el-empty v-if="!attachments.length" :description="t('common.table.empty')" :image-size="60" />
        </div>
      </el-tab-pane>

      <el-tab-pane :label="t('contract.contract.tabTimeline')" name="timeline">
        <ApprovalTimeline :records="records" :loading="timelineLoading" />
      </el-tab-pane>

      <el-tab-pane :label="t('contract.contract.tabTasksReports')" name="tasksReports">
        <div class="tasks-reports">
          <div class="section-title">{{ t('contract.contract.relatedTasks') }}</div>
          <el-table v-loading="tasksLoading" :data="tasks" border stripe size="small">
            <el-table-column :label="t('task.task.taskNo')" width="150">
              <template #default="{ row }">
                <el-button link type="primary" @click="openTask(row as unknown as Task)">{{ row.taskNo }}</el-button>
              </template>
            </el-table-column>
            <el-table-column :label="t('task.task.taskName')" prop="taskName" min-width="160" />
            <el-table-column :label="t('common.form.status')" width="110">
              <template #default="{ row }">
                <StatusTag :status="String(row.status)" i18n-prefix="task.task.status" />
              </template>
            </el-table-column>
            <el-table-column :label="t('task.task.createTime')" prop="createTime" width="160" />
          </el-table>

          <div class="section-title">{{ t('contract.contract.relatedReports') }}</div>
          <el-table v-loading="reportsLoading" :data="reports" border stripe size="small">
            <el-table-column :label="t('report.report.reportNo')" prop="reportNo" width="150" />
            <el-table-column :label="t('report.report.taskNo')" prop="taskNo" width="140" />
            <el-table-column :label="t('report.report.itemName')" prop="itemName" min-width="130" />
            <el-table-column :label="t('common.form.status')" width="110">
              <template #default="{ row }">
                <StatusTag :status="String(row.status)" i18n-prefix="report.report.status" />
              </template>
            </el-table-column>
            <el-table-column :label="t('report.report.createTime')" prop="createTime" width="160" />
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.contract-detail {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
  padding: var(--bs-space-4);
  height: 100%;
  overflow: auto;
  background: var(--bs-color-bg-surface);
}

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.detail-title {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.file-list {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.file-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-sm);
}

.tasks-reports {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}

.section-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}
</style>
