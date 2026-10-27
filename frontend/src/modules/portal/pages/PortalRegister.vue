<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage, type FormInstance } from 'element-plus'
import { portalRegister } from '@/api/portal'
import { useBrandingStore } from '@/stores/branding'

defineOptions({ name: 'PortalRegister' })

const { t } = useI18n()
const router = useRouter()
const branding = useBrandingStore()

const siteName = computed(() => branding.siteName || t('portal.portal.title'))

onMounted(() => void branding.load())

const formRef = ref<FormInstance>()
const loading = ref(false)
const form = reactive({
  username: '',
  password: '',
  passwordConfirm: '',
  companyName: '',
  contactName: '',
  phone: '',
  email: '',
})

const rules = {
  username: [
    { required: true, message: t('common.form.required') },
    { min: 4, max: 64, pattern: /^[a-zA-Z0-9_.-]+$/, message: '4-64', trigger: 'blur' },
  ],
  password: [{ required: true, min: 8, message: t('common.form.required'), trigger: 'blur' }],
  companyName: [{ required: true, min: 2, message: t('common.form.required'), trigger: 'blur' }],
}

async function doRegister() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  if (form.password !== form.passwordConfirm) {
    ElMessage.warning(t('portal.portal.passwordConfirm'))
    return
  }
  loading.value = true
  try {
    await portalRegister({
      username: form.username.trim(),
      password: form.password,
      companyName: form.companyName.trim(),
      contactName: form.contactName.trim(),
      phone: form.phone.trim(),
      email: form.email.trim(),
    })
    ElMessage.success(t('portal.portal.registerSuccess'))
    router.replace('/portal/login')
  } catch {
    /* portalHttp notifies */
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="portal-auth-page">
    <div class="portal-auth-card wide">
      <h1 class="portal-auth-title">{{ siteName }} · {{ t('portal.portal.register') }}</h1>
      <el-alert type="info" :closable="false" show-icon :title="t('portal.portal.registerFlowTip')" />
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="portal-auth-form">
        <el-form-item :label="t('portal.portal.username')" prop="username">
          <el-input v-model="form.username" :maxlength="64" />
        </el-form-item>
        <el-form-item :label="t('portal.portal.password')" prop="password">
          <el-input v-model="form.password" type="password" show-password :maxlength="64" />
        </el-form-item>
        <el-form-item :label="t('portal.portal.passwordConfirm')" prop="passwordConfirm">
          <el-input v-model="form.passwordConfirm" type="password" show-password :maxlength="64" />
        </el-form-item>
        <el-form-item :label="t('portal.portal.companyName')" prop="companyName">
          <el-input v-model="form.companyName" :maxlength="255" />
        </el-form-item>
        <el-form-item :label="t('portal.portal.contactName')">
          <el-input v-model="form.contactName" :maxlength="64" />
        </el-form-item>
        <el-form-item :label="t('portal.portal.phone')">
          <el-input v-model="form.phone" :maxlength="32" />
        </el-form-item>
        <el-form-item :label="t('portal.portal.email')">
          <el-input v-model="form.email" :maxlength="128" />
        </el-form-item>
        <el-button type="primary" size="large" class="portal-auth-btn" :loading="loading" @click="doRegister">
          {{ t('portal.portal.registerBtn') }}
        </el-button>
      </el-form>
      <div class="portal-auth-links">
        <el-button link type="primary" @click="router.push('/portal/login')">
          {{ t('portal.portal.hasAccount') }}
        </el-button>
        <el-button link @click="router.push('/portal/tenders')">{{ t('portal.portal.browseTenders') }}</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.portal-auth-page {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bs-color-bg-app);
  overflow: auto;
  padding: var(--bs-space-6) 0;
}

.portal-auth-card {
  width: 420px;
  padding: var(--bs-space-8);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-lg);
  background: var(--bs-color-bg-surface);
  box-shadow: var(--bs-shadow-elevation3);
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}

.portal-auth-card.wide {
  width: 480px;
}

.portal-auth-links {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

@media (max-width: 768px) {
  .portal-auth-card,
  .portal-auth-card.wide {
    width: calc(100vw - 2 * var(--bs-space-6));
    padding: var(--bs-space-5);
  }
}

.portal-auth-title {
  font-size: var(--bs-typography-font-size-xl);
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.portal-auth-form {
  display: flex;
  flex-direction: column;
}

.portal-auth-btn {
  width: 100%;
  margin-top: var(--bs-space-2);
}
</style>
