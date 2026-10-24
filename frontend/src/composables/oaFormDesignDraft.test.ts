import { beforeEach, describe, expect, it } from 'vitest'
import {
  clearOaFormDesignDraft,
  oaFormDesignDraftKey,
  readOaFormDesignDraft,
  writeOaFormDesignDraft,
  type OaFormDesignDraft,
} from './oaFormDesignDraft'

function makeDraft(savedAt = 1720000000000): OaFormDesignDraft {
  return {
    meta: {
      key: 'leave_apply',
      name: 'Leave Apply',
      category: 'hr',
      icon: 'Document',
      sort: 0,
      description: '',
      flowDefinitionId: null,
    },
    fields: [{ key: 'reason', label: 'Reason', type: 'text', required: true }],
    savedAt,
  }
}

describe('oaFormDesignDraft', () => {
  beforeEach(() => localStorage.clear())

  it('builds keys isolated by user and formKey, "new" for creation', () => {
    expect(oaFormDesignDraftKey(1, 'leave_apply')).toBe('oa.formDesign.draft.1.leave_apply')
    expect(oaFormDesignDraftKey(2, 'leave_apply')).toBe('oa.formDesign.draft.2.leave_apply')
    expect(oaFormDesignDraftKey(1, '')).toBe('oa.formDesign.draft.1.new')
    expect(oaFormDesignDraftKey(undefined, 'x')).toBe('oa.formDesign.draft.anon.x')
  })

  it('round-trips a draft', () => {
    const key = oaFormDesignDraftKey(1, 'leave_apply')
    expect(writeOaFormDesignDraft(key, makeDraft())).toBe(true)
    const draft = readOaFormDesignDraft(key)
    expect(draft?.meta.name).toBe('Leave Apply')
    expect(draft?.fields).toHaveLength(1)
    expect(draft?.savedAt).toBe(1720000000000)
  })

  it('returns null for missing or corrupted storage', () => {
    const missing = 'oa.formDesign.draft.1.nope'
    const bad = 'oa.formDesign.draft.1.bad'
    const half = 'oa.formDesign.draft.1.half'
    expect(readOaFormDesignDraft(missing)).toBeNull()
    localStorage.setItem(bad, '{bad json')
    expect(readOaFormDesignDraft(bad)).toBeNull()
    localStorage.setItem(half, JSON.stringify({ meta: {} }))
    expect(readOaFormDesignDraft(half)).toBeNull()
  })

  it('clears only the targeted draft', () => {
    const a = oaFormDesignDraftKey(1, 'new')
    const b = oaFormDesignDraftKey(1, 'leave_apply')
    writeOaFormDesignDraft(a, makeDraft())
    writeOaFormDesignDraft(b, makeDraft())
    clearOaFormDesignDraft(a)
    expect(readOaFormDesignDraft(a)).toBeNull()
    expect(readOaFormDesignDraft(b)).not.toBeNull()
  })
})
