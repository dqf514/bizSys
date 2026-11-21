<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { useListPage } from '@/composables/useListPage'
import { useFlowCapability } from '@/composables/useFlowCapability'
import { useDictOptions } from '@/composables/useDict'
import {
  approveDisposal,
  completeDisposal,
  createDisposal,
  deleteDisposal,
  disposalCounts,
  exportDisposals,
  getDisposal,
  listDisposals,
  submitDisposal,
  updateDisposal,
} from '@/api/asset'
import type { AssetDisposal } from '@/api/types'
import { useFixedAssetOptions } from '../composables/useAssetOptions'

defineOptions({ name: 'DisposalList' })

const { t } = useI18n()
const { load: loadFlowCaps, flowEnabled } = useFlowCapability()
const route = useRoute()
const router = useRouter()
const assetOpts = useFixedAssetOptions()
const typeDict = useDictOptions('disposal_type')

const searchModel = ref<Record<string, any>>({ q: '', disposalType: '' })
const searchFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'asset.disposal.disposalNo',
    placeholderKey: 'common.form.placeholderSearch',
    width: 240,
  },
  {
    key: 'disposalType',
    labelKey: 'asset.disposal.disposalType',
    type: 'select',
    width: 160,
    options: typeDict.opts.value,
  },
])

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'draft', labelKey: 'common.status.draft', count: 0 },
  { value: 'approving', labelKey: 'common.status.approving', count: 0 },
  { value: 'approved', labelKey: 'asset.status.approved', count: 0 },
  { value: 'done', labelKey: 'asset.status.done', count: 0 },
])

async function loadCounts() {
  try {
    const data = (await disposalCounts()) ?? {}
    for (const tab of statusTabs.value) {
      if (tab.value === 'all') continue
      tab.count = data[tab.value] ?? 0
    }
    const allTab = statusTabs.value.find((x) => x.value === 'all')
    if (allTab) allTab.count = data.all ?? 0
  } catch {
    /* counts optional */
  }
}

onMounted(() => {
  void loadCounts()
  void loadFlowCaps()
})

function buildFilters() {
  return { disposal_type: searchModel.value.disposalType || undefined }
}

const list = useListPage<AssetDisposal>({
  fetch: async (params) => {
    const data = await listDisposals({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(),
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) =>
    exportDisposals({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(),
    }),
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'disposalNo', labelKey: 'asset.disposal.disposalNo', width: 160, fixed: 'left', sortable: 'disposal_no' },
  { prop: 'assetNo', labelKey: 'asset.asset.assetNo', width: 130 },
  { prop: 'assetName', labelKey: 'asset.asset.name', minWidth: 150 },
  { prop: 'disposalType', labelKey: 'asset.disposal.disposalType', width: 110 },
  { prop: 'applyDate', labelKey: 'asset.disposal.applyDate', width: 120, sortable: 'apply_date' },
  { prop: 'originalValue', labelKey: 'asset.disposal.originalValue', width: 120, align: 'right' },
  { prop: 'netValue', labelKey: 'asset.disposal.netValue', width: 120, align: 'right' },
  { prop: 'disposalAmount', labelKey: 'asset.disposal.disposalAmount', width: 120, align: 'right' },
  { prop: 'handlerName', labelKey: 'asset.disposal.handler', width: 110 },
  { prop: 'status', labelKey: 'common.form.status', width: 100, sortable: 'status' },
]

function typeLabel(value: unknown) {
  const v = String(value ?? '')
  return typeDict.opts.value.find((o) => o.value === v)?.label || v || '-'
}

function rowActions(row: AssetDisposal): ActionItem[] {
  const s = String(row.status)
  const acts: ActionItem[] = [{ key: 'detail', tip: 'common.action.detail' }]
  if (s === 'draft') {
    acts.push({ key: 'edit', tip: 'common.action.edit', perm: 'asset:disposal:edit' })
    // F5：处置流程启用时走审批，流程停用才恢复人工直批
    if (flowEnabled('asset_disposal')) {
      acts.push({ key: 'submit', tip: 'asset.disposal.submit', perm: 'asset:disposal:submit' })
    } else {
      acts.push({ key: 'approve', tip: 'asset.disposal.approve', perm: 'asset:disposal:approve' })
    }
    acts.push({ key: 'delete', tip: 'common.action.delete', perm: 'asset:disposal:delete' })
  } else if (s === 'approved') {
    acts.push({ key: 'complete', tip: 'asset.disposal.complete', icon: 'CircleCheck', perm: 'asset:disposal:complete' })
  } else if (s === 'rejected') {
    if (flowEnabled('asset_disposal')) {
      acts.push({ key: 'submit', tip: 'asset.disposal.submit', perm: 'asset:disposal:submit' })
    }
    acts.push({ key: 'delete', tip: 'common.action.delete', perm: 'asset:disposal:delete' })
  }
  return acts
}

function onRowAction(key: string, row: AssetDisposal) {
  if (key === 'detail') void openDetail(row.id)
  else if (key === 'edit') openEdit(row)
  else if (key === 'submit') void doSubmit(row)
  else if (key === 'approve') void doApprove(row)
  else if (key === 'complete') void doComplete(row)
  else if (key === 'delete') void remove(row)
}

/* ---------- 提交处置审批（F5） ---------- */
async function doSubmit(row: AssetDisposal) {
  try {
    await ElMessageBox.confirm(t('asset.disposal.submitTip'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await submitDisposal(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------- form ---------- */
const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)

const form = reactive({
  assetId: null as number | null,
  disposalType: 'scrap',
  applyDate: '',
  disposalAmount: null as number | null,
  reason: '',
  handlerName: '',
  remark: '',
  version: null as number | null,
})

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('asset.disposal.create')
  Object.assign(form, {
    assetId: null,
    disposalType: 'scrap',
    applyDate: '',
    disposalAmount: null,
    reason: '',
    handlerName: '',
    remark: '',
    version: null,
  })
  dialogVisible.value = true
}

function openEdit(row: AssetDisposal) {
  editingId.value = row.id
  dialogTitle.value = t('asset.disposal.edit')
  Object.assign(form, {
    assetId: row.assetId,
    disposalType: row.disposalType || 'scrap',
    applyDate: row.applyDate ?? '',
    disposalAmount: row.disposalAmount ?? null,
    reason: row.reason,
    handlerName: row.handlerName,
    remark: row.remark,
    version: row.version,
  })
  dialogVisible.value = true
}

async function save() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  saving.value = true
  try {
    if (editingId.value) await updateDisposal(editingId.value, { ...form })
    else await createDisposal({ ...form })
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function doApprove(row: AssetDisposal) {
  try {
    await ElMessageBox.confirm(t('asset.disposal.approveTip'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await approveDisposal(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doComplete(row: AssetDisposal) {
  try {
    await ElMessageBox.confirm(t('asset.disposal.completeTip'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await completeDisposal(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function remove(row: AssetDisposal) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteDisposal(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------- detail drawer ---------- */
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<AssetDisposal | null>(null)

async function openDetail(id: number) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await getDisposal(id)
  } catch {
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

watch(
  () => route.query.detail,
  (v) => {
    const id = Number(v)
    if (!id) return
    void openDetail(id)
    router.replace({ query: { ...route.query, detail: undefined } })
  },
  { immediate: true },
)
</script>

<template>
  <ListPage :title="t('asset.disposal.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'asset:disposal:create'" type="primary" @click="openCreate">
        {{ t('asset.disposal.create') }}
      </el-button>
      <ExportButton v-permission="'asset:disposal:list:export'" :export-fn="() => list.exportList()" />
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '', disposalType: '' }; list.reset()"
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
        <template #disposalNo="{ row }">
          <el-button link type="primary" @click="openDetail(row.id)">{{ row.disposalNo }}</el-button>
        </template>
        <template #disposalType="{ row }">{{ typeLabel(row.disposalType) }}</template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="asset.status" />
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="150" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar
                :actions="rowActions(row as unknown as AssetDisposal)"
                @select="(k) => onRowAction(k, row as unknown as AssetDisposal)"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="var(--bs-layout-dialog-md)" append-to-body>
    <el-form ref="formRef" :model="form" label-width="110px">
      <el-form-item
        :label="t('asset.disposal.asset')"
        prop="assetId"
        :rules="[{ required: true, message: t('common.form.required') }]"
      >
        <el-select v-model="form.assetId" filterable style="width: 100%">
          <el-option v-for="o in assetOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('asset.disposal.disposalType')">
            <el-select v-model="form.disposalType" style="width: 100%">
              <el-option v-for="o in typeDict.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.disposal.applyDate')">
            <el-date-picker v-model="form.applyDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.disposal.disposalAmount')">
            <el-input-number v-model="form.disposalAmount" :min="0" :precision="2" :controls="false" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('asset.disposal.handler')">
            <el-input v-model="form.handlerName" :maxlength="64" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="t('asset.disposal.reason')">
        <el-input v-model="form.reason" type="textarea" :rows="3" :maxlength="1000" />
      </el-form-item>
      <el-form-item :label="t('asset.disposal.remark')">
        <el-input v-model="form.remark" type="textarea" :rows="2" :maxlength="500" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>

  <el-drawer v-model="detailVisible" size="var(--bs-layout-drawer-md)">
    <template #header>
      <div class="drawer-header">
        <span class="drawer-title">{{ detail?.disposalNo || t('asset.common.detail') }}</span>
        <StatusTag v-if="detail" :status="detail.status" i18n-prefix="asset.status" />
      </div>
    </template>
    <div v-loading="detailLoading" class="drawer-body">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="t('asset.disposal.asset')">
            {{ detail.assetNo }} {{ detail.assetName }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('asset.disposal.disposalType')">
            {{ detail.disposalTypeText || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('asset.disposal.applyDate')">{{ detail.applyDate || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.disposal.originalValue')">{{ detail.originalValue ?? '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.disposal.netValue')">{{ detail.netValue ?? '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.disposal.disposalAmount')">{{ detail.disposalAmount ?? '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.disposal.handler')">{{ detail.handlerName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.disposal.approver')">{{ detail.approverName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.disposal.approveAt')">{{ detail.approveAt || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('common.form.remark')">{{ detail.remark || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.disposal.reason')" :span="2">{{ detail.reason || '-' }}</el-descriptions-item>
        </el-descriptions>
      </template>
    </div>
  </el-drawer>
</template>

<style scoped>
.drawer-header {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.drawer-title {
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
}

.drawer-body {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}
</style>
