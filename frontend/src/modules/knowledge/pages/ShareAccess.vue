<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import {
  getPublicShareLink,
  listPublicShareDocuments,
  publicShareRawUrl,
  sendPublicShareCode,
  uploadPublicShareFile,
  verifyPublicShareCode,
} from '@/api/knowledge'
import type { PublicShareDocument, PublicShareInfo } from '@/api/types'

defineOptions({ name: 'ShareAccess' })

const { t } = useI18n()
const route = useRoute()

const token = computed(() => String(route.params.token ?? ''))

const info = ref<PublicShareInfo | null>(null)
const docs = ref<PublicShareDocument[]>([])
const loading = ref(false)
const access = ref('')
const verified = ref(false)

const phone = ref('')
const code = ref('')
const sending = ref(false)
const verifying = ref(false)
const uploading = ref(false)
const uploadFile = ref<File | null>(null)

const expired = computed(() => info.value?.status === 'expired')
const closed = computed(() => info.value?.status === 'closed')
const needVerify = computed(() => Boolean(info.value?.requirePhone) && !verified.value)
const canUpload = computed(() => info.value?.perm === 'upload' || info.value?.perm === 'edit')

async function loadInfo() {
  loading.value = true
  try {
    info.value = await getPublicShareLink(token.value)
  } catch {
    info.value = { title: '', perm: 'read', requirePhone: false, status: 'expired', remark: '', expireAt: '' }
  } finally {
    loading.value = false
  }
}

async function loadDocs() {
  try {
    const data = await listPublicShareDocuments(token.value, access.value)
    docs.value = data.items ?? []
  } catch {
    docs.value = []
  }
}

onMounted(async () => {
  await loadInfo()
  if (info.value && info.value.status === 'active' && !info.value.requirePhone) {
    verified.value = true
    await loadDocs()
  }
})

async function sendCode() {
  if (!/^1\d{10}$/.test(phone.value.trim())) {
    ElMessage.warning(t('knowledge.share.phone'))
    return
  }
  sending.value = true
  try {
    const res = await sendPublicShareCode(token.value, phone.value.trim())
    ElMessage.success(t('knowledge.share.codeSent'))
    if (res.debugCode) {
      code.value = res.debugCode
      ElMessage.info(res.debugCode)
    }
  } catch {
    /* http 层已提示 */
  } finally {
    sending.value = false
  }
}

async function verify() {
  verifying.value = true
  try {
    const res = await verifyPublicShareCode(token.value, phone.value.trim(), code.value.trim())
    access.value = res.token
    verified.value = true
    ElMessage.success(t('knowledge.share.verified'))
    await loadDocs()
  } catch {
    /* http 层已提示 */
  } finally {
    verifying.value = false
  }
}

function onFileChange(file: { raw?: File }) {
  uploadFile.value = file.raw ?? null
}

async function doUpload() {
  if (!uploadFile.value) return
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', uploadFile.value)
    await uploadPublicShareFile(token.value, access.value, fd)
    ElMessage.success(t('knowledge.share.uploadDone'))
    uploadFile.value = null
    await loadDocs()
  } catch {
    /* http 层已提示 */
  } finally {
    uploading.value = false
  }
}

function download(doc: PublicShareDocument) {
  window.open(publicShareRawUrl(token.value, doc.id, access.value), '_blank')
}

function fmtSize(n: number) {
  if (!n) return '-'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}
</script>

<template>
  <div class="share-page" v-loading="loading">
    <div class="share-card">
      <h1 class="share-title">{{ info?.title || t('knowledge.share.title') }}</h1>
      <p v-if="info?.remark" class="share-remark">{{ info.remark }}</p>
      <p v-if="info?.expireAt" class="share-expire">{{ t('knowledge.share.expireAt', { time: info.expireAt }) }}</p>

      <el-alert
        v-if="expired"
        :title="t('knowledge.share.expired')"
        type="warning"
        :closable="false"
        show-icon
      />
      <el-alert v-else-if="closed" :title="t('knowledge.share.closed')" type="error" :closable="false" show-icon />

      <template v-else-if="needVerify">
        <el-form label-position="top" class="share-form">
          <el-form-item :label="t('knowledge.share.phone')">
            <el-input v-model="phone" inputmode="tel" maxlength="11" placeholder="13800000000" />
          </el-form-item>
          <el-form-item :label="t('knowledge.share.code')">
            <div class="share-code-row">
              <el-input v-model="code" inputmode="numeric" maxlength="6" class="share-code-input" />
              <el-button :loading="sending" @click="sendCode()">{{ t('knowledge.share.sendCode') }}</el-button>
            </div>
            <div class="share-tip">{{ t('knowledge.share.codeSentTip') }}</div>
          </el-form-item>
          <el-button type="primary" :loading="verifying" @click="verify()">
            {{ t('knowledge.share.verify') }}
          </el-button>
        </el-form>
      </template>

      <template v-else>
        <ul v-if="docs.length" class="share-list">
          <li v-for="d in docs" :key="d.id" class="share-item">
            <div class="share-item-main">
              <div class="share-item-name">{{ d.title }}</div>
              <div class="share-item-meta">
                {{ d.ext || '-' }} · {{ fmtSize(d.size) }} · v{{ d.version }} · {{ d.updateTime }}
              </div>
            </div>
            <el-button size="small" @click="download(d)">{{ t('knowledge.share.downloadFile') }}</el-button>
          </li>
        </ul>
        <el-empty v-else :description="t('knowledge.share.noDocs')" />

        <div v-if="canUpload" class="share-upload">
          <el-upload :auto-upload="false" :show-file-list="true" :limit="1" :on-change="onFileChange">
            <el-button>{{ t('knowledge.share.uploadFile') }}</el-button>
          </el-upload>
          <el-button
            type="primary"
            size="small"
            :loading="uploading"
            :disabled="!uploadFile"
            style="margin-top: 8px"
            @click="doUpload()"
          >
            {{ t('common.action.submit') }}
          </el-button>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.share-page {
  min-height: 100vh;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: var(--bs-space-6) var(--bs-space-4);
  background: var(--bs-color-bg-app);
}

.share-card {
  width: 100%;
  max-width: 720px;
  background: var(--bs-color-bg-surface);
  border-radius: var(--bs-radius-lg);
  padding: var(--bs-space-6);
  box-shadow: var(--bs-shadow-elevation1);
}

.share-title {
  margin: 0 0 var(--bs-space-2);
  font-size: var(--bs-typography-font-size-xl);
}

.share-remark {
  margin: 0 0 var(--bs-space-1);
  color: var(--bs-color-fg-secondary);
}

.share-expire {
  margin: 0 0 var(--bs-space-3);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.share-form {
  margin-top: var(--bs-space-4);
}

.share-code-row {
  display: flex;
  gap: var(--bs-space-2);
  width: 100%;
}

.share-code-input {
  flex: 1 1 auto;
}

.share-tip {
  margin-top: var(--bs-space-1);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}

.share-list {
  list-style: none;
  margin: var(--bs-space-3) 0 0;
  padding: 0;
}

.share-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bs-space-3);
  padding: var(--bs-space-3) 0;
  border-bottom: 1px solid var(--bs-color-border-subtle);
}

.share-item-name {
  font-weight: 500;
}

.share-item-meta {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
  margin-top: 2px;
}

.share-upload {
  margin-top: var(--bs-space-4);
  padding-top: var(--bs-space-3);
  border-top: 1px solid var(--bs-color-border-subtle);
}
</style>
