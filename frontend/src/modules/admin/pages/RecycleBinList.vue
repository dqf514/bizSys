<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import PageHeader from '@/components/common/PageHeader.vue'
import ListTable from '@/components/list/ListTable.vue'
import type { ListColumn } from '@/components/list/types'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import {
  getRecycleSettings,
  listRecycleBin,
  purgeRecycleEntry,
  recycleModules,
  restoreRecycleEntry,
  updateRecycleSettings,
} from '@/api/admin'
import type { RecycleEntry } from '@/api/types'

defineOptions({ name: 'RecycleBinList' })

const { t } = useI18n()

const items = ref<RecycleEntry[]>([])
const modules = ref<{ module: string; count: number }[]>([])
const retentionDays = ref(180)
const loading = ref(false)
const query = reactive({ keyword: '', module: '' })

const moduleOptions = computed(() =>
  modules.value.map((m) => ({ label: `${m.module} (${m.count})`, value: m.module })),
)

const searchFields = computed<SearchField[]>(() => [
  { key: 'keyword', labelKey: 'common.action.search', type: 'input', width: 240 },
  { key: 'module', labelKey: 'knowledge.common.type', type: 'select', width: 200, options: moduleOptions.value },
])

async function load() {
  loading.value = true
  try {
    const params: Record<string, unknown> = { page: 1, size: 200 }
    if (query.keyword) params.q = query.keyword
    if (query.module) params.module = query.module
    const data = await listRecycleBin(params as never)
    items.value = data.items ?? []
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

async function loadSettings() {
  try {
    const data = await getRecycleSettings()
    retentionDays.value = data.retentionDays
  } catch {
    /* http 层已提示 */
  }
}

async function loadModules() {
  try {
    const data = await recycleModules()
    modules.value = data.items ?? []
  } catch {
    modules.value = []
  }
}

onMounted(async () => {
  await Promise.all([loadSettings(), loadModules()])
  await load()
})

function resetQuery() {
  query.keyword = ''
  query.module = ''
  void load()
}

const columns = computed<ListColumn[]>(() => [
  { prop: 'title', labelKey: 'knowledge.common.name', minWidth: 200 },
  { prop: 'resource', labelKey: 'knowledge.common.type', width: 150 },
  { prop: 'module', labelKey: 'knowledge.common.type', width: 130 },
  { prop: 'deletedByName', labelKey: 'knowledge.common.operator', width: 130 },
  { prop: 'deletedAt', labelKey: 'knowledge.common.updateTime', minWidth: 160 },
  { prop: 'purgeAfter', labelKey: 'knowledge.common.expireAt', minWidth: 160 },
  { prop: 'actions', labelKey: 'common.action.operate', width: 120, fixed: 'right', align: 'center', slot: 'actions' },
])

const rowActions = computed<ActionItem[]>(() => [
  { key: 'restore', tip: 'common.action.enable', perm: 'admin:recycle:restore' },
  { key: 'purge', tip: 'common.action.delete', perm: 'admin:recycle:purge' },
])

function onAction(key: string, row: RecycleEntry) {
  if (key === 'restore') void doRestore(row)
  else if (key === 'purge') void doPurge(row)
}

async function doRestore(row: RecycleEntry) {
  await restoreRecycleEntry(row.id)
  ElMessage.success(t('common.message.saveSuccess'))
  await Promise.all([load(), loadModules()])
}

async function doPurge(row: RecycleEntry) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  await purgeRecycleEntry(row.id)
  ElMessage.success(t('common.message.deleteSuccess'))
  await Promise.all([load(), loadModules()])
}

const savingSetting = ref(false)

async function saveRetention() {
  savingSetting.value = true
  try {
    const res = await updateRecycleSettings(retentionDays.value)
    retentionDays.value = res.retentionDays
    ElMessage.success(t('common.message.saveSuccess'))
    await load()
  } catch {
    /* http 层已提示 */
  } finally {
    savingSetting.value = false
  }
}
</script>

<template>
  <div class="bs-page">
    <PageHeader :title="t('menu.recycle')">
      <template #actions>
        <el-button @click="load()">{{ t('common.action.refresh') }}</el-button>
      </template>
    </PageHeader>

    <div class="bs-page-card">
      <div class="recycle-setting">
        <span class="recycle-setting-label">{{ t('admin.recycle.retentionDays') }}</span>
        <el-input-number v-model="retentionDays" :min="1" :max="3650" size="small" />
        <span class="recycle-setting-tip">{{ t('admin.recycle.retentionTip') }}</span>
        <el-button
          v-permission="'admin:recycle:setting'"
          type="primary"
          size="small"
          :loading="savingSetting"
          @click="saveRetention()"
        >
          {{ t('common.action.save') }}
        </el-button>
      </div>

      <SearchBar v-model="query" :fields="searchFields" @search="load()" @reset="resetQuery" />

      <ListTable
        :columns="columns"
        :data="items as unknown as Record<string, unknown>[]"
        :loading="loading"
        :show-pagination="false"
        row-key="id"
      >
        <template #actions="{ row }">
          <ActionBar
            :actions="rowActions"
            @select="(key: string) => onAction(key, row as unknown as RecycleEntry)"
          />
        </template>
      </ListTable>
    </div>
  </div>
</template>

<style scoped>
.recycle-setting {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  margin-bottom: var(--bs-space-2);
  flex-wrap: wrap;
}

.recycle-setting-label {
  font-weight: 600;
}

.recycle-setting-tip {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}
</style>
