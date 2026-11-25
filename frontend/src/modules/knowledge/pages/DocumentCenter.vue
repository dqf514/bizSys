<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import ListTable from '@/components/list/ListTable.vue'
import type { ListColumn } from '@/components/list/types'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import {
  createKnowledgeFolder,
  deleteKnowledgeDocument,
  knowledgeFolderTree,
  listKnowledgeCategories,
  listKnowledgeDocuments,
  listKnowledgePermissions,
  listKnowledgeSpaces,
  listKnowledgeVersions,
  previewKnowledgeDocument,
  rollbackKnowledgeVersion,
  setKnowledgePermissions,
  uploadKnowledgeDocument,
  uploadKnowledgeDocuments,
  uploadKnowledgeVersion,
} from '@/api/knowledge'
import { http } from '@/api/http'
import type {
  KnowledgeCategory,
  KnowledgeDocument,
  KnowledgeFolder,
  KnowledgePermission,
  KnowledgePreview,
  KnowledgeSpace,
  KnowledgeVersion,
} from '@/api/types'

defineOptions({ name: 'DocumentCenter' })

const { t } = useI18n()

const DOC_TYPES = ['document', 'system', 'board', 'sign', 'manual']

/* ---------------- 数据 ---------------- */
const items = ref<KnowledgeDocument[]>([])
const categories = ref<KnowledgeCategory[]>([])
const spaces = ref<KnowledgeSpace[]>([])
const folderTree = ref<KnowledgeFolder[]>([])
const total = ref(0)
const loading = ref(false)

const query = reactive<Record<string, unknown>>({
  page: 1,
  size: 20,
  q: '',
  categoryId: '',
  spaceId: '',
  folderId: '',
  docType: '',
})

const selectedCategoryId = ref<number | null>(null)

const spaceOptions = computed(() => spaces.value.map((s) => ({ label: s.name, value: s.id })))
const categoryOptions = computed(() => {
  const out: { label: string; value: number }[] = []
  const walk = (nodes: KnowledgeCategory[]) => {
    for (const n of nodes) {
      out.push({ label: n.name, value: n.id })
      if (n.children?.length) walk(n.children)
    }
  }
  walk(categories.value)
  return out
})
const docTypeOptions = computed(() =>
  DOC_TYPES.map((v) => ({ label: t(`knowledge.doc.type.${v}`), value: v })),
)

const searchFields = computed<SearchField[]>(() => [
  { key: 'q', labelKey: 'knowledge.common.keyword', type: 'input', width: 220 },
  {
    key: 'categoryId',
    labelKey: 'knowledge.common.category',
    type: 'select',
    width: 200,
    options: categoryOptions.value,
  },
  {
    key: 'spaceId',
    labelKey: 'knowledge.common.space',
    type: 'select',
    width: 180,
    options: spaceOptions.value,
  },
  {
    key: 'docType',
    labelKey: 'knowledge.common.docType',
    type: 'select',
    width: 160,
    options: docTypeOptions.value,
  },
])

/* ---------------- 加载 ---------------- */
async function loadCategories() {
  try {
    const data = await listKnowledgeCategories()
    categories.value = data.items ?? []
  } catch {
    categories.value = []
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

async function loadFolderTree() {
  const spaceId = Number(query.spaceId)
  if (!spaceId) {
    folderTree.value = []
    return
  }
  try {
    const data = await knowledgeFolderTree(spaceId)
    folderTree.value = data.items ?? []
  } catch {
    folderTree.value = []
  }
}

async function load() {
  loading.value = true
  try {
    const params: Record<string, unknown> = { page: query.page, size: query.size }
    if (query.q) params.q = query.q
    if (query.categoryId) params.categoryId = query.categoryId
    if (query.spaceId) params.spaceId = query.spaceId
    if (query.folderId) params.folderId = query.folderId
    if (query.docType) params.docType = query.docType
    const data = await listKnowledgeDocuments(params as never)
    items.value = data.items ?? []
    total.value = data.total ?? 0
  } catch {
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadCategories(), loadSpaces()])
  await load()
})

function onSearch() {
  query.page = 1
  void load()
}

function resetQuery() {
  query.q = ''
  query.categoryId = ''
  query.spaceId = ''
  query.folderId = ''
  query.docType = ''
  selectedCategoryId.value = null
  query.page = 1
  void load()
}

function onCategoryClick(node: KnowledgeCategory) {
  selectedCategoryId.value = selectedCategoryId.value === node.id ? null : node.id
  query.categoryId = selectedCategoryId.value ?? ''
  query.page = 1
  void load()
}

function onSpaceChange() {
  query.folderId = ''
  void loadFolderTree()
}

/* ---------------- 表格 ---------------- */
function fmtSize(n: number) {
  if (!n) return '-'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

const columns = computed<ListColumn[]>(() => [
  { prop: 'title', labelKey: 'knowledge.doc.docTitle', minWidth: 220, slot: 'title' },
  { prop: 'code', labelKey: 'knowledge.common.code', minWidth: 150 },
  { prop: 'docType', labelKey: 'knowledge.common.docType', width: 110, slot: 'docType' },
  { prop: 'ownerName', labelKey: 'knowledge.doc.author', width: 110 },
  { prop: 'currentVersion', labelKey: 'knowledge.doc.version', width: 90, align: 'center' },
  { prop: 'size', labelKey: 'knowledge.doc.size', width: 100, align: 'right', formatter: (row) => fmtSize(Number(row.size)) },
  { prop: 'updateTime', labelKey: 'knowledge.common.updateTime', minWidth: 160 },
  { prop: 'actions', labelKey: 'common.action.operate', width: 110, fixed: 'right', align: 'center', slot: 'actions' },
])

const rowActions = computed<ActionItem[]>(() => [
  { key: 'preview', tip: 'knowledge.doc.preview', perm: 'knowledge:preview' },
  { key: 'versions', tip: 'knowledge.doc.versions', perm: 'knowledge:document:list' },
  { key: 'share', tip: 'knowledge.doc.share', perm: 'knowledge:document:share' },
  { key: 'delete', tip: 'knowledge.doc.delete', perm: 'knowledge:document:delete' },
])

function onAction(key: string, row: KnowledgeDocument) {
  if (key === 'preview') void openPreview(row)
  else if (key === 'versions') void openVersions(row)
  else if (key === 'share') void openPermissions(row)
  else if (key === 'delete') void doDelete(row)
}

async function doDelete(row: KnowledgeDocument) {
  try {
    await ElMessageBox.confirm(t('knowledge.doc.deleteConfirm', { title: row.title }), t('common.action.confirm'), {
      type: 'warning',
    })
  } catch {
    return
  }
  await deleteKnowledgeDocument(row.id)
  ElMessage.success(t('common.message.deleteSuccess'))
  await load()
}

/* ---------------- 下载 ---------------- */
async function doDownload(row: KnowledgeDocument) {
  const resp = await http.get(`/api/v1/knowledge/documents/${row.id}/download`, { responseType: 'blob' })
  const blob = new Blob([resp.data])
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = row.title + (row.ext ? `.${row.ext}` : '')
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/* ---------------- 上传 ---------------- */
const uploadVisible = ref(false)
const uploadMode = ref<'single' | 'batch'>('single')
const uploadFile = ref<File | null>(null)
const uploadFiles = ref<File[]>([])
const uploadTitle = ref('')
const uploadCategoryId = ref<number | null>(null)
const uploadFolderId = ref<number | null>(null)
const uploading = ref(false)

function targetSpaceId(): number | null {
  const v = Number(query.spaceId)
  return v || null
}

function openUpload(mode: 'single' | 'batch') {
  if (!targetSpaceId()) {
    ElMessage.warning(t('knowledge.doc.selectSpace'))
    return
  }
  uploadMode.value = mode
  uploadFile.value = null
  uploadFiles.value = []
  uploadTitle.value = ''
  uploadCategoryId.value = (query.categoryId ? Number(query.categoryId) : null) ?? null
  uploadFolderId.value = (query.folderId ? Number(query.folderId) : null) ?? null
  uploadVisible.value = true
}

function onSingleChange(file: { raw?: File }) {
  uploadFile.value = file.raw ?? null
  if (!uploadTitle.value && file.raw) uploadTitle.value = file.raw.name.replace(/\.[^.]+$/, '')
}

function onBatchChange(file: { raw?: File }) {
  if (file.raw && !uploadFiles.value.includes(file.raw)) uploadFiles.value.push(file.raw)
}

async function submitUpload() {
  const spaceId = targetSpaceId()
  if (!spaceId) {
    ElMessage.warning(t('knowledge.doc.selectSpace'))
    return
  }
  uploading.value = true
  try {
    if (uploadMode.value === 'single') {
      if (!uploadFile.value) {
        ElMessage.warning(t('knowledge.doc.selectTarget'))
        return
      }
      const fd = new FormData()
      fd.append('file', uploadFile.value)
      fd.append('title', uploadTitle.value || uploadFile.value.name)
      fd.append('space_id', String(spaceId))
      if (uploadFolderId.value) fd.append('folder_id', String(uploadFolderId.value))
      if (uploadCategoryId.value) fd.append('category_id', String(uploadCategoryId.value))
      await uploadKnowledgeDocument(fd)
      ElMessage.success(t('knowledge.doc.uploadSuccess', { name: uploadTitle.value || uploadFile.value.name }))
    } else {
      if (!uploadFiles.value.length) {
        ElMessage.warning(t('knowledge.doc.selectTarget'))
        return
      }
      const fd = new FormData()
      for (const f of uploadFiles.value) fd.append('files', f)
      fd.append('space_id', String(spaceId))
      if (uploadFolderId.value) fd.append('folder_id', String(uploadFolderId.value))
      if (uploadCategoryId.value) fd.append('category_id', String(uploadCategoryId.value))
      const res = await uploadKnowledgeDocuments(fd)
      ElMessage.success(t('knowledge.doc.batchDone', { success: res.success, total: res.total }))
      const failed = res.items.filter((i) => !i.ok).map((i) => i.name)
      if (failed.length) ElMessage.warning(t('knowledge.doc.batchFailed', { names: failed.join('、') }))
    }
    uploadVisible.value = false
    await load()
  } catch {
    /* http 层已提示 */
  } finally {
    uploading.value = false
  }
}

/* ---------------- 文件夹 ---------------- */
const folderVisible = ref(false)
const folderForm = reactive({ name: '', parentId: null as number | null, categoryId: null as number | null })

function openFolderDialog() {
  if (!targetSpaceId()) {
    ElMessage.warning(t('knowledge.doc.selectSpace'))
    return
  }
  folderForm.name = ''
  folderForm.parentId = (query.folderId ? Number(query.folderId) : null) ?? null
  folderForm.categoryId = (query.categoryId ? Number(query.categoryId) : null) ?? null
  folderVisible.value = true
}

async function submitFolder() {
  const spaceId = targetSpaceId()
  if (!spaceId || !folderForm.name.trim()) return
  await createKnowledgeFolder({
    name: folderForm.name.trim(),
    space_id: spaceId,
    parent_id: folderForm.parentId,
    category_id: folderForm.categoryId,
  } as never)
  ElMessage.success(t('knowledge.category.saved'))
  folderVisible.value = false
  await loadFolderTree()
  await load()
}

/* ---------------- 在线浏览 ---------------- */
const previewVisible = ref(false)
const previewData = ref<KnowledgePreview | null>(null)
const previewRow = ref<KnowledgeDocument | null>(null)
const previewImageUrl = ref('')

async function openPreview(row: KnowledgeDocument) {
  previewRow.value = row
  previewData.value = null
  previewImageUrl.value = ''
  previewVisible.value = true
  try {
    const data = await previewKnowledgeDocument(row.id)
    previewData.value = data
    if (data.kind === 'image') {
      const resp = await http.get(`/api/v1/knowledge/documents/${row.id}/raw`, { responseType: 'blob' })
      previewImageUrl.value = URL.createObjectURL(new Blob([resp.data]))
    }
  } catch {
    previewData.value = { kind: 'none', text: '', message: t('knowledge.doc.previewUnsupported') }
  }
}

function closePreview() {
  if (previewImageUrl.value) URL.revokeObjectURL(previewImageUrl.value)
  previewImageUrl.value = ''
}

/* ---------------- 版本 ---------------- */
const versionVisible = ref(false)
const versionRow = ref<KnowledgeDocument | null>(null)
const versions = ref<KnowledgeVersion[]>([])
const versionComment = ref('')
const versionFile = ref<File | null>(null)

async function openVersions(row: KnowledgeDocument) {
  versionRow.value = row
  versionVisible.value = true
  versionComment.value = ''
  versionFile.value = null
  await loadVersions()
}

async function loadVersions() {
  if (!versionRow.value) return
  try {
    const data = await listKnowledgeVersions(versionRow.value.id)
    versions.value = data.items ?? []
  } catch {
    versions.value = []
  }
}

function onVersionChange(file: { raw?: File }) {
  versionFile.value = file.raw ?? null
}

async function submitVersion() {
  if (!versionRow.value || !versionFile.value) return
  const fd = new FormData()
  fd.append('file', versionFile.value)
  fd.append('comment', versionComment.value)
  await uploadKnowledgeVersion(versionRow.value.id, fd)
  ElMessage.success(t('common.message.saveSuccess'))
  versionComment.value = ''
  versionFile.value = null
  await loadVersions()
  await load()
}

async function doRollback(ver: KnowledgeVersion) {
  if (!versionRow.value) return
  await rollbackKnowledgeVersion(versionRow.value.id, ver.id)
  ElMessage.success(t('knowledge.doc.rollbackDone', { v: ver.versionNo }))
  await loadVersions()
  await load()
}

/* ---------------- 权限 ---------------- */
const permVisible = ref(false)
const permRow = ref<KnowledgeDocument | null>(null)
const permissions = ref<KnowledgePermission[]>([])
const permForm = reactive({
  subjectType: 'user',
  subjectId: null as number | null,
  subjectName: '',
  perm: 'read',
  isExternal: 0,
})

async function openPermissions(row: KnowledgeDocument) {
  permRow.value = row
  permVisible.value = true
  resetPermForm()
  await loadPermissions()
}

function resetPermForm() {
  permForm.subjectType = 'user'
  permForm.subjectId = null
  permForm.subjectName = ''
  permForm.perm = 'read'
  permForm.isExternal = 0
}

async function loadPermissions() {
  if (!permRow.value) return
  try {
    const data = await listKnowledgePermissions(permRow.value.id)
    permissions.value = data.items ?? []
  } catch {
    permissions.value = []
  }
}

async function addPermission() {
  if (!permRow.value || !permForm.subjectId) {
    ElMessage.warning(t('knowledge.perm.add'))
    return
  }
  const next = [
    ...permissions.value.map((p) => ({
      subjectType: p.subjectType,
      subjectId: p.subjectId,
      subjectName: p.subjectName,
      perm: p.perm,
      isExternal: p.isExternal,
      expireAt: p.expireAt ? p.expireAt : null,
    })),
    {
      subjectType: permForm.subjectType,
      subjectId: permForm.subjectId,
      subjectName: permForm.subjectName,
      perm: permForm.perm,
      isExternal: permForm.isExternal,
      expireAt: null,
    },
  ]
  const res = await setKnowledgePermissions(permRow.value.id, next as never)
  permissions.value = res.items ?? []
  resetPermForm()
  ElMessage.success(t('knowledge.perm.saved'))
}

async function removePermission(p: KnowledgePermission) {
  if (!permRow.value) return
  await setKnowledgePermissions(
    permRow.value.id,
    permissions.value
      .filter((x) => x.id !== p.id)
      .map((x) => ({
        subjectType: x.subjectType,
        subjectId: x.subjectId,
        subjectName: x.subjectName,
        perm: x.perm,
        isExternal: x.isExternal,
        expireAt: x.expireAt ? x.expireAt : null,
      })) as never,
  )
  await loadPermissions()
}
</script>

<template>
  <ListPage :title="t('knowledge.doc.title')" :loading="loading" class="bs-page--fill">
    <template #actions>
      <el-button v-permission="'knowledge:document:create'" type="primary" :icon="Upload" @click="openUpload('single')">
        {{ t('knowledge.doc.upload') }}
      </el-button>
      <el-button v-permission="'knowledge:document:create'" :icon="Upload" @click="openUpload('batch')">
        {{ t('knowledge.doc.uploadBatch') }}
      </el-button>
      <el-button v-permission="'knowledge:document:create'" @click="openFolderDialog()">
        {{ t('knowledge.common.newFolder') }}
      </el-button>
      <el-button @click="load()">{{ t('common.action.refresh') }}</el-button>
    </template>

    <template #searchBar>
      <SearchBar v-model="query" :fields="searchFields" @search="onSearch()" @reset="resetQuery()" />
    </template>

    <template #table>
      <div class="doc-layout">
        <aside class="doc-side">
          <div class="doc-side-title">{{ t('knowledge.common.category') }}</div>
          <el-tree
            :data="categories"
            node-key="id"
            :props="{ label: 'name', children: 'children' }"
            :expand-on-click-node="false"
            highlight-current
            @node-click="onCategoryClick"
          />
          <el-empty v-if="!categories.length" :description="t('knowledge.common.empty')" :image-size="60" />
        </aside>

        <div class="doc-main">
          <div class="doc-toolbar">
            <el-select
              v-model="query.spaceId"
              :placeholder="t('knowledge.doc.chooseSpace')"
              clearable
              style="width: 200px"
              @change="onSpaceChange"
            >
              <el-option v-for="s in spaces" :key="s.id" :label="s.name" :value="s.id" />
            </el-select>
            <el-tree-select
              v-model="query.folderId"
              :data="folderTree"
              node-key="id"
              :props="{ label: 'name', children: 'children' }"
              check-strictly
              clearable
              :placeholder="t('knowledge.common.folder')"
              style="width: 220px"
              @change="onSearch()"
            />
            <span class="doc-count">{{ t('common.table.total', { total }) }}</span>
          </div>

          <ListTable
            :columns="columns"
            :data="items as unknown as Record<string, unknown>[]"
            :loading="loading"
            :total="total"
            :page="Number(query.page)"
            :size="Number(query.size)"
            row-key="id"
            height="100%"
            @update:page="(v: number) => { query.page = v; load() }"
            @update:size="(v: number) => { query.size = v; query.page = 1; load() }"
          >
            <template #title="{ row }">
              <span class="doc-title">{{ row.title }}</span>
              <span v-if="row.ext" class="doc-ext">{{ row.ext }}</span>
            </template>
            <template #docType="{ row }">
              <el-tag size="small" type="info">{{ t(`knowledge.doc.type.${row.docType}`) }}</el-tag>
            </template>
            <template #actions="{ row }">
              <ActionBar
                :actions="rowActions"
                @select="(key: string) => onAction(key, row as unknown as KnowledgeDocument)"
              />
              <el-button link type="primary" @click="doDownload(row as unknown as KnowledgeDocument)">
                {{ t('knowledge.doc.download') }}
              </el-button>
            </template>
          </ListTable>
        </div>
      </div>
    </template>
  </ListPage>

  <!-- 上传 -->
  <el-dialog v-model="uploadVisible" :title="t('knowledge.doc.upload')" width="var(--bs-layout-dialog-md)" append-to-body>
    <el-form label-position="top">
      <el-form-item v-if="uploadMode === 'single'" :label="t('knowledge.doc.docTitle')">
        <el-input v-model="uploadTitle" />
      </el-form-item>
      <el-form-item :label="t('knowledge.common.category')">
        <el-select v-model="uploadCategoryId" clearable style="width: 100%">
          <el-option v-for="c in categoryOptions" :key="c.value" :label="c.label" :value="c.value" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('knowledge.common.folder')">
        <el-tree-select
          v-model="uploadFolderId"
          :data="folderTree"
          node-key="id"
          :props="{ label: 'name', children: 'children' }"
          check-strictly
          clearable
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item :label="t('knowledge.doc.upload')">
        <el-upload
          v-if="uploadMode === 'single'"
          :auto-upload="false"
          :show-file-list="true"
          :limit="1"
          :on-change="onSingleChange"
        >
          <el-button>{{ t('common.action.upload') }}</el-button>
        </el-upload>
        <el-upload
          v-else
          :auto-upload="false"
          :show-file-list="true"
          multiple
          :on-change="onBatchChange"
        >
          <el-button>{{ t('common.action.upload') }}</el-button>
        </el-upload>
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="uploadVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="uploading" @click="submitUpload()">
          {{ t('common.action.submit') }}
        </el-button>
      </div>
    </template>
  </el-dialog>

  <!-- 新建文件夹 -->
  <el-dialog v-model="folderVisible" :title="t('knowledge.common.newFolder')" width="var(--bs-layout-dialog-sm)" append-to-body>
    <el-form label-position="top">
      <el-form-item :label="t('knowledge.common.name')">
        <el-input v-model="folderForm.name" />
      </el-form-item>
      <el-form-item :label="t('knowledge.common.parentFolder')">
        <el-tree-select
          v-model="folderForm.parentId"
          :data="folderTree"
          node-key="id"
          :props="{ label: 'name', children: 'children' }"
          check-strictly
          clearable
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item :label="t('knowledge.common.category')">
        <el-select v-model="folderForm.categoryId" clearable style="width: 100%">
          <el-option v-for="c in categoryOptions" :key="c.value" :label="c.label" :value="c.value" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="folderVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" @click="submitFolder()">{{ t('common.action.save') }}</el-button>
      </div>
    </template>
  </el-dialog>

  <!-- 在线浏览 -->
  <el-drawer
    v-model="previewVisible"
    :title="previewRow?.title || t('knowledge.doc.preview')"
    size="var(--bs-layout-drawer-lg)"
    append-to-body
    @closed="closePreview"
  >
    <div v-if="previewData?.kind === 'image'" class="preview-image">
      <img :src="previewImageUrl" :alt="previewRow?.title" />
    </div>
    <pre v-else-if="previewData?.kind === 'text'" class="preview-text">{{ previewData.text }}</pre>
    <el-empty v-else :description="previewData?.message || t('knowledge.doc.noPreview')" />
  </el-drawer>

  <!-- 版本历史 -->
  <el-drawer
    v-model="versionVisible"
    :title="t('knowledge.doc.versions')"
    size="var(--bs-layout-drawer-md)"
    append-to-body
  >
    <div class="version-upload">
      <el-upload :auto-upload="false" :show-file-list="true" :limit="1" :on-change="onVersionChange">
        <el-button>{{ t('knowledge.doc.newVersion') }}</el-button>
      </el-upload>
      <el-input v-model="versionComment" :placeholder="t('knowledge.doc.versionComment')" style="margin-top: 8px" />
      <el-button type="primary" style="margin-top: 8px" @click="submitVersion()">
        {{ t('common.action.submit') }}
      </el-button>
    </div>
    <el-table :data="versions" size="small" style="margin-top: 12px">
      <el-table-column prop="versionNo" :label="t('knowledge.doc.version')" width="80" />
      <el-table-column prop="fileName" :label="t('knowledge.common.name')" min-width="180" />
      <el-table-column prop="operatorName" :label="t('knowledge.common.operator')" width="110" />
      <el-table-column prop="createTime" :label="t('knowledge.common.createTime')" min-width="150" />
      <el-table-column :label="t('common.action.operate')" width="120" align="center">
        <template #default="{ row }">
          <el-button link type="primary" @click="doRollback(row as KnowledgeVersion)">
            {{ t('knowledge.doc.rollback') }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-drawer>

  <!-- 权限与分享 -->
  <el-drawer
    v-model="permVisible"
    :title="t('knowledge.perm.title')"
    size="var(--bs-layout-drawer-md)"
    append-to-body
  >
    <el-alert :title="t('knowledge.perm.hint')" type="info" :closable="false" show-icon />
    <el-form label-position="top" style="margin-top: 12px">
      <el-form-item :label="t('knowledge.perm.subjectType')">
        <el-radio-group v-model="permForm.subjectType">
          <el-radio value="user">{{ t('knowledge.perm.subjectUser') }}</el-radio>
          <el-radio value="role">{{ t('knowledge.perm.subjectRole') }}</el-radio>
          <el-radio value="dept">{{ t('knowledge.perm.subjectDept') }}</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item :label="t('knowledge.perm.subject')">
        <el-input-number v-model="permForm.subjectId" :min="1" style="width: 160px" />
        <el-input v-model="permForm.subjectName" :placeholder="t('knowledge.perm.subject')" style="width: 220px; margin-left: 8px" />
      </el-form-item>
      <el-form-item :label="t('knowledge.perm.perm')">
        <el-select v-model="permForm.perm" style="width: 160px">
          <el-option :label="t('knowledge.perm.permRead')" value="read" />
          <el-option :label="t('knowledge.perm.permEdit')" value="edit" />
          <el-option :label="t('knowledge.perm.permManage')" value="manage" />
        </el-select>
        <el-checkbox v-model="permForm.isExternal" :true-value="1" :false-value="0" style="margin-left: 16px">
          {{ t('knowledge.perm.external') }}
        </el-checkbox>
      </el-form-item>
      <el-button type="primary" @click="addPermission()">{{ t('knowledge.perm.add') }}</el-button>
    </el-form>

    <el-table :data="permissions" size="small" style="margin-top: 12px">
      <el-table-column prop="subjectName" :label="t('knowledge.perm.subject')" min-width="140" />
      <el-table-column prop="subjectType" :label="t('knowledge.perm.subjectType')" width="110" />
      <el-table-column prop="perm" :label="t('knowledge.perm.perm')" width="100" />
      <el-table-column :label="t('knowledge.perm.internal')" width="90" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="row.isExternal ? 'warning' : 'info'">
            {{ row.isExternal ? t('knowledge.perm.external') : t('knowledge.perm.internal') }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="t('common.action.operate')" width="90" align="center">
        <template #default="{ row }">
          <el-button link type="danger" @click="removePermission(row as KnowledgePermission)">
            {{ t('common.action.delete') }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-drawer>
</template>

<style scoped>
.doc-layout {
  display: flex;
  gap: var(--bs-space-3);
  height: 100%;
  min-height: 0;
}

.doc-side {
  width: 220px;
  flex: 0 0 220px;
  overflow: auto;
  padding: var(--bs-space-2);
  border-right: 1px solid var(--bs-color-border-subtle);
}

.doc-side-title {
  font-weight: 600;
  margin-bottom: var(--bs-space-2);
  color: var(--bs-color-fg-secondary);
}

.doc-main {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.doc-toolbar {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  margin-bottom: var(--bs-space-2);
}

.doc-count {
  margin-left: auto;
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-sm);
}

.doc-title {
  font-weight: 500;
}

.doc-ext {
  margin-left: var(--bs-space-2);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}

.preview-image {
  text-align: center;
}

.preview-image img {
  max-width: 100%;
}

.preview-text {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  line-height: 1.7;
  margin: 0;
}

.version-upload {
  padding-bottom: var(--bs-space-2);
  border-bottom: 1px solid var(--bs-color-border-subtle);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--bs-space-2);
}
</style>
