<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import BackButton from '@/components/common/BackButton.vue'
import {
  createQuoteTemplate,
  getQuoteTemplate,
  newVersionQuoteTemplate,
  publishQuoteTemplate,
  updateQuoteTemplate,
} from '@/api/sales'
import type { QuotationItem, QuoteItemColumnConf } from '@/api/types'
import QuotationPreview from '../components/QuotationPreview.vue'

defineOptions({ name: 'QuoteTemplateDesigner' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const editId = Number(route.params.id || 0)
const loading = ref(false)
const saving = ref(false)
const publishing = ref(false)
const status = ref('draft')
const tplVersion = ref(1)

const form = reactive({
  key: '',
  name: '',
  sort: 0,
  headerHtml: '',
  introHtml: '',
  termsHtml: '',
  footerHtml: '',
  validDays: 30,
  itemColumns: [
    { key: 'spec', label: '', visible: true },
    { key: 'unit', label: '', visible: true },
    { key: 'remark', label: '', visible: true },
  ] as QuoteItemColumnConf[],
})

const readonly = computed(() => status.value === 'published')

const previewLayout = computed(() => ({
  headerHtml: form.headerHtml,
  introHtml: form.introHtml,
  termsHtml: form.termsHtml,
  footerHtml: form.footerHtml,
  validDays: form.validDays,
  itemColumns: form.itemColumns,
}))

// 预览示例数据（演示明细行，不随模板保存；文案走 i18n）
const sampleItems = computed<QuotationItem[]>(() => [
  {
    name: t('sales.template.sampleItem1Name'),
    spec: t('sales.template.sampleItem1Spec'),
    unit: t('sales.template.sampleItem1Unit'),
    qty: 2,
    unitPrice: 15000,
    amount: 30000,
    remark: t('sales.template.sampleItem1Remark'),
  },
  {
    name: t('sales.template.sampleItem2Name'),
    spec: '',
    unit: t('sales.template.sampleItem2Unit'),
    qty: 1,
    unitPrice: 5000,
    amount: 5000,
    remark: '',
  },
])

const COLUMN_KEYS = ['spec', 'unit', 'remark'] as const

function columnLabel(key: string) {
  return t(`sales.print.${key === 'spec' ? 'spec' : key === 'unit' ? 'unit' : 'remark'}`)
}

async function load() {
  if (!editId) return
  loading.value = true
  try {
    const d = await getQuoteTemplate(editId)
    form.key = d.key
    form.name = d.name
    form.sort = d.sort
    status.value = d.status
    tplVersion.value = d.tplVersion
    const l = d.layout ?? {}
    form.headerHtml = l.headerHtml ?? ''
    form.introHtml = l.introHtml ?? ''
    form.termsHtml = l.termsHtml ?? ''
    form.footerHtml = l.footerHtml ?? ''
    form.validDays = l.validDays ?? 30
    // 合并列配置：模板存的顺序/可见性/自定义列头优先，缺省列补齐
    const saved = l.itemColumns ?? []
    form.itemColumns = COLUMN_KEYS.map((k) => {
      const hit = saved.find((c) => c.key === k)
      return hit ? { key: k, label: hit.label ?? '', visible: hit.visible !== false } : { key: k, label: '', visible: true }
    })
  } catch {
    /* http notifies */
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())

function validate(): boolean {
  if (!form.key.trim() || !/^[a-z0-9_]+$/.test(form.key.trim())) {
    ElMessage.warning(t('sales.template.keyPlaceholder'))
    return false
  }
  if (!form.name.trim()) {
    ElMessage.warning(t('common.form.required'))
    return false
  }
  return true
}

async function save() {
  if (!validate()) return
  saving.value = true
  try {
    const data = {
      key: form.key.trim(),
      name: form.name.trim(),
      sort: form.sort,
      layout: {
        headerHtml: form.headerHtml,
        introHtml: form.introHtml,
        termsHtml: form.termsHtml,
        footerHtml: form.footerHtml,
        validDays: form.validDays,
        itemColumns: form.itemColumns,
      },
    }
    if (editId) await updateQuoteTemplate(editId, data)
    else {
      const created = await createQuoteTemplate(data)
      ElMessage.success(t('sales.template.saveSuccess'))
      router.replace(`/sales/templates/${created.id}/design`)
      return
    }
    ElMessage.success(t('sales.template.saveSuccess'))
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function publish() {
  try {
    await ElMessageBox.confirm(t('sales.template.publishConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  publishing.value = true
  try {
    await publishQuoteTemplate(editId)
    ElMessage.success(t('common.message.saveSuccess'))
    await load()
  } catch {
    /* http notifies */
  } finally {
    publishing.value = false
  }
}

async function newVersion() {
  try {
    await ElMessageBox.confirm(
      t('sales.template.newVersionConfirm', { n: tplVersion.value + 1 }),
      t('common.action.confirm'),
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    const nv = await newVersionQuoteTemplate(editId)
    ElMessage.success(t('common.message.saveSuccess'))
    router.push(`/sales/templates/${nv.id}/design`)
  } catch {
    /* http notifies */
  }
}
</script>

<template>
  <div class="tpl-designer" v-loading="loading">
    <div class="td-header">
      <div class="td-title">
        {{ editId ? `${t('sales.template.designTitle')} · ${form.name} V${tplVersion}` : t('sales.template.createTitle') }}
      </div>
      <BackButton />
    </div>

    <el-alert v-if="readonly" type="info" :closable="false" :title="t('sales.template.publishedReadonly')" />

    <div class="td-body">
      <!-- 左：版式表单 -->
      <el-form class="td-form" label-position="top" :disabled="readonly">
        <div class="td-row">
          <el-form-item :label="t('sales.template.key')" required>
            <el-input v-model="form.key" maxlength="64" :disabled="!!editId" :placeholder="t('sales.template.keyPlaceholder')" />
          </el-form-item>
          <el-form-item :label="t('sales.template.name')" required>
            <el-input v-model="form.name" maxlength="128" :placeholder="t('sales.template.namePlaceholder')" />
          </el-form-item>
        </div>
        <div class="td-row">
          <el-form-item :label="t('sales.template.sort')">
            <el-input-number v-model="form.sort" :min="0" :max="9999" style="width: 100%" />
          </el-form-item>
          <el-form-item :label="t('sales.template.validDays')">
            <el-input-number v-model="form.validDays" :min="0" :max="3650" style="width: 100%" />
          </el-form-item>
        </div>
        <el-form-item :label="t('sales.template.headerHtml')">
          <el-input v-model="form.headerHtml" type="textarea" :rows="2" maxlength="4000" :placeholder="t('sales.template.headerHtmlPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('sales.template.introHtml')">
          <el-input v-model="form.introHtml" type="textarea" :rows="3" maxlength="8000" />
        </el-form-item>
        <el-form-item :label="t('sales.template.termsHtml')">
          <el-input v-model="form.termsHtml" type="textarea" :rows="4" maxlength="8000" />
        </el-form-item>
        <el-form-item :label="t('sales.template.footerHtml')">
          <el-input v-model="form.footerHtml" type="textarea" :rows="2" maxlength="4000" />
        </el-form-item>
        <el-form-item :label="t('sales.template.itemColumns')">
          <div class="td-columns">
            <div v-for="col in form.itemColumns" :key="col.key" class="td-column-row">
              <el-checkbox v-model="col.visible">{{ columnLabel(col.key) }}</el-checkbox>
              <el-input
                v-model="col.label"
                size="small"
                maxlength="32"
                :disabled="!col.visible"
                :placeholder="t('sales.template.columnLabelPlaceholder')"
                style="width: 180px"
              />
            </div>
          </div>
        </el-form-item>
        <div class="td-actions" v-if="!readonly">
          <el-button :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
          <el-button
            v-if="editId"
            v-permission="'sales:template:publish'"
            type="primary"
            :loading="publishing"
            @click="publish"
          >
            {{ t('sales.template.publish') }}
          </el-button>
        </div>
        <div class="td-actions" v-else>
          <el-button v-permission="'sales:template:edit'" type="primary" plain @click="newVersion">
            {{ t('sales.template.newVersion') }}
          </el-button>
        </div>
      </el-form>

      <!-- 右：实时预览 -->
      <div class="td-preview">
        <div class="td-preview-title">{{ t('sales.template.preview') }}</div>
        <QuotationPreview
          :layout="previewLayout"
          quote-no="BJ202610090001"
          :customer-name="t('sales.quotation.customerName')"
          :items="sampleItems"
          :tax-rate="6"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.tpl-designer {
  padding: var(--bs-space-3);
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}

.td-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.td-title {
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
}

.td-body {
  display: grid;
  grid-template-columns: minmax(320px, 460px) 1fr;
  gap: var(--bs-space-4);
  align-items: start;
}

.td-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  column-gap: var(--bs-space-3);
}

.td-columns {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  width: 100%;
}

.td-column-row {
  display: flex;
  align-items: center;
  gap: var(--bs-space-3);
}

.td-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--bs-space-2);
}

.td-preview {
  min-width: 0;
}

.td-preview-title {
  font-weight: 600;
  margin-bottom: var(--bs-space-2);
}

@media (max-width: 768px) {
  .td-body {
    grid-template-columns: 1fr;
  }
}
</style>
