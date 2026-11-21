<script setup lang="ts">
/**
 * 物料清单（BOM）——父件/子件结构、版本管理、多级展开、用量对比。
 * 后端：/api/v1/asset/boms（asset/bom_router.py）
 */
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
import {
  activateBom,
  bomCounts,
  bomUsage,
  copyBom,
  createBom,
  deleteBom,
  explodeBom,
  exportBoms,
  getBom,
  listBoms,
  obsoleteBom,
  updateBom,
} from '@/api/asset'
import type {
  AssetBom,
  AssetBomExplode,
  AssetBomLineInput,
  AssetBomNode,
  AssetBomUsage,
} from '@/api/types'
import { useItemOptions } from '../composables/useAssetOptions'

defineOptions({ name: 'BomList' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const itemOpts = useItemOptions()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'asset.bom.searchPlaceholder',
    placeholderKey: 'common.form.placeholderSearch',
    width: 280,
  },
])

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'draft', labelKey: 'asset.status.draft', count: 0 },
  { value: 'effective', labelKey: 'asset.status.effective', count: 0 },
  { value: 'obsolete', labelKey: 'asset.status.obsolete', count: 0 },
])

async function loadCounts() {
  try {
    const data = (await bomCounts()) ?? {}
    for (const tab of statusTabs.value) {
      if (tab.value === 'all') continue
      tab.count = data[tab.value] ?? 0
    }
    const allTab = statusTabs.value.find((x) => x.value === 'all')
    if (allTab) {
      allTab.count = statusTabs.value.reduce((acc, x) => acc + (x.value === 'all' ? 0 : (x.count ?? 0)), 0)
    }
  } catch {
    /* counts optional */
  }
}

onMounted(() => void loadCounts())

const list = useListPage<AssetBom>({
  fetch: async (params) => {
    const data = await listBoms({ ...params, q: searchModel.value.q || undefined })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) => exportBoms({ ...params, q: searchModel.value.q || undefined }),
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'bomNo', labelKey: 'asset.bom.bomNo', width: 160, fixed: 'left', sortable: 'bom_no' },
  { prop: 'parentItemCode', labelKey: 'asset.bom.parentCode', width: 140 },
  { prop: 'parentItemName', labelKey: 'asset.bom.parentName', minWidth: 180 },
  { prop: 'parentSpec', labelKey: 'asset.bom.parentSpec', minWidth: 140 },
  { prop: 'version', labelKey: 'asset.bom.version', width: 100, sortable: 'bom_version' },
  { prop: 'lineCount', labelKey: 'asset.bom.lineCount', width: 100, align: 'right' },
  { prop: 'effectiveDate', labelKey: 'asset.bom.effectiveDate', width: 120, sortable: 'effective_date' },
  { prop: 'status', labelKey: 'common.form.status', width: 110, sortable: 'status' },
  { prop: 'createTime', labelKey: 'common.form.createTime', width: 160, sortable: 'create_time' },
]

function rowActions(row: AssetBom): ActionItem[] {
  const s = String(row.status)
  const acts: ActionItem[] = [{ key: 'detail', tip: 'common.action.detail' }]
  if (s === 'draft') {
    acts.push({ key: 'edit', tip: 'common.action.edit', perm: 'asset:bom:edit' })
    acts.push({ key: 'activate', tip: 'asset.bom.activate', icon: 'CircleCheck', perm: 'asset:bom:edit' })
    acts.push({ key: 'delete', tip: 'common.action.delete', perm: 'asset:bom:delete' })
  } else if (s === 'effective') {
    acts.push({ key: 'obsolete', tip: 'asset.bom.obsolete', icon: 'CircleClose', perm: 'asset:bom:edit' })
  }
  acts.push({ key: 'copy', tip: 'asset.bom.copy', icon: 'DocumentCopy', perm: 'asset:bom:create' })
  return acts
}

function onRowAction(key: string, row: AssetBom) {
  if (key === 'detail') void openDetail(row.id)
  else if (key === 'edit') openEdit(row)
  else if (key === 'activate') void doActivate(row)
  else if (key === 'obsolete') void doObsolete(row)
  else if (key === 'copy') void doCopy(row)
  else if (key === 'delete') void remove(row)
}

/* ---------- form ---------- */
const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  parentItemId: null as number | null,
  bomVersion: 'V1.0',
  effectiveDate: '',
  remark: '',
  lines: [] as AssetBomLineInput[],
  version: null as number | null,
})

function blankLine(): AssetBomLineInput {
  return { itemId: null, itemCode: '', itemName: '', spec: '', unit: '', qty: 1, lossRate: 0, refDesignator: '', position: '', remark: '' }
}

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('asset.bom.create')
  Object.assign(form, {
    parentItemId: null,
    bomVersion: 'V1.0',
    effectiveDate: '',
    remark: '',
    lines: [blankLine()],
    version: null,
  })
  void itemOpts.load()
  dialogVisible.value = true
}

async function openEdit(row: AssetBom) {
  try {
    const full = await getBom(row.id)
    editingId.value = full.id
    dialogTitle.value = t('asset.bom.edit')
    Object.assign(form, {
      parentItemId: full.parentItemId,
      bomVersion: full.version,
      effectiveDate: full.effectiveDate ?? '',
      remark: full.remark,
      lines: (full.lines ?? []).map((l) => ({
        itemId: l.itemId ?? null,
        itemCode: l.itemCode,
        itemName: l.itemName,
        spec: l.spec,
        unit: l.unit,
        qty: l.qty,
        lossRate: l.lossRate,
        refDesignator: l.refDesignator,
        position: l.position,
        remark: l.remark,
      })),
      version: full.lockVersion,
    })
    void itemOpts.load()
    dialogVisible.value = true
  } catch {
    /* http notifies */
  }
}

/** 选子件后自动带出名称/规格/单位；不允许选父件本身 */
function onLinePick(row: AssetBomLineInput, itemId: number | null) {
  if (!itemId) {
    row.itemId = null
    row.itemCode = ''
    row.itemName = ''
    row.spec = ''
    row.unit = ''
    return
  }
  if (form.parentItemId && itemId === form.parentItemId) {
    ElMessage.warning(t('asset.bom.selfReference'))
    row.itemId = null
    row.itemCode = ''
    row.itemName = ''
    return
  }
  const opt = itemOpts.items.value.find((o) => o.id === itemId)
  if (!opt) return
  row.itemId = opt.id
  row.itemCode = opt.code
  row.itemName = opt.name
  row.spec = opt.spec
  row.unit = opt.unit
}

async function save() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  if (!form.parentItemId) {
    ElMessage.warning(t('asset.bom.parentRequired'))
    return
  }
  const lines = form.lines.filter((l) => l.itemId)
  if (!lines.length) {
    ElMessage.warning(t('asset.bom.emptyLines'))
    return
  }
  if (lines.some((l) => l.itemId === form.parentItemId)) {
    ElMessage.warning(t('asset.bom.selfReference'))
    return
  }
  saving.value = true
  try {
    const payload = {
      parentItemId: form.parentItemId,
      bomVersion: form.bomVersion,
      effectiveDate: form.effectiveDate || null,
      remark: form.remark,
      lines,
      version: form.version,
    }
    if (editingId.value) await updateBom(editingId.value, payload)
    else await createBom(payload)
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function doActivate(row: AssetBom) {
  try {
    await ElMessageBox.confirm(t('asset.bom.activateTip'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await activateBom(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doObsolete(row: AssetBom) {
  try {
    await ElMessageBox.confirm(t('asset.bom.obsoleteTip'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await obsoleteBom(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doCopy(row: AssetBom) {
  try {
    await ElMessageBox.confirm(t('asset.bom.copyTip'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await copyBom(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function remove(row: AssetBom) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteBom(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------- detail drawer ---------- */
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<AssetBom | null>(null)
const explode = ref<AssetBomExplode | null>(null)
const usage = ref<AssetBomUsage | null>(null)
const usageQty = ref(1)

async function loadUsage(id: number) {
  try {
    usage.value = await bomUsage(id, usageQty.value)
  } catch {
    usage.value = null
  }
}

async function openDetail(id: number) {
  detailVisible.value = true
  detailLoading.value = true
  usageQty.value = 1
  try {
    detail.value = await getBom(id)
    explode.value = await explodeBom(id).catch(() => null)
    await loadUsage(id)
  } catch {
    detail.value = null
    explode.value = null
    usage.value = null
  } finally {
    detailLoading.value = false
  }
}

watch(usageQty, () => {
  if (detail.value) void loadUsage(detail.value.id)
})

/** 展开树节点文案 */
function nodeText(data: AssetBomNode) {
  return `${data.itemCode} ${data.itemName}`
}

// 深链互跳：/asset/boms?detail=<id>
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
  <ListPage :title="t('asset.bom.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'asset:bom:create'" type="primary" @click="openCreate">
        {{ t('asset.bom.create') }}
      </el-button>
      <ExportButton v-permission="'asset:bom:export'" :export-fn="() => list.exportList()" />
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
        <template #bomNo="{ row }">
          <el-button link type="primary" @click="openDetail(row.id)">{{ row.bomNo }}</el-button>
        </template>
        <template #version="{ row }">
          <el-tag size="small" effect="plain">{{ row.version }}</el-tag>
        </template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="asset.status" />
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="150" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar
                :actions="rowActions(row as unknown as AssetBom)"
                @select="(k) => onRowAction(k, row as unknown as AssetBom)"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <!-- 新建 / 编辑 BOM -->
  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="var(--bs-layout-dialog-xl)" append-to-body>
    <el-form ref="formRef" :model="form" label-width="110px">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('asset.bom.parentItem')" prop="parentItemId" :rules="[{ required: true, message: t('common.form.required') }]">
            <el-select
              v-model="form.parentItemId"
              filterable
              clearable
              :placeholder="t('asset.common.selectItem')"
              style="width: 100%"
            >
              <el-option v-for="o in itemOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item :label="t('asset.bom.version')" prop="bomVersion" :rules="[{ required: true, message: t('common.form.required') }]">
            <el-input v-model="form.bomVersion" :maxlength="32" />
          </el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item :label="t('asset.bom.effectiveDate')">
            <el-date-picker v-model="form.effectiveDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item :label="t('asset.bom.lines')">
        <div class="lines-editor">
          <el-table :data="form.lines" border size="small">
            <el-table-column :label="t('asset.bom.itemName')" min-width="220">
              <template #default="{ row }">
                <el-select
                  v-model="row.itemId"
                  filterable
                  clearable
                  :placeholder="t('asset.common.selectItem')"
                  style="width: 100%"
                  @change="(v: number | null) => onLinePick(row, v)"
                >
                  <el-option v-for="o in itemOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column :label="t('asset.bom.unitQty')" width="120">
              <template #default="{ row }">
                <el-input-number v-model="row.qty" :min="0.01" :precision="2" :controls="false" style="width: 100%" />
              </template>
            </el-table-column>
            <el-table-column :label="t('asset.bom.lossRate')" width="120">
              <template #default="{ row }">
                <el-input-number v-model="row.lossRate" :min="0" :max="100" :precision="2" :controls="false" style="width: 100%" />
              </template>
            </el-table-column>
            <el-table-column :label="t('asset.bom.refDesignator')" width="140">
              <template #default="{ row }"><el-input v-model="row.refDesignator" :maxlength="128" /></template>
            </el-table-column>
            <el-table-column :label="t('asset.bom.position')" width="140">
              <template #default="{ row }"><el-input v-model="row.position" :maxlength="64" /></template>
            </el-table-column>
            <el-table-column :label="t('common.action.operate')" width="80" align="center">
              <template #default="{ $index }">
                <el-button link type="danger" @click="form.lines.splice($index, 1)">{{ t('common.action.delete') }}</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-button class="add-line" size="small" @click="form.lines.push(blankLine())">
            {{ t('asset.common.addItem') }}
          </el-button>
        </div>
      </el-form-item>

      <el-form-item :label="t('asset.bom.remark')">
        <el-input v-model="form.remark" type="textarea" :rows="2" :maxlength="2000" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>

  <!-- BOM 详情 -->
  <el-drawer v-model="detailVisible" size="var(--bs-layout-drawer-lg)">
    <template #header>
      <div class="drawer-header">
        <span class="drawer-title">{{ detail?.bomNo || t('asset.common.detail') }}</span>
        <StatusTag v-if="detail" :status="detail.status" i18n-prefix="asset.status" />
      </div>
    </template>
    <div v-loading="detailLoading" class="drawer-body">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="t('asset.bom.parentItem')" :span="2">
            {{ detail.parentItemCode }} {{ detail.parentItemName }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('asset.bom.parentSpec')">{{ detail.parentSpec || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.bom.version')">{{ detail.version }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.bom.effectiveDate')">{{ detail.effectiveDate || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('common.form.createTime')">{{ detail.createTime || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.bom.remark')" :span="2">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div class="section-title">{{ t('asset.bom.lines') }}</div>
        <el-table :data="detail.lines ?? []" border stripe size="small">
          <el-table-column :label="t('asset.bom.itemName')" prop="itemName" min-width="140" />
          <el-table-column :label="t('asset.common.code')" prop="itemCode" width="120" />
          <el-table-column :label="t('asset.common.spec')" prop="spec" width="120" />
          <el-table-column :label="t('asset.common.unit')" prop="unit" width="70" />
          <el-table-column :label="t('asset.bom.unitQty')" prop="qty" width="90" align="right" />
          <el-table-column :label="t('asset.bom.lossRate')" prop="lossRate" width="90" align="right" />
          <el-table-column :label="t('asset.bom.requiredQty')" prop="requiredQty" width="100" align="right" />
          <el-table-column :label="t('asset.bom.refDesignator')" prop="refDesignator" width="110" />
          <el-table-column :label="t('asset.bom.position')" prop="position" width="110" />
        </el-table>

        <div class="section-title">{{ t('asset.bom.explode') }}</div>
        <el-tree
          v-if="explode?.tree?.length"
          :data="explode.tree"
          default-expand-all
          :expand-on-click-node="false"
        >
          <template #default="{ data }">
            <span class="tree-node">
              <span class="tree-node-main">{{ nodeText(data) }}</span>
              <span class="tree-node-meta">
                {{ t('asset.bom.unitQty') }} {{ data.qty }}
                {{ data.unit }}
                <template v-if="data.lossRate"> · {{ t('asset.bom.lossRate') }} {{ data.lossRate }}%</template>
              </span>
            </span>
          </template>
        </el-tree>
        <el-empty v-else :description="t('asset.bom.noChildren')" :image-size="60" />

        <div class="section-title usage-header">
          <span>{{ t('asset.bom.usage') }}</span>
          <div class="usage-qty">
            <span class="usage-label">{{ t('asset.bom.parentQty') }}</span>
            <el-input-number v-model="usageQty" :min="0.01" :precision="2" :controls="false" size="small" style="width: 110px" />
          </div>
        </div>
        <el-table v-if="usage?.lines?.length" :data="usage.lines" border stripe size="small">
          <el-table-column :label="t('asset.bom.itemName')" prop="itemName" min-width="140" />
          <el-table-column :label="t('asset.bom.requiredQty')" prop="requiredQty" width="110" align="right" />
          <el-table-column :label="t('asset.bom.actualOutQty')" prop="actualOutQty" width="110" align="right" />
          <el-table-column :label="t('asset.bom.diffQty')" prop="diffQty" width="100" align="right">
            <template #default="{ row }">
              <span :class="Number(row.diffQty) < 0 ? 'diff-negative' : 'diff-positive'">
                {{ row.diffQty }}
              </span>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else :description="t('asset.bom.noChildren')" :image-size="60" />
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

.section-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.usage-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.usage-qty {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.usage-label {
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-sm);
}

.lines-editor {
  width: 100%;
}

.add-line {
  margin-top: var(--bs-space-2);
}

.tree-node {
  display: inline-flex;
  align-items: baseline;
  gap: var(--bs-space-2);
}

.tree-node-meta {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}

.diff-negative {
  color: var(--bs-color-semantic-danger);
}

.diff-positive {
  color: var(--bs-color-semantic-success);
}
</style>
