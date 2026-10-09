<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import StatusTag from '@/components/common/StatusTag.vue'
import { getTask, sampleFlow } from '@/api/task'
import type { Task, TaskItem, TaskLog, TaskSample } from '@/api/types'

defineOptions({ name: 'TaskDetail' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const detail = ref<Task | null>(null)
const items = ref<TaskItem[]>([])
const samples = ref<TaskSample[]>([])
const logs = ref<TaskLog[]>([])
const loading = ref(false)
const activeTab = ref('basic')

async function load() {
  const id = Number(route.params.id)
  if (!id) return
  loading.value = true
  try {
    const data = await getTask(id)
    detail.value = data
    items.value = data.items ?? []
    samples.value = data.samples ?? []
    logs.value = data.logs ?? []
  } catch {
    detail.value = null
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())

async function doSampleFlow(row: TaskSample, action: 'in' | 'out') {
  if (!row.id) return
  const msg = action === 'in' ? t('task.task.inConfirm') : t('task.task.outConfirm')
  try {
    await ElMessageBox.confirm(msg, t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await sampleFlow(row.id, action)
    row.inStock = action === 'in' ? 'in' : 'out'
    ElMessage.success(t('common.message.submitSuccess'))
  } catch {
    /* http notifies */
  }
}
</script>

<template>
  <div class="task-detail" v-loading="loading">
    <div class="detail-header">
      <h2 class="detail-title">
        {{ detail?.taskName || t('task.task.detail') }}
        <StatusTag v-if="detail" :status="detail.status" i18n-prefix="task.task.status" />
      </h2>
      <el-button @click="router.push('/task/tasks')">{{ t('common.action.back') }}</el-button>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane :label="t('task.task.tabBasic')" name="basic">
        <el-descriptions v-if="detail" :column="2" border>
          <el-descriptions-item :label="t('task.task.taskNo')">{{ detail.taskNo }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.taskName')">{{ detail.taskName }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.taskType')">{{ detail.taskTypeLabel || detail.taskType }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.customerName')">{{ detail.customerName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.contractNo')">{{ detail.contractNo || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.bizBlock')">{{ detail.bizBlockLabel || detail.bizBlock || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.deptName')">{{ detail.deptName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.ownerName')">{{ detail.ownerName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.receiver')">{{ detail.receiver || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.receiverUnit')">{{ detail.receiverUnit || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.planFinishDate')">{{ detail.planFinishDate || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.partySystem')">{{ detail.partySystem || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.content')" :span="2">{{ detail.content || '-' }}</el-descriptions-item>
        </el-descriptions>
      </el-tab-pane>

      <el-tab-pane :label="t('task.task.tabItems')" name="items">
        <el-table :data="items" border stripe size="small">
          <el-table-column :label="t('task.task.itemCode')" prop="itemCode" width="120" />
          <el-table-column :label="t('task.task.itemName')" prop="name" min-width="140" />
          <el-table-column :label="t('task.task.itemStd')" prop="std" min-width="110" />
          <el-table-column :label="t('task.task.itemDept')" prop="dept" width="110" />
          <el-table-column :label="t('task.task.itemInspector')" prop="inspector" width="100" />
          <el-table-column :label="t('task.task.itemQty')" prop="qty" width="80" />
          <el-table-column :label="t('task.task.itemReportNo')" prop="reportNo" width="130" />
          <el-table-column :label="t('task.task.itemReportStatus')" prop="reportStatus" width="110" />
        </el-table>
      </el-tab-pane>

      <el-tab-pane :label="t('task.task.tabSamples')" name="samples">
        <el-table :data="samples" border stripe size="small">
          <el-table-column :label="t('task.task.sampleNo')" prop="sampleNo" width="130" />
          <el-table-column :label="t('task.task.sampleName')" prop="name" min-width="130" />
          <el-table-column :label="t('task.task.sampleModel')" prop="model" width="110" />
          <el-table-column :label="t('task.task.sampleVin')" prop="vin" width="140" />
          <el-table-column :label="t('task.task.sampleVehicleType')" prop="vehicleType" width="110" />
          <el-table-column :label="t('task.task.sampleDate')" prop="sampleDate" width="110" />
          <el-table-column :label="t('task.task.sampleInStock')" width="90">
            <template #default="{ row }">
              <StatusTag :status="String(row.inStock)" i18n-prefix="task.task.sampleStatus" />
            </template>
          </el-table-column>
          <el-table-column :label="t('common.action.operate')" width="150" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.inStock !== 'in'"
                link
                type="success"
                @click="doSampleFlow(row as unknown as TaskSample, 'in')"
              >
                {{ t('task.task.sampleIn') }}
              </el-button>
              <el-button
                v-if="row.inStock === 'in'"
                link
                type="warning"
                @click="doSampleFlow(row as unknown as TaskSample, 'out')"
              >
                {{ t('task.task.sampleOut') }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane :label="t('task.task.tabLogs')" name="logs">
        <el-table :data="logs" border stripe size="small">
          <el-table-column :label="t('task.task.logAction')" prop="action" width="120" />
          <el-table-column :label="t('task.task.logOperator')" prop="operatorName" width="120" />
          <el-table-column :label="t('task.task.logTime')" prop="createTime" width="160" />
          <el-table-column :label="t('task.task.logRemark')" prop="remark" min-width="180" />
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.task-detail {
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
</style>
