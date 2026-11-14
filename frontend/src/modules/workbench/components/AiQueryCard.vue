<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { ChatLineRound } from '@element-plus/icons-vue'
import WidgetShell from './WidgetShell.vue'
import { aiNlQuery } from '@/api/ai'
import { useAiCapabilities } from '@/composables/useAiCapabilities'
import type { NlQueryAnswer } from '@/api/types'

defineOptions({ name: 'AiQueryCard' })

const { t } = useI18n()
const router = useRouter()
const aiCaps = useAiCapabilities()

const capsReady = ref(false)
const asking = ref(false)
const question = ref('')
const answer = ref<NlQueryAnswer | null>(null)
/** 对话式追问上下文：回传上一轮的域与时间范围 */
const lastContext = ref<{ domain: string; timeFrom: string; timeTo: string } | null>(null)

const featureReady = computed(() => aiCaps.featureOn('nl_query'))
const notReadyTip = computed(() =>
  t(aiCaps.caps.value.enabled ? 'ai.common.featureDisabled' : 'ai.common.notConfigured'),
)

onMounted(async () => {
  await aiCaps.ensureLoaded()
  capsReady.value = true
})

async function ask() {
  const q = question.value.trim()
  if (!q || asking.value) return
  await aiCaps.ensureLoaded()
  if (!aiCaps.featureOn('nl_query')) {
    ElMessage.warning(notReadyTip.value)
    return
  }
  asking.value = true
  try {
    answer.value = await aiNlQuery(q, lastContext.value ?? undefined)
    lastContext.value = {
      domain: answer.value.domain,
      timeFrom: answer.value.timeRange.from,
      timeTo: answer.value.timeRange.to,
    }
  } catch {
    /* http layer already notified */
  } finally {
    asking.value = false
  }
}

function go() {
  if (answer.value?.link) router.push(answer.value.link)
}
</script>

<template>
  <WidgetShell :title="t('workbench.widget.aiQuery')">
    <div v-if="capsReady && !featureReady" class="nlq-hint">{{ notReadyTip }}</div>
    <template v-else>
      <div class="nlq-input">
        <el-input
          v-model="question"
          :placeholder="t('ai.nlQuery.placeholder')"
          clearable
          @keyup.enter="ask"
        >
          <template #prefix>
            <el-icon><ChatLineRound /></el-icon>
          </template>
        </el-input>
        <el-button type="primary" :loading="asking" :disabled="!question.trim()" @click="ask">
          {{ t('ai.nlQuery.ask') }}
        </el-button>
      </div>

      <div v-if="answer" class="nlq-answer">
        <div class="nlq-answer-head">
          <el-tag size="small" effect="plain">{{ answer.domainLabel }}</el-tag>
          <span v-if="answer.timeRange.from || answer.timeRange.to" class="nlq-range">
            {{ answer.timeRange.from || '…' }} ~ {{ answer.timeRange.to || '…' }}
          </span>
        </div>
        <div class="nlq-text">{{ answer.text }}</div>
        <div v-for="(row, i) in answer.rows" :key="i" class="nlq-row">
          <span class="nlq-row-label">{{ row.label }}</span>
          <span class="nlq-row-value">{{ row.value }}</span>
        </div>
        <div class="nlq-criteria">{{ answer.criteria }}</div>
        <el-button v-if="answer.link" link type="primary" size="small" class="nlq-goto" @click="go">
          {{ t('ai.nlQuery.gotoList') }}
        </el-button>
      </div>
      <div v-else class="nlq-examples">{{ t('ai.nlQuery.examples') }}</div>
    </template>
  </WidgetShell>
</template>

<style scoped>
.nlq-hint {
  padding: var(--bs-space-4) 0;
  text-align: center;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.nlq-input {
  display: flex;
  gap: var(--bs-space-2);
}

.nlq-answer {
  margin-top: var(--bs-space-3);
  padding: var(--bs-space-3);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-app);
}

.nlq-answer-head {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  margin-bottom: var(--bs-space-2);
}

.nlq-range {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.nlq-text {
  font-size: var(--bs-typography-font-size-sm);
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.nlq-row {
  display: flex;
  justify-content: space-between;
  gap: var(--bs-space-3);
  padding: var(--bs-space-1) 0;
  font-size: var(--bs-typography-font-size-sm);
}

.nlq-row-label {
  color: var(--bs-color-fg-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nlq-row-value {
  flex-shrink: 0;
  color: var(--bs-color-fg-default);
}

.nlq-criteria {
  margin-top: var(--bs-space-2);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.nlq-goto {
  margin-top: var(--bs-space-1);
  padding: 0;
}

.nlq-examples {
  margin-top: var(--bs-space-3);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
  line-height: 1.8;
  white-space: pre-line;
}
</style>
