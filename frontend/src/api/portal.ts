/** 合作方门户 API（独立认证，见 portalHttp.ts）。 */

import { portalDownload, portalRequest, setPortalToken } from './portalHttp'
import type {
  PortalBid,
  PortalContract,
  PortalEntrust,
  PortalPartner,
  PortalRegistration,
  PortalStaff,
  PortalTender,
  PortalTenderDetail,
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
  const data = await portalRequest<{ access_token: string; partner: PortalPartner }>({
    url: '/auth/login',
    method: 'post',
    data: { username, password },
  })
  setPortalToken(data.access_token)
  return data.partner
}

export function portalMe() {
  return portalRequest<PortalPartner>({ url: '/auth/me', method: 'get' })
}

export function portalLogout() {
  return portalRequest<void>({ url: '/auth/logout', method: 'post' })
}

export function listPortalTenders() {
  return portalRequest<{ items: PortalTender[] }>({ url: '/tenders', method: 'get' })
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
