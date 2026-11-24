import { beforeEach, describe, expect, it } from 'vitest'
import { clearTokens, getAccessToken, getRefreshToken, isRemembered, setTokens } from './http'

describe('token storage', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  it('keeps a remembered session in localStorage', () => {
    setTokens('a1', 'r1', true)
    expect(localStorage.getItem('bs.access_token')).toBe('a1')
    expect(sessionStorage.getItem('bs.access_token')).toBeNull()
    expect(getAccessToken()).toBe('a1')
    expect(getRefreshToken()).toBe('r1')
    expect(isRemembered()).toBe(true)
  })

  it('keeps a session-scoped login in sessionStorage', () => {
    setTokens('a2', 'r2', false)
    expect(sessionStorage.getItem('bs.access_token')).toBe('a2')
    expect(localStorage.getItem('bs.access_token')).toBeNull()
    expect(getAccessToken()).toBe('a2')
    expect(getRefreshToken()).toBe('r2')
    expect(isRemembered()).toBe(false)
  })

  it('clears the other store when switching mode', () => {
    setTokens('a1', 'r1', true)
    setTokens('a2', 'r2', false)
    expect(localStorage.getItem('bs.access_token')).toBeNull()
    expect(localStorage.getItem('bs.refresh_token')).toBeNull()
    expect(sessionStorage.getItem('bs.access_token')).toBe('a2')
  })

  it('reads legacy sessions that only live in localStorage', () => {
    localStorage.setItem('bs.access_token', 'legacy')
    localStorage.setItem('bs.refresh_token', 'legacy-r')
    expect(getAccessToken()).toBe('legacy')
    expect(getRefreshToken()).toBe('legacy-r')
    expect(isRemembered()).toBe(true)
  })

  it('clearTokens removes tokens from both stores', () => {
    setTokens('a1', 'r1', true)
    clearTokens()
    expect(getAccessToken()).toBe('')
    expect(getRefreshToken()).toBe('')
    expect(localStorage.getItem('bs.access_token')).toBeNull()
    expect(sessionStorage.getItem('bs.access_token')).toBeNull()
  })
})
