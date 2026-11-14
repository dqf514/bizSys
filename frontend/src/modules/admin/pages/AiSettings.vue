<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { getAiCenterSettings, listAiPrompts, updateAiCenterSettings } from '@/api/ai'
import type { AiFeatureKey, AiMaskingLevel, AiModelPrice, AiPromptInfo } from '@/api/types'

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
  'sample_ocr',
  'invoice_ocr',
  'price_ref',
  'assistant',
  'daily_digest',
  'knowledge',
]

const MASKING_LEVELS: AiMaskingLevel[] = ['off', 'standard', 'strict']

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
  sample_ocr: true,
  invoice_ocr: true,
  price_ref: true,
  assistant: true,
  daily_digest: true,
  knowledge: true,
})
const quota = reactive({
  userDailyCalls: 0,
  userDailyTokens: 0,
  globalDailyTokens: 0,
})
const masking = ref<AiMaskingLevel>('standard')
const modelPrices = ref<AiModelPrice[]>([])
const prompts = ref<AiPromptInfo[]>([])

function addPriceRow() {
  modelPrices.value.push({ model: '', input: 0, output: 0 })
}

function removePriceRow(idx: number) {
  modelPrices.value.splice(idx, 1)
}

async function load() {
  loading.value = true
  try {
    const data = await getAiCenterSettings()
    globalEnabled.value = data.enabled
    for (const f of FEATURES) features[f] = data.features[f] ?? true
    quota.userDailyCalls = data.quota.userDailyCalls
    quota.userDailyTokens = data.quota.userDailyTokens
    quota.globalDailyTokens = data.quota.globalDailyTokens
    masking.value = data.masking
    modelPrices.value = data.modelPrices.map((p) => ({ ...p }))
    prompts.value = await listAiPrompts()
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
      masking: masking.value,
      modelPrices: modelPrices.value.filter((p) => p.model.trim()),
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

    <el-card shadow="never" class="settings-card">
      <template #header>{{ t('ai.settings.masking') }}</template>
      <el-form label-width="220px">
        <el-form-item :label="t('ai.settings.maskingLevel')">
          <el-radio-group v-model="masking">
            <el-radio v-for="lv in MASKING_LEVELS" :key="lv" :value="lv">
              {{ t(`ai.settings.masking_${lv}`) }}
            </el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item>
          <div class="field-tip">{{ t('ai.settings.maskingTip') }}</div>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="settings-card settings-card-wide">
      <template #header>{{ t('ai.settings.modelPrices') }}</template>
      <div class="field-tip">{{ t('ai.settings.modelPricesTip') }}</div>
      <el-table :data="modelPrices" size="small" class="price-table">
        <el-table-column :label="t('ai.settings.priceModel')">
          <template #default="{ row }">
            <el-input v-model="row.model" :placeholder="t('ai.settings.priceModelPlaceholder')" />
          </template>
        </el-table-column>
        <el-table-column :label="t('ai.settings.priceInput')" width="180">
          <template #default="{ row }">
            <el-input-number v-model="row.input" :min="0" :max="1000" :precision="4" :step="0.1" controls-position="right" />
          </template>
        </el-table-column>
        <el-table-column :label="t('ai.settings.priceOutput')" width="180">
          <template #default="{ row }">
            <el-input-number v-model="row.output" :min="0" :max="1000" :precision="4" :step="0.1" controls-position="right" />
          </template>
        </el-table-column>
        <el-table-column width="70" align="center">
          <template #default="{ $index }">
            <el-button link type="danger" @click="removePriceRow($index)">
              {{ t('common.action.delete') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-button class="add-price" @click="addPriceRow">{{ t('ai.settings.addPrice') }}</el-button>
    </el-card>

    <el-card shadow="never" class="settings-card settings-card-wide">
      <template #header>{{ t('ai.settings.prompts') }}</template>
      <div class="field-tip">{{ t('ai.settings.promptsTip') }}</div>
      <el-table :data="prompts" size="small" max-height="360">
        <el-table-column prop="name" :label="t('ai.settings.promptName')" width="160" />
        <el-table-column :label="t('ai.settings.promptFeature')" width="150">
          <template #default="{ row }">
            {{ t(`ai.feature.${row.feature}`) }}
          </template>
        </el-table-column>
        <el-table-column prop="version" :label="t('ai.settings.promptVersion')" width="80" align="center" />
        <el-table-column prop="systemPreview" :label="t('ai.settings.promptPreview')" show-overflow-tooltip />
      </el-table>
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

.settings-card-wide {
  max-width: 960px;
}

.field-tip {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs, 12px);
  line-height: 1.6;
  margin-bottom: var(--bs-space-2);
}

.price-table {
  margin-bottom: var(--bs-space-2);
}

.add-price {
  margin-top: var(--bs-space-1);
}

.save-bar {
  max-width: 960px;
  display: flex;
  justify-content: flex-end;
}
</style>
