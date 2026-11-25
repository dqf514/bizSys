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
  createKnowledgeCategory,
  deleteKnowledgeCategory,
  listKnowledgeCategories,
  updateKnowledgeCategory,
} from '@/api/knowledge'
import type { KnowledgeCategory } from '@/api/types'

defineOptions({ name: 'CategoryList' })

const { t } = useI18n()

const categories = ref<KnowledgeCategory[]>([])
const loading = ref(false)
const selectedId = ref<number | null>(null)
const query = reactive({ keyword: '' })

const searchFields = computed<SearchField[]>(() => [
  { key: 'keyword', labelKey: 'knowledge.common.keyword', type: 'input', width: 240 },
])

/* ---------------- 树 ---------------- */
function flatten(nodes: KnowledgeCategory[], depth = 0): (KnowledgeCategory & { depth: number })[] {
  const out: (KnowledgeCategory & { depth: number })[] = []
  for (const n of nodes) {
    out.push({ ...n, depth })
    if (n.children?.length) out.push(...flatten(n.children, depth + 1))
  }
  return out
}

const allNodes = computed(() => flatten(categories.value))

/** 关键词命中的分类及其祖先 */
const matchedIds = computed(() => {
  const kw = query.keyword.trim().toLowerCase()
  if (!kw) return null
  const ids = new Set<number>()
  const walk = (nodes: KnowledgeCategory[], ancestors: number[]) => {
    for (const n of nodes) {
      const hit = [n.name, n.code].filter(Boolean).some((v) => String(v).toLowerCase().includes(kw))
      if (hit) {
        for (const a of ancestors) ids.add(a)
        ids.add(n.id)
      }
      if (n.children?.length) walk(n.children, [...ancestors, n.id])
    }
  }
  walk(categories.value, [])
  return ids
})

const treeProps = computed(() => ({ label: 'name', children: 'children' }))

/** 关键词命中的分类及其祖先构成剪枝后的树 */
const displayTree = computed(() => {
  if (!matchedIds.value) return categories.value
  const prune = (nodes: KnowledgeCategory[]): KnowledgeCategory[] =>
    nodes
      .filter((n) => matchedIds.value!.has(n.id))
      .map((n) => ({ ...n, children: prune(n.children ?? []) }))
  return prune(categories.value)
})

async function load() {
  loading.value = true
  try {
    const data = await listKnowledgeCategories()
    categories.value = data.items ?? []
  } catch {
    categories.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())

function onNodeClick(node: KnowledgeCategory) {
  selectedId.value = node.id
}

const current = computed(() => allNodes.value.find((n) => n.id === selectedId.value) ?? null)

/** 右侧列表：选中分类的直接子分类；未选中时展示顶级分类 */
const rows = computed(() => {
  const list = current.value ? current.value.children ?? [] : categories.value
  return list.map((c) => ({ ...c, depth: 0 }))
})

/* ---------------- 表格 ---------------- */
const columns = computed<ListColumn[]>(() => [
  { prop: 'name', labelKey: 'knowledge.common.name', minWidth: 200 },
  { prop: 'code', labelKey: 'knowledge.common.code', minWidth: 140 },
  { prop: 'level', labelKey: 'knowledge.common.level', width: 90, align: 'center' },
  { prop: 'docCount', labelKey: 'knowledge.category.docCount', width: 100, align: 'center' },
  { prop: 'description', labelKey: 'knowledge.common.description', minWidth: 180 },
  { prop: 'sort', labelKey: 'knowledge.common.sort', width: 90, align: 'center' },
  { prop: 'actions', labelKey: 'common.action.operate', width: 110, fixed: 'right', align: 'center', slot: 'actions' },
])

const rowActions = computed<ActionItem[]>(() => [
  { key: 'addChild', tip: 'knowledge.category.addChild', perm: 'knowledge:category:edit' },
  { key: 'edit', tip: 'knowledge.category.edit', perm: 'knowledge:category:edit' },
  { key: 'delete', tip: 'knowledge.category.delete', perm: 'knowledge:category:edit' },
])

function onAction(key: string, row: KnowledgeCategory) {
  if (key === 'addChild') openDialog(null, row.id)
  else if (key === 'edit') openDialog(row)
  else if (key === 'delete') void doDelete(row)
}

/* ---------------- 新增 / 编辑 ---------------- */
const dialogVisible = ref(false)
const editing = ref<KnowledgeCategory | null>(null)
const form = reactive({ name: '', code: '', parentId: null as number | null, sort: 0, description: '' })

function openDialog(row: KnowledgeCategory | null, parentId?: number | null) {
  editing.value = row
  form.name = row?.name ?? ''
  form.code = row?.code ?? ''
  form.parentId = row ? row.parentId : (parentId ?? selectedId.value)
  form.sort = row?.sort ?? 0
  form.description = row?.description ?? ''
  dialogVisible.value = true
}

async function submit() {
  if (!form.name.trim()) return
  const payload = {
    name: form.name.trim(),
    code: form.code.trim(),
    parent_id: form.parentId,
    sort: form.sort,
    description: form.description,
    status: 'enabled',
  }
  if (editing.value) await updateKnowledgeCategory(editing.value.id, payload as never)
  else await createKnowledgeCategory(payload as never)
  ElMessage.success(t('knowledge.category.saved'))
  dialogVisible.value = false
  await load()
}

async function doDelete(row: KnowledgeCategory) {
  try {
    await ElMessageBox.confirm(t('knowledge.category.deleteConfirm', { name: row.name }), t('common.action.confirm'), {
      type: 'warning',
    })
  } catch {
    return
  }
  await deleteKnowledgeCategory(row.id)
  ElMessage.success(t('common.message.deleteSuccess'))
  await load()
}
</script>

<template>
  <div class="bs-page bs-page--fill">
    <PageHeader :title="t('knowledge.category.title')">
      <template #actions>
        <el-button v-permission="'knowledge:category:edit'" type="primary" @click="openDialog(null, null)">
          {{ t('knowledge.category.addRoot') }}
        </el-button>
        <el-button @click="load()">{{ t('common.action.refresh') }}</el-button>
      </template>
    </PageHeader>

    <div class="bs-page-card cat-layout">
      <aside class="cat-side">
        <SearchBar v-model="query" :fields="searchFields" @search="() => undefined" @reset="query.keyword = ''" />
        <el-tree
          :data="displayTree"
          node-key="id"
          :props="treeProps"
          :expand-on-click-node="false"
          highlight-current
          @node-click="onNodeClick"
        />
        <el-empty v-if="!categories.length" :description="t('knowledge.common.empty')" :image-size="60" />
      </aside>

      <div class="cat-main">
        <div class="cat-breadcrumb">
          <el-tag v-if="current" type="info" size="small" closable @close="selectedId = null">
            {{ current.name }}
          </el-tag>
          <span v-else class="cat-hint">{{ t('knowledge.category.topLevel') }}</span>
        </div>
        <ListTable
          :columns="columns"
          :data="rows as unknown as Record<string, unknown>[]"
          :loading="loading"
          :show-pagination="false"
          row-key="id"
          height="100%"
        >
          <template #actions="{ row }">
            <ActionBar
              :actions="rowActions"
              @select="(key: string) => onAction(key, row as unknown as KnowledgeCategory)"
            />
          </template>
        </ListTable>
      </div>
    </div>
  </div>

  <el-dialog
    v-model="dialogVisible"
    :title="editing ? t('knowledge.category.edit') : t('knowledge.category.addRoot')"
    width="var(--bs-layout-dialog-sm)"
    append-to-body
  >
    <el-form label-position="top">
      <el-form-item :label="t('knowledge.common.name')">
        <el-input v-model="form.name" />
      </el-form-item>
      <el-form-item :label="t('knowledge.common.code')">
        <el-input v-model="form.code" />
      </el-form-item>
      <el-form-item :label="t('knowledge.category.parent')">
        <el-tree-select
          v-model="form.parentId"
          :data="categories"
          node-key="id"
          :props="treeProps"
          check-strictly
          clearable
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item :label="t('knowledge.common.sort')">
        <el-input-number v-model="form.sort" :min="0" />
      </el-form-item>
      <el-form-item :label="t('knowledge.common.description')">
        <el-input v-model="form.description" type="textarea" :rows="3" />
      </el-form-item>
      <el-alert :title="t('knowledge.category.moveTip')" type="info" :closable="false" show-icon />
    </el-form>
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" @click="submit()">{{ t('common.action.save') }}</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.cat-layout {
  display: flex;
  gap: var(--bs-space-3);
  height: calc(100% - var(--bs-layout-content-padding) * 2);
  min-height: 0;
}

.cat-side {
  width: 260px;
  flex: 0 0 260px;
  overflow: auto;
  padding: var(--bs-space-2);
  border-right: 1px solid var(--bs-color-border-subtle);
}

.cat-main {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.cat-breadcrumb {
  margin-bottom: var(--bs-space-2);
}

.cat-hint {
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-sm);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--bs-space-2);
}
</style>
