<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import {
  deleteBackup,
  downloadBackup,
  getMaintenanceSettings,
  listBackups,
  purgeData,
  runBackup,
  updateMaintenanceSettings,
  type BackupFile,
} from '@/api/maintenance'
import { useAuthStore } from '@/stores/auth'
import { useBrandingStore } from '@/stores/branding'

defineOptions({ name: 'AdminMaintenance' })

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const branding = useBrandingStore()

const loading = ref(false)
const savingBackup = ref(false)
const savingDemo = ref(false)
const runningBackup = ref(false)
const backups = ref<BackupFile[]>([])

const backup = reactive({ enabled: false, time: '02:00', retention: 7, dir: '' })
const mysqldumpAvailable = ref(false)
const dbBackend = ref('')
const showDemoAccounts = ref(false)

const purgeVisible = ref(false)
const purging = ref(false)
const purgeForm = reactive({ password: '', confirm: '', forceBackupSkip: false })

async function load() {
  loading.value = true
  try {
    const data = await getMaintenanceSettings()
    Object.assign(backup, {
      enabled: data.backup.enabled,
      time: data.backup.time,
      retention: data.backup.retention,
      dir: data.backup.dir,
    })
    mysqldumpAvailable.value = data.backup.mysqldumpAvailable
    dbBackend.value = data.backup.dbBackend
    showDemoAccounts.value = data.showDemoAccounts
    backups.value = await listBackups()
  } catch {
    /* http notifies */
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())

async function refreshBackups() {
  try {
    backups.value = await listBackups()
  } catch {
    /* http notifies */
  }
}

async function saveBackupSettings() {
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(backup.time)) {
    ElMessage.warning(t('admin.maintenance.timeInvalid'))
    return
  }
  savingBackup.value = true
  try {
    const data = await updateMaintenanceSettings({
      backup: {
        enabled: backup.enabled,
        time: backup.time,
        retention: backup.retention,
        dir: backup.dir,
      },
    })
    Object.assign(backup, {
      enabled: data.backup.enabled,
      time: data.backup.time,
      retention: data.backup.retention,
      dir: data.backup.dir,
    })
    ElMessage.success(t('common.message.saveSuccess'))
  } catch {
    /* http notifies */
  } finally {
    savingBackup.value = false
  }
}

async function saveDemoSetting() {
  savingDemo.value = true
  try {
    const data = await updateMaintenanceSettings({ showDemoAccounts: showDemoAccounts.value })
    showDemoAccounts.value = data.showDemoAccounts
    branding.apply({ showDemoAccounts: data.showDemoAccounts })
    ElMessage.success(t('common.message.saveSuccess'))
  } catch {
    /* http notifies */
  } finally {
    savingDemo.value = false
  }
}

async function doRunBackup() {
  runningBackup.value = true
  try {
    const info = await runBackup()
    ElMessage.success(t('admin.maintenance.runDone', { name: info.name }))
    await refreshBackups()
  } catch {
    /* http notifies */
  } finally {
    runningBackup.value = false
  }
}

async function doDeleteBackup(row: BackupFile) {
  try {
    await ElMessageBox.confirm(t('admin.maintenance.deleteConfirm', { name: row.name }), t('common.action.confirm'), {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await deleteBackup(row.name)
    ElMessage.success(t('common.message.deleteSuccess'))
    await refreshBackups()
  } catch {
    /* http notifies */
  }
}

function formatSize(size: number): string {
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${size} B`
}

function openPurge() {
  purgeForm.password = ''
  purgeForm.confirm = ''
  purgeForm.forceBackupSkip = false
  purgeVisible.value = true
}

async function doPurge() {
  if (!purgeForm.password) {
    ElMessage.warning(t('admin.maintenance.purgePasswordRequired'))
    return
  }
  if (purgeForm.confirm !== 'CLEAR') {
    ElMessage.warning(t('admin.maintenance.purgeConfirmMismatch'))
    return
  }
  purging.value = true
  try {
    await purgeData({
      password: purgeForm.password,
      confirm: purgeForm.confirm,
      forceBackupSkip: purgeForm.forceBackupSkip,
    })
    purgeVisible.value = false
    ElMessage.success(t('admin.maintenance.purgeDone'))
    // 会话已被服务端吊销，直接清本地状态回登录页
    await auth.doLogout()
    router.replace('/login')
  } catch {
    /* http notifies */
  } finally {
    purging.value = false
  }
}
</script>

<template>
  <div v-loading="loading" class="maintenance-page">
    <h2 class="page-title">{{ t('admin.maintenance.title') }}</h2>

    <div class="maintenance-grid">
      <el-card class="maintenance-card" shadow="never">
        <template #header>
          <span class="card-title">{{ t('admin.maintenance.backupSettings') }}</span>
        </template>
        <el-form label-width="140px" class="maintenance-form">
          <el-form-item :label="t('admin.maintenance.enabled')">
            <el-switch v-model="backup.enabled" v-permission="'admin:backup:manage'" />
            <span class="form-tip inline-tip">{{ t('admin.maintenance.enabledTip') }}</span>
          </el-form-item>
          <el-form-item :label="t('admin.maintenance.time')">
            <el-input v-model="backup.time" placeholder="02:00" class="time-input" maxlength="5" />
          </el-form-item>
          <el-form-item :label="t('admin.maintenance.retention')">
            <el-input-number v-model="backup.retention" :min="1" :max="90" />
            <span class="form-tip inline-tip">{{ t('admin.maintenance.retentionTip') }}</span>
          </el-form-item>
          <el-form-item :label="t('admin.maintenance.dir')">
            <el-input v-model="backup.dir" :placeholder="t('admin.maintenance.dirPlaceholder')" class="form-input" />
          </el-form-item>
          <el-form-item :label="t('admin.maintenance.tool')">
            <el-tag v-if="dbBackend === 'sqlite'" type="info">{{ t('admin.maintenance.toolSqlite') }}</el-tag>
            <el-tag v-else-if="mysqldumpAvailable" type="success">{{ t('admin.maintenance.toolMysqldump') }}</el-tag>
            <el-tag v-else type="warning">{{ t('admin.maintenance.toolBuiltin') }}</el-tag>
            <span v-if="dbBackend !== 'sqlite' && !mysqldumpAvailable" class="form-tip inline-tip">
              {{ t('admin.maintenance.toolUnavailable') }}
            </span>
          </el-form-item>
          <el-form-item>
            <el-button
              v-permission="'admin:backup:manage'"
              type="primary"
              :loading="savingBackup"
              @click="saveBackupSettings"
            >
              {{ t('common.action.save') }}
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <el-card class="maintenance-card" shadow="never">
        <template #header>
          <div class="card-header-row">
            <span class="card-title">{{ t('admin.maintenance.list') }}</span>
            <el-button
              v-permission="'admin:backup:manage'"
              type="primary"
              plain
              :loading="runningBackup"
              @click="doRunBackup"
            >
              {{ t('admin.maintenance.runNow') }}
            </el-button>
          </div>
        </template>
        <el-table :data="backups" size="small" class="backup-table">
          <el-table-column prop="name" :label="t('admin.maintenance.fileName')" min-width="240" show-overflow-tooltip />
          <el-table-column :label="t('admin.maintenance.size')" width="90">
            <template #default="{ row }">{{ formatSize(row.size) }}</template>
          </el-table-column>
          <el-table-column prop="createdAt" :label="t('admin.maintenance.createdAt')" width="160" />
          <el-table-column :label="t('admin.maintenance.kind')" width="90">
            <template #default="{ row }">
              {{ row.kind === 'auto' ? t('admin.maintenance.kindAuto') : t('admin.maintenance.kindManual') }}
            </template>
          </el-table-column>
          <el-table-column :label="t('common.action.operate')" width="150" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="downloadBackup(row.name)">
                {{ t('common.action.download') }}
              </el-button>
              <el-button v-permission="'admin:backup:manage'" link type="danger" @click="doDeleteBackup(row)">
                {{ t('common.action.delete') }}
              </el-button>
            </template>
          </el-table-column>
          <template #empty>{{ t('admin.maintenance.empty') }}</template>
        </el-table>
      </el-card>

      <el-card class="maintenance-card" shadow="never">
        <template #header>
          <span class="card-title">{{ t('admin.maintenance.debug') }}</span>
        </template>
        <el-form label-width="140px" class="maintenance-form">
          <el-form-item :label="t('admin.maintenance.showDemoAccounts')">
            <el-switch v-model="showDemoAccounts" v-permission="'admin:backup:manage'" />
            <span class="form-tip inline-tip">{{ t('admin.maintenance.showDemoTip') }}</span>
          </el-form-item>
          <el-form-item>
            <el-button
              v-permission="'admin:backup:manage'"
              type="primary"
              :loading="savingDemo"
              @click="saveDemoSetting"
            >
              {{ t('common.action.save') }}
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <el-card class="maintenance-card danger-card" shadow="never">
        <template #header>
          <span class="card-title danger-title">{{ t('admin.maintenance.danger') }}</span>
        </template>
        <p class="danger-desc">{{ t('admin.maintenance.dangerDesc') }}</p>
        <el-button v-permission="'admin:maintenance:purge'" type="danger" @click="openPurge">
          {{ t('admin.maintenance.purgeBtn') }}
        </el-button>
      </el-card>
    </div>

    <el-dialog v-model="purgeVisible" :title="t('admin.maintenance.purgeDialogTitle')" width="480px">
      <el-alert type="error" :closable="false" class="purge-alert">
        <p>{{ t('admin.maintenance.purgeWarn1') }}</p>
        <p>{{ t('admin.maintenance.purgeWarn2') }}</p>
        <p>{{ t('admin.maintenance.purgeWarn3') }}</p>
      </el-alert>
      <el-form label-width="110px" class="purge-form">
        <el-form-item :label="t('admin.maintenance.purgePassword')" required>
          <el-input v-model="purgeForm.password" type="password" show-password />
        </el-form-item>
        <el-form-item :label="t('admin.maintenance.purgeConfirm')" required>
          <el-input v-model="purgeForm.confirm" placeholder="CLEAR" />
          <div class="form-tip">{{ t('admin.maintenance.purgeConfirmTip') }}</div>
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="purgeForm.forceBackupSkip">{{ t('admin.maintenance.forceBackupSkip') }}</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="purgeVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="danger" :loading="purging" @click="doPurge">
          {{ t('admin.maintenance.purgeConfirmBtn') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.maintenance-page {
  height: 100%;
  overflow: auto;
  padding: var(--bs-space-4);
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-4);
}

.maintenance-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(480px, 100%), 1fr));
  gap: var(--bs-space-4);
  align-items: start;
}

.page-title {
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.maintenance-card {
  min-width: 0;
}

.card-title {
  font-weight: 600;
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.maintenance-form {
  max-width: 640px;
}

.form-input {
  max-width: 420px;
}

.time-input {
  max-width: 120px;
}

.form-tip {
  width: 100%;
  margin-top: 4px;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}

.inline-tip {
  width: auto;
  margin-top: 0;
  margin-left: var(--bs-space-2);
}

.backup-table {
  width: 100%;
}

.danger-card {
  border-color: var(--bs-color-danger-border, var(--el-color-danger-light-5));
}

.danger-title {
  color: var(--el-color-danger);
}

.danger-desc {
  margin: 0 0 var(--bs-space-3);
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-sm);
  line-height: 1.8;
  white-space: pre-line;
}

.purge-alert {
  margin-bottom: var(--bs-space-4);
}

.purge-alert p {
  margin: 0;
  line-height: 1.8;
}

.purge-form {
  margin-top: var(--bs-space-2);
}
</style>
