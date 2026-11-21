<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import CustomerSelect from '@/components/form/CustomerSelect.vue'
import BackButton from '@/components/common/BackButton.vue'
import { listPartnerContacts } from '@/api/crm'
import {
  aiGenerateQuotation,
  createQuotation,
  getQuotation,
  quoteTemplateOptions,
  submitQuotation,
  updateQuotation,
} from '@/api/sales'
import type { PartnerContact, QuotationItem, QuoteTemplate } from '@/api/types'
import QuotationPreview from '../components/QuotationPreview.vue'

defineOptions({ name: 'QuotationEdit' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const editId = Number(route.params.id || 0)
const loading = ref(false)
const saving = ref(false)
const aiLoading = ref(false)
const readonly = ref(false)

const form = reactive({
  title: '',
  customerId: undefined as number | undefined,
  customerName: '',
  contactName: '',
  contactPhone: '',
  contactEmail: '',
  templateId: undefined as number | undefined,
  requirement: '',
  introHtml: '',
  termsHtml: '',
  taxRate: 6,
  validUntil: '' as string,
  autoSend: false,
  aiMeta: '',
  items: [] as QuotationItem[],
})

// AI 生成来源徽标（本地即时状态 + 已保存的 aiMeta）
const aiSource = ref<'ai' | 'template' | 'history' | ''>('')
const aiTip = ref('')

const templates = ref<QuoteTemplate[]>([])
const contacts = ref<PartnerContact[]>([])
const previewLayout = ref<QuoteTemplate['layout'] | null>(null)

const totalAmount = computed(() =>
  form.items.reduce((s, it) => s + Number(it.qty || 0) * Number(it.unitPrice || 0), 0),
)

function rowAmount(it: QuotationItem) {
  return Number(it.qty || 0) * Number(it.unitPrice || 0)
}

function addItem() {
  form.items.push({ name: '', spec: '', unit: '', qty: 1, unitPrice: 0, amount: 0, remark: '' })
}

function removeItem(idx: number) {
  form.items.splice(idx, 1)
}

async function loadTemplates() {
  try {
    templates.value = await quoteTemplateOptions()
  } catch {
    templates.value = []
  }
}

function onTemplateChange(tid: number | undefined) {
  const tpl = templates.value.find((x) => x.id === tid)
  previewLayout.value = tpl?.layout ?? null
  if (!tpl) return
  // 模板带出默认内容（仅填充空字段，不覆盖用户已写内容）
  if (!form.introHtml) form.introHtml = tpl.layout?.introHtml ?? ''
  if (!form.termsHtml) form.termsHtml = tpl.layout?.termsHtml ?? ''
  if (!form.validUntil && tpl.layout?.validDays) {
    const d = new Date(Date.now() + Number(tpl.layout.validDays) * 86400000)
    form.validUntil = d.toISOString().slice(0, 10)
  }
}

async function onCustomerChange(v: number | string | null, option?: { label?: string }) {
  form.customerId = v ? Number(v) : undefined
  form.customerName = option?.label ?? ''
  contacts.value = []
  if (!form.customerId) return
  try {
    const r = await listPartnerContacts(form.customerId)
    contacts.value = r.items ?? []
    const primary = contacts.value.find((c) => c.isPrimary) ?? contacts.value[0]
    if (primary) applyContact(primary)
  } catch {
    /* 联系人可选 */
  }
}

function applyContact(c: PartnerContact) {
  form.contactName = c.name ?? ''
  form.contactPhone = c.phone ?? ''
  form.contactEmail = c.email ?? ''
}

function onContactPick(id: number) {
  const c = contacts.value.find((x) => x.id === id)
  if (c) applyContact(c)
}

async function generateByAi() {
  if (!form.requirement.trim()) {
    ElMessage.warning(t('sales.quotation.requirement'))
    return
  }
  aiLoading.value = true
  try {
    const r = await aiGenerateQuotation({
      quotationId: editId || undefined,
      customerId: form.customerId,
      templateId: form.templateId ?? undefined,
      requirement: form.requirement.trim(),
    })
    aiSource.value = r.source
    form.aiMeta = r.aiMeta
    if (r.title && !form.title) form.title = r.title
    if (r.introHtml) form.introHtml = r.introHtml
    if (r.termsHtml) form.termsHtml = r.termsHtml
    if (r.items.length) {
      form.items = r.items.map((it) => ({ ...it }))
    }
    if (r.source === 'ai') aiTip.value = t('sales.quotation.aiSuccessTip')
    else if (r.source === 'history') aiTip.value = t('sales.quotation.aiFailedHistoryTip')
    else if (r.fallbackReason === 'ai_not_configured') aiTip.value = t('sales.quotation.aiNotConfiguredTip')
    else aiTip.value = t('sales.quotation.aiFailedTemplateTip')
  } catch {
    /* http notifies */
  } finally {
    aiLoading.value = false
  }
}

function payload() {
  return {
    title: form.title.trim(),
    customerId: form.customerId,
    contactName: form.contactName.trim(),
    contactPhone: form.contactPhone.trim(),
    contactEmail: form.contactEmail.trim(),
    templateId: form.templateId ?? null,
    requirement: form.requirement,
    introHtml: form.introHtml,
    termsHtml: form.termsHtml,
    taxRate: Number(form.taxRate ?? 0),
    validUntil: form.validUntil || null,
    autoSend: form.autoSend,
    aiMeta: form.aiMeta,
    items: form.items
      .filter((it) => it.name.trim())
      .map((it) => ({
        name: it.name.trim(),
        spec: it.spec ?? '',
        unit: it.unit ?? '',
        qty: Number(it.qty || 0),
        unitPrice: Number(it.unitPrice || 0),
        remark: it.remark ?? '',
      })),
  }
}

function validate(): boolean {
  if (!form.title.trim()) {
    ElMessage.warning(t('sales.quotation.quoteTitle'))
    return false
  }
  if (!form.customerId) {
    ElMessage.warning(t('sales.quotation.customer'))
    return false
  }
  return true
}

async function save(submitAfter = false) {
  if (!validate()) return
  saving.value = true
  try {
    const data = payload()
    const saved = editId ? await updateQuotation(editId, data) : await createQuotation(data)
    ElMessage.success(t('sales.quotation.createSuccess'))
    if (submitAfter) {
      await submitQuotation(saved.id)
      ElMessage.success(t('common.message.submitSuccess'))
    }
    router.push('/sales/quotations')
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function load() {
  if (!editId) return
  loading.value = true
  try {
    const d = await getQuotation(editId)
    readonly.value = !['draft', 'rejected'].includes(d.status)
    Object.assign(form, {
      title: d.title,
      customerId: d.customerId,
      customerName: d.customerName,
      contactName: d.contactName,
      contactPhone: d.contactPhone,
      contactEmail: d.contactEmail,
      templateId: d.templateId ?? undefined,
      requirement: d.requirement,
      introHtml: d.introHtml,
      termsHtml: d.termsHtml,
      taxRate: d.taxRate,
      validUntil: d.validUntil,
      autoSend: d.autoSend,
      aiMeta: d.aiMeta,
      items: (d.items ?? []).map((it) => ({ ...it })),
    })
    previewLayout.value = d.layout ?? null
    if (d.aiMeta) {
      try {
        aiSource.value = JSON.parse(d.aiMeta)?.source ?? ''
      } catch {
        /* ignore */
      }
    }
    if (d.customerId) {
      try {
        const r = await listPartnerContacts(d.customerId)
        contacts.value = r.items ?? []
      } catch {
        /* 联系人可选 */
      }
    }
  } catch {
    /* http notifies */
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadTemplates()
  await load()
})
</script>

<template>
  <div class="bs-page" v-loading="loading">
    <div class="bs-page-header">
      <div class="bs-page-title">{{ editId ? t('sales.quotation.editTitle') : t('sales.quotation.createTitle') }}</div>
      <BackButton />
    </div>

    <el-alert v-if="readonly" type="info" :closable="false" class="qe-readonly" :title="t('sales.quotation.readonlyTip')" />

    <el-form label-position="top" :disabled="readonly">
      <div class="qe-grid">
        <el-form-item :label="t('sales.quotation.quoteTitle')" required>
          <el-input v-model="form.title" maxlength="255" :placeholder="t('sales.quotation.quoteTitlePlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('sales.quotation.customer')" required>
          <CustomerSelect :model-value="form.customerId" @change="onCustomerChange" />
        </el-form-item>
        <el-form-item :label="t('sales.quotation.template')">
          <el-select
            :model-value="form.templateId"
            clearable
            :placeholder="t('sales.quotation.templatePlaceholder')"
            @update:model-value="(v: number | undefined) => { form.templateId = v; onTemplateChange(v) }"
          >
            <el-option v-for="tpl in templates" :key="tpl.id" :label="`${tpl.name} V${tpl.tplVersion}`" :value="tpl.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('sales.quotation.contact')">
          <el-select
            :model-value="undefined"
            clearable
            :disabled="!contacts.length"
            :placeholder="t('sales.quotation.contactNamePlaceholder')"
            @update:model-value="(v: number) => v && onContactPick(v)"
          >
            <el-option v-for="c in contacts" :key="c.id" :label="`${c.name} ${c.phone || ''}`" :value="c.id!" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('sales.quotation.contactName')">
          <el-input v-model="form.contactName" maxlength="64" />
        </el-form-item>
        <el-form-item :label="t('sales.quotation.contactPhone')">
          <el-input v-model="form.contactPhone" maxlength="32" />
        </el-form-item>
        <el-form-item :label="t('sales.quotation.contactEmail')">
          <el-input v-model="form.contactEmail" maxlength="128" :placeholder="t('sales.quotation.contactEmailPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('sales.quotation.validUntil')">
          <el-date-picker v-model="form.validUntil" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item :label="t('sales.quotation.taxRate')">
          <el-input-number v-model="form.taxRate" :min="0" :max="100" :step="1" style="width: 100%" />
        </el-form-item>
      </div>

      <el-form-item :label="t('sales.quotation.requirement')">
        <el-input
          v-model="form.requirement"
          type="textarea"
          :rows="3"
          maxlength="4000"
          :placeholder="t('sales.quotation.requirementPlaceholder')"
        />
      </el-form-item>
      <div class="qe-ai-bar">
        <el-button type="primary" plain :loading="aiLoading" @click="generateByAi">
          {{ aiLoading ? t('sales.quotation.aiGenerating') : t('sales.quotation.aiGenerate') }}
        </el-button>
        <el-tag v-if="aiSource" size="small" effect="plain">
          {{ t(`sales.quotation.aiSource${aiSource === 'ai' ? 'Ai' : aiSource === 'history' ? 'History' : 'Template'}`) }}
        </el-tag>
        <span v-if="aiTip" class="qe-ai-tip">{{ aiTip }}</span>
      </div>

      <el-form-item :label="t('sales.quotation.items')">
        <div class="qe-items">
          <el-table :data="form.items" size="small" border>
            <el-table-column type="index" width="46" align="center" />
            <el-table-column :label="t('sales.quotation.itemName')" min-width="180">
              <template #default="{ row }">
                <el-input v-model="row.name" maxlength="255" />
              </template>
            </el-table-column>
            <el-table-column :label="t('sales.quotation.itemSpec')" min-width="140">
              <template #default="{ row }">
                <el-input v-model="row.spec" maxlength="255" />
              </template>
            </el-table-column>
            <el-table-column :label="t('sales.quotation.itemQty')" width="120">
              <template #default="{ row }">
                <el-input-number v-model="row.qty" :min="0.01" :precision="2" :controls="false" style="width: 100%" />
              </template>
            </el-table-column>
            <el-table-column :label="t('sales.quotation.itemUnit')" width="90">
              <template #default="{ row }">
                <el-input v-model="row.unit" maxlength="16" />
              </template>
            </el-table-column>
            <el-table-column :label="t('sales.quotation.itemUnitPrice')" width="130">
              <template #default="{ row }">
                <el-input-number v-model="row.unitPrice" :min="0" :precision="2" :controls="false" style="width: 100%" />
              </template>
            </el-table-column>
            <el-table-column :label="t('sales.quotation.itemAmount')" width="110" align="right">
              <template #default="{ row }">{{ rowAmount(row).toLocaleString(undefined, { minimumFractionDigits: 2 }) }}</template>
            </el-table-column>
            <el-table-column :label="t('sales.quotation.itemRemark')" min-width="120">
              <template #default="{ row }">
                <el-input v-model="row.remark" maxlength="255" />
              </template>
            </el-table-column>
            <el-table-column width="60" align="center">
              <template #default="{ $index }">
                <el-button link type="danger" icon="Delete" @click="removeItem($index)" />
              </template>
            </el-table-column>
          </el-table>
          <div class="qe-items-footer">
            <el-button size="small" icon="Plus" @click="addItem">{{ t('sales.quotation.addItem') }}</el-button>
            <div class="qe-total">
              {{ t('sales.quotation.totalAmount') }}：
              <b>{{ totalAmount.toLocaleString(undefined, { minimumFractionDigits: 2 }) }}</b>
            </div>
          </div>
        </div>
      </el-form-item>

      <el-form-item :label="t('sales.quotation.introHtml')">
        <el-input v-model="form.introHtml" type="textarea" :rows="3" maxlength="8000" />
      </el-form-item>
      <el-form-item :label="t('sales.quotation.termsHtml')">
        <el-input v-model="form.termsHtml" type="textarea" :rows="4" maxlength="8000" />
      </el-form-item>
      <el-form-item>
        <el-checkbox v-model="form.autoSend">{{ t('sales.quotation.autoSend') }}</el-checkbox>
        <span class="qe-autosend-tip">{{ t('sales.quotation.autoSendTip') }}</span>
      </el-form-item>

      <div class="qe-actions" v-if="!readonly">
        <el-button :loading="saving" @click="save(false)">{{ t('sales.quotation.save') }}</el-button>
        <el-button v-permission="'sales:quote:submit'" type="primary" :loading="saving" @click="save(true)">
          {{ t('sales.quotation.saveAndSubmit') }}
        </el-button>
      </div>
    </el-form>

    <div class="qe-preview">
      <div class="qe-preview-title">{{ t('sales.quotation.preview') }}</div>
      <QuotationPreview
        :layout="{ ...(previewLayout ?? {}), introHtml: form.introHtml, termsHtml: form.termsHtml }"
        :customer-name="form.customerName"
        :contact-name="form.contactName"
        :contact-phone="form.contactPhone"
        :valid-until="form.validUntil"
        :items="form.items"
        :tax-rate="form.taxRate"
      />
    </div>
  </div>
</template>

<style scoped>
.qe-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  column-gap: var(--bs-space-4);
}

.qe-ai-bar {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  margin: calc(-1 * var(--bs-space-2)) 0 var(--bs-space-2);
}

.qe-ai-tip {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.qe-items {
  width: 100%;
}

.qe-items-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: var(--bs-space-2);
}

.qe-total b {
  font-size: var(--bs-typography-font-size-lg);
}

.qe-autosend-tip {
  margin-left: var(--bs-space-2);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.qe-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--bs-space-2);
}

.qe-preview-title {
  font-weight: 600;
  margin-bottom: var(--bs-space-2);
}

@media (max-width: 768px) {
  .qe-grid {
    grid-template-columns: 1fr;
  }
}
</style>
