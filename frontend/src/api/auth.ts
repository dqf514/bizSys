import { request, download } from './http'
import type {
  BankAccount,
  CaptchaResult,
  EmergencyContact,
  LoginOutcome,
  LoginResult,
  MfaSendResult,
  ProfileInfo,
  RefreshResult,
  StepUpResult,
  UserPrefs,
  UserProfile,
} from './types'

export function getCaptcha() {
  return request<CaptchaResult>({ url: '/auth/captcha', method: 'get' })
}

export function login(username: string, password: string, captcha: { captchaId: string; captchaText: string }) {
  return request<LoginOutcome>({
    url: '/auth/login',
    method: 'post',
    data: { username, password, captchaId: captcha.captchaId, captchaText: captcha.captchaText },
  })
}

export function mfaSend(mfaToken: string, channel: 'sms' | 'email') {
  return request<MfaSendResult>({ url: '/auth/mfa/send', method: 'post', data: { mfaToken, channel } })
}

export function mfaVerify(mfaToken: string, code: string) {
  return request<LoginResult>({ url: '/auth/mfa/verify', method: 'post', data: { mfaToken, code } })
}

export function mfaToggle(enabled: boolean, stepUpToken: string) {
  return request<{ mfaEnabled: boolean }>({
    url: '/auth/mfa/toggle',
    method: 'post',
    data: { enabled },
    headers: { 'X-Step-Up-Token': stepUpToken },
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

export function changePassword(oldPassword: string, newPassword: string) {
  return request<void>({
    url: '/auth/password',
    method: 'post',
    data: { old_password: oldPassword, new_password: newPassword },
  })
}

export function wecomQrUrl(redirectUri: string) {
  return request<{ url: string; state: string }>({
    url: '/auth/wecom/qr-url',
    method: 'get',
    params: { redirect_uri: redirectUri },
  })
}

export function wecomCallback(code: string, state: string) {
  return request<LoginResult>({
    url: '/auth/wecom/callback',
    method: 'post',
    data: { code, state },
  })
}

export function updatePrefs(prefs: UserPrefs) {
  return request<void>({
    url: '/admin/prefs',
    method: 'put',
    data: { prefs },
  })
}

// ---------------- 批次B 个人档案 ----------------

export function getProfile() {
  return request<ProfileInfo>({ url: '/auth/profile', method: 'get' })
}

export function updateProfile(data: { mobile: string; email: string }, stepUpToken = '') {
  return request<ProfileInfo>({
    url: '/auth/profile',
    method: 'patch',
    data,
    headers: stepUpToken ? { 'X-Step-Up-Token': stepUpToken } : {},
  })
}

export function stepUp(password: string) {
  return request<StepUpResult>({ url: '/auth/step-up', method: 'post', data: { password } })
}

export function uploadAvatar(file: File) {
  const form = new FormData()
  form.append('file', file)
  return request<{ avatarUrl: string }>({
    url: '/auth/profile/avatar',
    method: 'post',
    data: form,
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function listContacts() {
  return request<EmergencyContact[]>({ url: '/auth/profile/contacts', method: 'get' })
}

export function createContact(data: Omit<EmergencyContact, 'id' | 'createTime'>) {
  return request<EmergencyContact>({ url: '/auth/profile/contacts', method: 'post', data })
}

export function updateContact(id: number, data: Omit<EmergencyContact, 'id' | 'createTime'>) {
  return request<EmergencyContact>({ url: `/auth/profile/contacts/${id}`, method: 'put', data })
}

export function deleteContact(id: number) {
  return request<void>({ url: `/auth/profile/contacts/${id}`, method: 'delete' })
}

export function listBankAccounts() {
  return request<BankAccount[]>({ url: '/auth/profile/bank-accounts', method: 'get' })
}

export type BankAccountIn = Pick<BankAccount, 'bankName' | 'cardNo' | 'holderName'>

function withStepUp(stepUpToken: string) {
  return { headers: { 'X-Step-Up-Token': stepUpToken } }
}

export function createBankAccount(data: BankAccountIn, stepUpToken: string) {
  return request<BankAccount>({ url: '/auth/profile/bank-accounts', method: 'post', data, ...withStepUp(stepUpToken) })
}

export function updateBankAccount(id: number, data: BankAccountIn, stepUpToken: string) {
  return request<BankAccount>({
    url: `/auth/profile/bank-accounts/${id}`,
    method: 'put',
    data,
    ...withStepUp(stepUpToken),
  })
}

export function deleteBankAccount(id: number, stepUpToken: string) {
  return request<void>({ url: `/auth/profile/bank-accounts/${id}`, method: 'delete', ...withStepUp(stepUpToken) })
}

export function revealBankAccount(id: number, stepUpToken: string) {
  return request<BankAccount>({
    url: `/auth/profile/bank-accounts/${id}/reveal`,
    method: 'get',
    ...withStepUp(stepUpToken),
  })
}

export function downloadFile(fileId: string | number, fileName = 'file') {
  return download({ url: `/contract/attachments/${fileId}`, method: 'get' }, fileName)
}
