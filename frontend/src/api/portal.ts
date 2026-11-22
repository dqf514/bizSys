/** 合作方门户 API（独立认证，见 portalHttp.ts）。 */

import { portalBlob, portalDownload, portalRequest, setPortalToken } from './portalHttp'
import type {
  PortalBid,
  PortalBilling,
  PortalBranding,
  PortalContract,
  PortalEntrust,
  PortalHandover,
  PortalHostOption,
  PortalPartner,
  PortalProgress,
  PortalRegistration,
  PortalReport,
  PortalStaff,
  PortalTender,
  PortalTenderDetail,
  PortalVisit,
  PortalVisitDetail,
  PortalZoneOption,
} from './types'

export function portalRegister(data: {
  username: string
  password: string
  companyName: string
  contactName?: string
  phone?: string
  email?: string
  /** B2：supplier 供应商投标（默认）/ customer 客户自助下单 */
  companyType?: 'supplier' | 'customer'
}) {
  return portalRequest<PortalPartner>({ url: '/auth/register', method: 'post', data })
}

export async function portalLogin(username: string, password: string) {
  const data = await portalRequest<{
    access_token: string
    refresh_token?: string
    partner: PortalPartner
  }>({
    url: '/auth/login',
    method: 'post',
    data: { username, password },
  })
  setPortalToken(data.access_token, data.refresh_token)
  return data.partner
}

export function portalMe() {
  return portalRequest<PortalPartner>({ url: '/auth/me', method: 'get' })
}

export function portalLogout() {
  return portalRequest<void>({ url: '/auth/logout', method: 'post' })
}

/** 门户站点信息（公开） */
export function portalBranding() {
  return portalRequest<PortalBranding>({ url: '/branding', method: 'get' })
}

/** 账号信息（自助维护） */
export function portalAccount() {
  return portalRequest<PortalPartner>({ url: '/account', method: 'get' })
}

export function portalUpdateAccount(data: {
  companyName?: string
  contactName?: string
  phone?: string
  email?: string
}) {
  return portalRequest<PortalPartner>({ url: '/account', method: 'put', data })
}

export function portalChangePassword(data: { oldPassword: string; newPassword: string }) {
  return portalRequest<void>({ url: '/account/password', method: 'post', data })
}

export function listPortalTenders(params?: { page?: number; size?: number; q?: string }) {
  return portalRequest<{ items: PortalTender[]; total: number; page: number; size: number }>({
    url: '/tenders',
    method: 'get',
    params,
  })
}

export function portalTenderDetail(id: number) {
  return portalRequest<PortalTenderDetail>({ url: `/tenders/${id}`, method: 'get' })
}

export function portalRegisterTender(id: number, form: FormData) {
  return portalRequest<PortalRegistration>({ url: `/tenders/${id}/register`, method: 'post', data: form })
}

export function myPortalRegistrations() {
  return portalRequest<{ items: PortalRegistration[] }>({ url: '/registrations', method: 'get' })
}

export function portalSubmitBid(id: number, form: FormData) {
  return portalRequest<PortalBid>({ url: `/tenders/${id}/bid`, method: 'post', data: form })
}

export function myPortalBids() {
  return portalRequest<{ items: PortalBid[] }>({ url: '/bids', method: 'get' })
}

export function downloadMyRegistrationAttachment(regId: number) {
  return portalDownload(`/registrations/${regId}/attachment`)
}

export function downloadMyBidProposal(bidId: number) {
  return portalDownload(`/bids/${bidId}/proposal`)
}

/* ---------- B2 客户自助：在线委托 + 外来人员登记 ---------- */

export function portalRegisterCustomer(data: {
  username: string
  password: string
  companyName: string
  contactName?: string
  phone?: string
  email?: string
}) {
  return portalRegister({ ...data, companyType: 'customer' })
}

export function myPortalContracts() {
  return portalRequest<{ items: PortalContract[] }>({ url: '/contracts', method: 'get' })
}

export function myPortalEntrusts() {
  return portalRequest<{ items: PortalEntrust[] }>({ url: '/entrusts', method: 'get' })
}

export function portalCreateEntrust(data: Partial<PortalEntrust> & { items?: unknown[] }) {
  return portalRequest<PortalEntrust>({ url: '/entrusts', method: 'post', data })
}

export function portalCancelEntrust(id: number) {
  return portalRequest<PortalEntrust>({ url: `/entrusts/${id}/cancel`, method: 'post' })
}

export function myPortalStaffs() {
  return portalRequest<{ items: PortalStaff[] }>({ url: '/staff', method: 'get' })
}

export function portalRegisterStaff(data: Partial<PortalStaff>) {
  return portalRequest<PortalStaff>({ url: '/staff', method: 'post', data })
}

/* ---------- F6 访客预约（门户 → 内部审批 → 通行凭证 → 扫码签到） ---------- */

/** 被访人候选（公开，只含姓名/部门） */
export function listPortalHosts(params?: { q?: string }) {
  return portalRequest<{ items: PortalHostOption[] }>({ url: '/hosts', method: 'get', params })
}

/** 可申请区域（公开） */
export function listPortalZones() {
  return portalRequest<{ items: PortalZoneOption[] }>({ url: '/zones', method: 'get' })
}

/** 我的访客预约 */
export function myPortalVisits() {
  return portalRequest<{ items: PortalVisit[] }>({ url: '/visits', method: 'get' })
}

export function portalVisitDetail(id: number) {
  return portalRequest<PortalVisitDetail>({ url: `/visits/${id}`, method: 'get' })
}

/** 提交来访申请（进入内部审批流） */
export function portalCreateVisit(data: {
  visitorName: string
  visitorCompany?: string
  visitorType?: string
  idNo?: string
  phone?: string
  plateNo?: string
  hostUserId: number
  zoneIds?: number[]
  purpose?: string
  planStart?: string
  planEnd?: string
  escortNames?: string
  ndaSigned?: boolean
  remark?: string
}) {
  return portalRequest<PortalVisit>({ url: '/visits', method: 'post', data })
}

export function portalCancelVisit(id: number, remark = '') {
  return portalRequest<PortalVisit>({
    url: `/visits/${id}/cancel`,
    method: 'post',
    data: { remark },
  })
}

/** 通行凭证（含二维码载荷 code） */
export function portalVisitCredential(id: number) {
  return portalRequest<{
    credentialNo: string
    code: string
    expireAt: string
    zoneNames: string[]
  }>({ url: `/visits/${id}/credential`, method: 'get' })
}

/** 通行二维码（SVG，需带 token，故走 blob 通道） */
export function portalVisitQr(id: number) {
  return portalBlob(`/visits/${id}/credential/qr`)
}

export function portalVisitCheckIn(id: number, deviceId = '') {
  return portalRequest<PortalVisit>({
    url: `/visits/${id}/checkin`,
    method: 'post',
    data: { method: 'qrcode', deviceId },
  })
}

export function portalVisitCheckOut(id: number, deviceId = '') {
  return portalRequest<PortalVisit>({
    url: `/visits/${id}/checkout`,
    method: 'post',
    data: { method: 'qrcode', deviceId },
  })
}

/* ---------- F6 对外业务能力：进度 / 报告 / 对账 / 交接 ---------- */

/** 我的项目进度看板 */
export function portalProgress() {
  return portalRequest<PortalProgress>({ url: '/progress', method: 'get' })
}

/** 可查阅的正式报告 */
export function myPortalReports() {
  return portalRequest<{ items: PortalReport[] }>({ url: '/reports', method: 'get' })
}

/** 签发一次性下载码（可转发给同事代下载） */
export function portalIssueDownloadCode(reportId: number) {
  return portalRequest<{ reportId: number; code: string; expiresIn: number }>({
    url: `/reports/${reportId}/download-code`,
    method: 'post',
  })
}

/** 按一次性下载码下载报告 */
export function portalDownloadReport(reportId: number, code: string) {
  return portalDownload(`/reports/${reportId}/download`, { code })
}

/** 对账单 / 开票 / 回款 */
export function portalBilling() {
  return portalRequest<PortalBilling>({ url: '/billing', method: 'get' })
}

/** 样品 / 样车交接单 */
export function portalHandovers() {
  return portalRequest<{ items: PortalHandover[] }>({ url: '/handovers', method: 'get' })
}
