<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Camera, Delete, Edit, Plus, View } from '@element-plus/icons-vue'
import StepUpDialog from '../components/StepUpDialog.vue'
import * as authApi from '@/api/auth'
import type { BankAccountIn } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import type { BankAccount, EmergencyContact, ProfileInfo } from '@/api/types'

defineOptions({ name: 'ProfilePage' })

const { t } = useI18n()
const auth = useAuthStore()

const profile = ref<ProfileInfo | null>(null)
const loading = ref(false)
const tab = ref('basic')

const initial = computed(() => (profile.value?.name || profile.value?.username || '?').slice(0, 1))

// ---- step-up token 缓存（5 分钟，提前 10s 过期） ----
const stepUpRef = ref<InstanceType<typeof StepUpDialog>>()
const stepUpToken = ref('')
const stepUpExpireAt = ref(0)

async function ensureStepUp(): Promise<string> {
  if (stepUpToken.value && Date.now() < stepUpExpireAt.value) return stepUpToken.value
  const r = await stepUpRef.value!.open()
  stepUpToken.value = r.stepUpToken
  stepUpExpireAt.value = Date.now() + (r.expiresIn - 10) * 1000
  return r.stepUpToken
}

async function load() {
  loading.value = true
  try {
    profile.value = await authApi.getProfile()
    contactForm.mobile = profile.value.mobile
    contactForm.email = profile.value.email
  } finally {
    loading.value = false
  }
}

// ---- 头像 ----
const fileInput = ref<HTMLInputElement>()
const avatarPreview = ref('')
const avatarFile = ref<File | null>(null)
const avatarDialog = ref(false)
const avatarSaving = ref(false)

function pickAvatar() {
  fileInput.value?.click()
}

function onAvatarPicked(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  ;(e.target as HTMLInputElement).value = ''
  if (!file) return
  if (file.size > 5 * 1024 * 1024) {
    ElMessage.error(t('auth.profile.avatarTip'))
    return
  }
  avatarFile.value = file
  avatarPreview.value = URL.createObjectURL(file)
  avatarDialog.value = true
}

async function confirmAvatar() {
  if (!avatarFile.value) return
  avatarSaving.value = true
  try {
    const r = await authApi.uploadAvatar(avatarFile.value)
    if (profile.value) profile.value.avatarUrl = r.avatarUrl
    // 顶栏头像同步
    await auth.fetchMe()
    avatarDialog.value = false
    ElMessage.success(t('auth.profile.saveSuccess'))
  } finally {
    avatarSaving.value = false
  }
}

// ---- 联系方式（变更需 step-up） ----
const contactForm = reactive({ mobile: '', email: '' })
const contactSaving = ref(false)
const contactDirty = computed(
  () => profile.value && (contactForm.mobile !== profile.value.mobile || contactForm.email !== profile.value.email),
)

async function saveContact() {
  if (!profile.value) return
  contactSaving.value = true
  try {
    let token = ''
    if (contactDirty.value) token = await ensureStepUp()
    profile.value = await authApi.updateProfile({ mobile: contactForm.mobile, email: contactForm.email }, token)
    ElMessage.success(t('auth.profile.saveSuccess'))
  } catch {
    /* 取消或失败均已提示 */
  } finally {
    contactSaving.value = false
  }
}

// ---- 紧急联系人 ----
const contacts = ref<EmergencyContact[]>([])
const contactsLoading = ref(false)
const contactDialog = ref(false)
const contactEditingId = ref(0)
const contactEditForm = reactive({ name: '', relation: '', phone: '', remark: '' })

async function loadContacts() {
  contactsLoading.value = true
  try {
    contacts.value = await authApi.listContacts()
  } finally {
    contactsLoading.value = false
  }
}

function openContactDialog(row?: EmergencyContact) {
  contactEditingId.value = row?.id ?? 0
  contactEditForm.name = row?.name ?? ''
  contactEditForm.relation = row?.relation ?? ''
  contactEditForm.phone = row?.phone ?? ''
  contactEditForm.remark = row?.remark ?? ''
  contactDialog.value = true
}

async function saveContactRow() {
  if (!contactEditForm.name.trim()) return
  if (contactEditingId.value) await authApi.updateContact(contactEditingId.value, { ...contactEditForm })
  else await authApi.createContact({ ...contactEditForm })
  contactDialog.value = false
  ElMessage.success(t('auth.profile.saveSuccess'))
  await loadContacts()
}

async function removeContact(row: EmergencyContact) {
  await ElMessageBox.confirm(t('auth.profile.contactDeleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  await authApi.deleteContact(row.id)
  await loadContacts()
}

// ---- 银行卡 ----
const banks = ref<BankAccount[]>([])
const banksLoading = ref(false)
const revealed = ref<Record<number, string>>({})
const bankDialog = ref(false)
const bankEditingId = ref(0)
const bankForm = reactive<BankAccountIn>({ bankName: '', cardNo: '', holderName: '' })

async function loadBanks() {
  banksLoading.value = true
  try {
    banks.value = await authApi.listBankAccounts()
  } finally {
    banksLoading.value = false
  }
}

async function revealBank(row: BankAccount) {
  if (revealed.value[row.id]) {
    const next = { ...revealed.value }
    delete next[row.id]
    revealed.value = next
    return
  }
  try {
    const token = await ensureStepUp()
    const full = await authApi.revealBankAccount(row.id, token)
    revealed.value = { ...revealed.value, [row.id]: full.cardNo }
  } catch {
    /* 取消 */
  }
}

function openBankDialog(row?: BankAccount) {
  bankEditingId.value = row?.id ?? 0
  bankForm.bankName = row?.bankName ?? ''
  // 列表只有脱敏值，编辑时卡号需重新完整输入
  bankForm.cardNo = ''
  bankForm.holderName = row?.holderName ?? ''
  bankDialog.value = true
}

async function saveBank() {
  if (!bankForm.bankName.trim() || !bankForm.cardNo.trim() || !bankForm.holderName.trim()) return
  try {
    const token = await ensureStepUp()
    if (bankEditingId.value) await authApi.updateBankAccount(bankEditingId.value, { ...bankForm }, token)
    else await authApi.createBankAccount({ ...bankForm }, token)
    bankDialog.value = false
    revealed.value = {}
    ElMessage.success(t('auth.profile.saveSuccess'))
    await loadBanks()
  } catch {
    /* 取消或失败均已提示 */
  }
}

async function removeBank(row: BankAccount) {
  try {
    await ElMessageBox.confirm(t('auth.profile.bankDeleteConfirm'), t('common.action.confirm'), { type: 'warning' })
    const token = await ensureStepUp()
    await authApi.deleteBankAccount(row.id, token)
    await loadBanks()
  } catch {
    /* 取消 */
  }
}

onMounted(() => {
  void load()
  void loadContacts()
  void loadBanks()
})
</script>

<template>
  <div class="profile-page" v-loading="loading">
    <section class="profile-hero">
      <button class="avatar-wrap" type="button" :title="t('auth.profile.changeAvatar')" @click="pickAvatar">
        <img v-if="profile?.avatarUrl" :src="profile.avatarUrl" class="avatar-img" alt="" />
        <span v-else class="avatar-fallback">{{ initial }}</span>
        <span class="avatar-mask"><el-icon><Camera /></el-icon></span>
      </button>
      <input
        ref="fileInput"
        type="file"
        accept=".jpg,.jpeg,.png,.webp"
        hidden
        @change="onAvatarPicked"
      />
      <div class="hero-meta">
        <h1 class="hero-name">{{ profile?.name || '-' }}</h1>
        <p class="hero-sub">
          {{ profile?.username }}
          <span v-if="profile?.employeeNo" class="hero-tag">{{ profile.employeeNo }}</span>
          <span v-for="r in profile?.roles ?? []" :key="r" class="hero-tag">{{ r }}</span>
        </p>
      </div>
    </section>

    <el-tabs v-model="tab" class="profile-tabs">
      <!-- 基本资料 -->
      <el-tab-pane :label="t('auth.profile.tabBasic')" name="basic">
        <el-descriptions :column="2" border class="profile-desc">
          <el-descriptions-item :label="t('auth.profile.name')">{{ profile?.name || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('auth.login.username')">{{ profile?.username }}</el-descriptions-item>
          <el-descriptions-item :label="t('auth.profile.employeeNo')">{{ profile?.employeeNo || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('auth.profile.hireDate')">{{ profile?.hireDate || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('auth.profile.jobLevel')">{{ profile?.jobLevel || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('auth.profile.avatar')">
            <el-button link type="primary" @click="pickAvatar">{{ t('auth.profile.changeAvatar') }}</el-button>
          </el-descriptions-item>
        </el-descriptions>
        <p class="section-tip">{{ t('auth.profile.orgManagedTip') }}</p>
      </el-tab-pane>

      <!-- 联系方式 -->
      <el-tab-pane :label="t('auth.profile.tabContact')" name="contact">
        <el-form label-width="110px" class="contact-form">
          <el-form-item :label="t('auth.profile.mobile')">
            <el-input v-model="contactForm.mobile" maxlength="32" />
          </el-form-item>
          <el-form-item :label="t('auth.profile.email')">
            <el-input v-model="contactForm.email" maxlength="128" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="contactSaving" :disabled="!contactDirty" @click="saveContact">
              {{ t('common.action.save') }}
            </el-button>
          </el-form-item>
        </el-form>
        <p class="section-tip">{{ t('auth.profile.contactChangeTip') }}</p>
      </el-tab-pane>

      <!-- 组织信息（只读） -->
      <el-tab-pane :label="t('auth.profile.tabOrg')" name="org">
        <el-descriptions :column="2" border class="profile-desc">
          <el-descriptions-item :label="t('auth.user.dept')">{{ profile?.deptName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('auth.profile.leader')">
            {{ profile?.leaderName || t('auth.profile.noLeader') }}
          </el-descriptions-item>
        </el-descriptions>
        <p class="section-tip">{{ t('auth.profile.orgManagedTip') }}</p>
      </el-tab-pane>

      <!-- 紧急联系人 -->
      <el-tab-pane :label="t('auth.profile.tabContacts')" name="contacts">
        <div class="table-bar">
          <el-button type="primary" :icon="Plus" @click="openContactDialog()">
            {{ t('auth.profile.addContact') }}
          </el-button>
        </div>
        <el-table :data="contacts" v-loading="contactsLoading">
          <el-table-column prop="name" :label="t('auth.profile.contactName')" min-width="120" />
          <el-table-column prop="relation" :label="t('auth.profile.relation')" width="120" />
          <el-table-column prop="phone" :label="t('auth.profile.phone')" min-width="140" />
          <el-table-column prop="remark" :label="t('auth.profile.remark')" min-width="160" show-overflow-tooltip />
          <el-table-column :label="t('common.action.operate')" width="120" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" :icon="Edit" @click="openContactDialog(row)" />
              <el-button link type="danger" :icon="Delete" @click="removeContact(row)" />
            </template>
          </el-table-column>
          <template #empty>{{ t('auth.profile.emptyContacts') }}</template>
        </el-table>
      </el-tab-pane>

      <!-- 银行卡 -->
      <el-tab-pane :label="t('auth.profile.tabBank')" name="bank">
        <div class="table-bar">
          <el-button type="primary" :icon="Plus" @click="openBankDialog()">
            {{ t('auth.profile.addBank') }}
          </el-button>
        </div>
        <el-table :data="banks" v-loading="banksLoading">
          <el-table-column prop="bankName" :label="t('auth.profile.bankName')" min-width="140" />
          <el-table-column :label="t('auth.profile.cardNo')" min-width="200">
            <template #default="{ row }">
              <span class="card-no">{{ revealed[row.id] || row.cardNo }}</span>
              <el-button
                link
                type="primary"
                :icon="View"
                :title="t('auth.profile.reveal')"
                @click="revealBank(row)"
              />
            </template>
          </el-table-column>
          <el-table-column prop="holderName" :label="t('auth.profile.holderName')" min-width="120" />
          <el-table-column :label="t('common.action.operate')" width="120" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" :icon="Edit" @click="openBankDialog(row)" />
              <el-button link type="danger" :icon="Delete" @click="removeBank(row)" />
            </template>
          </el-table-column>
          <template #empty>{{ t('auth.profile.emptyBanks') }}</template>
        </el-table>
        <p class="section-tip">{{ t('auth.profile.maskedTip') }}</p>
      </el-tab-pane>
    </el-tabs>

    <!-- 头像预览确认 -->
    <el-dialog v-model="avatarDialog" :title="t('auth.profile.avatarPreview')" width="360px" append-to-body>
      <div class="avatar-preview">
        <img :src="avatarPreview" class="avatar-preview-img" alt="" />
        <p class="section-tip">{{ t('auth.profile.avatarTip') }}</p>
      </div>
      <template #footer>
        <el-button @click="avatarDialog = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="avatarSaving" @click="confirmAvatar">
          {{ t('common.action.save') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 联系人编辑 -->
    <el-dialog
      v-model="contactDialog"
      :title="t(contactEditingId ? 'auth.profile.editContact' : 'auth.profile.addContact')"
      width="440px"
      append-to-body
    >
      <el-form label-width="90px">
        <el-form-item :label="t('auth.profile.contactName')" required>
          <el-input v-model="contactEditForm.name" maxlength="64" />
        </el-form-item>
        <el-form-item :label="t('auth.profile.relation')">
          <el-input v-model="contactEditForm.relation" maxlength="32" />
        </el-form-item>
        <el-form-item :label="t('auth.profile.phone')">
          <el-input v-model="contactEditForm.phone" maxlength="32" />
        </el-form-item>
        <el-form-item :label="t('auth.profile.remark')">
          <el-input v-model="contactEditForm.remark" maxlength="255" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="contactDialog = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :disabled="!contactEditForm.name.trim()" @click="saveContactRow">
          {{ t('common.action.save') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 银行卡编辑 -->
    <el-dialog
      v-model="bankDialog"
      :title="t(bankEditingId ? 'auth.profile.editBank' : 'auth.profile.addBank')"
      width="440px"
      append-to-body
    >
      <el-form label-width="90px">
        <el-form-item :label="t('auth.profile.bankName')" required>
          <el-input v-model="bankForm.bankName" maxlength="64" />
        </el-form-item>
        <el-form-item :label="t('auth.profile.cardNo')" required>
          <el-input v-model="bankForm.cardNo" maxlength="30" />
        </el-form-item>
        <el-form-item :label="t('auth.profile.holderName')" required>
          <el-input v-model="bankForm.holderName" maxlength="64" />
        </el-form-item>
      </el-form>
      <p class="section-tip">{{ t('auth.profile.bankStepUpTip') }}</p>
      <template #footer>
        <el-button @click="bankDialog = false">{{ t('common.action.cancel') }}</el-button>
        <el-button
          type="primary"
          :disabled="!bankForm.bankName.trim() || !bankForm.cardNo.trim() || !bankForm.holderName.trim()"
          @click="saveBank"
        >
          {{ t('common.action.save') }}
        </el-button>
      </template>
    </el-dialog>

    <StepUpDialog ref="stepUpRef" />
  </div>
</template>

<style scoped>
.profile-page {
  padding: var(--bs-space-4);
  max-width: 960px;
  margin: 0 auto;
}

.profile-hero {
  display: flex;
  align-items: center;
  gap: var(--bs-space-4);
  padding: var(--bs-space-5);
  border-radius: var(--bs-radius-lg);
  background: var(--bs-color-bg-surface);
  border: 1px solid var(--bs-color-border-subtle);
  margin-bottom: var(--bs-space-4);
}

.avatar-wrap {
  position: relative;
  width: 72px;
  height: 72px;
  border-radius: 50%;
  border: none;
  padding: 0;
  cursor: pointer;
  overflow: hidden;
  background: var(--bs-color-brand-primary-soft);
  flex: none;
}

.avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  font-size: 28px;
  color: var(--bs-color-primary);
}

.avatar-mask {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bs-color-bg-overlay);
  color: var(--bs-color-fg-inverse);
  opacity: 0;
  transition: opacity var(--bs-duration) var(--bs-ease);
}

.avatar-wrap:hover .avatar-mask {
  opacity: 1;
}

.hero-name {
  margin: 0;
  font-size: var(--bs-typography-font-size-xl);
  color: var(--bs-color-fg-default);
}

.hero-sub {
  margin: var(--bs-space-1) 0 0;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  flex-wrap: wrap;
}

.hero-tag {
  padding: 0 var(--bs-space-2);
  border-radius: var(--bs-radius-sm);
  background: var(--bs-color-fill-light);
  font-size: var(--bs-typography-font-size-xs);
}

.profile-tabs {
  padding: 0 var(--bs-space-2);
}

.profile-desc {
  max-width: 720px;
}

.section-tip {
  margin: var(--bs-space-2) 0 0;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}

.contact-form {
  max-width: 480px;
}

.table-bar {
  margin-bottom: var(--bs-space-3);
}

.card-no {
  font-family: monospace;
  margin-right: var(--bs-space-1);
}

.avatar-preview {
  text-align: center;
}

.avatar-preview-img {
  width: 200px;
  height: 200px;
  border-radius: 50%;
  object-fit: cover;
}
</style>
