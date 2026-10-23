<script setup lang="ts">
/** 全站资源选择控件：弹窗检索（q + 分页），选中回填 {id, name}；
 * 完整资源行通过 pick 事件抛出，供 FormRenderer 按 mappings 带出字段。
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Search } from '@element-plus/icons-vue'
import type { OaResourceItem, OaResourceType, OaResourceValue } from '@/api/types'
import { searchOaResources } from '@/api/oa'

const props = defineProps<{
  modelValue: OaResourceValue | null
  resource: OaResourceType | ''
  disabled?: boolean
  placeholder?: string
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: OaResourceValue | null): void
  (e: 'pick', item: OaResourceItem | null): void
}>()

const { t } = useI18n()

const open = ref(false)
const q = ref('')
const page = ref(1)
const size = 10
const items = ref<OaResourceItem[]>([])
const total = ref(0)
const loading = ref(false)
const pickedId = ref<number | null>(null)

async function load() {
  if (!props.resource) return
  loading.value = true
  try {
    const data = await searchOaResources(props.resource, { q: q.value, page: page.value, size })
    items.value = data.items ?? []
    total.value = data.total ?? 0
  } catch {
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function openDialog() {
  if (props.disabled) return
  open.value = true
  q.value = ''
  page.value = 1
  pickedId.value = props.modelValue?.id ?? null
  void load()
}

function onSearch() {
  page.value = 1
  void load()
}

function onRowChange(row: OaResourceItem | undefined) {
  pickedId.value = row?.id ?? null
}

function confirm() {
  const item = items.value.find((i) => i.id === pickedId.value) ?? null
  if (!item) return
  emit('update:modelValue', { id: item.id, name: item.label })
  emit('pick', item)
  open.value = false
}

function clear() {
  emit('update:modelValue', null)
  emit('pick', null)
}
</script>

<template>
  <div class="res-picker">
    <el-input
      :model-value="props.modelValue?.name ?? ''"
      readonly
      :placeholder="placeholder || t('oa.form.resourcePlaceholder')"
      :disabled="props.disabled"
      class="res-input"
      @click="openDialog"
    >
      <template #append>
        <el-button :disabled="props.disabled" @click="openDialog">{{ t('oa.form.resourcePick') }}</el-button>
      </template>
    </el-input>
    <el-button
      v-if="props.modelValue && !props.disabled"
      link
      type="danger"
      class="res-clear"
      @click="clear"
    >
      {{ t('common.action.clear') }}
    </el-button>

    <el-dialog v-model="open" :title="t('oa.form.resourcePick')" width="640px" append-to-body>
      <div class="res-search">
        <el-input
          v-model="q"
          :placeholder="t('oa.form.resourceSearchTip')"
          clearable
          :prefix-icon="Search"
          @keyup.enter="onSearch"
          @clear="onSearch"
        />
        <el-button type="primary" plain @click="onSearch">{{ t('common.action.search') }}</el-button>
      </div>
      <el-table
        v-loading="loading"
        :data="items"
        highlight-current-row
        height="320"
        @current-change="onRowChange"
        @row-dblclick="(row: OaResourceItem) => { pickedId = row.id; confirm() }"
      >
        <el-table-column prop="label" :label="t('oa.form.resourceName')" min-width="180" show-overflow-tooltip />
        <el-table-column prop="sub" :label="t('oa.form.resourceNo')" min-width="140" show-overflow-tooltip />
      </el-table>
      <div class="res-pager">
        <el-pagination
          v-model:current-page="page"
          :total="total"
          :page-size="size"
          layout="total, prev, pager, next"
          @current-change="load"
        />
      </div>
      <template #footer>
        <el-button @click="open = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :disabled="pickedId === null" @click="confirm">
          {{ t('common.action.confirm') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.res-picker {
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.res-input {
  flex: 1;
}

.res-input :deep(.el-input__inner) {
  cursor: pointer;
}

.res-clear {
  flex-shrink: 0;
}

.res-search {
  display: flex;
  gap: var(--bs-space-2);
  margin-bottom: var(--bs-space-3);
}

.res-pager {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--bs-space-3);
}
</style>
