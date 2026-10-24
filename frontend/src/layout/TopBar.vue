<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox, ElIcon, ElMessage, ElPopover } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import {
  Fold,
  Expand,
  Search,
  Sunny,
  Moon,
  User,
  SwitchButton,
  Lock,
  Odometer,
  Star,
  StarFilled,
  Brush,
} from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useBrandingStore } from '@/stores/branding'
import { useThemeStore, ACCENTS, type Density, type ThemeMode } from '@/stores/theme'
import { changePassword as changePasswordApi } from '@/api/auth'
import { useShortcuts } from '@/composables/useShortcuts'
import type { Locale } from '@/i18n'
import NotifyBell from './NotifyBell.vue'

defineOptions({ name: 'TopBar' })

defineProps<{ collapsed: boolean }>()
const emit = defineEmits<{
  (e: 'toggle-nav'): void
  (e: 'open-command'): void
}>()

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const branding = useBrandingStore()
const theme = useThemeStore()
const { t } = useI18n()
const { isEligible, isFavorite, toggleFavorite } = useShortcuts()
const accountVisible = ref(false)

const brandText = computed(() => branding.siteName || t('common.app.short'))

onMounted(() => void branding.load())

const breadcrumbs = computed(() => {
  const matched = route.matched.filter((r) => r.meta?.titleKey || r.meta?.title)
  return matched.map((r) => ({
    path: r.path,
    title: r.meta?.titleKey ? t(String(r.meta.titleKey)) : String(r.meta?.title ?? ''),
  }))
})

const themeModes: { value: ThemeMode; labelKey: string }[] = [
  { value: 'light', labelKey: 'common.theme.light' },
  { value: 'dark', labelKey: 'common.theme.dark' },
  { value: 'brand-smvic', labelKey: 'common.theme.brand' },
]

const densities: { value: Density; labelKey: string }[] = [
  { value: 'comfortable', labelKey: 'common.theme.comfortable' },
  { value: 'compact', labelKey: 'common.theme.compact' },
]

const locales: { value: Locale; labelKey: string }[] = [
  { value: 'zh-CN', labelKey: 'common.lang.zhCN' },
  { value: 'en-US', labelKey: 'common.lang.enUS' },
]

function closeAccount() {
  accountVisible.value = false
}

function openProfile() {
  closeAccount()
  router.push('/profile')
}

function openChangePassword() {
  closeAccount()
  changePassword()
}

async function doLogout() {
  closeAccount()
  try {
    await ElMessageBox.confirm(t('auth.user.logoutConfirm'), t('common.action.confirm'), {
      type: 'warning',
    })
  } catch {
    return
  }
  await auth.doLogout()
  router.push('/login')
}

const pwdVisible = ref(false)
const pwdFormRef = ref<FormInstance>()
const pwdSaving = ref(false)
const pwdForm = reactive({ oldPassword: '', newPassword: '', confirmPassword: '' })

const pwdRules = computed<FormRules>(() => ({
  oldPassword: [{ required: true, message: t('common.form.required'), trigger: 'blur' }],
  newPassword: [{ required: true, message: t('common.form.required'), trigger: 'blur' }],
  confirmPassword: [
    { required: true, message: t('common.form.required'), trigger: 'blur' },
    {
      validator: (_rule, value: string, cb) =>
        value === pwdForm.newPassword ? cb() : cb(new Error(t('auth.user.passwordMismatch'))),
      trigger: 'blur',
    },
  ],
}))

function changePassword() {
  pwdForm.oldPassword = ''
  pwdForm.newPassword = ''
  pwdForm.confirmPassword = ''
  pwdVisible.value = true
}

async function submitPassword() {
  if (!pwdFormRef.value) return
  const ok = await pwdFormRef.value.validate().catch(() => false)
  if (!ok) return
  pwdSaving.value = true
  try {
    await changePasswordApi(pwdForm.oldPassword, pwdForm.newPassword)
    pwdVisible.value = false
    ElMessage.success(t('auth.user.changeSuccess'))
    try {
      await ElMessageBox.confirm(t('auth.user.reloginTip'), t('common.action.confirm'), {
        confirmButtonText: t('auth.user.relogin'),
        cancelButtonText: t('auth.user.reloginLater'),
        type: 'success',
      })
      await auth.doLogout()
      router.push('/login')
    } catch {
      /* stay logged in */
    }
  } catch {
    /* http notifies */
  } finally {
    pwdSaving.value = false
  }
}
</script>

<template>
  <div class="topbar">
    <button class="icon-btn" type="button" :title="t('common.action.collapse')" @click="emit('toggle-nav')">
      <ElIcon :size="16">
        <Fold v-if="!collapsed" />
        <Expand v-else />
      </ElIcon>
    </button>

    <div class="brand">
      <img v-if="branding.logoUrl" :src="branding.logoUrl" :alt="brandText" class="brand-logo" />
      <ElIcon v-else :size="18" class="brand-icon"><Odometer /></ElIcon>
      <span class="brand-text">{{ brandText }}</span>
    </div>

    <el-breadcrumb separator="/" class="crumb">
      <el-breadcrumb-item v-for="(item, i) in breadcrumbs" :key="i" :to="i < breadcrumbs.length - 1 ? { path: item.path } : undefined">
        {{ item.title }}
      </el-breadcrumb-item>
    </el-breadcrumb>

    <div class="spacer" />

    <button
      v-if="isEligible"
      class="icon-btn star-btn"
      :class="{ favored: isFavorite }"
      type="button"
      :title="isFavorite ? t('common.shortcut.unfavorite') : t('common.shortcut.favorite')"
      @click="toggleFavorite"
    >
      <ElIcon :size="16">
        <StarFilled v-if="isFavorite" />
        <Star v-else />
      </ElIcon>
    </button>

    <button class="cmd-trigger" type="button" @click="emit('open-command')">
      <ElIcon :size="14"><Search /></ElIcon>
      <span>{{ t('common.command.placeholder') }}</span>
      <kbd>Ctrl K</kbd>
    </button>

    <div class="actions">
      <NotifyBell />

      <ElPopover
        v-model:visible="accountVisible"
        trigger="click"
        placement="bottom-end"
        :width="300"
        popper-class="account-pop"
      >
        <template #reference>
          <button class="account-btn" type="button">
            <span class="avatar">
              <img v-if="auth.user?.avatarUrl" :src="auth.user.avatarUrl" class="avatar-img" alt="" />
              <template v-else>{{ (auth.user?.name || auth.user?.username || '?').slice(0, 1) }}</template>
            </span>
            <span class="account-name">{{ auth.user?.name || auth.user?.username }}</span>
          </button>
        </template>

        <div class="account-panel">
          <div class="account-head">
            <span class="avatar avatar-lg">
              <img v-if="auth.user?.avatarUrl" :src="auth.user.avatarUrl" class="avatar-img" alt="" />
              <template v-else>{{ (auth.user?.name || auth.user?.username || '?').slice(0, 1) }}</template>
            </span>
            <div class="account-meta">
              <div class="account-display">{{ auth.user?.name || auth.user?.username }}</div>
              <div class="account-sub">{{ auth.user?.deptName || auth.user?.username }}</div>
            </div>
          </div>

          <button class="panel-item" type="button" @click="openProfile">
            <ElIcon><User /></ElIcon>{{ t('auth.user.profile') }}
          </button>
          <button class="panel-item" type="button" @click="openChangePassword">
            <ElIcon><Lock /></ElIcon>{{ t('auth.user.changePassword') }}
          </button>

          <div class="panel-divider" />

          <div class="panel-section">
            <div class="panel-label">
              <ElIcon><Brush /></ElIcon>{{ t('common.theme.appearance') }}
            </div>
            <div class="seg-row">
              <button
                v-for="m in themeModes"
                :key="m.value"
                type="button"
                class="seg-btn"
                :class="{ active: theme.theme === m.value }"
                @click="theme.setTheme(m.value)"
              >
                <ElIcon v-if="m.value === 'light'"><Sunny /></ElIcon>
                <ElIcon v-else-if="m.value === 'dark'"><Moon /></ElIcon>
                {{ t(m.labelKey) }}
              </button>
            </div>
            <div class="accent-row">
              <button
                v-for="a in ACCENTS"
                :key="a"
                type="button"
                class="accent-swatch-btn"
                :class="[`accent-${a}`, { active: theme.accent === a }]"
                :title="a"
                @click="theme.setAccent(a)"
              />
            </div>
            <div class="seg-row">
              <button
                v-for="d in densities"
                :key="d.value"
                type="button"
                class="seg-btn"
                :class="{ active: theme.density === d.value }"
                @click="theme.setDensity(d.value)"
              >
                {{ t(d.labelKey) }}
              </button>
            </div>
          </div>

          <div class="panel-section">
            <div class="panel-label">{{ t('common.lang.switch') }}</div>
            <div class="seg-row">
              <button
                v-for="l in locales"
                :key="l.value"
                type="button"
                class="seg-btn"
                :class="{ active: theme.locale === l.value }"
                @click="theme.setAppLocale(l.value)"
              >
                {{ t(l.labelKey) }}
              </button>
            </div>
          </div>

          <div class="panel-divider" />

          <button class="panel-item danger" type="button" @click="doLogout">
            <ElIcon><SwitchButton /></ElIcon>{{ t('auth.user.logout') }}
          </button>
        </div>
      </ElPopover>
    </div>

    <el-dialog v-model="pwdVisible" :title="t('auth.user.changePassword')" width="420px" append-to-body>
      <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="110px">
        <el-form-item :label="t('auth.user.oldPassword')" prop="oldPassword">
          <el-input v-model="pwdForm.oldPassword" type="password" show-password />
        </el-form-item>
        <el-form-item :label="t('auth.user.newPassword')" prop="newPassword">
          <el-input v-model="pwdForm.newPassword" type="password" show-password />
        </el-form-item>
        <el-form-item :label="t('auth.user.confirmPassword')" prop="confirmPassword">
          <el-input v-model="pwdForm.confirmPassword" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwdVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="pwdSaving" @click="submitPassword">
          {{ t('common.action.save') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.topbar {
  height: 100%;
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  padding: 0 var(--bs-space-3);
}

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: var(--bs-radius-sm);
  background: transparent;
  color: var(--bs-color-fg-secondary);
  cursor: pointer;
}

.icon-btn:hover {
  background: var(--bs-color-fill-hover);
  color: var(--bs-color-fg-default);
}

.star-btn.favored,
.star-btn.favored:hover {
  color: var(--bs-color-primary);
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--bs-space-1);
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.brand-icon {
  color: var(--bs-color-primary);
}

.brand-logo {
  max-width: 24px;
  max-height: 24px;
  object-fit: contain;
}

.crumb {
  margin-left: var(--bs-space-2);
}

.spacer {
  flex: 1;
}

.cmd-trigger {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  height: 28px;
  min-width: 220px;
  padding: 0 var(--bs-space-2);
  border: 1px solid var(--bs-color-border-default);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-fill-lighter);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
  cursor: pointer;
}

.cmd-trigger kbd {
  margin-left: auto;
  padding: 0 4px;
  border: 1px solid var(--bs-color-border-default);
  border-radius: var(--bs-radius-sm);
  background: var(--bs-color-bg-surface);
  font-size: 10px;
}

.actions {
  display: flex;
  align-items: center;
  gap: var(--bs-space-1);
}

.account-btn {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  height: 32px;
  padding: 0 var(--bs-space-2);
  border: none;
  border-radius: var(--bs-radius-md);
  background: transparent;
  color: var(--bs-color-fg-default);
  cursor: pointer;
}

.account-btn:hover {
  background: var(--bs-color-fill-hover);
}

.avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: var(--bs-radius-full);
  background: var(--bs-color-brand-primary-soft);
  color: var(--bs-color-primary);
  font-size: var(--bs-typography-font-size-xs);
  font-weight: 600;
  overflow: hidden;
}

.avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar-lg {
  width: 36px;
  height: 36px;
  font-size: var(--bs-typography-font-size-base);
}

.account-name {
  font-size: var(--bs-typography-font-size-sm);
}

.account-panel {
  display: flex;
  flex-direction: column;
}

.account-head {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  padding: var(--bs-space-2);
}

.account-meta {
  min-width: 0;
}

.account-display {
  font-weight: 600;
  color: var(--bs-color-fg-default);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.account-sub {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.panel-item {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  width: 100%;
  padding: var(--bs-space-2);
  border: none;
  border-radius: var(--bs-radius-sm);
  background: transparent;
  color: var(--bs-color-fg-default);
  font-size: var(--bs-typography-font-size-sm);
  cursor: pointer;
  text-align: left;
}

.panel-item:hover {
  background: var(--bs-color-fill-hover);
}

.panel-item.danger {
  color: var(--bs-color-semantic-danger);
}

.panel-divider {
  height: 1px;
  margin: var(--bs-space-1) 0;
  background: var(--bs-color-border-subtle);
}

.panel-section {
  padding: var(--bs-space-1) var(--bs-space-2) var(--bs-space-2);
}

.panel-label {
  display: flex;
  align-items: center;
  gap: var(--bs-space-1);
  margin-bottom: var(--bs-space-1);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.seg-row {
  display: flex;
  gap: var(--bs-space-1);
  margin-bottom: var(--bs-space-1);
}

.seg-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px var(--bs-space-2);
  border: 1px solid var(--bs-color-border-default);
  border-radius: var(--bs-radius-sm);
  background: var(--bs-color-bg-surface);
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-xs);
  cursor: pointer;
}

.seg-btn.active {
  border-color: var(--bs-color-primary);
  color: var(--bs-color-primary);
  background: var(--bs-color-brand-primary-soft);
}

.accent-row {
  display: flex;
  gap: var(--bs-space-2);
  margin: var(--bs-space-1) 0;
}

.accent-swatch-btn {
  width: 16px;
  height: 16px;
  border: 2px solid transparent;
  border-radius: var(--bs-radius-full);
  cursor: pointer;
  padding: 0;
}

.accent-swatch-btn.active {
  border-color: var(--bs-color-primary);
}

.accent-blue { background: var(--bs-color-accent-blue); }
.accent-green { background: var(--bs-color-accent-green); }
.accent-purple { background: var(--bs-color-accent-purple); }
.accent-orange { background: var(--bs-color-accent-orange); }
.accent-cyan { background: var(--bs-color-accent-cyan); }
.accent-red { background: var(--bs-color-accent-red); }
</style>
