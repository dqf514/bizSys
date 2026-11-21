<script setup lang="ts">
/** 访客预警（B3）：滞留超时 / 尾随 / 闯入 / 越权 / 黑名单命中 的处置闭环。 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import { useListPage } from '@/composables/useListPage'
import { handleVisitorAlert, listVisitorAlerts, scanVisitorOverdue, visitorAlertCounts } from '@/api/visitor'
import type { VisitorAlert } from '@/api/types'

defineOptions({ name: 'AlertList' })

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ q: '', alert_type: '', level: '' })
const searchFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'visitor.alert.searchName',
    placeholderKey: 'visitor.alert.placeholderName',
    width: 240,
  },
  {
    key: 'alert_type',
    labelKey: 'visitor.alert.alertType',
    type: 'select',
    options: [
      { label: t('visitor.alert.typeOverstay'), value: 'overstay' },
      { label: t('visitor.alert.typeTailgating'), value: 'tailgating' },
      { label: t('visitor.alert.typeIntrusion'), value: 'intrusion' },
      { label: t('visitor.alert.typeZoneDenied'), value: 'zone_denied' },
      { label: t('visitor.alert.typeBlacklist'), value: 'blacklist' },
    ],
    width: 170,
  },
  {
    key: 'level',
    labelKey: 'visitor.alert.level',
    type: 'select',
    options: [
      { label: t('visitor.alert.levelLow'), value: 'low' },
      { label: t('visitor.alert.levelMedium'), value: 'medium' },
      { label: t('visitor.alert.levelHigh'), value: 'high' },
    ],
    width: 120,
  },
])

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'open', labelKey: 'visitor.alert.statusOpen', count: 0 },
  { value: 'handled', labelKey: 'visitor.alert.statusHandled', count: 0 },
  { value: 'ignored', labelKey: 'visitor.alert.statusIgnored', count: 0 },
])

const counts = ref<Record<string, number>>({})

async function loadCounts() {
  try {
    counts.value = (await visitorAlertCounts()) ?? {}
    for (const tab of statusTabs.value) {
      if (tab.value === 'all') continue
      tab.count = counts.value[tab.value] ?? 0
    }
    const allTab = statusTabs.value.find((x) => x.value === 'all')
    if (allTab) allTab.count = counts.value.all ?? 0
  } catch {
    /* counts optional */
  }
}

onMounted(() => void loadCounts())

function buildFilters(params: Record<string, unknown>) {
  return {
    ...((params.filters as Record<string, unknown>) || {}),
    alert_type: searchModel.value.alert_type || undefined,
    level: searchModel.value.level || undefined,
  }
}

const list = useListPage<VisitorAlert>({
  fetch: async (params) => {
    const data = await listVisitorAlerts({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(params),
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'occurredAt', labelKey: 'visitor.alert.occurredAt', width: 165, fixed: 'left', sortable: 'occurred_at' },
  { prop: 'alertType', labelKey: 'visitor.alert.alertType', width: 130, sortable: 'alert_type' },
  { prop: 'level', labelKey: 'visitor.alert.level', width: 100, sortable: 'level' },
  { prop: 'zoneName', labelKey: 'visitor.alert.zoneName', width: 140 },
  { prop: 'message', labelKey: 'visitor.alert.message', minWidth: 200 },
  { prop: 'status', labelKey: 'visitor.alert.status', width: 100, sortable: 'status' },
  { prop: 'handledByName', labelKey: 'visitor.alert.handledByName', width: 110 },
  { prop: 'handledAt', labelKey: 'visitor.alert.handledAt', width: 165 },
]

function levelTagType(level: string): 'info' | 'warning' | 'danger' {
  if (level === 'high') return 'danger'
  if (level === 'medium') return 'warning'
  return 'info'
}

function rowActions(row: VisitorAlert): ActionItem[] {
  const acts: ActionItem[] = []
  if (row.status === 'open') {
    acts.push({ key: 'handle', tip: 'visitor.alert.handle', icon: 'CircleCheck', perm: 'visitor:alert:handle' })
  }
  return acts
}

/* ---------------- 处置 ---------------- */
const handleVisible = ref(false)
const handleTarget = ref<VisitorAlert | null>(null)
const handleForm = ref<{ status: 'handled' | 'ignored'; handle_remark: string }>({
  status: 'handled',
  handle_remark: '',
})

function openHandle(row: VisitorAlert) {
  handleTarget.value = row
  handleForm.value = { status: 'handled', handle_remark: '' }
  handleVisible.value = true
}

async function submitHandle() {
  if (!handleTarget.value) return
  try {
    await handleVisitorAlert(handleTarget.value.id, {
      status: handleForm.value.status,
      handle_remark: handleForm.value.handle_remark,
    })
    ElMessage.success(t('common.message.submitSuccess'))
    handleVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doScan() {
  try {
    const r = await scanVisitorOverdue()
    ElMessage.success(t('common.message.submitSuccess'))
    if (r?.scanned) {
      ElMessage.warning(t('visitor.alert.scanResult', { count: r.scanned }))
    }
    list.refresh()
  } catch {
    /* http notifies */
  }
}

function onRowAction(key: string, row: VisitorAlert) {
  if (key === 'handle') openHandle(row)
}
</script>

<template>
  <ListPage :title="t('visitor.alert.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'visitor:alert:handle'" @click="doScan">
        {{ t('visitor.alert.scan') }}
      </el-button>
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '', alert_type: '', level: '' }; list.reset()"
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
        <template #alertType="{ row }">
          {{ row.alertTypeText || row.alertType }}
        </template>
        <template #level="{ row }">
          <el-tag :type="levelTagType(String(row.level))" size="small" effect="light" round>
            {{ t(`visitor.alert.level${String(row.level || '').replace(/^./, (c) => c.toUpperCase())}`) }}
          </el-tag>
        </template>
        <template #status="{ row }">
          <el-tag
            :type="row.status === 'open' ? 'danger' : row.status === 'handled' ? 'success' : 'info'"
            size="small"
            effect="light"
            round
          >
            {{
              row.status === 'open'
                ? t('visitor.alert.statusOpen')
                : row.status === 'handled'
                  ? t('visitor.alert.statusHandled')
                  : t('visitor.alert.statusIgnored')
            }}
          </el-tag>
        </template>
        <template #extraColumns>
          <el-table-column
            :label="t('common.action.operate')"
            width="110"
            fixed="right"
            align="center"
            header-align="center"
          >
            <template #default="{ row }">
              <ActionBar
                :actions="rowActions(row as unknown as VisitorAlert)"
                @select="(k) => onRowAction(k, row as unknown as VisitorAlert)"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog v-model="handleVisible" :width="'var(--bs-layout-dialog-sm)'" :title="t('visitor.alert.handleTitle')">
    <el-form label-position="top">
      <el-form-item :label="t('visitor.alert.message')">
        <div class="alert-msg">{{ handleTarget?.message }}</div>
      </el-form-item>
      <el-form-item :label="t('visitor.alert.status')">
        <el-radio-group v-model="handleForm.status">
          <el-radio value="handled">{{ t('visitor.alert.statusHandled') }}</el-radio>
          <el-radio value="ignored">{{ t('visitor.alert.statusIgnored') }}</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item :label="t('visitor.alert.handleRemark')">
        <el-input v-model="handleForm.handle_remark" type="textarea" :rows="3" :maxlength="2000" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="handleVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="submitHandle">{{ t('common.action.submit') }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.alert-msg {
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
