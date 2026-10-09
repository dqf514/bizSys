<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { Delete, Download } from '@element-plus/icons-vue'
import type { Attachment } from '@/api/types'

const props = defineProps<{
  files: Attachment[]
  upload: (file: File) => Promise<Attachment | void>
  download: (fileId: number | string, fileName: string) => Promise<void>
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:files', v: Attachment[]): void
}>()

const { t } = useI18n()
const inputRef = ref<HTMLInputElement>()
const uploading = ref(false)

function pick() {
  if (props.disabled) return
  inputRef.value?.click()
}

async function onFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  uploading.value = true
  try {
    const result = await props.upload(file)
    const next: Attachment = result?.id
      ? result
      : { id: Date.now(), fileName: file.name, size: file.size }
    emit('update:files', [...props.files, next])
    ElMessage.success(t('common.message.saveSuccess'))
  } catch {
    /* http notifies */
  } finally {
    uploading.value = false
  }
}

function remove(id: number | string) {
  emit(
    'update:files',
    props.files.filter((f) => f.id !== id),
  )
}

function fmtSize(size: number) {
  if (!size) return ''
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}
</script>

<template>
  <div class="upload-files">
    <div class="file-list">
      <div v-for="f in props.files" :key="String(f.id)" class="file-row">
        <span class="file-name bs-truncate">{{ f.fileName }}</span>
        <span class="file-size">{{ fmtSize(f.size) }}</span>
        <el-button link type="primary" :icon="Download" @click="props.download(f.id, f.fileName)" />
        <el-button v-if="!props.disabled" link type="danger" :icon="Delete" @click="remove(f.id)" />
      </div>
    </div>
    <el-button v-if="!props.disabled" :loading="uploading" @click="pick">
      {{ t('common.action.upload') }}
    </el-button>
    <input ref="inputRef" type="file" class="hidden-input" @change="onFile" />
  </div>
</template>

<style scoped>
.upload-files {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.file-list {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-1);
}

.file-row {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  padding: 4px 8px;
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-sm);
  background: var(--bs-color-fill-lighter);
  font-size: var(--bs-typography-font-size-sm);
}

.file-name {
  flex: 1;
}

.file-size {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}

.hidden-input {
  display: none;
}
</style>
