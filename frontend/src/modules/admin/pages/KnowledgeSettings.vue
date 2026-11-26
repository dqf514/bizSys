<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import PageHeader from '@/components/common/PageHeader.vue'
import { getKnowledgeSettings, updateKnowledgeSettings } from '@/api/knowledge'

defineOptions({ name: 'KnowledgeSettings' })

const { t } = useI18n()

const loading = ref(false)
const saving = ref(false)
const form = reactive({
  allowedExt: [] as string[],
  maxMb: 100,
  previewMaxChars: 20000,
})
const defaultExt = ref<string[]>([])

async function load() {
  loading.value = true
  try {
    const data = await getKnowledgeSettings()
    form.allowedExt = data.allowedExt ?? []
    form.maxMb = data.maxMb
    form.previewMaxChars = data.previewMaxChars
    defaultExt.value = data.defaultAllowedExt ?? []
  } catch {
    /* http 层已提示 */
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())

async function save() {
  saving.value = true
  try {
    const res = await updateKnowledgeSettings({
      allowedExt: form.allowedExt,
      maxMb: form.maxMb,
      previewMaxChars: form.previewMaxChars,
    })
    form.allowedExt = res.allowedExt ?? form.allowedExt
    form.maxMb = res.maxMb
    form.previewMaxChars = res.previewMaxChars
    ElMessage.success(t('knowledge.settings.saved'))
  } catch {
    /* http 层已提示 */
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="bs-page">
    <PageHeader :title="t('knowledge.settings.title')">
      <template #actions>
        <el-button v-permission="'knowledge:setting:edit'" type="primary" :loading="saving" @click="save()">
          {{ t('common.action.save') }}
        </el-button>
      </template>
    </PageHeader>

    <div class="bs-page-card">
      <el-form label-position="top" v-loading="loading">
        <el-form-item :label="t('knowledge.settings.allowedExt')">
          <el-select
            v-model="form.allowedExt"
            multiple
            filterable
            allow-create
            default-first-option
            :placeholder="t('knowledge.settings.allowedExtTip')"
            style="width: 100%"
          >
            <el-option v-for="ext in defaultExt" :key="ext" :label="ext" :value="ext" />
          </el-select>
          <div class="settings-tip">{{ t('knowledge.settings.allowedExtTip') }}</div>
        </el-form-item>

        <el-form-item :label="t('knowledge.settings.maxMb')">
          <el-input-number v-model="form.maxMb" :min="1" :max="2048" />
        </el-form-item>

        <el-form-item :label="t('knowledge.settings.previewMaxChars')">
          <el-input-number v-model="form.previewMaxChars" :min="1000" :max="200000" :step="1000" />
        </el-form-item>

        <div class="settings-tip">{{ t('knowledge.settings.defaultExt') }}：{{ defaultExt.join(', ') }}</div>
      </el-form>
    </div>
  </div>
</template>

<style scoped>
.settings-tip {
  margin-top: var(--bs-space-1);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}
</style>
