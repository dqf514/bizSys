<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import { useListPage } from '@/composables/useListPage'
import {
  createKnowledgeEntry,
  deleteKnowledgeEntry,
  downloadKnowledgeAttachment,
  listKnowledgeEntries,
  updateKnowledgeEntry,
  uploadKnowledgeAttachment,
} from '@/api/ai'
import type { KnowledgeEntry } from '@/api/types'

defineOptions({ name: 'AiKnowledge' })

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'ai.knowledge.entryTitle', placeholderKey: 'ai.knowledge.askPlaceholder', width: 240 },
]

const list = useListPage<KnowledgeEntry>({
  fetch: async (params) => {
    const data = await listKnowledgeEntries({ ...params, q: searchModel.value.q || undefined })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
})

const columns: ListColumn[] = [
  { prop: 'title', labelKey: 'ai.knowledge.entryTitle', minWidth: 200, showOverflowTooltip: true },
  { prop: 'category', labelKey: 'ai.knowledge.entryCategory', width: 120 },
  { prop: 'content', labelKey: 'ai.knowledge.entryContent', minWidth: 220, showOverflowTooltip: true },
  { prop: 'attachmentName', labelKey: 'ai.knowledge.attachment', width: 160, slot: 'attachment' },
  { prop: 'updateTime', labelKey: 'finance.invoice.createTime', width: 160 },
]

/* ---------- 编辑对话框 ---------- */
const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const saving = ref(false)
const form = reactive({ title: '', category: '', content: '' })
const attachInput = ref<HTMLInputElement | null>(null)
const attachUploading = ref(false)

function openCreate() {
  editingId.value = null
  Object.assign(form, { title: '', category: '', content: '' })
  dialogVisible.value = true
}

function openEdit(row: KnowledgeEntry) {
  editingId.value = row.id
  Object.assign(form, { title: row.title, category: row.category, content: row.content })
  dialogVisible.value = true
}

async function save() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  saving.value = true
  try {
    if (editingId.value) await updateKnowledgeEntry(editingId.value, { ...form })
    else await createKnowledgeEntry({ ...form })
    ElMessage.success(t('ai.knowledge.saveOk'))
    dialogVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function remove(row: KnowledgeEntry) {
  const yes = await ElMessageBox.confirm(t('ai.knowledge.confirmDelete'), { type: 'warning' }).catch(() => false)
  if (!yes) return
  await deleteKnowledgeEntry(row.id)
  ElMessage.success(t('ai.knowledge.deleteOk'))
  list.refresh()
}

function openAttach() {
  attachInput.value?.click()
}

async function onAttachFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || !editingId.value || attachUploading.value) return
  attachUploading.value = true
  try {
    await uploadKnowledgeAttachment(editingId.value, file)
    ElMessage.success(t('ai.knowledge.saveOk'))
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    attachUploading.value = false
  }
}
</script>

<template>
  <ListPage :title="t('ai.knowledge.manage')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'admin:ai:knowledge'" type="primary" class="kb-add-btn" @click="openCreate">
        {{ t('ai.knowledge.addEntry') }}
      </el-button>
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
        @sort-change="list.onSortChange"
      >
        <template #attachment="{ row }">
          <el-button
            v-if="(row as unknown as KnowledgeEntry).hasAttachment"
            link
            type="primary"
            size="small"
            @click="
              downloadKnowledgeAttachment(
                (row as unknown as KnowledgeEntry).id,
                (row as unknown as KnowledgeEntry).attachmentName || 'attachment',
              )
            "
          >
            {{ (row as unknown as KnowledgeEntry).attachmentName }}
          </el-button>
          <span v-else>-</span>
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="120" fixed="right" align="center">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openEdit(row as unknown as KnowledgeEntry)">
                {{ t('common.action.edit') }}
              </el-button>
              <el-button link type="danger" size="small" @click="remove(row as unknown as KnowledgeEntry)">
                {{ t('common.action.delete') }}
              </el-button>
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog
    v-model="dialogVisible"
    :title="editingId ? t('ai.knowledge.editEntry') : t('ai.knowledge.addEntry')"
    width="var(--bs-layout-dialog-md)"
    append-to-body
  >
    <el-form ref="formRef" :model="form" label-width="90px">
      <el-form-item
        :label="t('ai.knowledge.entryTitle')"
        prop="title"
        :rules="[{ required: true, message: t('common.form.required') }]"
      >
        <el-input v-model="form.title" maxlength="128" />
      </el-form-item>
      <el-form-item :label="t('ai.knowledge.entryCategory')">
        <el-input v-model="form.category" maxlength="64" />
      </el-form-item>
      <el-form-item :label="t('ai.knowledge.entryContent')">
        <el-input v-model="form.content" type="textarea" :rows="8" maxlength="20000" />
      </el-form-item>
      <el-form-item v-if="editingId" :label="t('ai.knowledge.attachment')">
        <el-button size="small" :loading="attachUploading" class="kb-attach-btn" @click="openAttach">
          {{ t('ai.knowledge.uploadAttachment') }}
        </el-button>
        <input ref="attachInput" type="file" style="display: none" @change="onAttachFile" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>
</template>
