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
  createKnowledgeSpace,
  deleteKnowledgeSpace,
  listKnowledgeSpaces,
  updateKnowledgeSpace,
} from '@/api/knowledge'
import type { KnowledgeSpace } from '@/api/types'

defineOptions({ name: 'SpaceList' })

const { t } = useI18n()

const spaces = ref<KnowledgeSpace[]>([])
const loading = ref(false)
const query = reactive({ keyword: '', type: '' })

const typeOptions = computed(() => [
  { label: t('knowledge.space.personal'), value: 'personal' },
  { label: t('knowledge.space.shared'), value: 'shared' },
])

const searchFields = computed<SearchField[]>(() => [
  { key: 'keyword', labelKey: 'knowledge.common.keyword', type: 'input', width: 240 },
  { key: 'type', labelKey: 'knowledge.common.type', type: 'select', width: 160, options: typeOptions.value },
])

const filtered = computed(() => {
  const kw = query.keyword.trim().toLowerCase()
  return spaces.value.filter((s) => {
    if (query.type && s.type !== query.type) return false
    if (!kw) return true
    return [s.name, s.description, s.ownerName].filter(Boolean).some((v) => String(v).toLowerCase().includes(kw))
  })
})

async function load() {
  loading.value = true
  try {
    const data = await listKnowledgeSpaces()
    spaces.value = data.items ?? []
  } catch {
    spaces.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())

function resetQuery() {
  query.keyword = ''
  query.type = ''
}

const columns = computed<ListColumn[]>(() => [
  { prop: 'name', labelKey: 'knowledge.common.name', minWidth: 200 },
  { prop: 'type', labelKey: 'knowledge.common.type', width: 120, slot: 'type' },
  { prop: 'ownerName', labelKey: 'knowledge.space.owner', width: 130 },
  { prop: 'description', labelKey: 'knowledge.common.description', minWidth: 200 },
  { prop: 'status', labelKey: 'knowledge.common.status', width: 100, slot: 'status' },
  { prop: 'createTime', labelKey: 'knowledge.common.createTime', minWidth: 160 },
  { prop: 'actions', labelKey: 'common.action.operate', width: 110, fixed: 'right', align: 'center', slot: 'actions' },
])

const rowActions = computed<ActionItem[]>(() => [
  { key: 'edit', tip: 'knowledge.space.edit', perm: 'knowledge:space:edit' },
  { key: 'delete', tip: 'knowledge.space.delete', perm: 'knowledge:space:edit' },
])

function onAction(key: string, row: KnowledgeSpace) {
  if (key === 'edit') openDialog(row)
  else if (key === 'delete') void doDelete(row)
}

/* ---------------- 新增 / 编辑 ---------------- */
const dialogVisible = ref(false)
const editing = ref<KnowledgeSpace | null>(null)
const form = reactive({ name: '', type: 'personal', description: '', status: 'enabled' })

function openDialog(row: KnowledgeSpace | null) {
  editing.value = row
  form.name = row?.name ?? ''
  form.type = row?.type ?? 'personal'
  form.description = row?.description ?? ''
  form.status = row?.status ?? 'enabled'
  dialogVisible.value = true
}

async function submit() {
  if (!form.name.trim()) return
  const payload = {
    name: form.name.trim(),
    type: form.type,
    description: form.description,
    status: form.status,
    owner_id: editing.value?.ownerId ?? null,
    dept_id: editing.value?.deptId ?? null,
  }
  if (editing.value) await updateKnowledgeSpace(editing.value.id, payload as never)
  else await createKnowledgeSpace(payload as never)
  ElMessage.success(t('common.message.saveSuccess'))
  dialogVisible.value = false
  await load()
}

async function doDelete(row: KnowledgeSpace) {
  try {
    await ElMessageBox.confirm(t('knowledge.space.deleteConfirm', { name: row.name }), t('common.action.confirm'), {
      type: 'warning',
    })
  } catch {
    return
  }
  await deleteKnowledgeSpace(row.id)
  ElMessage.success(t('common.message.deleteSuccess'))
  await load()
}
</script>

<template>
  <div class="bs-page">
    <PageHeader :title="t('knowledge.space.title')">
      <template #actions>
        <el-button v-permission="'knowledge:space:edit'" type="primary" @click="openDialog(null)">
          {{ t('knowledge.space.create') }}
        </el-button>
        <el-button @click="load()">{{ t('common.action.refresh') }}</el-button>
      </template>
    </PageHeader>

    <div class="bs-page-card">
      <SearchBar v-model="query" :fields="searchFields" @search="() => undefined" @reset="resetQuery" />
      <el-alert :title="t('knowledge.space.sharedTip')" type="info" :closable="false" show-icon class="space-tip" />
      <ListTable
        :columns="columns"
        :data="filtered as unknown as Record<string, unknown>[]"
        :loading="loading"
        :show-pagination="false"
        row-key="id"
      >
        <template #type="{ row }">
          <el-tag size="small" :type="row.type === 'shared' ? 'warning' : 'info'">
            {{ row.type === 'shared' ? t('knowledge.space.shared') : t('knowledge.space.personal') }}
          </el-tag>
        </template>
        <template #status="{ row }">
          <el-tag size="small" :type="row.status === 'enabled' ? 'success' : 'info'">
            {{ row.status === 'enabled' ? t('knowledge.common.enabled') : t('knowledge.common.disabled') }}
          </el-tag>
        </template>
        <template #actions="{ row }">
          <ActionBar
            :actions="rowActions"
            @select="(key: string) => onAction(key, row as unknown as KnowledgeSpace)"
          />
        </template>
      </ListTable>
    </div>
  </div>

  <el-dialog
    v-model="dialogVisible"
    :title="editing ? t('knowledge.space.edit') : t('knowledge.space.create')"
    width="var(--bs-layout-dialog-sm)"
    append-to-body
  >
    <el-form label-position="top">
      <el-form-item :label="t('knowledge.common.name')">
        <el-input v-model="form.name" :placeholder="t('knowledge.space.namePlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('knowledge.common.type')">
        <el-radio-group v-model="form.type">
          <el-radio value="personal">{{ t('knowledge.space.personal') }}</el-radio>
          <el-radio value="shared">{{ t('knowledge.space.shared') }}</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item :label="t('knowledge.common.description')">
        <el-input v-model="form.description" type="textarea" :rows="3" />
      </el-form-item>
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
.space-tip {
  margin-bottom: var(--bs-space-2);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--bs-space-2);
}
</style>
