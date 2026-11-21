<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { CircleCheckFilled, InfoFilled, WarningFilled } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import StatusTag from '@/components/common/StatusTag.vue'
import ApprovalTimeline from '@/components/approval/ApprovalTimeline.vue'
import { getReport } from '@/api/report'
import { aiReportAssist, aiReportSummary, updateReportConclusion, updateReportRemark } from '@/api/ai'
import { useAiCapabilities } from '@/composables/useAiCapabilities'
import type { ReportAssistCheckItem, ReportAssistIssue, ReportAssistKind, ReportDetail } from '@/api/types'

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

// ---------------- AI 全文辅助（结论草稿 / 校对 / 完整性；仅结论采用后落库） ----------------

type AssistIssue = ReportAssistIssue & { state?: 'adopted' | 'ignored' }

const assistVisible = ref(false)
const assistKind = ref<ReportAssistKind>('conclusion')
const assistLoading = ref(false)
const assistAdopting = ref(false)
const assistConclusion = ref('')
const assistIssues = ref<AssistIssue[]>([])
const assistItems = ref<ReportAssistCheckItem[]>([])

const assistTitle = computed(() => t(`ai.reportAssist.title.${assistKind.value}`))

async function openAssist(kind: ReportAssistKind) {
  await aiCaps.ensureLoaded()
  if (!aiCaps.featureOn('report_assist')) {
    ElMessage.warning(t(aiCaps.caps.value.enabled ? 'ai.common.featureDisabled' : 'ai.common.notConfigured'))
    return
  }
  if (!props.reportId) return
  assistKind.value = kind
  assistVisible.value = true
  assistLoading.value = true
  assistConclusion.value = ''
  assistIssues.value = []
  assistItems.value = []
  try {
    const res = await aiReportAssist(props.reportId, kind)
    if (kind === 'conclusion') assistConclusion.value = res.conclusion ?? ''
    else if (kind === 'proofread') assistIssues.value = (res.issues ?? []).map((i) => ({ ...i }))
    else assistItems.value = res.items ?? []
  } catch {
    assistVisible.value = false
  } finally {
    assistLoading.value = false
  }
}

async function adoptConclusion() {
  if (!props.reportId) return
  assistAdopting.value = true
  try {
    await updateReportConclusion(props.reportId, assistConclusion.value)
    ElMessage.success(t('ai.reportAssist.adopted'))
    assistVisible.value = false
    if (detail.value) detail.value.conclusion = assistConclusion.value
  } catch {
    /* http notifies */
  } finally {
    assistAdopting.value = false
  }
}
</script>

<template>
  <el-drawer v-model="visible" :title="t('report.report.detail')" size="var(--bs-layout-drawer-md)" append-to-body>
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
        <div class="assist-bar">
          <span class="assist-label">{{ t('ai.reportAssist.section') }}</span>
          <el-button v-permission="'report:create'" size="small" plain @click="openAssist('conclusion')">
            {{ t('ai.reportAssist.conclusion') }}
          </el-button>
          <el-button v-permission="'report:create'" size="small" plain @click="openAssist('proofread')">
            {{ t('ai.reportAssist.proofread') }}
          </el-button>
          <el-button v-permission="'report:create'" size="small" plain @click="openAssist('completeness')">
            {{ t('ai.reportAssist.completeness') }}
          </el-button>
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
          <el-descriptions-item :label="t('report.report.conclusion')" :span="2">
            {{ detail.conclusion || '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <div class="section-title">{{ t('report.report.timeline') }}</div>
        <ApprovalTimeline :records="detail.timeline ?? []" />
      </template>
    </div>

    <el-dialog v-model="summaryVisible" :title="t('ai.reportSummary.dialogTitle')" width="var(--bs-layout-dialog-md)" append-to-body>
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
    <el-dialog v-model="assistVisible" :title="assistTitle" width="var(--bs-layout-dialog-lg)" append-to-body>
      <div v-loading="assistLoading">
        <template v-if="assistLoading">
          <div class="summary-loading">{{ t('ai.reportAssist.generating') }}</div>
        </template>
        <template v-else-if="assistKind === 'conclusion'">
          <el-alert type="info" :closable="false" :title="t('ai.common.aiDraftTip')" class="summary-tip" />
          <el-input
            v-model="assistConclusion"
            type="textarea"
            :rows="10"
            maxlength="4000"
            show-word-limit
            :disabled="!remarkEditable"
          />
          <div v-if="!remarkEditable" class="summary-locked">{{ t('ai.reportAssist.lockedTip') }}</div>
        </template>
        <template v-else-if="assistKind === 'proofread'">
          <el-alert type="info" :closable="false" :title="t('ai.reportAssist.onlyShowTip')" class="summary-tip" />
          <div v-if="!assistIssues.length" class="assist-empty">{{ t('ai.reportAssist.noIssues') }}</div>
          <div v-for="(issue, idx) in assistIssues" :key="idx" class="issue-row" :class="`is-${issue.state ?? ''}`">
            <div class="issue-body">
              <div v-if="issue.position" class="issue-position">{{ issue.position }}</div>
              <div class="issue-line">
                <span class="issue-tag">{{ t('ai.reportAssist.original') }}</span>{{ issue.original }}
              </div>
              <div class="issue-line">
                <span class="issue-tag">{{ t('ai.reportAssist.suggestion') }}</span>{{ issue.suggestion }}
              </div>
            </div>
            <div class="issue-actions">
              <el-button
                size="small" type="primary" plain :disabled="issue.state === 'adopted'"
                @click="issue.state = 'adopted'"
              >
                {{ issue.state === 'adopted' ? t('ai.reportAssist.adoptedState') : t('ai.reportAssist.adoptIssue') }}
              </el-button>
              <el-button
                size="small" plain :disabled="issue.state === 'ignored'" @click="issue.state = 'ignored'"
              >
                {{ issue.state === 'ignored' ? t('ai.reportAssist.ignoredState') : t('ai.reportAssist.ignoreIssue') }}
              </el-button>
            </div>
          </div>
        </template>
        <template v-else>
          <el-alert type="info" :closable="false" :title="t('ai.reportAssist.onlyShowTip')" class="summary-tip" />
          <div v-for="item in assistItems" :key="item.key + item.detail" class="check-row">
            <el-icon :class="item.ok ? 'check-ok' : 'check-bad'">
              <CircleCheckFilled v-if="item.ok" />
              <WarningFilled v-else />
            </el-icon>
            <span class="check-detail">{{ item.detail }}</span>
          </div>
        </template>
      </div>
      <template #footer>
        <el-button @click="assistVisible = false">{{ t('common.action.close') }}</el-button>
        <el-button
          v-if="assistKind === 'conclusion'"
          type="primary"
          :loading="assistAdopting"
          :disabled="assistLoading || !remarkEditable || !assistConclusion.trim()"
          @click="adoptConclusion"
        >
          {{ t('ai.reportAssist.adopt') }}
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

.assist-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--bs-space-2);
  padding: var(--bs-space-2) var(--bs-space-3);
  border: 1px dashed var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
}

.assist-label {
  font-size: var(--bs-typography-font-size-sm);
  font-weight: 600;
  color: var(--bs-color-fg-secondary);
}

.assist-empty {
  padding: var(--bs-space-4);
  text-align: center;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.issue-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--bs-space-3);
  padding: var(--bs-space-2) 0;
  border-bottom: 1px solid var(--bs-color-border-subtle);
}

.issue-row.is-adopted {
  opacity: 0.55;
}

.issue-row.is-ignored {
  opacity: 0.4;
}

.issue-position {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
  margin-bottom: var(--bs-space-1);
}

.issue-line {
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-default);
}

.issue-tag {
  display: inline-block;
  margin-right: var(--bs-space-2);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.issue-actions {
  display: flex;
  flex-shrink: 0;
  gap: var(--bs-space-1);
}

.check-row {
  display: flex;
  align-items: flex-start;
  gap: var(--bs-space-2);
  padding: var(--bs-space-1) 0;
}

.check-ok {
  color: var(--bs-color-semantic-success);
  margin-top: 2px;
}

.check-bad {
  color: var(--bs-color-semantic-warning);
  margin-top: 2px;
}

.check-detail {
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-default);
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
