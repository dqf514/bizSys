<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

export interface RemoteOption {
  id: number | string
  label: string
  sub?: string
}

const props = withDefaults(
  defineProps<{
    modelValue?: number | string | null
    fetch: (q: string) => Promise<RemoteOption[]>
    placeholder?: string
    disabled?: boolean
    clearable?: boolean
    allowCreate?: boolean
    width?: string | number
  }>(),
  {
    modelValue: null,
    clearable: true,
    disabled: false,
    allowCreate: false,
    width: '100%',
  },
)

const emit = defineEmits<{
  (e: 'update:modelValue', v: number | string | null): void
  (e: 'change', v: number | string | null, option?: RemoteOption): void
}>()

const { t } = useI18n()
const loading = ref(false)
const options = ref<RemoteOption[]>([])
const selectedLabel = ref('')
let timer: ReturnType<typeof setTimeout> | null = null
let seq = 0

async function search(q: string) {
  const current = ++seq
  loading.value = true
  try {
    const list = await props.fetch(q)
    if (current === seq) options.value = list
  } catch {
    if (current === seq) options.value = []
  } finally {
    if (current === seq) loading.value = false
  }
}

function debounceSearch(q: string) {
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => void search(q), 300)
}

function onChange(val: number | string | null) {
  emit('update:modelValue', val)
  const opt = options.value.find((o) => String(o.id) === String(val))
  emit('change', val, opt)
  selectedLabel.value = opt?.label ?? ''
}

watch(
  () => props.modelValue,
  (v) => {
    if (v === null || v === undefined || v === '') {
      selectedLabel.value = ''
      return
    }
    const opt = options.value.find((o) => String(o.id) === String(v))
    if (opt) selectedLabel.value = opt.label
    else {
      // load initial value once
      void search('').then(() => {
        const found = options.value.find((o) => String(o.id) === String(v))
        if (found) selectedLabel.value = found.label
      })
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (timer) clearTimeout(timer)
})
</script>

<template>
  <el-select
    :model-value="props.modelValue ?? undefined"
    :placeholder="props.placeholder || t('common.form.placeholderSelect')"
    :loading="loading"
    :disabled="props.disabled"
    :clearable="props.clearable"
    filterable
    remote
    :remote-method="debounceSearch"
    :style="{ width: typeof props.width === 'number' ? props.width + 'px' : props.width }"
    @change="onChange"
    @visible-change="(v: boolean) => { if (v) void search('') }"
  >
    <el-option v-for="opt in options" :key="String(opt.id)" :label="opt.label" :value="opt.id">
      <div class="remote-option">
        <span>{{ opt.label }}</span>
        <span v-if="opt.sub" class="remote-sub">{{ opt.sub }}</span>
      </div>
    </el-option>
  </el-select>
</template>

<style scoped>
.remote-option {
  display: flex;
  justify-content: space-between;
  gap: var(--bs-space-2);
}

.remote-sub {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}
</style>
