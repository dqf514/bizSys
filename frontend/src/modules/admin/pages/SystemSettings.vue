<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, type UploadRequestOptions } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { getSettings, updateSettings, uploadLogo, uploadFavicon, clearFavicon, testMessaging } from '@/api/settings'
import { useBrandingStore } from '@/stores/branding'

defineOptions({ name: 'SystemSettings' })

const { t } = useI18n()
const branding = useBrandingStore()

const loading = ref(false)
const savingBasic = ref(false)
const savingWecom = ref(false)
const savingEmail = ref(false)
const savingSms = ref(false)
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

// ---- 消息通道 ----
const emailForm = reactive({
  host: '',
  port: 0,
  security: 'ssl',
  username: '',
  password: '',
  passwordSet: false,
  sender: '',
})
const smsForm = reactive({
  provider: '',
  aliyun: { accessKeyId: '', accessKeySecret: '', accessKeySecretSet: false, signName: '', templateCode: '' },
  tencent: { secretId: '', secretKey: '', secretKeySet: false, sdkAppId: '', signName: '', templateId: '' },
  huawei: { appKey: '', appSecret: '', appSecretSet: false, sender: '', templateId: '' },
  customHttp: { url: '', paramTemplate: '', authHeader: '', authHeaderSet: false },
})

const testDialog = ref(false)
const testChannel = ref<'sms' | 'email'>('email')
const testTarget = ref('')
const testSending = ref(false)

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
    Object.assign(emailForm, {
      host: data.messaging.email.host,
      port: data.messaging.email.port,
      security: data.messaging.email.security,
      username: data.messaging.email.username,
      password: '',
      passwordSet: data.messaging.email.passwordSet,
      sender: data.messaging.email.sender,
    })
    smsForm.provider = data.messaging.sms.provider
    Object.assign(smsForm.aliyun, { ...data.messaging.sms.aliyun, accessKeySecret: '' })
    Object.assign(smsForm.tencent, { ...data.messaging.sms.tencent, secretKey: '' })
    Object.assign(smsForm.huawei, { ...data.messaging.sms.huawei, appSecret: '' })
    Object.assign(smsForm.customHttp, { ...data.messaging.sms.customHttp, authHeader: '' })
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

async function saveEmail() {
  savingEmail.value = true
  try {
    const email: NonNullable<NonNullable<Parameters<typeof updateSettings>[0]['messaging']>['email']> = {
      host: emailForm.host.trim(),
      port: emailForm.port || 0,
      security: emailForm.security,
      username: emailForm.username.trim(),
      sender: emailForm.sender.trim(),
    }
    if (emailForm.password.trim()) email.password = emailForm.password.trim()
    const data = await updateSettings({ messaging: { email } })
    emailForm.password = ''
    emailForm.passwordSet = data.messaging.email.passwordSet
    ElMessage.success(t('common.message.saveSuccess'))
  } catch {
    /* http notifies */
  } finally {
    savingEmail.value = false
  }
}

async function saveSms() {
  savingSms.value = true
  try {
    const sms: NonNullable<NonNullable<Parameters<typeof updateSettings>[0]['messaging']>['sms']> = {
      provider: smsForm.provider,
      aliyun: {
        accessKeyId: smsForm.aliyun.accessKeyId.trim(),
        signName: smsForm.aliyun.signName.trim(),
        templateCode: smsForm.aliyun.templateCode.trim(),
      },
      tencent: {
        secretId: smsForm.tencent.secretId.trim(),
        sdkAppId: smsForm.tencent.sdkAppId.trim(),
        signName: smsForm.tencent.signName.trim(),
        templateId: smsForm.tencent.templateId.trim(),
      },
      huawei: {
        appKey: smsForm.huawei.appKey.trim(),
        sender: smsForm.huawei.sender.trim(),
        templateId: smsForm.huawei.templateId.trim(),
      },
      customHttp: {
        url: smsForm.customHttp.url.trim(),
        paramTemplate: smsForm.customHttp.paramTemplate.trim(),
      },
    }
    if (smsForm.aliyun.accessKeySecret.trim()) sms.aliyun!.accessKeySecret = smsForm.aliyun.accessKeySecret.trim()
    if (smsForm.tencent.secretKey.trim()) sms.tencent!.secretKey = smsForm.tencent.secretKey.trim()
    if (smsForm.huawei.appSecret.trim()) sms.huawei!.appSecret = smsForm.huawei.appSecret.trim()
    if (smsForm.customHttp.authHeader.trim()) sms.customHttp!.authHeader = smsForm.customHttp.authHeader.trim()
    const data = await updateSettings({ messaging: { sms } })
    smsForm.aliyun.accessKeySecret = ''
    smsForm.tencent.secretKey = ''
    smsForm.huawei.appSecret = ''
    smsForm.customHttp.authHeader = ''
    smsForm.aliyun.accessKeySecretSet = data.messaging.sms.aliyun.accessKeySecretSet
    smsForm.tencent.secretKeySet = data.messaging.sms.tencent.secretKeySet
    smsForm.huawei.appSecretSet = data.messaging.sms.huawei.appSecretSet
    smsForm.customHttp.authHeaderSet = data.messaging.sms.customHttp.authHeaderSet
    ElMessage.success(t('common.message.saveSuccess'))
  } catch {
    /* http notifies */
  } finally {
    savingSms.value = false
  }
}

function openMessagingTest(channel: 'sms' | 'email') {
  testChannel.value = channel
  testTarget.value = ''
  testDialog.value = true
}

async function doMessagingTest() {
  if (!testTarget.value.trim()) return
  testSending.value = true
  try {
    const r = await testMessaging(testChannel.value, testTarget.value.trim())
    testDialog.value = false
    if (r.debugCode) ElMessage.warning(t('settings.messaging.testSentDebug', { code: r.debugCode }))
    else ElMessage.success(t('settings.messaging.testSentReal'))
  } catch {
    /* http notifies */
  } finally {
    testSending.value = false
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

    <el-card class="settings-card" shadow="never">
      <template #header>
        <span class="card-title">{{ t('settings.messaging.title') }}</span>
      </template>
      <el-form label-width="140px" class="settings-form">
        <h3 class="section-title">{{ t('settings.messaging.emailTitle') }}</h3>
        <el-form-item :label="t('settings.messaging.host')">
          <el-input
            v-model="emailForm.host"
            :placeholder="t('settings.messaging.hostPlaceholder')"
            maxlength="128"
            class="form-input"
          />
        </el-form-item>
        <el-form-item :label="t('settings.messaging.port')">
          <el-input-number v-model="emailForm.port" :min="0" :max="65535" controls-position="right" />
          <span class="form-tip inline-tip">{{ t('settings.messaging.portTip') }}</span>
        </el-form-item>
        <el-form-item :label="t('settings.messaging.security')">
          <el-radio-group v-model="emailForm.security">
            <el-radio-button value="ssl">SSL</el-radio-button>
            <el-radio-button value="starttls">STARTTLS</el-radio-button>
            <el-radio-button value="none">None</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="t('settings.messaging.username')">
          <el-input v-model="emailForm.username" maxlength="128" class="form-input" />
        </el-form-item>
        <el-form-item :label="t('settings.messaging.password')">
          <el-input
            v-model="emailForm.password"
            type="password"
            show-password
            :placeholder="
              emailForm.passwordSet
                ? t('settings.messaging.secretSetPlaceholder')
                : t('settings.messaging.secretPlaceholder')
            "
            maxlength="128"
            class="form-input"
          />
        </el-form-item>
        <el-form-item :label="t('settings.messaging.sender')">
          <el-input
            v-model="emailForm.sender"
            :placeholder="t('settings.messaging.senderPlaceholder')"
            maxlength="128"
            class="form-input"
          />
        </el-form-item>
        <el-form-item>
          <el-button v-permission="'admin:setting:edit'" type="primary" :loading="savingEmail" @click="saveEmail">
            {{ t('common.action.save') }}
          </el-button>
          <el-button v-permission="'admin:setting:edit'" @click="openMessagingTest('email')">
            {{ t('settings.messaging.testSend') }}
          </el-button>
        </el-form-item>
      </el-form>

      <el-divider />

      <el-form label-width="140px" class="settings-form">
        <h3 class="section-title">{{ t('settings.messaging.smsTitle') }}</h3>
        <el-form-item :label="t('settings.messaging.provider')">
          <el-select v-model="smsForm.provider" class="form-input">
            <el-option value="" :label="t('settings.messaging.providerNone')" />
            <el-option value="aliyun" :label="t('settings.messaging.providerAliyun')" />
            <el-option value="tencent" :label="t('settings.messaging.providerTencent')" />
            <el-option value="huawei" :label="t('settings.messaging.providerHuawei')" />
            <el-option value="custom_http" :label="t('settings.messaging.providerCustom')" />
          </el-select>
        </el-form-item>

        <template v-if="smsForm.provider === 'aliyun'">
          <el-form-item :label="t('settings.messaging.accessKeyId')">
            <el-input v-model="smsForm.aliyun.accessKeyId" maxlength="128" class="form-input" />
          </el-form-item>
          <el-form-item :label="t('settings.messaging.accessKeySecret')">
            <el-input
              v-model="smsForm.aliyun.accessKeySecret"
              type="password"
              show-password
              :placeholder="
                smsForm.aliyun.accessKeySecretSet
                  ? t('settings.messaging.secretSetPlaceholder')
                  : t('settings.messaging.secretPlaceholder')
              "
              maxlength="128"
              class="form-input"
            />
          </el-form-item>
          <el-form-item :label="t('settings.messaging.signName')">
            <el-input v-model="smsForm.aliyun.signName" maxlength="64" class="form-input" />
          </el-form-item>
          <el-form-item :label="t('settings.messaging.templateCode')">
            <el-input v-model="smsForm.aliyun.templateCode" maxlength="64" class="form-input" />
          </el-form-item>
          <div class="form-tip provider-tip">{{ t('settings.messaging.providerPendingTip') }}</div>
        </template>

        <template v-else-if="smsForm.provider === 'tencent'">
          <el-form-item :label="t('settings.messaging.secretId')">
            <el-input v-model="smsForm.tencent.secretId" maxlength="128" class="form-input" />
          </el-form-item>
          <el-form-item :label="t('settings.messaging.secretKey')">
            <el-input
              v-model="smsForm.tencent.secretKey"
              type="password"
              show-password
              :placeholder="
                smsForm.tencent.secretKeySet
                  ? t('settings.messaging.secretSetPlaceholder')
                  : t('settings.messaging.secretPlaceholder')
              "
              maxlength="128"
              class="form-input"
            />
          </el-form-item>
          <el-form-item :label="t('settings.messaging.sdkAppId')">
            <el-input v-model="smsForm.tencent.sdkAppId" maxlength="64" class="form-input" />
          </el-form-item>
          <el-form-item :label="t('settings.messaging.signName')">
            <el-input v-model="smsForm.tencent.signName" maxlength="64" class="form-input" />
          </el-form-item>
          <el-form-item :label="t('settings.messaging.templateId')">
            <el-input v-model="smsForm.tencent.templateId" maxlength="64" class="form-input" />
          </el-form-item>
          <div class="form-tip provider-tip">{{ t('settings.messaging.providerPendingTip') }}</div>
        </template>

        <template v-else-if="smsForm.provider === 'huawei'">
          <el-form-item :label="t('settings.messaging.appKey')">
            <el-input v-model="smsForm.huawei.appKey" maxlength="128" class="form-input" />
          </el-form-item>
          <el-form-item :label="t('settings.messaging.appSecret')">
            <el-input
              v-model="smsForm.huawei.appSecret"
              type="password"
              show-password
              :placeholder="
                smsForm.huawei.appSecretSet
                  ? t('settings.messaging.secretSetPlaceholder')
                  : t('settings.messaging.secretPlaceholder')
              "
              maxlength="128"
              class="form-input"
            />
          </el-form-item>
          <el-form-item :label="t('settings.messaging.smsSender')">
            <el-input v-model="smsForm.huawei.sender" maxlength="64" class="form-input" />
          </el-form-item>
          <el-form-item :label="t('settings.messaging.templateId')">
            <el-input v-model="smsForm.huawei.templateId" maxlength="64" class="form-input" />
          </el-form-item>
          <div class="form-tip provider-tip">{{ t('settings.messaging.providerPendingTip') }}</div>
        </template>

        <template v-else-if="smsForm.provider === 'custom_http'">
          <el-form-item :label="t('settings.messaging.gatewayUrl')">
            <el-input
              v-model="smsForm.customHttp.url"
              :placeholder="t('settings.messaging.gatewayUrlPlaceholder')"
              maxlength="255"
              class="form-input"
            />
          </el-form-item>
          <el-form-item :label="t('settings.messaging.paramTemplate')">
            <el-input
              v-model="smsForm.customHttp.paramTemplate"
              type="textarea"
              :rows="2"
              maxlength="512"
              class="form-input"
            />
            <div class="form-tip">{{ t('settings.messaging.paramTemplateTip') }}</div>
          </el-form-item>
          <el-form-item :label="t('settings.messaging.authHeader')">
            <el-input
              v-model="smsForm.customHttp.authHeader"
              type="password"
              show-password
              :placeholder="
                smsForm.customHttp.authHeaderSet
                  ? t('settings.messaging.secretSetPlaceholder')
                  : t('settings.messaging.secretPlaceholder')
              "
              maxlength="255"
              class="form-input"
            />
          </el-form-item>
        </template>

        <div v-else class="form-tip provider-tip">{{ t('settings.messaging.notConfiguredTip') }}</div>

        <el-form-item>
          <el-button v-permission="'admin:setting:edit'" type="primary" :loading="savingSms" @click="saveSms">
            {{ t('common.action.save') }}
          </el-button>
          <el-button v-permission="'admin:setting:edit'" @click="openMessagingTest('sms')">
            {{ t('settings.messaging.testSend') }}
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
    </div>

    <!-- 消息通道测试发送 -->
    <el-dialog v-model="testDialog" :title="t('settings.messaging.testTitle')" width="420px" append-to-body>
      <el-form label-width="100px">
        <el-form-item
          :label="testChannel === 'email' ? t('settings.messaging.testTargetEmail') : t('settings.messaging.testTargetPhone')"
          required
        >
          <el-input v-model="testTarget" maxlength="128" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="testDialog = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="testSending" :disabled="!testTarget.trim()" @click="doMessagingTest">
          {{ t('settings.messaging.testSend') }}
        </el-button>
      </template>
    </el-dialog>
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

.section-title {
  margin: 0 0 var(--bs-space-3);
  font-size: var(--bs-typography-font-size-sm);
  font-weight: 600;
  color: var(--bs-color-fg-secondary);
}

.provider-tip {
  margin: 0 0 var(--bs-space-3) 140px;
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
