<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import StatusTag from '@/components/common/StatusTag.vue'
import ApprovalTimeline from '@/components/approval/ApprovalTimeline.vue'
import { getReport } from '@/api/report'
import { aiReportSummary, updateReportRemark } from '@/api/ai'
import { useAiCapabilities } from '@/composables/useAiCapabilities'
import type { ReportDetail } from '@/api/types'

defineOptions({ name: 'ReportDetailDrawer' })

const props = defineProps<{
  modelValue: boolean
  reportId: number | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
}>()

const { t } = useI18n()
const router = useRouter()

function go(path: string) {
  visible.value = false
  router.push(path)
}

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const loading = ref(false)
const detail = ref<ReportDetail | null>(null)

async function load(id: number) {
  loading.value = true
  try {
    detail.value = await getReport(id)
  } catch {
    detail.value = null
  } finally {
    loading.value = false
  }
}

watch(
  [() => props.modelValue, () => props.reportId],
  ([v, id]) => {
    detail.value = null
    if (v && id) void load(id)
  },
  { immediate: true },
)

// ---------------- AI 报告摘要（草稿 → 人工编辑 → 采用才写 remark） ----------------

const aiCaps = useAiCapabilities()
const summaryVisible = ref(false)
const summaryLoading = ref(false)
const summaryAdopting = ref(false)
const summaryText = ref('')

const remarkEditable = computed(() => ['uploaded', 'rejected'].includes(detail.value?.status ?? ''))

async function openSummary() {
  await aiCaps.ensureLoaded()
  if (!aiCaps.featureOn('report_summary')) {
    ElMessage.warning(t(aiCaps.caps.value.enabled ? 'ai.common.featureDisabled' : 'ai.common.notConfigured'))
    return
  }
  if (!props.reportId) return
  summaryVisible.value = true
  summaryLoading.value = true
  summaryText.value = ''
  try {
    const draft = await aiReportSummary(props.reportId)
    summaryText.value = draft.summary
  } catch {
    summaryVisible.value = false
  } finally {
    summaryLoading.value = false
  }
}

async function adoptSummary() {
  if (!props.reportId) return
  summaryAdopting.value = true
  try {
    await updateReportRemark(props.reportId, summaryText.value)
    ElMessage.success(t('ai.reportSummary.adopted'))
    summaryVisible.value = false
    if (detail.value) detail.value.remark = summaryText.value
  } catch {
    /* http notifies */
  } finally {
    summaryAdopting.value = false
  }
}
</script>

<template>
  <el-drawer v-model="visible" :title="t('report.report.detail')" size="640px" append-to-body>
    <div v-loading="loading" class="drawer-body">
      <template v-if="detail">
        <div class="drawer-actions">
          <el-button v-permission="'report:create'" size="small" type="primary" plain @click="openSummary">
            {{ t('ai.reportSummary.button') }}
          </el-button>
          <el-tooltip
            v-if="!remarkEditable"
            :content="t('ai.reportSummary.lockedTip')"
            placement="top"
          >
            <el-icon class="lock-hint"><InfoFilled /></el-icon>
          </el-tooltip>
        </div>
        <el-descriptions :column="2" border>
          <el-descriptions-item :label="t('report.report.reportNo')">{{ detail.reportNo }}</el-descriptions-item>
          <el-descriptions-item :label="t('report.report.taskNo')">
            <el-link v-if="detail.taskId" type="primary" @click="go(`/task/tasks/${detail.taskId}`)">
              {{ detail.taskNo }}
            </el-link>
            <span v-else>{{ detail.taskNo || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item :label="t('report.report.contractNo')">
            <el-link v-if="detail.contractId" type="primary" @click="go(`/contract/contracts/${detail.contractId}`)">
              {{ detail.contractNo }}
            </el-link>
            <span v-else>{{ detail.contractNo || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item :label="t('report.report.itemName')">{{ detail.itemName }}</el-descriptions-item>
          <el-descriptions-item :label="t('report.report.customerName')">
            <el-link v-if="detail.customerId" type="primary" @click="go(`/crm/customers?detail=${detail.customerId}`)">
              {{ detail.customerName }}
            </el-link>
            <span v-else>{{ detail.customerName || '-' }}</span>
          </el-descriptions-item>
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

    <el-dialog v-model="summaryVisible" :title="t('ai.reportSummary.dialogTitle')" width="640px" append-to-body>
      <div v-loading="summaryLoading">
        <template v-if="summaryLoading">
          <div class="summary-loading">{{ t('ai.reportSummary.generating') }}</div>
        </template>
        <template v-else>
          <el-alert type="info" :closable="false" :title="t('ai.common.aiDraftTip')" class="summary-tip" />
          <el-input
            v-model="summaryText"
            type="textarea"
            :rows="10"
            maxlength="4000"
            show-word-limit
            :disabled="!remarkEditable"
          />
          <div v-if="!remarkEditable" class="summary-locked">{{ t('ai.reportSummary.lockedTip') }}</div>
        </template>
      </div>
      <template #footer>
        <el-button @click="summaryVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button
          type="primary"
          :loading="summaryAdopting"
          :disabled="summaryLoading || !remarkEditable || !summaryText.trim()"
          @click="adoptSummary"
        >
          {{ t('ai.reportSummary.adopt') }}
        </el-button>
      </template>
    </el-dialog>
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

.drawer-actions {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.lock-hint {
  color: var(--bs-color-fg-muted);
}

.summary-loading {
  padding: var(--bs-space-4);
  text-align: center;
  color: var(--bs-color-fg-secondary);
}

.summary-tip {
  margin-bottom: var(--bs-space-3);
}

.summary-locked {
  margin-top: var(--bs-space-2);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}
</style>
