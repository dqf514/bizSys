<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, type UploadRequestOptions } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { getSettings, updateSettings, uploadLogo, uploadFavicon, clearFavicon } from '@/api/settings'
import { useBrandingStore } from '@/stores/branding'

defineOptions({ name: 'SystemSettings' })

const { t } = useI18n()
const branding = useBrandingStore()

const loading = ref(false)
const savingBasic = ref(false)
const savingWecom = ref(false)
const logoStamp = ref(Date.now())
const faviconStamp = ref(Date.now())

const basic = reactive({ siteName: '', logoUrl: '', faviconUrl: '' })
const wecom = reactive({
  enabled: false,
  corpId: '',
  agentId: '',
  secret: '',
  secretSet: false,
  callbackUrl: '',
})

const logoSrc = computed(() => (basic.logoUrl ? `${basic.logoUrl}?v=${logoStamp.value}` : ''))
const faviconSrc = computed(() => (basic.faviconUrl ? `${basic.faviconUrl}?v=${faviconStamp.value}` : ''))
const callbackDisplay = computed(() => wecom.callbackUrl || `${window.location.origin}/login`)

const LOGO_EXTS = ['png', 'jpg', 'jpeg', 'svg', 'webp']
const LOGO_MAX_BYTES = 2 * 1024 * 1024
const FAVICON_EXTS = ['ico', 'png']
const FAVICON_MAX_BYTES = 1024 * 1024

async function load() {
  loading.value = true
  try {
    const data = await getSettings()
    basic.siteName = data.siteName
    basic.logoUrl = data.logoUrl
    basic.faviconUrl = data.faviconUrl
    Object.assign(wecom, {
      enabled: data.wecom.enabled,
      corpId: data.wecom.corpId,
      agentId: data.wecom.agentId,
      secret: '',
      secretSet: data.wecom.secretSet,
      callbackUrl: data.wecom.callbackUrl,
    })
  } catch {
    /* http notifies */
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())

async function saveBasic() {
  if (!basic.siteName.trim()) {
    ElMessage.warning(t('common.form.required'))
    return
  }
  savingBasic.value = true
  try {
    const data = await updateSettings({ siteName: basic.siteName.trim() })
    basic.siteName = data.siteName
    branding.apply({ siteName: data.siteName })
    ElMessage.success(t('common.message.saveSuccess'))
  } catch {
    /* http notifies */
  } finally {
    savingBasic.value = false
  }
}

async function saveWecom() {
  savingWecom.value = true
  try {
    const payload: Parameters<typeof updateSettings>[0] = {
      wecom: {
        enabled: wecom.enabled,
        corpId: wecom.corpId.trim(),
        agentId: wecom.agentId.trim(),
        callbackUrl: wecom.callbackUrl.trim(),
      },
    }
    if (wecom.secret.trim()) payload.wecom!.secret = wecom.secret.trim()
    const data = await updateSettings(payload)
    wecom.secret = ''
    wecom.secretSet = data.wecom.secretSet
    branding.apply({ wecomEnabled: data.wecom.enabled && data.wecom.secretSet })
    ElMessage.success(t('common.message.saveSuccess'))
  } catch {
    /* http notifies */
  } finally {
    savingWecom.value = false
  }
}

function checkLogo(file: File): boolean {
  const ext = file.name.includes('.') ? file.name.split('.').pop()!.toLowerCase() : ''
  if (!LOGO_EXTS.includes(ext)) {
    ElMessage.warning(t('settings.basic.logoTypeError'))
    return false
  }
  if (file.size > LOGO_MAX_BYTES) {
    ElMessage.warning(t('settings.basic.logoSizeError'))
    return false
  }
  return true
}

async function doUploadLogo(options: UploadRequestOptions) {
  try {
    const data = await uploadLogo(options.file as File)
    basic.logoUrl = data.logoUrl
    logoStamp.value = Date.now()
    branding.apply({ logoUrl: data.logoUrl })
    ElMessage.success(t('common.message.saveSuccess'))
  } catch {
    /* http notifies */
  }
}

function checkFavicon(file: File): boolean {
  const ext = file.name.includes('.') ? file.name.split('.').pop()!.toLowerCase() : ''
  if (!FAVICON_EXTS.includes(ext)) {
    ElMessage.warning(t('settings.basic.faviconTypeError'))
    return false
  }
  if (file.size > FAVICON_MAX_BYTES) {
    ElMessage.warning(t('settings.basic.faviconSizeError'))
    return false
  }
  return true
}

async function doUploadFavicon(options: UploadRequestOptions) {
  try {
    const data = await uploadFavicon(options.file as File)
    basic.faviconUrl = data.faviconUrl
    faviconStamp.value = Date.now()
    branding.apply({ faviconUrl: data.faviconUrl })
    ElMessage.success(t('common.message.saveSuccess'))
  } catch {
    /* http notifies */
  }
}

async function doClearFavicon() {
  try {
    await clearFavicon()
    basic.faviconUrl = ''
    branding.apply({ faviconUrl: '' })
    ElMessage.success(t('common.message.saveSuccess'))
  } catch {
    /* http notifies */
  }
}

async function copyCallback() {
  try {
    await navigator.clipboard.writeText(callbackDisplay.value)
    ElMessage.success(t('common.message.copySuccess'))
  } catch {
    ElMessage.warning(t('common.message.operationFailed'))
  }
}
</script>

<template>
  <div v-loading="loading" class="settings-page">
    <h2 class="page-title">{{ t('settings.title') }}</h2>

    <div class="settings-grid">
      <el-card class="settings-card" shadow="never">
      <template #header>
        <span class="card-title">{{ t('settings.basic.title') }}</span>
      </template>
      <el-form label-width="140px" class="settings-form">
        <el-form-item :label="t('settings.basic.siteName')" required>
          <el-input
            v-model="basic.siteName"
            :placeholder="t('settings.basic.siteNamePlaceholder')"
            maxlength="128"
            class="form-input"
          />
        </el-form-item>
        <el-form-item :label="t('settings.basic.logo')">
          <div class="logo-row">
            <div class="logo-preview">
              <img v-if="logoSrc" :src="logoSrc" :alt="t('settings.basic.logo')" class="logo-img" />
              <span v-else class="logo-empty">{{ t('settings.basic.logoEmpty') }}</span>
            </div>
            <el-upload :show-file-list="false" :before-upload="checkLogo" :http-request="doUploadLogo" accept=".png,.jpg,.jpeg,.svg,.webp">
              <el-button v-permission="'admin:setting:edit'" type="primary" plain>
                {{ basic.logoUrl ? t('settings.basic.changeLogo') : t('settings.basic.uploadLogo') }}
              </el-button>
            </el-upload>
          </div>
          <div class="form-tip">{{ t('settings.basic.logoTip') }}</div>
        </el-form-item>
        <el-form-item :label="t('settings.basic.favicon')">
          <div class="logo-row">
            <div class="favicon-preview">
              <img v-if="faviconSrc" :src="faviconSrc" :alt="t('settings.basic.favicon')" class="favicon-img" />
              <span v-else class="logo-empty">{{ t('settings.basic.faviconEmpty') }}</span>
            </div>
            <el-upload :show-file-list="false" :before-upload="checkFavicon" :http-request="doUploadFavicon" accept=".ico,.png">
              <el-button v-permission="'admin:setting:edit'" type="primary" plain>
                {{ basic.faviconUrl ? t('settings.basic.changeFavicon') : t('settings.basic.uploadFavicon') }}
              </el-button>
            </el-upload>
            <el-button v-if="basic.faviconUrl" v-permission="'admin:setting:edit'" @click="doClearFavicon">
              {{ t('settings.basic.clearFavicon') }}
            </el-button>
          </div>
          <div class="form-tip">{{ t('settings.basic.faviconTip') }}</div>
        </el-form-item>
        <el-form-item>
          <el-button v-permission="'admin:setting:edit'" type="primary" :loading="savingBasic" @click="saveBasic">
            {{ t('common.action.save') }}
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="settings-card" shadow="never">
      <template #header>
        <span class="card-title">{{ t('settings.wecom.title') }}</span>
      </template>
      <el-form label-width="140px" class="settings-form">
        <el-form-item :label="t('settings.wecom.enabled')">
          <el-switch v-model="wecom.enabled" />
          <span class="form-tip inline-tip">{{ t('settings.wecom.notEnabledTip') }}</span>
        </el-form-item>
        <el-form-item :label="t('settings.wecom.corpId')">
          <el-input v-model="wecom.corpId" :placeholder="t('settings.wecom.corpIdPlaceholder')" class="form-input" />
        </el-form-item>
        <el-form-item :label="t('settings.wecom.agentId')">
          <el-input v-model="wecom.agentId" :placeholder="t('settings.wecom.agentIdPlaceholder')" class="form-input" />
        </el-form-item>
        <el-form-item :label="t('settings.wecom.secret')">
          <el-input
            v-model="wecom.secret"
            type="password"
            show-password
            :placeholder="wecom.secretSet ? t('settings.wecom.secretSetPlaceholder') : t('settings.wecom.secretPlaceholder')"
            class="form-input"
          />
        </el-form-item>
        <el-form-item :label="t('settings.wecom.callbackUrl')">
          <div class="callback-row">
            <el-input :model-value="callbackDisplay" readonly class="form-input" />
            <el-button @click="copyCallback">{{ t('settings.wecom.copy') }}</el-button>
          </div>
          <div class="form-tip">{{ t('settings.wecom.callbackUrlTip') }}</div>
        </el-form-item>
        <el-form-item>
          <el-button v-permission="'admin:setting:edit'" type="primary" :loading="savingWecom" @click="saveWecom">
            {{ t('common.action.save') }}
          </el-button>
        </el-form-item>
      </el-form>

      <el-collapse class="guide-collapse">
        <el-collapse-item :title="t('settings.guide.title')" name="guide">
          <ol class="guide-steps">
            <li>{{ t('settings.guide.step1') }}</li>
            <li>{{ t('settings.guide.step2') }}</li>
            <li>{{ t('settings.guide.step3') }}</li>
            <li>{{ t('settings.guide.step4') }}</li>
            <li>{{ t('settings.guide.step5') }}</li>
          </ol>
        </el-collapse-item>
      </el-collapse>
    </el-card>
    </div>
  </div>
</template>

<style scoped>
.settings-page {
  height: 100%;
  overflow: auto;
  padding: var(--bs-space-4);
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-4);
}

/* full-width responsive grid: 2+ columns on wide screens, wraps on narrow */
.settings-grid {
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

.settings-card {
  min-width: 0;
}

.card-title {
  font-weight: 600;
}

.settings-form {
  max-width: 640px;
}

.form-input {
  max-width: 420px;
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

.logo-row {
  display: flex;
  align-items: center;
  gap: var(--bs-space-3);
}

.logo-preview {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 120px;
  height: 48px;
  border: 1px dashed var(--bs-color-border-default);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-fill-lighter);
  overflow: hidden;
}

.logo-img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.favicon-preview {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border: 1px dashed var(--bs-color-border-default);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-fill-lighter);
  overflow: hidden;
}

.favicon-img {
  width: 32px;
  height: 32px;
  object-fit: contain;
}

.logo-empty {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}

.callback-row {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  width: 100%;
}

.guide-collapse {
  margin-top: var(--bs-space-3);
  border-top: 1px solid var(--bs-color-border-subtle);
}

.guide-steps {
  margin: 0;
  padding-left: var(--bs-space-5);
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-sm);
  line-height: 2;
}
</style>
