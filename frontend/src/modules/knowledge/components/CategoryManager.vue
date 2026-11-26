<script setup lang="ts">
/**
 * 分类管理抽屉（微盘式文档中心内嵌）。
 *
 * B12 起分类不再作为独立导航入口 —— 管理能力并入文档中心页面，
 * 分类树本身仍是多级可定义的（物化路径 /1/3/），供文档归类与门户制度展示复用。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import {
  createKnowledgeCategory,
  deleteKnowledgeCategory,
  listKnowledgeCategories,
  updateKnowledgeCategory,
} from '@/api/knowledge'
import type { KnowledgeCategory } from '@/api/types'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void; (e: 'changed'): void }>()

const { t } = useI18n()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const categories = ref<KnowledgeCategory[]>([])
const loading = ref(false)
const selectedId = ref<number | null>(null)

const treeProps = computed(() => ({ label: 'name', children: 'children' }))

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

watch(
  () => props.modelValue,
  (v) => {
    if (v) void load()
  },
)

const current = computed(
  () => categories.value.find((n) => n.id === selectedId.value) ?? null,
)

/** 右侧列表：选中分类的直接子分类；未选中时展示顶级分类 */
const rows = computed(() => (current.value ? current.value.children ?? [] : categories.value))

/* ---------------- 新增 / 编辑 ---------------- */
const dialogVisible = ref(false)
const editing = ref<KnowledgeCategory | null>(null)
const form = ref({ name: '', code: '', parentId: null as number | null, sort: 0, description: '' })

function openDialog(row: KnowledgeCategory | null, parentId?: number | null) {
  editing.value = row
  form.value = {
    name: row?.name ?? '',
    code: row?.code ?? '',
    parentId: row ? row.parentId : (parentId ?? selectedId.value),
    sort: row?.sort ?? 0,
    description: row?.description ?? '',
  }
  dialogVisible.value = true
}

async function submit() {
  if (!form.value.name.trim()) return
  const payload = {
    name: form.value.name.trim(),
    code: form.value.code.trim(),
    parent_id: form.value.parentId,
    sort: form.value.sort,
    description: form.value.description,
    status: 'enabled',
  }
  if (editing.value) await updateKnowledgeCategory(editing.value.id, payload as never)
  else await createKnowledgeCategory(payload as never)
  ElMessage.success(t('knowledge.category.saved'))
  dialogVisible.value = false
  await load()
  emit('changed')
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
  if (selectedId.value === row.id) selectedId.value = null
  await load()
  emit('changed')
}
</script>

<template>
  <el-drawer
    v-model="visible"
    :title="t('knowledge.category.title')"
    size="var(--bs-layout-drawer-lg)"
    append-to-body
  >
    <div class="cat-manager">
      <aside class="cat-side">
        <el-tree
          :data="categories"
          node-key="id"
          :props="treeProps"
          :expand-on-click-node="false"
          highlight-current
          @node-click="(node: KnowledgeCategory) => (selectedId = node.id)"
        />
        <el-empty v-if="!categories.length" :description="t('knowledge.common.empty')" :image-size="60" />
      </aside>

      <div class="cat-main">
        <div class="cat-bar">
          <el-button v-permission="'knowledge:category:edit'" type="primary" @click="openDialog(null, null)">
            {{ t('knowledge.category.addRoot') }}
          </el-button>
          <el-tag v-if="current" type="info" size="small" closable @close="selectedId = null">
            {{ current.name }}
          </el-tag>
          <span v-else class="cat-hint">{{ t('knowledge.category.topLevel') }}</span>
        </div>

        <el-table :data="rows" size="small" height="100%" row-key="id">
          <el-table-column prop="name" :label="t('knowledge.common.name')" min-width="180" />
          <el-table-column prop="code" :label="t('knowledge.common.code')" min-width="120" />
          <el-table-column prop="level" :label="t('knowledge.common.level')" width="80" align="center" />
          <el-table-column prop="docCount" :label="t('knowledge.category.docCount')" width="90" align="center" />
          <el-table-column :label="t('common.action.operate')" width="150" align="center">
            <template #default="{ row }">
              <el-button
                v-permission="'knowledge:category:edit'"
                link
                type="primary"
                @click="openDialog(null, row.id)"
              >
                {{ t('knowledge.category.addChild') }}
              </el-button>
              <el-button
                v-permission="'knowledge:category:edit'"
                link
                type="primary"
                @click="openDialog(row)"
              >
                {{ t('knowledge.category.edit') }}
              </el-button>
              <el-button
                v-permission="'knowledge:category:edit'"
                link
                type="danger"
                @click="doDelete(row)"
              >
                {{ t('knowledge.category.delete') }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
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
  </el-drawer>
</template>

<style scoped>
.cat-manager {
  display: flex;
  gap: var(--bs-space-3);
  height: 100%;
  min-height: 0;
}

.cat-side {
  width: 240px;
  flex: 0 0 240px;
  overflow: auto;
  padding-right: var(--bs-space-2);
  border-right: 1px solid var(--bs-color-border-subtle);
}

.cat-main {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.cat-bar {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
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
