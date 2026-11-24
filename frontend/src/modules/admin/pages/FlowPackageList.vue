<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import ListTable from '@/components/list/ListTable.vue'
import type { ListColumn } from '@/components/list/types'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import {
  FLOW_PACKAGE_SCHEMA,
  exportAllFlowPackages,
  exportFlowPackage,
  importFlowPackages,
  listFlowDefs,
} from '@/api/admin'
import type { FlowDef, FlowPackageImportResult } from '@/api/types'

defineOptions({ name: 'FlowPackageList' })

const { t } = useI18n()

const items = ref<FlowDef[]>([])
const loading = ref(false)
const query = reactive<Record<string, unknown>>({ q: '', bizType: '' })

/* ---------- 检索 ---------- */
const bizTypeOptions = computed(() => {
  const set = new Set<string>()
  for (const d of items.value) if (d.bizType) set.add(d.bizType)
  return [...set].map((v) => ({ label: v, value: v }))
})

const searchFields = computed<SearchField[]>(() => [
  { key: 'q', labelKey: 'admin.flowPackage.keyword', type: 'input', width: 240 },
  {
    key: 'bizType',
    labelKey: 'admin.flowPackage.bizType',
    type: 'select',
    width: 160,
    options: bizTypeOptions.value,
  },
])

const filteredItems = computed(() => {
  const kw = String(query.q ?? '').trim().toLowerCase()
  const biz = String(query.bizType ?? '')
  return items.value.filter((d) => {
    if (biz && d.bizType !== biz) return false
    if (!kw) return true
    return [d.code, d.name, d.bizType, d.remark]
      .filter(Boolean)
      .some((v) => String(v).toLowerCase().includes(kw))
  })
})

async function load() {
  loading.value = true
  try {
    const data = await listFlowDefs()
    items.value = Array.isArray(data) ? data : (data.items ?? [])
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())

function resetQuery() {
  query.q = ''
  query.bizType = ''
}

/* ---------- 导出 ---------- */
const EXPORT_PERM = 'admin:flow:export'
const IMPORT_PERM = 'admin:flow:import'

async function doExportOne(row: FlowDef) {
  await exportFlowPackage(row.code)
}

async function doExportAll() {
  await exportAllFlowPackages(String(query.bizType ?? ''))
}

const rowActions: ActionItem[] = [{ key: 'export', tip: 'admin.flowPackage.exportOne', perm: EXPORT_PERM }]

function onAction(key: string, row: FlowDef) {
  if (key === 'export') void doExportOne(row)
}

/* ---------- 导入 ---------- */
const importVisible = ref(false)
const importing = ref(false)
const importInfo = reactive({ schema: '', total: 0, fileName: '' })
const importResult = ref<FlowPackageImportResult | null>(null)
const rawPayload = ref<unknown>(null)

async function onFileChange(file: { raw?: File; name?: string }) {
  const raw = file.raw
  if (!raw) return
  let payload: unknown
  try {
    payload = JSON.parse(await raw.text())
  } catch {
    ElMessage.error(t('admin.flowPackage.parseFailed'))
    return
  }
  const schema = (payload as { schema?: string })?.schema
  if (schema !== FLOW_PACKAGE_SCHEMA) {
    ElMessage.error(t('admin.flowPackage.badSchema', { schema: schema || '-' }))
    return
  }
  const list = (payload as { packages?: unknown[] })?.packages
  if (!Array.isArray(list) || !list.length) {
    ElMessage.error(t('admin.flowPackage.emptyPackages'))
    return
  }
  rawPayload.value = payload
  importInfo.schema = schema
  importInfo.total = list.length
  importInfo.fileName = file.name ?? ''
  importResult.value = null
  importVisible.value = true
  // 先做一次试导入（只校验不落库），把问题暴露在确认之前
  await runImport(true)
}

async function runImport(dryRun: boolean) {
  if (!rawPayload.value) return
  importing.value = true
  try {
    importResult.value = await importFlowPackages(rawPayload.value, dryRun)
    if (!dryRun) {
      ElMessage.success(
        t('admin.flowPackage.importDone', {
          created: importResult.value.created,
          updated: importResult.value.updated,
        }),
      )
      importVisible.value = false
      await load()
    }
  } catch {
    /* http notifies */
  } finally {
    importing.value = false
  }
}

/* ---------- 表格 ---------- */
const columns = computed<ListColumn[]>(() => [
  { prop: 'name', labelKey: 'admin.flowPackage.name', minWidth: 180 },
  { prop: 'code', labelKey: 'admin.flowPackage.code', minWidth: 220 },
  { prop: 'bizType', labelKey: 'admin.flowPackage.bizType', width: 110 },
  { prop: 'version', labelKey: 'admin.flowPackage.version', width: 90, align: 'center' },
  { prop: 'nodeCount', labelKey: 'admin.flowPackage.nodeCount', width: 90, align: 'center' },
  { prop: 'enabled', labelKey: 'admin.flowPackage.enabled', width: 90, align: 'center' },
  {
    prop: 'actions',
    labelKey: 'common.action.operate',
    width: 110,
    fixed: 'right',
    align: 'center',
    slot: 'actions',
  },
])

function nodeCount(row: Record<string, unknown>) {
  const nodes = row.nodes as unknown[] | undefined
  return nodes?.length ?? 0
}
</script>

<template>
  <ListPage :title="t('admin.flowPackage.title')" :loading="loading">
    <template #actions>
      <el-upload
        v-permission="IMPORT_PERM"
        :auto-upload="false"
        :show-file-list="false"
        accept=".json,application/json"
        :on-change="onFileChange"
      >
        <el-button type="primary" :icon="Upload">
          {{ t('admin.flowPackage.import') }}
        </el-button>
      </el-upload>
      <el-button v-permission="EXPORT_PERM" @click="doExportAll()">
        {{ t('admin.flowPackage.exportAll') }}
      </el-button>
      <el-button @click="load()">{{ t('common.action.refresh') }}</el-button>
    </template>

    <template #searchBar>
      <SearchBar v-model="query" :fields="searchFields" @search="load()" @reset="resetQuery()" />
    </template>

    <template #table>
      <ListTable :columns="columns" :data="filteredItems as unknown as Record<string, unknown>[]" :loading="loading" row-key="id" height="100%">
        <template #nodeCount="{ row }">{{ nodeCount(row) }}</template>
        <template #enabled="{ row }">
          <el-tag :type="Number(row.enabled) ? 'success' : 'info'" size="small">
            {{ Number(row.enabled) ? t('common.form.enabled') : t('common.form.disabled') }}
          </el-tag>
        </template>
        <template #actions="{ row }">
          <ActionBar :actions="rowActions" @select="(key: string) => onAction(key, row as unknown as FlowDef)" />
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog
    v-model="importVisible"
    :title="t('admin.flowPackage.importTitle')"
    width="var(--bs-layout-dialog-md)"
    append-to-body
  >
    <el-descriptions :column="1" border size="small">
      <el-descriptions-item :label="t('admin.flowPackage.fileName')">
        {{ importInfo.fileName || '-' }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('admin.flowPackage.schema')">
        {{ importInfo.schema }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('admin.flowPackage.packageCount')">
        {{ importInfo.total }}
      </el-descriptions-item>
    </el-descriptions>

    <template v-if="importResult">
      <el-alert
        class="import-result"
        :type="importResult.errors.length ? 'warning' : 'success'"
        :closable="false"
        show-icon
      >
        <template #title>
          {{
            t('admin.flowPackage.dryRunSummary', {
              total: importResult.total,
              created: importResult.created,
              updated: importResult.updated,
              formCreated: importResult.formCreated,
              formUpdated: importResult.formUpdated,
            })
          }}
        </template>
      </el-alert>
      <ul v-if="importResult.errors.length" class="import-errors">
        <li v-for="(e, i) in importResult.errors" :key="i">{{ e }}</li>
      </ul>
    </template>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="importVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button :loading="importing" @click="runImport(true)">
          {{ t('admin.flowPackage.dryRun') }}
        </el-button>
        <el-button
          v-permission="IMPORT_PERM"
          type="primary"
          :loading="importing"
          :disabled="Boolean(importResult?.errors.length)"
          @click="runImport(false)"
        >
          {{ t('admin.flowPackage.confirmImport') }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.import-result {
  margin-top: var(--bs-space-3);
}

.import-errors {
  margin: var(--bs-space-2) 0 0;
  padding-left: var(--bs-space-4);
  color: var(--bs-color-semantic-danger);
  font-size: var(--bs-typography-font-size-sm);
  max-height: 180px;
  overflow: auto;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--bs-space-2);
}
</style>
