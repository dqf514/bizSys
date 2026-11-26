<script setup lang="ts">
/**
 * 文档中心（微盘式布局）。
 *
 * B12：导航与呈现参考微盘 —— 左侧固定导航栏（搜索 / 文件·分类页签 / 最近查看 /
 * 我的空间 / 我分享的 / 置顶 / 共享），右侧主区为目录列表（子文件夹 + 文档混排，
 * 列：名称 / 最近更新 / 更新者 / 大小），支持列表·网格两种视图与前进后退。
 *
 * 分类不再作为独立导航入口（可选项，后期供企业门户展示制度文档），
 * 分类树在左栏「分类」页签内浏览，管理能力由页面内的分类管理抽屉承担。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowLeft,
  ArrowRight,
  Document as DocIcon,
  Files,
  Folder as FolderIcon,
  Grid,
  List,
  Plus,
  Search,
  Upload,
} from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import ListTable from '@/components/list/ListTable.vue'
import type { ListColumn, SortChange } from '@/components/list/types'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import CategoryManager from '@/modules/knowledge/components/CategoryManager.vue'
import SpaceManager from '@/modules/knowledge/components/SpaceManager.vue'
import {
  browseKnowledge,
  createKnowledgeFolder,
  createKnowledgeLink,
  deleteKnowledgeDocument,
  deleteKnowledgeFolder,
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
import { download, http } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import type {
  KnowledgeBrowseDocument,
  KnowledgeBrowseFolder,
  KnowledgeBrowseResult,
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
const auth = useAuthStore()

const RECENT_KEY = 'bs.kb.recent'

/* ---------------- 基础数据 ---------------- */
const spaces = ref<KnowledgeSpace[]>([])
const categories = ref<KnowledgeCategory[]>([])
const folderTree = ref<KnowledgeFolder[]>([])
const loading = ref(false)

const currentUserId = computed(() => auth.user?.id ?? null)

/* ---------------- 视图状态 ---------------- */
const view = ref<'files' | 'categories'>('files')
const viewMode = ref<'list' | 'grid'>('list')
const keyword = ref('')
const spaceId = ref<number | null>(null)
const folderId = ref<number | null>(null)
const categoryId = ref<number | null>(null)
const sort = ref('updateTime')
const order = ref<'asc' | 'desc'>('desc')
const page = ref(1)
const size = ref(50)

const browseResult = ref<KnowledgeBrowseResult | null>(null)
const folders = ref<KnowledgeBrowseFolder[]>([])
const docs = ref<KnowledgeBrowseDocument[]>([])
const total = ref(0)

/* ---------------- 导航历史 ---------------- */
interface DriveLocation {
  spaceId: number | null
  folderId: number | null
  categoryId: number | null
}
const history = ref<DriveLocation[]>([{ spaceId: null, folderId: null, categoryId: null }])
const historyIndex = ref(0)
const canBack = computed(() => historyIndex.value > 0)
const canForward = computed(() => historyIndex.value < history.value.length - 1)

function applyLocation(loc: DriveLocation) {
  spaceId.value = loc.spaceId
  folderId.value = loc.folderId
  categoryId.value = loc.categoryId
  view.value = loc.categoryId != null ? 'categories' : 'files'
  page.value = 1
  void load()
}

function navigate(loc: DriveLocation) {
  history.value = history.value.slice(0, historyIndex.value + 1)
  history.value.push(loc)
  historyIndex.value = history.value.length - 1
  applyLocation(loc)
}

function goBack() {
  if (!canBack.value) return
  historyIndex.value -= 1
  const loc = history.value[historyIndex.value]
  if (loc) applyLocation(loc)
}

function goForward() {
  if (!canForward.value) return
  historyIndex.value += 1
  const loc = history.value[historyIndex.value]
  if (loc) applyLocation(loc)
}

function goSpace(s: KnowledgeSpace | null) {
  navigate({ spaceId: s?.id ?? null, folderId: null, categoryId: null })
}

function goFolder(f: KnowledgeBrowseFolder) {
  navigate({ spaceId: f.spaceId, folderId: f.id, categoryId: null })
}

function goCategory(c: KnowledgeCategory) {
  navigate({ spaceId: null, folderId: null, categoryId: c.id })
}

/* ---------------- 左栏分组 ---------------- */
const mySpaces = computed(() =>
  spaces.value.filter((s) => s.type === 'personal' && s.ownerId === currentUserId.value),
)
const sharedByMe = computed(() =>
  spaces.value.filter((s) => s.type === 'shared' && s.ownerId === currentUserId.value),
)
const pinnedSpaces = computed(() => spaces.value.filter((s) => s.pinned))
/** 共享空间按归属部门分组（微盘的「共享」分组） */
const sharedGroups = computed(() => {
  const groups: { key: string; name: string; spaces: KnowledgeSpace[] }[] = []
  for (const s of spaces.value) {
    if (s.type !== 'shared' || s.ownerId === currentUserId.value) continue
    const key = s.deptName || s.ownerName || String(s.ownerId ?? '')
    let g = groups.find((x) => x.key === key)
    if (!g) {
      g = { key, name: key, spaces: [] }
      groups.push(g)
    }
    g.spaces.push(s)
  }
  return groups
})

const groups = reactive({ pinned: true, shared: true })

/* ---------------- 最近查看 ---------------- */
interface RecentDoc {
  id: number
  title: string
  updateTime: string
}
const recentDocs = ref<RecentDoc[]>([])

function loadRecent() {
  try {
    const raw = localStorage.getItem(RECENT_KEY)
    recentDocs.value = raw ? (JSON.parse(raw) as RecentDoc[]) : []
  } catch {
    recentDocs.value = []
  }
}

function pushRecent(doc: { id: number; title: string; updateTime?: string }) {
  const next: RecentDoc[] = [
    { id: doc.id, title: doc.title, updateTime: doc.updateTime ?? '' },
    ...recentDocs.value.filter((d) => d.id !== doc.id),
  ].slice(0, 8)
  recentDocs.value = next
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(next))
  } catch {
    /* 隐私模式忽略 */
  }
}

/* ---------------- 存储用量 ---------------- */
const storageUsed = computed(() => {
  const size = browseResult.value?.stats?.mySize ?? 0
  if (!size) return '0 B'
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  if (size < 1024 * 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  return `${(size / 1024 / 1024 / 1024).toFixed(2)} GB`
})
const myDocCount = computed(() => browseResult.value?.stats?.myDocCount ?? 0)

/* ---------------- 加载 ---------------- */
async function loadSpaces() {
  try {
    const data = await listKnowledgeSpaces()
    spaces.value = data.items ?? []
  } catch {
    spaces.value = []
  }
}

async function loadCategories() {
  try {
    const data = await listKnowledgeCategories()
    categories.value = data.items ?? []
  } catch {
    categories.value = []
  }
}

async function loadFolderTree() {
  if (!spaceId.value) {
    folderTree.value = []
    return
  }
  try {
    const data = await knowledgeFolderTree(spaceId.value)
    folderTree.value = data.items ?? []
  } catch {
    folderTree.value = []
  }
}

async function load() {
  loading.value = true
  try {
    if (view.value === 'categories') {
      const params: Record<string, unknown> = { page: page.value, size: size.value }
      if (keyword.value) params.q = keyword.value
      if (categoryId.value) params.categoryId = categoryId.value
      const data = await listKnowledgeDocuments(params as never)
      folders.value = []
      docs.value = (data.items ?? []) as KnowledgeBrowseDocument[]
      total.value = data.total ?? 0
    } else {
      const params: Record<string, unknown> = {
        page: page.value,
        size: size.value,
        sort: sort.value,
        order: order.value,
      }
      if (keyword.value) params.q = keyword.value
      if (spaceId.value) params.spaceId = spaceId.value
      if (folderId.value) params.folderId = folderId.value
      const data = await browseKnowledge(params as never)
      browseResult.value = data
      folders.value = data.folders ?? []
      docs.value = data.documents?.items ?? []
      total.value = data.documents?.total ?? 0
    }
  } catch {
    folders.value = []
    docs.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  loadRecent()
  await Promise.all([loadSpaces(), loadCategories()])
  await load()
})

watch(spaceId, () => {
  void loadFolderTree()
})

function onSearch() {
  page.value = 1
  void load()
}

function clearSearch() {
  keyword.value = ''
  page.value = 1
  void load()
}

function switchView(v: 'files' | 'categories') {
  view.value = v
  page.value = 1
  void load()
}

function onCategoryClick(node: KnowledgeCategory) {
  goCategory(node)
}

function onSortChange(payload: SortChange) {
  if (!payload.sortField) return
  sort.value = payload.sortField
  order.value = payload.order === 'ascending' ? 'asc' : 'desc'
  page.value = 1
  void load()
}

/* ---------------- 面包屑 / 标题 ---------------- */
const crumbs = computed(() => {
  if (view.value === 'categories') {
    const cat = categories.value.find((c) => c.id === categoryId.value)
    return cat ? [{ id: cat.id, name: cat.name, kind: 'category' as const }] : []
  }
  const out: { id: number; name: string; kind: 'space' | 'folder' }[] = []
  if (spaceId.value && browseResult.value?.space) {
    out.push({ id: spaceId.value, name: browseResult.value.space.name, kind: 'space' })
  }
  for (const b of browseResult.value?.breadcrumb ?? []) {
    out.push({ id: b.id, name: b.name, kind: 'folder' })
  }
  return out
})

const currentTitle = computed(() => {
  if (view.value === 'categories') {
    const cat = categories.value.find((c) => c.id === categoryId.value)
    return cat?.name ?? t('knowledge.drive.allCategories')
  }
  if (folderId.value) {
    const last = crumbs.value[crumbs.value.length - 1]
    return last?.name ?? t('knowledge.drive.allFiles')
  }
  if (spaceId.value) return browseResult.value?.space?.name ?? t('knowledge.drive.allFiles')
  return t('knowledge.drive.allFiles')
})

/* ---------------- 行模型 ---------------- */
interface DriveRow extends Record<string, unknown> {
  id: string
  kind: 'folder' | 'document'
  name: string
  ext: string
  updateTime: string
  updater: string
  size: number
  docCount: number
  externalAccess: boolean
  restricted: boolean
  folder: KnowledgeBrowseFolder | null
  document: KnowledgeBrowseDocument | null
}

const rows = computed<DriveRow[]>(() => {
  const out: DriveRow[] = []
  for (const f of folders.value) {
    out.push({
      id: `f-${f.id}`,
      kind: 'folder',
      name: f.name,
      ext: '',
      updateTime: f.createTime,
      updater: '',
      size: 0,
      docCount: f.docCount,
      externalAccess: f.externalAccess,
      restricted: f.restricted,
      folder: f,
      document: null,
    })
  }
  for (const d of docs.value) {
    out.push({
      id: `d-${d.id}`,
      kind: 'document',
      name: d.title,
      ext: d.ext,
      updateTime: d.updateTime,
      updater: d.updaterName || d.ownerName,
      size: d.size,
      docCount: 0,
      externalAccess: d.externalAccess,
      restricted: d.restricted,
      folder: null,
      document: d,
    })
  }
  return out
})

function fmtSize(n: number) {
  if (!n) return '-'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

const EXT_TONE: Record<string, string> = {
  pdf: 'var(--bs-color-semantic-danger)',
  doc: 'var(--bs-color-semantic-info)',
  docx: 'var(--bs-color-semantic-info)',
  wps: 'var(--bs-color-semantic-info)',
  xls: 'var(--bs-color-semantic-success)',
  xlsx: 'var(--bs-color-semantic-success)',
  et: 'var(--bs-color-semantic-success)',
  ppt: 'var(--bs-color-semantic-warning)',
  pptx: 'var(--bs-color-semantic-warning)',
  dps: 'var(--bs-color-semantic-warning)',
  zip: 'var(--bs-color-accent-purple)',
  rar: 'var(--bs-color-accent-purple)',
  '7z': 'var(--bs-color-accent-purple)',
  jpg: 'var(--bs-color-accent-cyan)',
  jpeg: 'var(--bs-color-accent-cyan)',
  png: 'var(--bs-color-accent-cyan)',
  gif: 'var(--bs-color-accent-cyan)',
  bmp: 'var(--bs-color-accent-cyan)',
  webp: 'var(--bs-color-accent-cyan)',
  txt: 'var(--bs-color-fg-secondary)',
  md: 'var(--bs-color-fg-secondary)',
  csv: 'var(--bs-color-fg-secondary)',
}

function toneOf(ext: string) {
  return EXT_TONE[(ext || '').toLowerCase()] || 'var(--bs-color-fg-muted)'
}

/* ---------------- 表格 ---------------- */
const columns = computed<ListColumn[]>(() => [
  {
    prop: 'name',
    labelKey: 'knowledge.drive.fileName',
    minWidth: 260,
    slot: 'name',
    sortable: view.value === 'files' ? 'name' : undefined,
  },
  {
    prop: 'updateTime',
    labelKey: 'knowledge.drive.lastUpdate',
    width: 170,
    sortable: view.value === 'files' ? 'updateTime' : undefined,
  },
  { prop: 'updater', labelKey: 'knowledge.drive.updater', width: 130 },
  {
    prop: 'size',
    labelKey: 'knowledge.doc.size',
    width: 110,
    align: 'right',
    sortable: view.value === 'files' ? 'size' : undefined,
    formatter: (row) => (row.kind === 'folder' ? '-' : fmtSize(Number(row.size))),
  },
  { prop: 'actions', labelKey: 'common.action.operate', width: 120, fixed: 'right', align: 'center', slot: 'actions' },
])

const folderActions = computed<ActionItem[]>(() => [
  { key: 'enter', tip: 'knowledge.drive.enter', icon: 'FolderOpened' },
  { key: 'link', tip: 'knowledge.drive.shareLink', icon: 'Link', perm: 'knowledge:link:create' },
  { key: 'delete', tip: 'knowledge.doc.delete', icon: 'Delete', perm: 'knowledge:document:delete' },
])

const docActions = computed<ActionItem[]>(() => [
  { key: 'preview', tip: 'knowledge.doc.preview', icon: 'View', perm: 'knowledge:preview' },
  { key: 'versions', tip: 'knowledge.doc.versions', icon: 'CopyDocument', perm: 'knowledge:document:list' },
  { key: 'perm', tip: 'knowledge.doc.share', icon: 'Lock', perm: 'knowledge:document:share' },
  { key: 'link', tip: 'knowledge.drive.shareLink', icon: 'Link', perm: 'knowledge:link:create' },
  { key: 'download', tip: 'knowledge.doc.download', icon: 'Download', perm: 'knowledge:download' },
  { key: 'delete', tip: 'knowledge.doc.delete', icon: 'Delete', perm: 'knowledge:document:delete' },
])

function onAction(key: string, row: DriveRow) {
  if (key === 'enter' && row.folder) {
    goFolder(row.folder)
    return
  }
  if (key === 'preview' && row.document) {
    void openPreview(row.document)
    return
  }
  if (key === 'versions' && row.document) {
    void openVersions(row.document)
    return
  }
  if (key === 'perm' && row.document) {
    void openPermissions(row.document)
    return
  }
  if (key === 'link') {
    openLinkDialog(row)
    return
  }
  if (key === 'download' && row.document) {
    void doDownload(row.document)
    return
  }
  if (key === 'delete') {
    void doDelete(row)
  }
}

function onRowClick(row: DriveRow) {
  if (row.kind === 'folder' && row.folder) goFolder(row.folder)
}

/* ---------------- 删除 ---------------- */
async function doDelete(row: DriveRow) {
  if (row.kind === 'folder' && row.folder) {
    try {
      await ElMessageBox.confirm(
        t('knowledge.drive.deleteFolderConfirm', { name: row.name }),
        t('common.action.confirm'),
        { type: 'warning' },
      )
    } catch {
      return
    }
    await deleteKnowledgeFolder(row.folder.id)
    ElMessage.success(t('common.message.deleteSuccess'))
  } else if (row.document) {
    try {
      await ElMessageBox.confirm(
        t('knowledge.doc.deleteConfirm', { title: row.name }),
        t('common.action.confirm'),
        { type: 'warning' },
      )
    } catch {
      return
    }
    await deleteKnowledgeDocument(row.document.id)
    ElMessage.success(t('common.message.deleteSuccess'))
  }
  await load()
}

/* ---------------- 下载 ---------------- */
async function doDownload(row: KnowledgeDocument) {
  await download(
    { url: `/knowledge/documents/${row.id}/download`, method: 'get' },
    row.title + (row.ext ? `.${row.ext}` : ''),
  )
}

/* ---------------- 上传 ---------------- */
const uploadVisible = ref(false)
const uploadMode = ref<'single' | 'batch'>('single')
const uploadFile = ref<File | null>(null)
const uploadFiles = ref<File[]>([])
const uploadTitle = ref('')
const uploadSpaceId = ref<number | null>(null)
const uploadFolderId = ref<number | null>(null)
const uploadCategoryId = ref<number | null>(null)
const uploading = ref(false)

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

function openUpload(mode: 'single' | 'batch') {
  uploadMode.value = mode
  uploadFile.value = null
  uploadFiles.value = []
  uploadTitle.value = ''
  uploadSpaceId.value = spaceId.value ?? spaces.value[0]?.id ?? null
  uploadFolderId.value = folderId.value
  uploadCategoryId.value = categoryId.value
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
  const sid = uploadSpaceId.value
  if (!sid) {
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
      fd.append('space_id', String(sid))
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
      fd.append('space_id', String(sid))
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

/* ---------------- 新建文件夹 ---------------- */
const folderVisible = ref(false)
const folderForm = reactive({ name: '', parentId: null as number | null, categoryId: null as number | null })

function openFolderDialog() {
  if (!spaceId.value) {
    ElMessage.warning(t('knowledge.doc.selectSpace'))
    return
  }
  folderForm.name = ''
  folderForm.parentId = folderId.value
  folderForm.categoryId = categoryId.value
  folderVisible.value = true
}

async function submitFolder() {
  if (!spaceId.value || !folderForm.name.trim()) return
  await createKnowledgeFolder({
    name: folderForm.name.trim(),
    space_id: spaceId.value,
    parent_id: folderForm.parentId,
    category_id: folderForm.categoryId,
  } as never)
  ElMessage.success(t('knowledge.category.saved'))
  folderVisible.value = false
  await load()
}

/* ---------------- 管理器弹层 ---------------- */
const categoryManagerVisible = ref(false)
const spaceManagerVisible = ref(false)

function onCreateCommand(cmd: string) {
  if (cmd === 'folder') openFolderDialog()
  else if (cmd === 'space') spaceManagerVisible.value = true
  else if (cmd === 'category') categoryManagerVisible.value = true
}

/* ---------------- 在线浏览 ---------------- */
const previewVisible = ref(false)
const previewData = ref<KnowledgePreview | null>(null)
const previewTitle = ref('')
const previewImageUrl = ref('')

async function loadPreview(docId: number) {
  try {
    const data = await previewKnowledgeDocument(docId)
    previewData.value = data
    if (data.kind === 'image') {
      const resp = await http.get(`/knowledge/documents/${docId}/raw`, { responseType: 'blob' })
      previewImageUrl.value = URL.createObjectURL(new Blob([resp.data]))
    }
  } catch {
    previewData.value = { kind: 'none', text: '', message: t('knowledge.doc.previewUnsupported') }
  }
}

async function openPreview(row: KnowledgeDocument) {
  previewTitle.value = row.title
  previewData.value = null
  previewImageUrl.value = ''
  previewVisible.value = true
  pushRecent({ id: row.id, title: row.title, updateTime: row.updateTime })
  await loadPreview(row.id)
}

async function openRecent(doc: RecentDoc) {
  previewTitle.value = doc.title
  previewData.value = null
  previewImageUrl.value = ''
  previewVisible.value = true
  await loadPreview(doc.id)
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

/* ---------------- 外部分享链接 ---------------- */
const linkVisible = ref(false)
const linkTarget = ref<DriveRow | null>(null)
const linkPerm = ref<'read' | 'upload' | 'edit'>('read')
const linkExpireDays = ref(7)
const linkRequirePhone = ref(true)
const linkResult = ref('')

function openLinkDialog(row: DriveRow) {
  linkTarget.value = row
  linkPerm.value = 'read'
  linkExpireDays.value = 7
  linkRequirePhone.value = true
  linkResult.value = ''
  linkVisible.value = true
}

async function submitLink() {
  const row = linkTarget.value
  if (!row) return
  const res = await createKnowledgeLink({
    resourceType: row.kind === 'folder' ? 'folder' : 'document',
    resourceId: row.kind === 'folder' ? row.folder!.id : row.document!.id,
    perm: linkPerm.value,
    requirePhone: linkRequirePhone.value ? 1 : 0,
    expireDays: linkExpireDays.value,
  })
  linkResult.value = `${window.location.origin}/knowledge/share/${res.token}`
  ElMessage.success(t('knowledge.link.created'))
  await load()
}

async function copyLink() {
  if (!linkResult.value) return
  try {
    await navigator.clipboard.writeText(linkResult.value)
    ElMessage.success(t('knowledge.link.copied'))
  } catch {
    ElMessage.warning(t('knowledge.link.copied'))
  }
}
</script>

<template>
  <div class="bs-page bs-page--fill drive">
    <!-- 左栏：微盘式导航 -->
    <aside class="drive-side">
      <el-input
        v-model="keyword"
        :placeholder="t('knowledge.drive.searchPlaceholder')"
        clearable
        class="drive-search"
        @keyup.enter="onSearch()"
        @clear="clearSearch()"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>

      <div class="drive-tabs">
        <button
          type="button"
          class="drive-tab"
          :class="{ active: view === 'files' }"
          @click="switchView('files')"
        >
          {{ t('knowledge.drive.filesTab') }}
        </button>
        <button
          type="button"
          class="drive-tab"
          :class="{ active: view === 'categories' }"
          @click="switchView('categories')"
        >
          {{ t('knowledge.drive.categoriesTab') }}
        </button>
      </div>

      <div v-if="view === 'files'" class="drive-nav">
        <section v-if="recentDocs.length" class="drive-group">
          <div class="drive-group-title">{{ t('knowledge.drive.recent') }}</div>
          <div v-for="d in recentDocs" :key="d.id" class="drive-item" @click="openRecent(d)">
            <el-icon class="drive-item-icon"><DocIcon /></el-icon>
            <span class="drive-item-text">{{ d.title }}</span>
          </div>
        </section>

        <section class="drive-group">
          <div
            class="drive-item"
            :class="{ active: !spaceId && !folderId }"
            @click="goSpace(null)"
          >
            <el-icon class="drive-item-icon"><Files /></el-icon>
            <span class="drive-item-text">{{ t('knowledge.drive.allFiles') }}</span>
          </div>
        </section>

        <section v-if="mySpaces.length" class="drive-group">
          <div class="drive-group-title">{{ t('knowledge.drive.mySpaces') }}</div>
          <div
            v-for="s in mySpaces"
            :key="s.id"
            class="drive-item"
            :class="{ active: spaceId === s.id }"
            @click="goSpace(s)"
          >
            <el-icon class="drive-item-icon"><FolderIcon /></el-icon>
            <span class="drive-item-text">{{ s.name }}</span>
          </div>
        </section>

        <section v-if="sharedByMe.length" class="drive-group">
          <div class="drive-group-title">{{ t('knowledge.drive.sharedByMe') }}</div>
          <div
            v-for="s in sharedByMe"
            :key="s.id"
            class="drive-item"
            :class="{ active: spaceId === s.id }"
            @click="goSpace(s)"
          >
            <el-icon class="drive-item-icon"><FolderIcon /></el-icon>
            <span class="drive-item-text">{{ s.name }}</span>
          </div>
        </section>

        <section v-if="pinnedSpaces.length" class="drive-group">
          <div class="drive-group-title" @click="groups.pinned = !groups.pinned">
            {{ t('knowledge.drive.pinned') }}
          </div>
          <div v-show="groups.pinned">
            <div
              v-for="s in pinnedSpaces"
              :key="s.id"
              class="drive-item"
              :class="{ active: spaceId === s.id }"
              @click="goSpace(s)"
            >
              <el-icon class="drive-item-icon"><FolderIcon /></el-icon>
              <span class="drive-item-text">{{ s.name }}</span>
            </div>
          </div>
        </section>

        <section v-if="sharedGroups.length" class="drive-group">
          <div class="drive-group-title" @click="groups.shared = !groups.shared">
            {{ t('knowledge.drive.shared') }}
          </div>
          <div v-show="groups.shared">
            <div v-for="g in sharedGroups" :key="g.key" class="drive-subgroup">
              <div class="drive-subgroup-title">{{ g.name }}</div>
              <div
                v-for="s in g.spaces"
                :key="s.id"
                class="drive-item"
                :class="{ active: spaceId === s.id }"
                @click="goSpace(s)"
              >
                <el-icon class="drive-item-icon"><FolderIcon /></el-icon>
                <span class="drive-item-text">{{ s.name }}</span>
              </div>
            </div>
          </div>
        </section>
      </div>

      <div v-else class="drive-nav">
        <el-tree
          :data="categories"
          node-key="id"
          :props="{ label: 'name', children: 'children' }"
          :expand-on-click-node="false"
          highlight-current
          :default-expanded-keys="categoryId ? [categoryId] : []"
          @node-click="onCategoryClick"
        />
        <el-empty v-if="!categories.length" :description="t('knowledge.common.empty')" :image-size="60" />
      </div>

      <div class="drive-side-foot">
        <el-button
          v-permission="'knowledge:category:edit'"
          link
          type="primary"
          @click="categoryManagerVisible = true"
        >
          {{ t('knowledge.drive.categoryManage') }}
        </el-button>
        <el-button
          v-permission="'knowledge:space:edit'"
          link
          type="primary"
          @click="spaceManagerVisible = true"
        >
          {{ t('knowledge.drive.spaceManage') }}
        </el-button>
        <div class="drive-usage">
          {{ t('knowledge.drive.storageUsage', { size: storageUsed, count: myDocCount }) }}
        </div>
      </div>
    </aside>

    <!-- 主区 -->
    <section class="drive-main">
      <header class="drive-head">
        <div class="drive-head-left">
          <el-button-group>
            <el-button :icon="ArrowLeft" :disabled="!canBack" @click="goBack()" />
            <el-button :icon="ArrowRight" :disabled="!canForward" @click="goForward()" />
          </el-button-group>
          <el-breadcrumb separator="/">
            <el-breadcrumb-item v-for="c in crumbs" :key="`${c.kind}-${c.id}`">
              <a
                @click="
                  c.kind === 'space'
                    ? goSpace(spaces.find((s) => s.id === c.id) ?? null)
                    : c.kind === 'category'
                      ? goCategory(categories.find((x) => x.id === c.id)!)
                      : goFolder({ id: c.id, spaceId: spaceId ?? 0 } as KnowledgeBrowseFolder)
                "
              >
                {{ c.name }}
              </a>
            </el-breadcrumb-item>
          </el-breadcrumb>
          <span class="drive-title">{{ currentTitle }}</span>
        </div>
        <div class="drive-head-right">
          <el-dropdown @command="(c: string) => (c === 'single' || c === 'batch') && openUpload(c)">
            <el-button type="primary" :icon="Upload">
              {{ t('knowledge.doc.upload') }}
              <el-icon class="el-icon--right"><ArrowRight /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="single">{{ t('knowledge.doc.upload') }}</el-dropdown-item>
                <el-dropdown-item command="batch">{{ t('knowledge.doc.uploadBatch') }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-dropdown @command="onCreateCommand">
            <el-button :icon="Plus">{{ t('knowledge.drive.create') }}</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="folder">{{ t('knowledge.common.newFolder') }}</el-dropdown-item>
                <el-dropdown-item command="space">{{ t('knowledge.space.create') }}</el-dropdown-item>
                <el-dropdown-item command="category">{{ t('knowledge.drive.categoryManage') }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-radio-group v-model="viewMode" size="small">
            <el-radio-button value="list">
              <el-icon><List /></el-icon>
            </el-radio-button>
            <el-radio-button value="grid">
              <el-icon><Grid /></el-icon>
            </el-radio-button>
          </el-radio-group>
        </div>
      </header>

      <div class="drive-body">
        <ListTable
          v-if="viewMode === 'list'"
          :columns="columns"
          :data="rows as unknown as Record<string, unknown>[]"
          :loading="loading"
          :total="total"
          :page="page"
          :size="size"
          row-key="id"
          height="100%"
          @row-click="(r: Record<string, unknown>) => onRowClick(r as unknown as DriveRow)"
          @sort-change="onSortChange"
          @update:page="(v: number) => { page = v; load() }"
          @update:size="(v: number) => { size = v; page = 1; load() }"
        >
          <template #name="{ row }">
            <div class="drive-name">
              <el-icon v-if="row.kind === 'folder'" class="drive-icon drive-icon-folder">
                <FolderIcon />
              </el-icon>
              <span
                v-else
                class="drive-icon drive-icon-file"
                :style="{ color: toneOf(String(row.ext || '')) }"
              >
                {{ (row.ext || 'file').slice(0, 3).toUpperCase() }}
              </span>
              <span class="drive-name-text">{{ row.name }}</span>
              <el-tag v-if="row.externalAccess" size="small" type="warning" class="drive-tag">
                {{ t('knowledge.drive.externalAccess') }}
              </el-tag>
              <el-tag v-if="row.restricted" size="small" type="info" class="drive-tag">
                {{ t('knowledge.drive.restricted') }}
              </el-tag>
              <span v-if="row.kind === 'folder'" class="drive-count">
                {{ t('knowledge.drive.itemCount', { count: row.docCount }) }}
              </span>
            </div>
          </template>
          <template #actions="{ row }">
            <ActionBar
              :actions="row.kind === 'folder' ? folderActions : docActions"
              :max-inline="3"
              @select="(key: string) => onAction(key, row as unknown as DriveRow)"
            />
          </template>
        </ListTable>

        <div v-else v-loading="loading" class="drive-grid">
          <el-empty v-if="!rows.length" :description="t('knowledge.common.empty')" />
          <article v-for="row in rows" :key="row.id" class="drive-card" @click="onRowClick(row)">
            <div class="drive-card-head">
              <el-icon v-if="row.kind === 'folder'" class="drive-icon drive-icon-folder">
                <FolderIcon />
              </el-icon>
              <span
                v-else
                class="drive-icon drive-icon-file"
                :style="{ color: toneOf(String(row.ext || '')) }"
              >
                {{ (row.ext || 'file').slice(0, 3).toUpperCase() }}
              </span>
              <span class="drive-name-text">{{ row.name }}</span>
            </div>
            <div class="drive-card-meta">
              <span>{{ row.updateTime }}</span>
              <span>{{ row.kind === 'folder' ? '-' : fmtSize(row.size) }}</span>
            </div>
            <div class="drive-card-foot">
              <el-tag v-if="row.externalAccess" size="small" type="warning">
                {{ t('knowledge.drive.externalAccess') }}
              </el-tag>
              <el-tag v-if="row.restricted" size="small" type="info">
                {{ t('knowledge.drive.restricted') }}
              </el-tag>
              <ActionBar
                :actions="row.kind === 'folder' ? folderActions : docActions"
                :max-inline="3"
                @select="(key: string) => onAction(key, row)"
              />
            </div>
          </article>
          <div v-if="total > size" class="drive-grid-pager">
            <el-pagination
              :current-page="page"
              :page-size="size"
              :total="total"
              layout="prev, pager, next"
              background
              @current-change="(v: number) => { page = v; load() }"
            />
          </div>
        </div>
      </div>
    </section>
  </div>

  <!-- 上传 -->
  <el-dialog v-model="uploadVisible" :title="t('knowledge.doc.upload')" width="var(--bs-layout-dialog-md)" append-to-body>
    <el-form label-position="top">
      <el-form-item v-if="uploadMode === 'single'" :label="t('knowledge.doc.docTitle')">
        <el-input v-model="uploadTitle" />
      </el-form-item>
      <el-form-item :label="t('knowledge.common.space')">
        <el-select v-model="uploadSpaceId" style="width: 100%">
          <el-option v-for="o in spaceOptions" :key="o.value" :label="o.label" :value="o.value" />
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
      <el-form-item :label="t('knowledge.common.category')">
        <el-select v-model="uploadCategoryId" clearable style="width: 100%">
          <el-option v-for="c in categoryOptions" :key="c.value" :label="c.label" :value="c.value" />
        </el-select>
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

  <!-- 外部分享链接 -->
  <el-dialog v-model="linkVisible" :title="t('knowledge.link.create')" width="var(--bs-layout-dialog-sm)" append-to-body>
    <el-form label-position="top">
      <el-form-item :label="t('knowledge.link.resourceType')">
        <el-input :model-value="linkTarget?.name" disabled />
      </el-form-item>
      <el-form-item :label="t('knowledge.link.perm')">
        <el-select v-model="linkPerm" style="width: 100%">
          <el-option :label="t('knowledge.link.permRead')" value="read" />
          <el-option :label="t('knowledge.link.permUpload')" value="upload" />
          <el-option :label="t('knowledge.link.permEdit')" value="edit" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('knowledge.link.expireDays')">
        <el-input-number v-model="linkExpireDays" :min="0" :max="365" />
      </el-form-item>
      <el-form-item :label="t('knowledge.link.requirePhone')">
        <el-switch v-model="linkRequirePhone" />
      </el-form-item>
      <el-form-item v-if="linkResult" :label="t('knowledge.link.token')">
        <el-input :model-value="linkResult" readonly>
          <template #append>
            <el-button @click="copyLink()">{{ t('knowledge.link.copy') }}</el-button>
          </template>
        </el-input>
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="linkVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" @click="submitLink()">{{ t('common.action.submit') }}</el-button>
      </div>
    </template>
  </el-dialog>

  <!-- 在线浏览 -->
  <el-drawer
    v-model="previewVisible"
    :title="previewTitle || t('knowledge.doc.preview')"
    size="var(--bs-layout-drawer-lg)"
    append-to-body
    @closed="closePreview"
  >
    <div v-if="previewData?.kind === 'image'" class="preview-image">
      <img :src="previewImageUrl" :alt="previewTitle" />
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

  <!-- 分类管理 -->
  <CategoryManager
    v-model="categoryManagerVisible"
    @changed="loadCategories(); load()"
  />

  <!-- 空间管理 -->
  <SpaceManager v-model="spaceManagerVisible" @changed="loadSpaces(); load()" />
</template>

<style scoped>
/* 根容器：左右两栏（微盘式）。
   注意 `.bs-page` 基类是 `flex-direction: column`，这里必须显式改回 row，
   否则左栏会被当成纵向排列、主区落到下方。 */
.drive {
  display: flex;
  flex-direction: row;
  align-items: stretch;
  gap: 0;
  padding: 0;
  overflow: hidden;
  height: 100%;
  min-height: 0;
}

/* ---------------- 左栏 ---------------- */
.drive-side {
  width: 260px;
  flex: 0 0 260px;
  display: flex;
  flex-direction: column;
  min-width: 0;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  padding: var(--bs-space-3) var(--bs-space-2);
  border-right: 1px solid var(--bs-color-border-subtle);
  background: var(--bs-color-bg-surface);
}

.drive-search {
  flex: none;
  margin-bottom: var(--bs-space-2);
}

.drive-tabs {
  flex: none;
  display: flex;
  gap: var(--bs-space-1);
  padding-bottom: var(--bs-space-2);
  border-bottom: 1px solid var(--bs-color-border-subtle);
}

.drive-tab {
  flex: 1;
  padding: var(--bs-space-1) 0;
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-secondary);
  background: transparent;
  border: none;
  border-radius: var(--bs-radius-sm);
  cursor: pointer;
}

.drive-tab:hover {
  background: var(--bs-color-fill-hover);
}

.drive-tab.active {
  color: var(--bs-color-brand-primary);
  background: var(--bs-color-brand-primary-soft);
  font-weight: 600;
}

/* 导航区：唯一可滚动的一段，与页脚互不重叠 */
.drive-nav {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: var(--bs-space-2) 0;
}

.drive-group {
  margin-bottom: var(--bs-space-3);
}

.drive-group-title {
  padding: var(--bs-space-1) var(--bs-space-2);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
  cursor: pointer;
  user-select: none;
}

.drive-subgroup {
  margin-bottom: var(--bs-space-2);
}

.drive-subgroup-title {
  padding: var(--bs-space-1) var(--bs-space-2);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.drive-item {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  padding: var(--bs-space-2);
  border-radius: var(--bs-radius-sm);
  color: var(--bs-color-fg-default);
  font-size: var(--bs-typography-font-size-sm);
  line-height: 1.5;
  cursor: pointer;
}

.drive-item:hover {
  background: var(--bs-color-fill-hover);
}

.drive-item.active {
  background: var(--bs-color-brand-primary-soft);
  color: var(--bs-color-brand-primary);
  font-weight: 600;
}

.drive-item-icon {
  flex: none;
  color: var(--bs-color-fg-muted);
}

.drive-item-text {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.drive-side-foot {
  flex: none;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bs-space-2);
  padding-top: var(--bs-space-2);
  border-top: 1px solid var(--bs-color-border-subtle);
}

.drive-usage {
  width: 100%;
  padding: var(--bs-space-1) 0 0;
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

/* ---------------- 主区 ---------------- */
.drive-main {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: var(--bs-layout-content-padding);
}

.drive-head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bs-space-3);
  flex-wrap: wrap;
  margin-bottom: var(--bs-space-3);
}

.drive-head-left {
  display: flex;
  align-items: center;
  gap: var(--bs-space-3);
  min-width: 0;
}

.drive-head-right {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.drive-title {
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.drive-body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

/* ---------------- 行内容 ---------------- */
.drive-name {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  min-width: 0;
}

.drive-icon-folder {
  flex: none;
  color: var(--bs-color-brand-primary);
}

.drive-icon-file {
  flex: none;
  width: 22px;
  text-align: center;
  font-size: var(--bs-typography-font-size-xs);
  font-weight: 700;
}

.drive-name-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.drive-tag {
  flex: none;
}

.drive-count {
  flex: none;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}

/* ---------------- 网格视图 ---------------- */
.drive-grid {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--bs-space-3);
  align-content: start;
}

.drive-card {
  padding: var(--bs-space-3);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.drive-card:hover {
  border-color: var(--bs-color-brand-primary);
}

.drive-card-head {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  min-width: 0;
}

.drive-card-meta {
  display: flex;
  justify-content: space-between;
  gap: var(--bs-space-2);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.drive-card-foot {
  display: flex;
  align-items: center;
  gap: var(--bs-space-1);
  min-height: 20px;
}

.drive-grid-pager {
  grid-column: 1 / -1;
  display: flex;
  justify-content: center;
  padding: var(--bs-space-2) 0;
}

/* ---------------- 预览 ---------------- */
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

@media (max-width: 767px) {
  .drive {
    flex-direction: column;
    height: auto;
    overflow: auto;
  }

  .drive-side {
    width: 100%;
    flex: 0 0 auto;
    height: auto;
    border-right: none;
    border-bottom: 1px solid var(--bs-color-border-subtle);
    max-height: 40vh;
  }

  .drive-main {
    height: auto;
    padding: var(--bs-space-3);
    min-height: 60vh;
  }
}
</style>
