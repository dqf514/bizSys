<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { myPortalReports, portalDownloadReport, portalIssueDownloadCode } from '@/api/portal'
import type { PortalReport } from '@/api/types'

defineOptions({ name: 'PortalReports' })

const { t } = useI18n()

const reports = ref<PortalReport[]>([])
const loading = ref(false)
const codeVisible = ref(false)
const current = ref<PortalReport | null>(null)
const code = ref('')
const codeExpire = ref(0)

async function load() {
  loading.value = true
  try {
    const res = await myPortalReports()
    reports.value = res.items || []
  } finally {
    loading.value = false
  }
}

async function issueCode(r: PortalReport) {
  const res = await portalIssueDownloadCode(r.id)
  current.value = r
  code.value = res.code
  codeExpire.value = res.expiresIn
  codeVisible.value = true
}

async function downloadNow() {
  if (!current.value) return
  try {
    await portalDownloadReport(current.value.id, code.value)
    ElMessage.success(t('portal.portal.reports.downloadSuccess'))
    codeVisible.value = false
    await load()
  } catch {
    /* 拦截器已提示 */
  }
}

async function copyCode() {
  try {
    await navigator.clipboard.writeText(code.value)
    ElMessage.success(t('portal.portal.reports.codeCopied'))
  } catch {
    ElMessage.warning(code.value)
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="bs-page portal-reports">
    <div class="bs-page-header">
      <h2 class="bs-page-title">{{ t('portal.portal.reports.title') }}</h2>
    </div>

    <el-alert type="info" :closable="false" :title="t('portal.portal.reports.tip')" show-icon />

    <el-empty v-if="!loading && !reports.length" :description="t('portal.portal.empty')" />

    <div class="portal-report-list">
      <article v-for="r in reports" :key="r.id" class="portal-report-card">
        <div class="portal-report-main">
          <span class="portal-report-name">{{ r.fileName || r.reportNo }}</span>
          <span class="portal-report-no">{{ r.reportNo }}</span>
          <span class="portal-report-time">{{ r.sealedAt || r.createTime }}</span>
        </div>
        <el-button type="primary" plain @click="issueCode(r)">
          {{ t('portal.portal.reports.download') }}
        </el-button>
      </article>
    </div>

    <el-dialog v-model="codeVisible" :title="t('portal.portal.reports.codeTitle')" width="var(--bs-layout-dialog-xs)">
      <p class="portal-code-tip">{{ t('portal.portal.reports.codeTip') }}</p>
      <div class="portal-code-box">{{ code }}</div>
      <div class="portal-code-actions">
        <el-button @click="copyCode">{{ t('portal.portal.reports.copyCode') }}</el-button>
        <el-button type="primary" @click="downloadNow">{{ t('portal.portal.reports.downloadNow') }}</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.portal-reports {
  gap: var(--bs-space-4);
}

.portal-report-list {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}

.portal-report-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bs-space-3);
  padding: var(--bs-space-4);
  background: var(--bs-color-bg-surface);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
}

.portal-report-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 2px;
}

.portal-report-name {
  font-weight: 600;
  color: var(--bs-color-fg-default);
  word-break: break-all;
}

.portal-report-no,
.portal-report-time {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.portal-code-tip {
  margin: 0 0 var(--bs-space-3);
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-sm);
}

.portal-code-box {
  padding: var(--bs-space-3);
  background: var(--bs-color-fill-lighter);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  font-family: var(--bs-typography-font-family-mono);
  font-size: var(--bs-typography-font-size-lg);
  text-align: center;
  letter-spacing: 2px;
  word-break: break-all;
}

.portal-code-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--bs-space-2);
  margin-top: var(--bs-space-4);
}

@media (max-width: 767px) {
  .portal-report-card {
    flex-direction: column;
    align-items: stretch;
    padding: var(--bs-space-3);
  }
}
</style>
