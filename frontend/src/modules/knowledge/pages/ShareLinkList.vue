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
  closeKnowledgeLink,
  createKnowledgeLink,
  knowledgeFolderTree,
  listKnowledgeDocuments,
  listKnowledgeLinks,
  listKnowledgeSpaces,
} from '@/api/knowledge'
import type { KnowledgeDocument, KnowledgeFolder, KnowledgeShareLink, KnowledgeSpace } from '@/api/types'

defineOptions({ name: 'ShareLinkList' })

const { t } = useI18n()

const links = ref<KnowledgeShareLink[]>([])
const spaces = ref<KnowledgeSpace[]>([])
const loading = ref(false)
const query = reactive({ keyword: '', status: '' })

const statusOptions = computed(() => [
  { label: t('knowledge.link.statusActive'), value: 'active' },
  { label: t('knowledge.link.statusClosed'), value: 'closed' },
  { label: t('knowledge.link.statusExpired'), value: 'expired' },
])

const searchFields = computed<SearchField[]>(() => [
  { key: 'keyword', labelKey: 'knowledge.common.keyword', type: 'input', width: 240 },
  { key: 'status', labelKey: 'knowledge.common.status', type: 'select', width: 160, options: statusOptions.value },
])

async function load() {
  loading.value = true
  try {
    const params: Record<string, unknown> = { page: 1, size: 200 }
    if (query.keyword) params.q = query.keyword
    if (query.status) params.status = query.status
    const data = await listKnowledgeLinks(params as never)
    links.value = data.items ?? []
  } catch {
    links.value = []
  } finally {
    loading.value = false
  }
}

async function loadSpaces() {
  try {
    const data = await listKnowledgeSpaces()
    spaces.value = data.items ?? []
  } catch {
    spaces.value = []
  }
}

onMounted(async () => {
  await loadSpaces()
  await load()
})

function resetQuery() {
  query.keyword = ''
  query.status = ''
  void load()
}

const columns = computed<ListColumn[]>(() => [
  { prop: 'title', labelKey: 'knowledge.common.name', minWidth: 180 },
  { prop: 'resourceType', labelKey: 'knowledge.link.resourceType', width: 120, slot: 'resourceType' },
  { prop: 'perm', labelKey: 'knowledge.link.perm', width: 130, slot: 'perm' },
  { prop: 'status', labelKey: 'knowledge.common.status', width: 110, slot: 'status' },
  { prop: 'expireAt', labelKey: 'knowledge.common.expireAt', minWidth: 160 },
  { prop: 'uploadCount', labelKey: 'knowledge.link.uploads', width: 100, align: 'center' },
  { prop: 'downloadCount', labelKey: 'knowledge.link.downloads', width: 100, align: 'center' },
  { prop: 'creatorName', labelKey: 'knowledge.link.creator', width: 110 },
  { prop: 'actions', labelKey: 'common.action.operate', width: 110, fixed: 'right', align: 'center', slot: 'actions' },
])

const rowActions = computed<ActionItem[]>(() => [
  { key: 'copy', tip: 'knowledge.link.copy', perm: 'knowledge:link:list' },
  { key: 'close', tip: 'knowledge.link.close', perm: 'knowledge:link:delete' },
])

function linkUrl(row: KnowledgeShareLink) {
  return `${window.location.origin}/knowledge/share/${row.token}`
}

function onAction(key: string, row: KnowledgeShareLink) {
  if (key === 'copy') void doCopy(row)
  else if (key === 'close') void doClose(row)
}

async function doCopy(row: KnowledgeShareLink) {
  const url = linkUrl(row)
  try {
    await navigator.clipboard.writeText(url)
    ElMessage.success(t('knowledge.link.copied'))
  } catch {
    ElMessageBox.alert(url, t('knowledge.link.linkLabel'))
  }
}

async function doClose(row: KnowledgeShareLink) {
  try {
    await ElMessageBox.confirm(t('knowledge.link.closeConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  await closeKnowledgeLink(row.id)
  ElMessage.success(t('common.message.deleteSuccess'))
  await load()
}

/* ---------------- 新建链接 ---------------- */
const dialogVisible = ref(false)
const form = reactive({
  resourceType: 'folder',
  spaceId: null as number | null,
  folderId: null as number | null,
  documentId: null as number | null,
  perm: 'read',
  requirePhone: 1,
  expireDays: 7,
  maxUpload: 0,
  remark: '',
})

const folderTree = ref<KnowledgeFolder[]>([])
const spaceDocs = ref<KnowledgeDocument[]>([])

const spaceOptions = computed(() => spaces.value.map((s) => ({ label: s.name, value: s.id })))
const docOptions = computed(() =>
  spaceDocs.value.map((d) => ({ label: `${d.title}（v${d.currentVersion}）`, value: d.id })),
)

async function onSpaceChange() {
  form.folderId = null
  form.documentId = null
  folderTree.value = []
  spaceDocs.value = []
  if (!form.spaceId) return
  try {
    const data = await knowledgeFolderTree(form.spaceId)
    folderTree.value = data.items ?? []
  } catch {
    folderTree.value = []
  }
  try {
    const data = await listKnowledgeDocuments({ page: 1, size: 200, spaceId: form.spaceId } as never)
    spaceDocs.value = data.items ?? []
  } catch {
    spaceDocs.value = []
  }
}

function openDialog() {
  form.resourceType = 'folder'
  form.spaceId = spaces.value[0]?.id ?? null
  form.folderId = null
  form.documentId = null
  form.perm = 'read'
  form.requirePhone = 1
  form.expireDays = 7
  form.maxUpload = 0
  form.remark = ''
  dialogVisible.value = true
  void onSpaceChange()
}

async function submit() {
  const resourceId = form.resourceType === 'folder' ? form.folderId : form.documentId
  if (!resourceId) {
    ElMessage.warning(
      form.resourceType === 'folder' ? t('knowledge.link.needFolder') : t('knowledge.doc.selectTarget'),
    )
    return
  }
  const res = await createKnowledgeLink({
    resourceType: form.resourceType,
    resourceId,
    perm: form.perm,
    requirePhone: form.requirePhone,
    expireDays: form.expireDays,
    maxUpload: form.maxUpload,
    remark: form.remark,
  })
  ElMessage.success(t('knowledge.link.created'))
  dialogVisible.value = false
  await load()
  void doCopy({ token: res.token } as KnowledgeShareLink)
}
</script>

<template>
  <div class="bs-page">
    <PageHeader :title="t('knowledge.link.title')">
      <template #actions>
        <el-button v-permission="'knowledge:link:create'" type="primary" @click="openDialog()">
          {{ t('knowledge.link.create') }}
        </el-button>
        <el-button @click="load()">{{ t('common.action.refresh') }}</el-button>
      </template>
    </PageHeader>

    <div class="bs-page-card">
      <SearchBar v-model="query" :fields="searchFields" @search="load()" @reset="resetQuery" />
      <ListTable
        :columns="columns"
        :data="links as unknown as Record<string, unknown>[]"
        :loading="loading"
        :show-pagination="false"
        row-key="id"
      >
        <template #resourceType="{ row }">
          <el-tag size="small" type="info">
            {{ row.resourceType === 'folder' ? t('knowledge.link.resourceFolder') : t('knowledge.link.resourceDocument') }}
          </el-tag>
        </template>
        <template #perm="{ row }">
          <el-tag size="small">
            {{
              row.perm === 'upload'
                ? t('knowledge.link.permUpload')
                : row.perm === 'edit'
                  ? t('knowledge.link.permEdit')
                  : t('knowledge.link.permRead')
            }}
          </el-tag>
        </template>
        <template #status="{ row }">
          <el-tag size="small" :type="row.status === 'active' ? 'success' : 'info'">
            {{
              row.status === 'active'
                ? t('knowledge.link.statusActive')
                : row.status === 'closed'
                  ? t('knowledge.link.statusClosed')
                  : t('knowledge.link.statusExpired')
            }}
          </el-tag>
        </template>
        <template #actions="{ row }">
          <ActionBar
            :actions="rowActions"
            @select="(key: string) => onAction(key, row as unknown as KnowledgeShareLink)"
          />
        </template>
      </ListTable>
    </div>
  </div>

  <el-dialog
    v-model="dialogVisible"
    :title="t('knowledge.link.create')"
    width="var(--bs-layout-dialog-md)"
    append-to-body
  >
    <el-form label-position="top">
      <el-form-item :label="t('knowledge.link.resourceType')">
        <el-radio-group v-model="form.resourceType">
          <el-radio value="folder">{{ t('knowledge.link.resourceFolder') }}</el-radio>
          <el-radio value="document">{{ t('knowledge.link.resourceDocument') }}</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item :label="t('knowledge.common.space')">
        <el-select v-model="form.spaceId" style="width: 100%" @change="onSpaceChange()">
          <el-option v-for="s in spaceOptions" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="form.resourceType === 'folder'" :label="t('knowledge.common.folder')">
        <el-tree-select
          v-model="form.folderId"
          :data="folderTree"
          node-key="id"
          :props="{ label: 'name', children: 'children' }"
          check-strictly
          clearable
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item v-else :label="t('knowledge.doc.docTitle')">
        <el-select v-model="form.documentId" filterable clearable style="width: 100%">
          <el-option v-for="d in docOptions" :key="d.value" :label="d.label" :value="d.value" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('knowledge.link.perm')">
        <el-select v-model="form.perm" style="width: 100%">
          <el-option :label="t('knowledge.link.permRead')" value="read" />
          <el-option :label="t('knowledge.link.permUpload')" value="upload" />
          <el-option :label="t('knowledge.link.permEdit')" value="edit" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('knowledge.link.requirePhone')">
        <el-switch v-model="form.requirePhone" :active-value="1" :inactive-value="0" />
      </el-form-item>
      <el-form-item :label="t('knowledge.link.expireDays')">
        <el-input-number v-model="form.expireDays" :min="0" :max="365" />
      </el-form-item>
      <el-form-item :label="t('knowledge.link.maxUpload')">
        <el-input-number v-model="form.maxUpload" :min="0" />
        <span class="field-tip">{{ t('knowledge.link.maxUploadTip') }}</span>
      </el-form-item>
      <el-form-item :label="t('knowledge.link.remark')">
        <el-input v-model="form.remark" type="textarea" :rows="2" />
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
.field-tip {
  margin-left: var(--bs-space-2);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--bs-space-2);
}
</style>
