import { request, download } from './http'
import type { LoginResult, RefreshResult, UserProfile, UserPrefs } from './types'

export function login(username: string, password: string) {
  return request<LoginResult>({
    url: '/auth/login',
    method: 'post',
    data: { username, password },
  })
}

export function refresh(refreshToken: string) {
  return request<RefreshResult>({
    url: '/auth/refresh',
    method: 'post',
    data: { refresh_token: refreshToken },
  })
}

export function logout(refreshToken?: string) {
  return request<void>({
    url: '/auth/logout',
    method: 'post',
    data: refreshToken ? { refresh_token: refreshToken } : {},
  })
}

export function me() {
  return request<UserProfile>({ url: '/auth/me', method: 'get' })
}

export function updatePrefs(prefs: UserPrefs) {
  return request<void>({
    url: '/admin/prefs',
    method: 'put',
    data: { prefs },
  })
}

export function downloadFile(fileId: string | number, fileName = 'file') {
  return download({ url: `/contract/attachments/${fileId}`, method: 'get' }, fileName)
}
