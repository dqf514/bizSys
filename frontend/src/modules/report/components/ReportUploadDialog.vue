<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import RemoteSelect, { type RemoteOption } from '@/components/form/RemoteSelect.vue'
import { reportItemOptions, uploadReport } from '@/api/report'

defineOptions({ name: 'ReportUploadDialog' })

const props = defineProps<{
  modelValue: boolean
  /** 限定到单个任务（任务详情场景）；不传则为全局条目 */
  taskId?: number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  /** 上传成功后触发，供外部刷新列表/详情 */
  (e: 'uploaded'): void
}>()

const { t } = useI18n()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const saving = ref(false)
const form = reactive({ itemId: null as number | null })
const pickedFile = ref<File | null>(null)
const fileInputRef = ref<HTMLInputElement>()

watch(
  () => props.modelValue,
  (v) => {
    if (v) {
      form.itemId = null
      pickedFile.value = null
    }
  },
)

async function fetchItemOptions(q: string): Promise<RemoteOption[]> {
  try {
    const options = await reportItemOptions(q, props.taskId)
    return (options ?? []).map((x) => ({ id: x.value, label: x.label, sub: x.sub }))
  } catch {
    return []
  }
}

function pickFile() {
  fileInputRef.value?.click()
}

function onFilePicked(e: Event) {
  const input = e.target as HTMLInputElement
  pickedFile.value = input.files?.[0] ?? null
  input.value = ''
}

async function save() {
  if (!form.itemId || !pickedFile.value) {
    ElMessage.warning(pickedFile.value ? t('common.form.required') : t('report.report.noFile'))
    return
  }
  saving.value = true
  try {
    await uploadReport(form.itemId, pickedFile.value)
    ElMessage.success(t('common.message.createSuccess'))
    visible.value = false
    emit('uploaded')
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" :title="t('report.report.upload')" width="560px" append-to-body>
    <el-form label-width="110px">
      <el-form-item :label="t('report.report.selectItem')" required>
        <RemoteSelect v-model="form.itemId" :fetch="fetchItemOptions" />
        <div class="form-tip">{{ t('report.report.selectItemTip') }}</div>
      </el-form-item>
      <el-form-item :label="t('report.report.selectFile')" required>
        <div class="file-pick">
          <el-button @click="pickFile">{{ t('report.report.selectFile') }}</el-button>
          <span v-if="pickedFile" class="file-name bs-truncate">{{ pickedFile.name }}</span>
        </div>
        <div class="form-tip">{{ t('report.report.fileTip') }}</div>
      </el-form-item>
    </el-form>
    <input ref="fileInputRef" type="file" accept=".pdf,.doc,.docx" class="hidden-input" @change="onFilePicked" />
    <template #footer>
      <el-button @click="visible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.form-tip {
  width: 100%;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}

.file-pick {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  width: 100%;
}

.file-name {
  flex: 1;
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-sm);
}

.hidden-input {
  display: none;
}
</style>
