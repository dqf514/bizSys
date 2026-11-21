<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { askKnowledge, downloadKnowledgeAttachment } from '@/api/ai'
import { useAiCapabilities } from '@/composables/useAiCapabilities'
import type { KnowledgeAskResult } from '@/api/types'

defineOptions({ name: 'KnowledgeAsk' })

const { t } = useI18n()
const aiCaps = useAiCapabilities()

const question = ref('')
const asking = ref(false)
const result = ref<KnowledgeAskResult | null>(null)

onMounted(() => void aiCaps.ensureLoaded())

async function ask() {
  const q = question.value.trim()
  if (!q || asking.value) return
  asking.value = true
  try {
    result.value = await askKnowledge(q)
  } catch {
    /* http 层已提示 */
  } finally {
    asking.value = false
  }
}
</script>

<template>
  <div class="bs-page bs-page--narrow kb-ask">
    <div class="kb-ask-head">
      <h3 class="kb-title">{{ t('ai.knowledge.askTitle') }}</h3>
    </div>
    <div class="kb-input">
      <el-input
        v-model="question"
        :placeholder="t('ai.knowledge.askPlaceholder')"
        clearable
        class="kb-question"
        @keyup.enter="ask"
      />
      <el-button type="primary" :loading="asking" :disabled="!question.trim()" @click="ask">
        {{ t('ai.knowledge.ask') }}
      </el-button>
    </div>

    <template v-if="result">
      <el-alert
        v-if="result.degraded"
        :title="t('ai.knowledge.degradedTip')"
        type="info"
        :closable="false"
        class="kb-degraded"
      />
      <div v-if="result.answer" class="kb-answer">{{ result.answer }}</div>
      <div v-if="result.sources.length" class="kb-sources">
        {{ t('ai.knowledge.sources') }}：
        <el-tag v-for="s in result.sources" :key="s.id" size="small" effect="plain" class="kb-source-tag">
          {{ s.title }}
        </el-tag>
      </div>
      <template v-if="result.entries.length">
        <div v-for="e in result.entries" :key="e.id" class="kb-entry">
          <div class="kb-entry-head">
            <span class="kb-entry-title">{{ e.title }}</span>
            <el-tag v-if="e.category" size="small" effect="plain">{{ e.category }}</el-tag>
            <el-button
              v-if="e.hasAttachment"
              link
              type="primary"
              size="small"
              @click="downloadKnowledgeAttachment(e.id, e.attachmentName || 'attachment')"
            >
              {{ t('ai.knowledge.download') }}
            </el-button>
          </div>
          <div class="kb-entry-excerpt">{{ e.excerpt }}</div>
        </div>
      </template>
      <el-empty
        v-else-if="!result.answer"
        :description="t('ai.knowledge.noHit')"
        :image-size="60"
      />
    </template>
  </div>
</template>

<style scoped>
.kb-title {
  margin: 0 0 var(--bs-space-3);
  font-size: var(--bs-typography-font-size-lg);
  color: var(--bs-color-fg-default);
}

.kb-input {
  display: flex;
  gap: var(--bs-space-2);
}

.kb-degraded {
  margin-top: var(--bs-space-3);
}

.kb-answer {
  margin-top: var(--bs-space-3);
  padding: var(--bs-space-3);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
  color: var(--bs-color-fg-default);
  font-size: var(--bs-typography-font-size-sm);
  line-height: 1.8;
  white-space: pre-line;
}

.kb-sources {
  margin-top: var(--bs-space-2);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.kb-source-tag {
  margin-right: var(--bs-space-1);
}

.kb-entry {
  margin-top: var(--bs-space-3);
  padding: var(--bs-space-3);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
}

.kb-entry-head {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.kb-entry-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.kb-entry-excerpt {
  margin-top: var(--bs-space-1);
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-sm);
  line-height: 1.7;
  white-space: pre-line;
}
</style>
