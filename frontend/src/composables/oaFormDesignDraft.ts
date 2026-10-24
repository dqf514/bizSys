/**
 * OA 表单设计器本地草稿：设计过程中防抖自动保存到 localStorage，防意外关闭/刷新丢失。
 * 仅编辑器防意外，不改变后端草稿/发布语义。键按 userId + formKey 隔离（新建用 "new"）。
 */
import type { OaField } from '@/api/types'

export interface OaFormDesignDraftMeta {
  key: string
  name: string
  category: string
  icon: string
  sort: number
  description: string
  flowDefinitionId: number | null
}

export interface OaFormDesignDraft {
  meta: OaFormDesignDraftMeta
  fields: OaField[]
  savedAt: number
}

const PREFIX = 'oa.formDesign.draft.'

export function oaFormDesignDraftKey(userId: number | string | undefined, formKey: string): string {
  return `${PREFIX}${userId ?? 'anon'}.${formKey || 'new'}`
}

export function readOaFormDesignDraft(key: string): OaFormDesignDraft | null {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return null
    const d = JSON.parse(raw) as Partial<OaFormDesignDraft> | null
    if (!d || typeof d !== 'object') return null
    if (!d.meta || typeof d.meta !== 'object' || !Array.isArray(d.fields)) return null
    if (typeof d.savedAt !== 'number') return null
    return d as OaFormDesignDraft
  } catch {
    return null
  }
}

export function writeOaFormDesignDraft(key: string, draft: OaFormDesignDraft): boolean {
  try {
    localStorage.setItem(key, JSON.stringify(draft))
    return true
  } catch {
    return false /* storage unavailable (private mode etc.) — skip silently */
  }
}

export function clearOaFormDesignDraft(key: string) {
  try {
    localStorage.removeItem(key)
  } catch {
    /* storage 不可用时静默跳过 */
  }
}
