<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { getAiCenterSettings, updateAiCenterSettings } from '@/api/ai'
import type { AiFeatureKey } from '@/api/types'

defineOptions({ name: 'AiSettings' })

const { t } = useI18n()

const FEATURES: AiFeatureKey[] = [
  'quote',
  'contract_ocr',
  'task_photo',
  'report_summary',
  'approval_assist',
  'contract_risk',
  'report_assist',
  'nl_query',
  'hr_prefill',
  'oa_prefill',
  'flow_route',
  'flow_anomaly',
  'tender_assist',
]

const loading = ref(false)
const saving = ref(false)
const globalEnabled = ref(false)
const features = reactive<Record<AiFeatureKey, boolean>>({
  quote: true,
  contract_ocr: true,
  task_photo: true,
  report_summary: true,
  approval_assist: true,
  contract_risk: true,
  report_assist: true,
  nl_query: true,
  hr_prefill: true,
  oa_prefill: true,
  flow_route: true,
  flow_anomaly: true,
  tender_assist: true,
})
const quota = reactive({
  userDailyCalls: 0,
  userDailyTokens: 0,
  globalDailyTokens: 0,
})

async function load() {
  loading.value = true
  try {
    const data = await getAiCenterSettings()
    globalEnabled.value = data.enabled
    for (const f of FEATURES) features[f] = data.features[f] ?? true
    quota.userDailyCalls = data.quota.userDailyCalls
    quota.userDailyTokens = data.quota.userDailyTokens
    quota.globalDailyTokens = data.quota.globalDailyTokens
  } catch {
    /* http layer already notified */
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    await updateAiCenterSettings({
      features: { ...features },
      quota: { ...quota },
    })
    ElMessage.success(t('common.message.saveSuccess'))
  } catch {
    /* http layer already notified */
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="ai-settings-page" v-loading="loading">
    <div class="page-title">{{ t('ai.settings.title') }}</div>

    <el-alert
      v-if="!globalEnabled"
      type="warning"
      :closable="false"
      :title="t('ai.settings.connectionTip')"
      class="connection-alert"
    />

    <el-card shadow="never" class="settings-card">
      <template #header>{{ t('ai.settings.featureSwitches') }}</template>
      <el-form label-width="220px">
        <el-form-item v-for="f in FEATURES" :key="f" :label="t(`ai.feature.${f}`)">
          <el-switch v-model="features[f]" />
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="settings-card">
      <template #header>{{ t('ai.settings.quota') }}</template>
      <el-form label-width="220px">
        <el-form-item :label="t('ai.settings.userDailyCalls')">
          <el-input-number v-model="quota.userDailyCalls" :min="0" :max="100000" />
        </el-form-item>
        <el-form-item :label="t('ai.settings.userDailyTokens')">
          <el-input-number v-model="quota.userDailyTokens" :min="0" :max="100000000" :step="10000" />
        </el-form-item>
        <el-form-item :label="t('ai.settings.globalDailyTokens')">
          <el-input-number v-model="quota.globalDailyTokens" :min="0" :max="100000000" :step="100000" />
        </el-form-item>
      </el-form>
    </el-card>

    <div class="save-bar">
      <el-button type="primary" :loading="saving" @click="save">{{ t('ai.settings.save') }}</el-button>
    </div>
  </div>
</template>

<style scoped>
.ai-settings-page {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
  height: 100%;
  min-height: 0;
  overflow: auto;
  padding: var(--bs-space-3);
}

.page-title {
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.settings-card {
  max-width: 720px;
}

.save-bar {
  max-width: 720px;
  display: flex;
  justify-content: flex-end;
}
</style>
