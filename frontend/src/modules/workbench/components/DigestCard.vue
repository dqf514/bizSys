<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import WidgetShell from './WidgetShell.vue'
import { getDailyDigest, pushDailyDigest } from '@/api/ai'
import { useAiCapabilities } from '@/composables/useAiCapabilities'
import type { DailyDigestResult } from '@/api/types'

defineOptions({ name: 'DigestCard' })

const { t } = useI18n()
const aiCaps = useAiCapabilities()

const capsReady = ref(false)
const loading = ref(false)
const pushing = ref(false)
const digest = ref<DailyDigestResult | null>(null)

// 摘要有降级模板（AI 不可用时仍可用），不依赖功能开关显隐
onMounted(async () => {
  await aiCaps.ensureLoaded()
  capsReady.value = true
})

async function generate() {
  if (loading.value) return
  loading.value = true
  try {
    digest.value = await getDailyDigest()
  } catch {
    /* http 层已提示 */
  } finally {
    loading.value = false
  }
}

async function push() {
  if (!digest.value || pushing.value) return
  pushing.value = true
  try {
    const r = await pushDailyDigest(digest.value.summary, digest.value.highlights)
    const channel = t(r.channel === 'wecom' ? 'ai.digest.channelWecom' : 'ai.digest.channelNotify')
    ElMessage.success(t('ai.digest.pushed', { channel }))
  } catch {
    /* http 层已提示 */
  } finally {
    pushing.value = false
  }
}
</script>

<template>
  <WidgetShell :title="t('workbench.widget.aiDigest')">
    <div v-if="!digest" class="digest-empty">
      <el-button
        type="primary"
        plain
        :loading="loading"
        :disabled="!capsReady"
        class="digest-generate-btn"
        @click="generate"
      >
        {{ t('ai.digest.generate') }}
      </el-button>
    </div>
    <template v-else>
      <el-alert
        v-if="digest.degraded"
        :title="t('ai.digest.degradedTip')"
        type="info"
        :closable="false"
        class="digest-degraded"
      />
      <div class="digest-summary">{{ digest.summary }}</div>
      <div v-if="digest.highlights.length" class="digest-highlights">
        <div class="digest-sub">{{ t('ai.digest.highlights') }}</div>
        <div v-for="(h, i) in digest.highlights" :key="i" class="digest-highlight">· {{ h }}</div>
      </div>
      <div class="digest-actions">
        <el-button size="small" :loading="loading" @click="generate">
          {{ t('ai.digest.regenerate') }}
        </el-button>
        <el-button size="small" type="primary" :loading="pushing" class="digest-push-btn" @click="push">
          {{ t('ai.digest.push') }}
        </el-button>
      </div>
    </template>
  </WidgetShell>
</template>

<style scoped>
.digest-empty {
  padding: var(--bs-space-4) 0;
  text-align: center;
}

.digest-degraded {
  margin-bottom: var(--bs-space-2);
}

.digest-summary {
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-default);
  line-height: 1.8;
}

.digest-highlights {
  margin-top: var(--bs-space-2);
}

.digest-sub {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
  margin-bottom: var(--bs-space-1);
}

.digest-highlight {
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-secondary);
  line-height: 1.8;
}

.digest-actions {
  margin-top: var(--bs-space-3);
  display: flex;
  justify-content: flex-end;
  gap: var(--bs-space-2);
}
</style>
