import { describe, expect, it } from 'vitest'
import i18n, { setLocale } from './i18n'

/** t() 找不到键时会原样返回 key —— 以此判定译文是否真实挂载 */
function resolved(key: string): string {
  return i18n.global.t(key)
}

describe('i18n messages wired by namespace', () => {
  it('resolves common.* keys (regression: common was spread to root)', () => {
    for (const key of ['common.action.search', 'common.action.reset', 'common.form.createTime', 'common.app.short']) {
      expect(resolved(key), key).not.toBe(key)
    }
  })

  it('resolves every domain namespace', () => {
    const samples = [
      'menu.workbench',
      'menu.customer',
      'auth.user.logoutConfirm',
      'workbench.title',
      'admin.audit.title',
      'approval.approval.timeline',
      'crm.customer.create',
      'contract.contract.detail',
      'task.task.outConfirm',
    ]
    for (const key of samples) {
      expect(resolved(key), `${key} => ${resolved(key)}`).not.toBe(key)
    }
  })

  it('switches locale to en-US and back', () => {
    setLocale('en-US')
    expect(i18n.global.locale.value).toBe('en-US')
    expect(resolved('common.action.search')).not.toBe('common.action.search')
    setLocale('zh-CN')
    expect(i18n.global.locale.value).toBe('zh-CN')
  })
})
