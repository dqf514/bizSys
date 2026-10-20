import { download, request } from './http'

export interface BackupSettings {
  enabled: boolean
  time: string
  retention: number
  dir: string
  mysqldumpAvailable: boolean
  dbBackend: string
}

export interface MaintenanceSettings {
  backup: BackupSettings
  showDemoAccounts: boolean
}

export interface BackupFile {
  name: string
  size: number
  kind: string
  tool: string
  createdAt: string
}

export interface PurgeResult {
  counts: Record<string, number>
  backup: BackupFile
}

export function getMaintenanceSettings() {
  return request<MaintenanceSettings>({ url: '/admin/maintenance/settings', method: 'get' })
}

export function updateMaintenanceSettings(data: {
  backup?: { enabled?: boolean; time?: string; retention?: number; dir?: string }
  showDemoAccounts?: boolean
}) {
  return request<MaintenanceSettings>({ url: '/admin/maintenance/settings', method: 'put', data })
}

export function runBackup() {
  return request<BackupFile>({ url: '/admin/maintenance/backup/run', method: 'post' })
}

export function listBackups() {
  return request<BackupFile[]>({ url: '/admin/maintenance/backups', method: 'get' })
}

export function downloadBackup(name: string) {
  return download({ url: `/admin/maintenance/backups/${encodeURIComponent(name)}/download`, method: 'get' }, name)
}

export function deleteBackup(name: string) {
  return request<null>({ url: `/admin/maintenance/backups/${encodeURIComponent(name)}`, method: 'delete' })
}

export function purgeData(data: { password: string; confirm: string; forceBackupSkip?: boolean }) {
  return request<PurgeResult>({ url: '/admin/maintenance/purge', method: 'post', data })
}
