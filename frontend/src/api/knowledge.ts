import { request, toQuery } from './http'
import type {
  KnowledgeBatchResult,
  KnowledgeBrowseResult,
  KnowledgeCategory,
  KnowledgeDocument,
  KnowledgeFolder,
  KnowledgePermission,
  KnowledgePreview,
  KnowledgeSettings,
  KnowledgeShareLink,
  KnowledgeShareLinkCreated,
  KnowledgeSpace,
  KnowledgeVersion,
  ListQuery,
  PageResult,
  PublicShareDocument,
  PublicShareInfo,
} from './types'

/* ---------------- 分类（多级树） ---------------- */

export function listKnowledgeCategories() {
  return request<{ items: KnowledgeCategory[] }>({ url: '/knowledge/categories', method: 'get' })
}

export function createKnowledgeCategory(data: Partial<KnowledgeCategory>) {
  return request<{ id: number; name: string; path: string; level: number }>({
    url: '/knowledge/categories',
    method: 'post',
    data,
  })
}

export function updateKnowledgeCategory(id: number, data: Partial<KnowledgeCategory>) {
  return request<{ id: number; name: string; path: string; level: number }>({
    url: `/knowledge/categories/${id}`,
    method: 'put',
    data,
  })
}

export function deleteKnowledgeCategory(id: number) {
  return request<void>({ url: `/knowledge/categories/${id}`, method: 'delete' })
}

/* ---------------- 空间 ---------------- */

export function listKnowledgeSpaces() {
  return request<{ items: KnowledgeSpace[] }>({ url: '/knowledge/spaces', method: 'get' })
}

export function createKnowledgeSpace(data: Partial<KnowledgeSpace>) {
  return request<KnowledgeSpace>({ url: '/knowledge/spaces', method: 'post', data })
}

export function updateKnowledgeSpace(id: number, data: Partial<KnowledgeSpace>) {
  return request<KnowledgeSpace>({ url: `/knowledge/spaces/${id}`, method: 'put', data })
}

export function deleteKnowledgeSpace(id: number) {
  return request<void>({ url: `/knowledge/spaces/${id}`, method: 'delete' })
}

/** 置顶 / 取消置顶空间 */
export function pinKnowledgeSpace(id: number, pinned: boolean) {
  return request<KnowledgeSpace>({
    url: `/knowledge/spaces/${id}/pin`,
    method: 'post',
    data: { pinned: pinned ? 1 : 0 },
  })
}

/* ---------------- 微盘式目录浏览 ---------------- */

/** 一次取回「子文件夹 + 文档」 */
export function browseKnowledge(params: {
  spaceId?: number | null
  folderId?: number | null
  categoryId?: number | null
  q?: string
  page?: number
  size?: number
  sort?: string
  order?: string
}) {
  return request<KnowledgeBrowseResult>({
    url: '/knowledge/browse',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

/* ---------------- 文件夹 ---------------- */

export function listKnowledgeFolders(params: { spaceId?: number; parentId?: number }) {
  return request<{ items: KnowledgeFolder[] }>({
    url: '/knowledge/folders',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function knowledgeFolderTree(spaceId: number) {
  return request<{ items: KnowledgeFolder[] }>({
    url: '/knowledge/folders/tree',
    method: 'get',
    params: { spaceId },
  })
}

export function createKnowledgeFolder(data: Partial<KnowledgeFolder>) {
  return request<KnowledgeFolder>({ url: '/knowledge/folders', method: 'post', data })
}

export function updateKnowledgeFolder(id: number, data: Partial<KnowledgeFolder>) {
  return request<KnowledgeFolder>({ url: `/knowledge/folders/${id}`, method: 'put', data })
}

export function deleteKnowledgeFolder(id: number) {
  return request<void>({ url: `/knowledge/folders/${id}`, method: 'delete' })
}

/* ---------------- 文档 ---------------- */

export function listKnowledgeDocuments(params: ListQuery) {
  return request<PageResult<KnowledgeDocument>>({
    url: '/knowledge/documents',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function getKnowledgeDocument(id: number) {
  return request<KnowledgeDocument>({ url: `/knowledge/documents/${id}`, method: 'get' })
}

export function updateKnowledgeDocument(id: number, data: Partial<KnowledgeDocument>) {
  return request<KnowledgeDocument>({ url: `/knowledge/documents/${id}`, method: 'put', data })
}

export function deleteKnowledgeDocument(id: number) {
  return request<void>({ url: `/knowledge/documents/${id}`, method: 'delete' })
}

/** 单个文档上传 */
export function uploadKnowledgeDocument(form: FormData) {
  return request<KnowledgeDocument>({
    url: '/knowledge/documents',
    method: 'post',
    data: form,
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/** 批量上传 */
export function uploadKnowledgeDocuments(form: FormData) {
  return request<KnowledgeBatchResult>({
    url: '/knowledge/documents/batch',
    method: 'post',
    data: form,
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function listKnowledgeVersions(docId: number) {
  return request<{ items: KnowledgeVersion[] }>({
    url: `/knowledge/documents/${docId}/versions`,
    method: 'get',
  })
}

/** 上传新版本 */
export function uploadKnowledgeVersion(docId: number, form: FormData) {
  return request<KnowledgeVersion>({
    url: `/knowledge/documents/${docId}/versions`,
    method: 'post',
    data: form,
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/** 回滚到历史版本（生成新版本，历史保留） */
export function rollbackKnowledgeVersion(docId: number, versionId: number) {
  return request<KnowledgeVersion>({
    url: `/knowledge/documents/${docId}/rollback/${versionId}`,
    method: 'post',
  })
}

/** 在线预览（服务端抽文本） */
export function previewKnowledgeDocument(docId: number) {
  return request<KnowledgePreview>({ url: `/knowledge/documents/${docId}/preview`, method: 'get' })
}

/** 原文件地址（需带 Authorization，图片/pdf 直开） */
export function knowledgeRawUrl(docId: number) {
  return `/api/v1/knowledge/documents/${docId}/raw`
}

/** 原文件下载地址（需带 Authorization） */
export function knowledgeDownloadUrl(docId: number) {
  return `/api/v1/knowledge/documents/${docId}/download`
}

/* ---------------- 授权 ---------------- */

export function listKnowledgePermissions(docId: number) {
  return request<{ items: KnowledgePermission[] }>({
    url: `/knowledge/documents/${docId}/permissions`,
    method: 'get',
  })
}

/** 整体覆盖文档授权 */
export function setKnowledgePermissions(docId: number, data: Partial<KnowledgePermission>[]) {
  return request<{ items: KnowledgePermission[] }>({
    url: `/knowledge/documents/${docId}/permissions`,
    method: 'put',
    data,
  })
}

export function deleteKnowledgePermission(id: number) {
  return request<void>({ url: `/knowledge/permissions/${id}`, method: 'delete' })
}

/* ---------------- 分享链接 ---------------- */

export function listKnowledgeLinks(params: ListQuery) {
  return request<PageResult<KnowledgeShareLink>>({
    url: '/knowledge/links',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function createKnowledgeLink(data: {
  resourceType: string
  resourceId: number
  perm?: string
  requirePhone?: number
  expireDays?: number
  maxUpload?: number
  remark?: string
}) {
  return request<KnowledgeShareLinkCreated>({ url: '/knowledge/links', method: 'post', data })
}

export function closeKnowledgeLink(id: number) {
  return request<void>({ url: `/knowledge/links/${id}`, method: 'delete' })
}

/* ---------------- 设置 ---------------- */

export function getKnowledgeSettings() {
  return request<KnowledgeSettings>({ url: '/knowledge/settings', method: 'get' })
}

export function updateKnowledgeSettings(data: Partial<KnowledgeSettings>) {
  return request<KnowledgeSettings>({ url: '/knowledge/settings', method: 'put', data })
}

/* ---------------- 外部分享（公开，无需登录） ---------------- */

export function getPublicShareLink(token: string) {
  return request<PublicShareInfo>({ url: `/knowledge/public/links/${token}`, method: 'get' })
}

export function sendPublicShareCode(token: string, phone: string) {
  return request<{ sent: boolean; debugCode?: string; cooldown?: number }>({
    url: `/knowledge/public/links/${token}/code`,
    method: 'post',
    data: { phone },
  })
}

export function verifyPublicShareCode(token: string, phone: string, code: string) {
  return request<{ token: string; perm: string; title: string }>({
    url: `/knowledge/public/links/${token}/verify`,
    method: 'post',
    data: { phone, code },
  })
}

export function listPublicShareDocuments(token: string, access: string) {
  return request<{ items: PublicShareDocument[]; perm: string; title: string }>({
    url: `/knowledge/public/links/${token}/documents`,
    method: 'get',
    params: { access },
  })
}

/** 外部人员上传文件到分享文件夹 */
export function uploadPublicShareFile(token: string, access: string, form: FormData) {
  return request<{ id: number; title: string }>({
    url: `/knowledge/public/links/${token}/upload`,
    method: 'post',
    data: form,
    params: { access },
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/** 外部分享文件下载地址（带 access 令牌，公开） */
export function publicShareRawUrl(token: string, docId: number, access: string) {
  return `/api/v1/knowledge/public/links/${token}/raw/${docId}?access=${encodeURIComponent(access)}`
}
