<script setup lang="ts">
/**
 * 物料台账（CSV 第 23 项）——统一存货视角的台账视图：呆滞/低库存预警筛选 + BOM 关联反查。
 * 后端：/api/v1/asset/items（含呆滞预警字段与 filters[stagnant|stagnant_level|warning|low_stock]）。
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { useListPage } from '@/composables/useListPage'
import { useDictOptions } from '@/composables/useDict'
import { exportItems, itemBomRefs, itemCounts, listItems } from '@/api/asset'
import type { AssetItem, AssetItemBomRefs } from '@/api/types'

defineOptions({ name: 'MaterialList' })

const { t } = useI18n()
const categoryDict = useDictOptions('stock_category')

/** 预警维度页签：all 全部 / warning 有预警 / lowStock 低库存 / stagnant 呆滞 */
const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'warning', labelKey: 'asset.material.tabWarning', count: 0 },
  { value: 'lowStock', labelKey: 'asset.material.tabLowStock', count: 0 },
  { value: 'stagnant', labelKey: 'asset.material.tabStagnant', count: 0 },
])

const searchModel = ref<Record<string, any>>({ q: '', category: '', level: '' })
const searchFields = computed<SearchField[]>(() => [
  { key: 'q', labelKey: 'asset.item.name', placeholderKey: 'common.form.placeholderSearch', width: 220 },
  {
    key: 'category',
    labelKey: 'asset.item.category',
    type: 'select',
    width: 160,
    options: categoryDict.opts.value,
  },
  {
    key: 'level',
    labelKey: 'asset.material.level',
    type: 'select',
    width: 160,
    options: [
      { label: t('asset.material.levelNormal'), value: 'normal' },
      { label: t('asset.material.levelSlow'), value: 'slow' },
      { label: t('asset.material.levelStagnant'), value: 'stagnant' },
      { label: t('asset.material.levelDead'), value: 'dead' },
    ],
  },
])

const counts = ref<Record<string, number>>({})

const stagnantCount = computed(() => Number(counts.value.stagnant ?? 0))
const lowStockCount = computed(() => Number(counts.value.lowStock ?? 0))
const stagnantAmountTotal = computed(() => Number(counts.value.stagnantAmount ?? 0))

async function loadCounts() {
  try {
    const data = (await itemCounts()) ?? {}
    counts.value = data
    for (const tab of statusTabs.value) {
      if (tab.value === 'all') {
        tab.count = data.all ?? 0
        continue
      }
      tab.count = data[tab.value] ?? 0
    }
  } catch {
    /* counts optional */
  }
}

onMounted(() => void loadCounts())

/** 页签 → 后端筛选参数 */
function buildFilters(tab: string) {
  const filters: Record<string, string> = {}
  if (searchModel.value.category) filters.category = searchModel.value.category
  if (searchModel.value.level) filters.stagnant_level = searchModel.value.level
  if (tab === 'warning') filters.warning = '1'
  else if (tab === 'lowStock') filters.low_stock = '1'
  else if (tab === 'stagnant') filters.stagnant = '1'
  return filters
}

const list = useListPage<AssetItem>({
  fetch: async (params) => {
    const tab = String(params.status ?? 'all')
    const data = await listItems({
      page: Number(params.page ?? 1),
      size: Number(params.size ?? 20),
      q: searchModel.value.q || undefined,
      filters: buildFilters(tab),
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) => {
    const tab = String(params.status ?? 'all')
    return exportItems({
      q: searchModel.value.q || undefined,
      filters: buildFilters(tab),
    })
  },
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'code', labelKey: 'asset.item.code', width: 140, fixed: 'left', sortable: 'code' },
  { prop: 'name', labelKey: 'asset.item.name', minWidth: 160, sortable: 'name' },
  { prop: 'spec', labelKey: 'asset.item.spec', minWidth: 130 },
  { prop: 'unit', labelKey: 'asset.item.unit', width: 80 },
  { prop: 'category', labelKey: 'asset.item.category', width: 110 },
  { prop: 'qtyOnHand', labelKey: 'asset.item.qtyOnHand', width: 110, align: 'right' },
  { prop: 'unitPrice', labelKey: 'asset.item.unitPrice', width: 110, align: 'right', sortable: 'unit_price' },
  { prop: 'stagnantLevel', labelKey: 'asset.material.level', width: 110 },
  { prop: 'idleDays', labelKey: 'asset.material.idleDays', width: 110, align: 'right' },
  { prop: 'lastMoveAt', labelKey: 'asset.material.lastMoveAt', width: 160 },
  { prop: 'stagnantAmount', labelKey: 'asset.material.stagnantAmount', width: 130, align: 'right' },
  { prop: 'warning', labelKey: 'asset.material.warning', width: 100 },
  { prop: 'createTime', labelKey: 'common.form.createTime', width: 160, sortable: 'create_time' },
]

function categoryLabel(value: unknown) {
  const v = String(value ?? '')
  return categoryDict.opts.value.find((x) => x.value === v)?.label || v || '-'
}

function levelType(level: unknown): 'success' | 'warning' | 'danger' | 'info' {
  switch (String(level)) {
    case 'slow':
      return 'warning'
    case 'stagnant':
    case 'dead':
      return 'danger'
    case 'normal':
      return 'success'
    default:
      return 'info'
  }
}

function rowActions(): ActionItem[] {
  return [{ key: 'bom', tip: 'asset.material.bomRefs', icon: 'Files' }]
}

function onRowAction(key: string, row: AssetItem) {
  if (key === 'bom') void openBomRefs(row.id)
}

/* ---------- BOM 关联抽屉 ---------- */
const refsVisible = ref(false)
const refsLoading = ref(false)
const refs = ref<AssetItemBomRefs | null>(null)

async function openBomRefs(id: number) {
  refsVisible.value = true
  refsLoading.value = true
  try {
    refs.value = await itemBomRefs(id)
  } catch {
    refs.value = null
  } finally {
    refsLoading.value = false
  }
}
</script>

<template>
  <ListPage :title="t('asset.material.title')" :loading="list.loading.value">
    <template #actions>
      <ExportButton v-permission="'asset:material:export'" :export-fn="() => list.exportList()" />
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '', category: '', level: '' }; list.reset()"
      />
    </template>

    <template #statusTabs>
      <StatusTabs
        :tabs="statusTabs"
        :model-value="String(list.query.status)"
        @update:model-value="list.setStatus($event)"
      />
    </template>

    <template #toolbar>
      <div class="summary-bar">
        <span class="summary-item">
          {{ t('asset.material.stagnantTotal') }}
          <b>{{ stagnantCount }}</b>
        </span>
        <span class="summary-item">
          {{ t('asset.material.lowStockTotal') }}
          <b>{{ lowStockCount }}</b>
        </span>
        <span class="summary-item">
          {{ t('asset.material.stagnantAmountTotal') }}
          <b>{{ stagnantAmountTotal }}</b>
        </span>
      </div>
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
        <template #code="{ row }">
          <span class="code-cell">{{ row.code }}</span>
        </template>
        <template #category="{ row }">{{ categoryLabel(row.category) }}</template>
        <template #stagnantLevel="{ row }">
          <el-tag :type="levelType(row.stagnantLevel)" size="small" effect="light" round>
            {{ row.stagnantLevelText || row.stagnantLevel }}
          </el-tag>
        </template>
        <template #warning="{ row }">
          <el-tag v-if="row.warning" type="danger" size="small" effect="light" round>
            {{ t('asset.material.hasWarning') }}
          </el-tag>
          <span v-else>{{ t('asset.material.noWarning') }}</span>
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="100" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar
                :actions="rowActions()"
                @select="(k) => onRowAction(k, row as unknown as AssetItem)"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-drawer v-model="refsVisible" size="var(--bs-layout-drawer-md)" :title="t('asset.material.bomRefs')">
    <div v-loading="refsLoading" class="drawer-body">
      <template v-if="refs">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item :label="t('asset.common.code')">{{ refs.itemCode }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.item.name')">{{ refs.itemName }}</el-descriptions-item>
        </el-descriptions>

        <div class="section-title">{{ t('asset.material.asParent') }}</div>
        <el-table v-if="refs.asParent?.length" :data="refs.asParent" border stripe size="small">
          <el-table-column :label="t('asset.bom.bomNo')" prop="bomNo" min-width="140" />
          <el-table-column :label="t('asset.bom.version')" prop="version" width="90" />
          <el-table-column :label="t('asset.bom.lineCount')" prop="lineCount" width="90" align="right" />
          <el-table-column :label="t('common.form.status')" width="100">
            <template #default="{ row }">
              <StatusTag :status="String(row.status)" i18n-prefix="asset.status" />
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else :description="t('asset.material.noBom')" :image-size="60" />

        <div class="section-title">{{ t('asset.material.asChild') }}</div>
        <el-table v-if="refs.asChild?.length" :data="refs.asChild" border stripe size="small">
          <el-table-column :label="t('asset.bom.bomNo')" prop="bomNo" min-width="140" />
          <el-table-column :label="t('asset.bom.parentName')" prop="parentItemName" min-width="140" />
          <el-table-column :label="t('asset.bom.version')" prop="version" width="90" />
          <el-table-column :label="t('asset.bom.unitQty')" prop="qty" width="90" align="right" />
          <el-table-column :label="t('asset.bom.position')" prop="position" width="110" />
        </el-table>
        <el-empty v-else :description="t('asset.material.noBom')" :image-size="60" />
      </template>
    </div>
  </el-drawer>
</template>

<style scoped>
.summary-bar {
  display: flex;
  align-items: center;
  gap: var(--bs-space-4);
  width: 100%;
  padding: var(--bs-space-2) var(--bs-layout-content-padding);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-secondary);
}

.summary-item b {
  color: var(--bs-color-fg-default);
  margin-left: var(--bs-space-1);
}

.code-cell {
  font-family: var(--bs-font-family-mono, monospace);
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
</style>
