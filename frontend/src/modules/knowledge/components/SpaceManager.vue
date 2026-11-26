<script setup lang="ts">
/**
 * 空间管理弹窗（微盘式文档中心内嵌）。
 *
 * B12 起空间不再作为独立导航入口 —— 「我的空间 / 共享空间」在文档中心左栏直接呈现，
 * 空间的新增、编辑、置顶与删除在这里集中管理。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import {
  createKnowledgeSpace,
  deleteKnowledgeSpace,
  listKnowledgeSpaces,
  pinKnowledgeSpace,
  updateKnowledgeSpace,
} from '@/api/knowledge'
import type { KnowledgeSpace } from '@/api/types'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void; (e: 'changed'): void }>()

const { t } = useI18n()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const spaces = ref<KnowledgeSpace[]>([])
const loading = ref(false)

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

watch(
  () => props.modelValue,
  (v) => {
    if (v) void load()
  },
)

/* ---------------- 新增 / 编辑 ---------------- */
const dialogVisible = ref(false)
const editing = ref<KnowledgeSpace | null>(null)
const form = ref({ name: '', type: 'personal', description: '', pinned: 0 })

function openDialog(row: KnowledgeSpace | null) {
  editing.value = row
  form.value = {
    name: row?.name ?? '',
    type: row?.type ?? 'personal',
    description: row?.description ?? '',
    pinned: row?.pinned ?? 0,
  }
  dialogVisible.value = true
}

async function submit() {
  if (!form.value.name.trim()) return
  const payload = {
    name: form.value.name.trim(),
    type: form.value.type,
    description: form.value.description,
    status: 'enabled',
    pinned: form.value.pinned,
    owner_id: editing.value?.ownerId ?? null,
    dept_id: editing.value?.deptId ?? null,
  }
  if (editing.value) await updateKnowledgeSpace(editing.value.id, payload as never)
  else await createKnowledgeSpace(payload as never)
  ElMessage.success(t('common.message.saveSuccess'))
  dialogVisible.value = false
  await load()
  emit('changed')
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
  emit('changed')
}

async function togglePin(row: KnowledgeSpace) {
  await pinKnowledgeSpace(row.id, !row.pinned)
  await load()
  emit('changed')
}
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="t('knowledge.space.title')"
    width="var(--bs-layout-dialog-lg)"
    append-to-body
  >
    <el-alert :title="t('knowledge.space.sharedTip')" type="info" :closable="false" show-icon class="space-tip" />

    <div class="space-bar">
      <el-button v-permission="'knowledge:space:edit'" type="primary" @click="openDialog(null)">
        {{ t('knowledge.space.create') }}
      </el-button>
      <el-button @click="load()">{{ t('common.action.refresh') }}</el-button>
    </div>

    <el-table v-loading="loading" :data="spaces" size="small" row-key="id" max-height="420">
      <el-table-column prop="name" :label="t('knowledge.common.name')" min-width="160" />
      <el-table-column prop="type" :label="t('knowledge.common.type')" width="110">
        <template #default="{ row }">
          <el-tag size="small" :type="row.type === 'shared' ? 'warning' : 'info'">
            {{ row.type === 'shared' ? t('knowledge.space.shared') : t('knowledge.space.personal') }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="ownerName" :label="t('knowledge.space.owner')" width="120" />
      <el-table-column prop="description" :label="t('knowledge.common.description')" min-width="160" />
      <el-table-column :label="t('common.action.operate')" width="180" align="center">
        <template #default="{ row }">
          <el-button
            v-permission="'knowledge:space:edit'"
            link
            type="primary"
            @click="togglePin(row)"
          >
            {{ row.pinned ? t('knowledge.drive.unpin') : t('knowledge.drive.pin') }}
          </el-button>
          <el-button
            v-permission="'knowledge:space:edit'"
            link
            type="primary"
            @click="openDialog(row)"
          >
            {{ t('knowledge.space.edit') }}
          </el-button>
          <el-button
            v-permission="'knowledge:space:edit'"
            link
            type="danger"
            @click="doDelete(row)"
          >
            {{ t('knowledge.space.delete') }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

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
  </el-dialog>
</template>

<style scoped>
.space-tip {
  margin-bottom: var(--bs-space-2);
}

.space-bar {
  display: flex;
  gap: var(--bs-space-2);
  margin-bottom: var(--bs-space-2);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--bs-space-2);
}
</style>
