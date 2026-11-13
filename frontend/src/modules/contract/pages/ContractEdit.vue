<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import CustomerSelect from '@/components/form/CustomerSelect.vue'
import RemoteSelect, { type RemoteOption } from '@/components/form/RemoteSelect.vue'
import SmartInput from '@/components/form/SmartInput.vue'
import UploadFiles from '@/components/form/UploadFiles.vue'
import { useDictOptions } from '@/composables/useDict'
import { recordSmartHistory } from '@/composables/smartInputHistory'
import { useAiCapabilities } from '@/composables/useAiCapabilities'
import { aiParseContract } from '@/api/ai'
import {
  getContract,
  createContract,
  updateContract,
  submitContract,
  uploadContractAttachment,
  downloadAttachment,
  deleteAttachment,
  frameworkContractOptions,
} from '@/api/contract'
import type { Attachment, Contract, ContractParseResult, CustomerOption } from '@/api/types'

defineOptions({ name: 'ContractEdit' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const formRef = ref<FormInstance>()
const savingDraft = ref(false)
const savingSubmit = ref(false)
const loading = ref(false)
const isEdit = ref(false)
const contractId = ref<number | null>(null)

const form = reactive({
  name: '',
  customerId: undefined as number | undefined,
  customerName: '',
  contractType: '',
  subjectType: '',
  amount: 0 as number | string,
  startDate: '',
  endDate: '',
  payCycle: '',
  delivery: '',
  sealType: '',
  handlerName: '',
  frameworkNo: '',
  paymentOrg: '',
  contactPerson: '',
  contactPhone: '',
  remark: '',
})

const attachments = ref<Attachment[]>([])
// files chosen before the contract is saved — uploaded for real after create
const pendingFiles = ref<{ localId: string; file: File; category: string }[]>([])

type AttachmentCategory = 'econtract' | 'other'

function attCategory(a: Attachment): AttachmentCategory {
  return a.category === 'econtract' ? 'econtract' : 'other'
}

const econtractFiles = computed(() => attachments.value.filter((a) => attCategory(a) === 'econtract'))
const otherFiles = computed(() => attachments.value.filter((a) => attCategory(a) === 'other'))

const typeOpts = useDictOptions('contract_type')
const payCycleOpts = useDictOptions('pay_cycle')
const deliveryOpts = useDictOptions('delivery_way')

const endDateRules = [
  { required: true, message: t('common.form.required') },
  {
    validator: (_r: unknown, v: string, cb: (e?: Error) => void) => {
      cb(v && form.startDate && v < form.startDate ? new Error(t('contract.contract.endBeforeStart')) : undefined)
    },
  },
]

/** 框架合同下拉：仅当前客户已通过的框架合同；未选客户时为空 */
async function fetchFrameworkOptions(q: string): Promise<RemoteOption[]> {
  if (!form.customerId) return []
  try {
    const opts = await frameworkContractOptions(form.customerId, q || undefined)
    return (opts ?? []).map((o) => ({ id: o.id, label: o.label, sub: o.sub }))
  } catch {
    return []
  }
}

function onCustomerChange(v: number | string | null, opt?: CustomerOption) {
  form.customerId = v as number
  form.customerName = opt?.label ?? ''
  if (opt) {
    // customer change overwrites with the customer's own values; user can still edit afterwards
    form.paymentOrg = opt.payOrg ?? ''
    form.contactPerson = opt.contactPerson ?? ''
    form.contactPhone = opt.contactPhone ?? ''
  }
  // 换客户后原框架合同号不再有效
  form.frameworkNo = ''
}

async function load() {
  const idParam = route.params.id
  if (!idParam) return
  isEdit.value = true
  contractId.value = Number(idParam)
  loading.value = true
  try {
    const data: Contract = await getContract(contractId.value)
    Object.assign(form, {
      name: data.name ?? '',
      customerId: data.customerId ?? undefined,
      customerName: data.customerName ?? '',
      contractType: data.contractType ?? '',
      subjectType: data.subjectType ?? '',
      amount: data.amount ?? 0,
      startDate: data.startDate ?? '',
      endDate: data.endDate ?? '',
      payCycle: data.payCycle ?? '',
      delivery: data.delivery ?? '',
      sealType: data.sealType ?? '',
      handlerName: data.handlerName ?? '',
      frameworkNo: data.frameworkNo ?? '',
      paymentOrg: data.paymentOrg ?? '',
      contactPerson: data.contactPerson ?? '',
      contactPhone: data.contactPhone ?? '',
      remark: data.remark ?? '',
    })
    attachments.value = data.attachments ?? []
    if (data.status !== 'draft' && data.status !== 'rejected') {
      ElMessage.warning(t('contract.contract.statusApproving'))
      router.replace(`/contract/contracts/${contractId.value}`)
    }
  } catch {
    /* http notifies */
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())

/** 落库（新建/更新 + 暂存附件上传 + 智能输入历史），返回合同 id；失败返回 null */
async function persist(): Promise<number | null> {
  try {
    const payload = {
      ...form,
      amount: Number(form.amount) || 0,
      // never submit locally-staged attachments (their ids are placeholders)
      attachments: attachments.value.filter((a) => !pendingFiles.value.some((p) => p.localId === a.id)),
    }
    if (isEdit.value && contractId.value) {
      await updateContract(contractId.value, payload)
    } else {
      const created = await createContract(payload)
      contractId.value = created?.id ?? null
      isEdit.value = true
    }
    if (contractId.value && pendingFiles.value.length) {
      await flushPending(contractId.value)
    }
    recordSmartHistory('contract.sealType', form.sealType)
    recordSmartHistory('contract.handlerName', form.handlerName)
    recordSmartHistory('contract.paymentOrg', form.paymentOrg)
    return contractId.value
  } catch {
    /* http notifies */
    return null
  }
}

/** 保存草稿：仅校验名称+客户（草稿宽容），不发编号、不进流程 */
async function saveDraft() {
  if (!formRef.value) return
  const ok = await formRef.value
    .validateField(['name', 'customerId'])
    .then(() => true)
    .catch(() => false)
  if (!ok) return
  savingDraft.value = true
  try {
    if ((await persist()) === null) return
    ElMessage.success(t('common.message.saveSuccess'))
    router.push('/contract/contracts')
  } finally {
    savingDraft.value = false
  }
}

/** 提交审批：完整校验 → 落库 → 发起审批流（发编号、进入审批中） */
async function saveAndSubmit() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  savingSubmit.value = true
  try {
    const id = await persist()
    if (id === null) return
    await submitContract(id)
    ElMessage.success(t('common.message.submitSuccess'))
    router.push('/contract/contracts')
  } catch {
    /* http notifies */
  } finally {
    savingSubmit.value = false
  }
}

function onFilesUpdate(files: Attachment[], category: AttachmentCategory) {
  // UploadFiles 只携带本分类的列表，合并回全量 attachments
  attachments.value = [...attachments.value.filter((a) => attCategory(a) !== category), ...files]
  // dropping a staged file in the list must also drop it from the upload queue
  pendingFiles.value = pendingFiles.value.filter(
    (p) => p.category !== category || files.some((f) => f.id === p.localId),
  )
}

async function upload(file: File, category: AttachmentCategory) {
  if (!contractId.value) {
    // stage locally; uploaded for real once the contract exists
    const localId = `local-${Date.now()}-${pendingFiles.value.length}`
    pendingFiles.value.push({ localId, file, category })
    return { id: localId, fileName: file.name, size: file.size, category }
  }
  return uploadContractAttachment(contractId.value, file, category)
}

async function flushPending(id: number) {
  for (const p of [...pendingFiles.value]) {
    const real = await uploadContractAttachment(id, p.file, p.category as AttachmentCategory)
    attachments.value = attachments.value.map((a) => (a.id === p.localId ? real : a))
    pendingFiles.value = pendingFiles.value.filter((x) => x.localId !== p.localId)
  }
}

async function removeAttachment(fileId: number) {
  await deleteAttachment(fileId)
  ElMessage.success(t('common.message.deleteSuccess'))
}

async function download(fileId: number | string, fileName: string) {
  const pending = pendingFiles.value.find((p) => p.localId === fileId)
  if (pending) {
    const url = URL.createObjectURL(pending.file)
    const a = document.createElement('a')
    a.href = url
    a.download = fileName
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    return
  }
  return downloadAttachment(fileId, fileName)
}

function cancel() {
  router.push('/contract/contracts')
}

// ---------------- AI 合同识别（草稿 → 人工确认回填，不直接落库） ----------------

const aiCaps = useAiCapabilities()
const parseFileInput = ref<HTMLInputElement | null>(null)
const parseDialogVisible = ref(false)
const parsing = ref(false)
const parseResult = ref<ContractParseResult | null>(null)
const parseCandidateId = ref<number | undefined>(undefined)

async function openAiParse() {
  await aiCaps.ensureLoaded()
  if (!aiCaps.featureOn('contract_ocr')) {
    ElMessage.warning(t(aiCaps.caps.value.enabled ? 'ai.common.featureDisabled' : 'ai.common.notConfigured'))
    return
  }
  parseFileInput.value?.click()
}

async function onParseFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  parsing.value = true
  parseResult.value = null
  parseCandidateId.value = undefined
  parseDialogVisible.value = true
  try {
    parseResult.value = await aiParseContract(file)
  } catch {
    parseDialogVisible.value = false
  } finally {
    parsing.value = false
  }
}

/** 回填：仅写非空识别字段；客户仅在人工选了候选时绑定 id */
function applyParse() {
  const r = parseResult.value
  if (!r) return
  const f = r.fields
  if (f.name) form.name = f.name
  if (f.amount) form.amount = f.amount
  if (f.startDate) form.startDate = f.startDate
  if (f.endDate) form.endDate = f.endDate
  if (f.payCycle) form.payCycle = f.payCycle
  if (f.delivery) form.delivery = f.delivery
  if (f.sealType) form.sealType = f.sealType
  if (f.paymentOrg) form.paymentOrg = f.paymentOrg
  if (f.contactPerson) form.contactPerson = f.contactPerson
  if (f.contactPhone) form.contactPhone = f.contactPhone
  if (f.remark) form.remark = f.remark
  if (parseCandidateId.value !== undefined) {
    const c = r.customerCandidates.find((x) => x.id === parseCandidateId.value)
    if (c) {
      form.customerId = c.id
      form.customerName = c.name
      form.frameworkNo = ''
    }
  }
  parseDialogVisible.value = false
  ElMessage.success(t('ai.contractParse.applied'))
}
</script>

<template>
  <div class="contract-edit" v-loading="loading">
    <div class="edit-header">
      <h2 class="edit-title">{{ isEdit ? t('contract.contract.edit') : t('contract.contract.create') }}</h2>
      <div>
        <el-button v-permission="'contract:create'" class="ai-parse-btn" @click="openAiParse">
          {{ t('ai.contractParse.button') }}
        </el-button>
        <el-button @click="cancel">{{ t('common.action.cancel') }}</el-button>
        <el-button :loading="savingDraft" @click="saveDraft">{{ t('common.action.saveDraft') }}</el-button>
        <el-button type="primary" :loading="savingSubmit" @click="saveAndSubmit">{{ t('common.action.submitApproval') }}</el-button>
      </div>
    </div>

    <el-form ref="formRef" :model="form" label-width="130px" class="edit-form">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.name')" prop="name" :rules="[{ required: true, message: t('common.form.required') }]">
            <el-input v-model="form.name" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.customer')" prop="customerId" :rules="[{ required: true, message: t('common.form.required') }]">
            <CustomerSelect :model-value="form.customerId" @change="onCustomerChange" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.contractType')">
            <el-select
              v-model="form.contractType"
              clearable
              filterable
              :placeholder="t('common.form.placeholderSelect')"
              style="width: 100%"
            >
              <el-option v-for="o in typeOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.amount')" prop="amount">
            <el-input-number v-model="form.amount" :min="0" :precision="2" :step="1000" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.startDate')" prop="startDate" :rules="[{ required: true, message: t('common.form.required') }]">
            <el-date-picker v-model="form.startDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" @change="formRef?.validateField('endDate').catch(() => false)" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.endDate')" prop="endDate" :rules="endDateRules">
            <el-date-picker v-model="form.endDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.payCycle')">
            <el-select
              v-model="form.payCycle"
              clearable
              filterable
              :placeholder="t('common.form.placeholderSelect')"
              style="width: 100%"
            >
              <el-option v-for="o in payCycleOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.delivery')">
            <el-select
              v-model="form.delivery"
              clearable
              filterable
              :placeholder="t('common.form.placeholderSelect')"
              style="width: 100%"
            >
              <el-option v-for="o in deliveryOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.sealType')">
            <SmartInput v-model="form.sealType" field="contract.sealType" :maxlength="32" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.handlerName')">
            <SmartInput v-model="form.handlerName" field="contract.handlerName" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.frameworkNo')">
            <RemoteSelect
              v-model="form.frameworkNo"
              :fetch="fetchFrameworkOptions"
              :placeholder="t('contract.contract.frameworkNoPlaceholder')"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.paymentOrg')">
            <SmartInput v-model="form.paymentOrg" field="contract.paymentOrg" :maxlength="128" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.contactPerson')">
            <el-input v-model="form.contactPerson" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.contactPhone')">
            <el-input v-model="form.contactPhone" :maxlength="32" />
          </el-form-item>
        </el-col>
        <el-col :span="24">
          <el-form-item :label="t('contract.contract.remark')">
            <el-input v-model="form.remark" type="textarea" :rows="3" />
          </el-form-item>
        </el-col>
        <el-col :span="24">
          <el-form-item :label="t('contract.contract.attachments')">
            <div class="att-groups">
              <div class="att-group">
                <div class="att-group-title">{{ t('contract.contract.attCatEcontract') }}</div>
                <UploadFiles
                  :files="econtractFiles"
                  :upload="(f: File) => upload(f, 'econtract')"
                  :download="download"
                  :remove-fn="removeAttachment"
                  @update:files="(v: Attachment[]) => onFilesUpdate(v, 'econtract')"
                />
              </div>
              <div class="att-group">
                <div class="att-group-title">{{ t('contract.contract.attCatOther') }}</div>
                <UploadFiles
                  :files="otherFiles"
                  :upload="(f: File) => upload(f, 'other')"
                  :download="download"
                  :remove-fn="removeAttachment"
                  @update:files="(v: Attachment[]) => onFilesUpdate(v, 'other')"
                />
              </div>
            </div>
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>

    <input
      ref="parseFileInput"
      type="file"
      accept=".pdf,.docx,.txt,.jpg,.jpeg,.png"
      style="display: none"
      @change="onParseFileChange"
    />

    <el-dialog v-model="parseDialogVisible" :title="t('ai.contractParse.dialogTitle')" width="640px" append-to-body>
      <div v-loading="parsing">
        <template v-if="parsing">
          <div class="parse-loading">{{ t('ai.contractParse.parsing') }}</div>
        </template>
        <template v-else-if="parseResult">
          <el-alert type="info" :closable="false" :title="t('ai.common.aiDraftTip')" class="parse-tip" />
          <el-form label-width="120px" class="parse-form">
            <div class="parse-section">{{ t('ai.contractParse.fields') }}</div>
            <el-form-item :label="t('contract.contract.name')">
              <el-input v-model="parseResult.fields.name" maxlength="128" />
            </el-form-item>
            <el-form-item :label="t('ai.contractParse.customerRaw')">
              <el-input v-model="parseResult.fields.customerName" maxlength="128" />
            </el-form-item>
            <el-form-item :label="t('ai.contractParse.customerCandidate')">
              <el-select
                v-model="parseCandidateId"
                clearable
                :placeholder="t('common.form.placeholderSelect')"
                style="width: 100%"
              >
                <el-option
                  v-for="c in parseResult.customerCandidates"
                  :key="c.id"
                  :label="c.name"
                  :value="c.id"
                />
              </el-select>
              <div v-if="!parseResult.customerCandidates.length" class="parse-no-candidate">
                {{ t('ai.contractParse.noCandidate') }}
              </div>
            </el-form-item>
            <el-form-item :label="t('contract.contract.amount')">
              <el-input-number v-model="parseResult.fields.amount" :min="0" :precision="2" style="width: 100%" />
            </el-form-item>
            <el-form-item :label="t('contract.contract.startDate')">
              <el-date-picker v-model="parseResult.fields.startDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
            <el-form-item :label="t('contract.contract.endDate')">
              <el-date-picker v-model="parseResult.fields.endDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
            <el-form-item :label="t('contract.contract.payCycle')">
              <el-input v-model="parseResult.fields.payCycle" maxlength="32" />
            </el-form-item>
            <el-form-item :label="t('contract.contract.delivery')">
              <el-input v-model="parseResult.fields.delivery" maxlength="32" />
            </el-form-item>
            <el-form-item :label="t('contract.contract.sealType')">
              <el-input v-model="parseResult.fields.sealType" maxlength="32" />
            </el-form-item>
            <el-form-item :label="t('contract.contract.paymentOrg')">
              <el-input v-model="parseResult.fields.paymentOrg" maxlength="128" />
            </el-form-item>
            <el-form-item :label="t('contract.contract.contactPerson')">
              <el-input v-model="parseResult.fields.contactPerson" maxlength="64" />
            </el-form-item>
            <el-form-item :label="t('contract.contract.contactPhone')">
              <el-input v-model="parseResult.fields.contactPhone" maxlength="32" />
            </el-form-item>
            <el-form-item :label="t('contract.contract.remark')">
              <el-input v-model="parseResult.fields.remark" type="textarea" :rows="2" maxlength="500" />
            </el-form-item>
          </el-form>
        </template>
      </div>
      <template #footer>
        <el-button @click="parseDialogVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :disabled="!parseResult" @click="applyParse">
          {{ t('ai.contractParse.apply') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.contract-edit {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
  padding: var(--bs-space-4);
  height: 100%;
  overflow: auto;
  background: var(--bs-color-bg-surface);
}

.edit-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.edit-title {
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
}

.edit-form {
  max-width: 960px;
}

.att-groups {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
  width: 100%;
}

.att-group-title {
  font-size: var(--bs-typography-font-size-sm);
  font-weight: 600;
  color: var(--bs-color-fg-muted);
  margin-bottom: var(--bs-space-1);
}

.parse-loading {
  padding: var(--bs-space-4);
  text-align: center;
  color: var(--bs-color-fg-secondary);
}

.parse-tip {
  margin-bottom: var(--bs-space-3);
}

.parse-section {
  font-size: var(--bs-typography-font-size-sm);
  font-weight: 600;
  color: var(--bs-color-fg-muted);
  margin-bottom: var(--bs-space-2);
}

.parse-no-candidate {
  font-size: var(--bs-typography-font-size-xs, 12px);
  color: var(--bs-color-fg-muted);
  line-height: 1.4;
}
</style>
