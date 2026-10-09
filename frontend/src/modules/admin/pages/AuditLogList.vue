<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import { useListPage } from '@/composables/useListPage'
import { listAuditLogs } from '@/api/admin'
import type { AuditLog } from '@/api/types'

defineOptions({ name: 'AuditLogList' })

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'admin.audit.username', width: 180 },
  { key: 'module', labelKey: 'admin.audit.module', width: 140 },
]

const list = useListPage<AuditLog>({
  fetch: async (params) => {
    const data = await listAuditLogs({
      ...params,
      q: searchModel.value.q || undefined,
      filters: { module: searchModel.value.module || undefined },
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
})

const columns: ListColumn[] = [
  { prop: 'username', labelKey: 'admin.audit.username', width: 120 },
  { prop: 'module', labelKey: 'admin.audit.module', width: 100 },
  { prop: 'action', labelKey: 'admin.audit.action', width: 110 },
  { prop: 'bizType', labelKey: 'admin.audit.bizType', width: 100 },
  { prop: 'bizId', labelKey: 'admin.audit.bizId', width: 90 },
  { prop: 'detail', labelKey: 'admin.audit.detail', minWidth: 200 },
  { prop: 'ip', labelKey: 'admin.audit.ip', width: 120 },
  { prop: 'createTime', labelKey: 'admin.audit.createTime', width: 160 },
]

const detailVisible = ref(false)
const detailRow = ref<AuditLog | null>(null)

function viewDetail(row: AuditLog) {
  detailRow.value = row
  detailVisible.value = true
}
</script>

<template>
  <ListPage :title="t('admin.audit.title')" :loading="list.loading.value">
    <template #actions>
      <el-button @click="list.refresh()">{{ t('common.action.refresh') }}</el-button>
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '' }; list.reset()"
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
        @update:page="list.setPage"
        @update:size="list.setSize"
      >
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="110" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="viewDetail(row as unknown as AuditLog)">
                {{ t('admin.audit.viewDetail') }}
              </el-button>
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog v-model="detailVisible" :title="t('admin.audit.viewDetail')" width="560px" append-to-body>
    <el-descriptions v-if="detailRow" :column="1" border>
      <el-descriptions-item :label="t('admin.audit.username')">{{ detailRow.username }}</el-descriptions-item>
      <el-descriptions-item :label="t('admin.audit.module')">{{ detailRow.module }}</el-descriptions-item>
      <el-descriptions-item :label="t('admin.audit.action')">{{ detailRow.action }}</el-descriptions-item>
      <el-descriptions-item :label="t('admin.audit.traceId')">{{ detailRow.traceId || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('admin.audit.ip')">{{ detailRow.ip }}</el-descriptions-item>
      <el-descriptions-item :label="t('admin.audit.detail')">
        <pre class="detail-pre">{{ detailRow.detail }}</pre>
      </el-descriptions-item>
    </el-descriptions>
  </el-dialog>
</template>

<style scoped>
.detail-pre {
  margin: 0;
  max-height: 240px;
  overflow: auto;
  font-family: var(--bs-typography-font-family-mono);
  font-size: var(--bs-typography-font-size-xs);
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
