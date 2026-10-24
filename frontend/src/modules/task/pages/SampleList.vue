<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar from '@/components/list/ActionBar.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { useListPage } from '@/composables/useListPage'
import { listSamples, sampleCounts, exportSamples } from '@/api/task'
import type { SampleRow } from '@/api/types'

defineOptions({ name: 'SampleList' })

const { t } = useI18n()
const router = useRouter()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'task.sample.searchQ', placeholderKey: 'task.sample.placeholderQ', width: 260 },
]

const statusTabs = ref<StatusTabItem[]>([
  { value: 'in', labelKey: 'task.sample.stockIn', count: 0 },
  { value: 'out', labelKey: 'task.sample.stockOut', count: 0 },
  { value: 'all', labelKey: 'common.action.all', count: 0 },
])

async function loadCounts() {
  try {
    const counts = (await sampleCounts()) ?? {}
    for (const tab of statusTabs.value) {
      tab.count = counts[tab.value] ?? 0
    }
  } catch {
    /* counts optional */
  }
}

const list = useListPage<SampleRow>({
  fetch: async (params) => {
    const data = await listSamples({ ...params, q: searchModel.value.q || undefined })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) => exportSamples({ ...params, q: searchModel.value.q || undefined }),
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'sampleNo', labelKey: 'task.sample.sampleNo', width: 170, fixed: 'left', sortable: 'sample_no' },
  { prop: 'name', labelKey: 'task.sample.name', minWidth: 140, sortable: 'name' },
  { prop: 'model', labelKey: 'task.sample.model', width: 120 },
  { prop: 'vin', labelKey: 'task.sample.vin', width: 160 },
  { prop: 'taskNo', labelKey: 'task.sample.task', width: 150, sortable: 'task_no' },
  { prop: 'customerName', labelKey: 'task.sample.customer', minWidth: 140, sortable: 'customer_name' },
  { prop: 'sampleDate', labelKey: 'task.sample.sampleDate', width: 110, sortable: 'sample_date' },
  { prop: 'inStock', labelKey: 'task.sample.inStock', width: 90, sortable: 'in_stock' },
  { prop: 'createTime', labelKey: 'task.sample.createTime', width: 160, sortable: 'create_time' },
]

function openTask(row: SampleRow) {
  router.push(`/task/tasks/${row.taskId}`)
}
</script>

<template>
  <ListPage :title="t('task.sample.title')" :loading="list.loading.value">
    <template #actions>
      <ExportButton v-permission="'task:sample:list:export'" :export-fn="() => list.exportList()" />
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '' }; list.reset()"
      />
    </template>

    <template #statusTabs>
      <StatusTabs
        :tabs="statusTabs"
        :model-value="String(list.query.status)"
        @update:model-value="list.setStatus($event)"
      />
    </template>

    <template #table>
      <ListTable
        :columns="columns"
        :data="list.items.value as unknown as Record<string, unknown>[]"
        :loading="list.loading.value"
        :total="list.total.value"
        :page="Number(list.query.page)"
        :size="Number(list.query.size)"
        row-key="id"
        @update:page="list.setPage"
        @update:size="list.setSize"
        @sort-change="list.onSortChange"
      >
        <template #inStock="{ row }">
          <StatusTag :status="String(row.inStock)" i18n-prefix="task.sample.stock" />
        </template>
        <template #taskNo="{ row }">
          <el-button link type="primary" @click="openTask(row as unknown as SampleRow)">
            {{ row.taskNo || '-' }}
          </el-button>
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="90" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar
                :actions="[{ key: 'goTask', tip: 'task.sample.goTask', icon: 'Position' }]"
                @select="openTask(row as unknown as SampleRow)"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>
</template>
