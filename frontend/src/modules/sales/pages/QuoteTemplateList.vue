<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import {
  listQuoteTemplates,
  publishQuoteTemplate,
  disableQuoteTemplate,
  newVersionQuoteTemplate,
  deleteQuoteTemplate,
} from '@/api/sales'
import type { QuoteTemplate } from '@/api/types'

defineOptions({ name: 'QuoteTemplateList' })

const { t } = useI18n()
const router = useRouter()

const loading = ref(false)
const rows = ref<QuoteTemplate[]>([])
const keyword = ref('')

const filtered = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  if (!q) return rows.value
  return rows.value.filter((r) => r.name.toLowerCase().includes(q) || r.key.toLowerCase().includes(q))
})

async function load() {
  loading.value = true
  try {
    rows.value = (await listQuoteTemplates()) ?? []
  } catch {
    rows.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())

function rowActions(row: QuoteTemplate): ActionItem[] {
  const acts: ActionItem[] = [{ key: 'design', tip: 'sales.template.design', perm: 'sales:template:edit' }]
  if (row.status !== 'published') {
    acts.push({ key: 'publish', tip: 'sales.template.publish', perm: 'sales:template:publish' })
  } else {
    acts.push({ key: 'disable', tip: 'sales.template.disable', perm: 'sales:template:publish' })
  }
  acts.push({ key: 'newVersion', tip: 'sales.template.newVersion', perm: 'sales:template:edit' })
  if (row.status === 'draft') acts.push({ key: 'delete', tip: 'common.action.delete', danger: true, perm: 'sales:template:edit' })
  return acts
}

function onRowAction(key: string, row: QuoteTemplate) {
  if (key === 'design') router.push(`/sales/templates/${row.id}/design`)
  else if (key === 'publish') void doPublish(row)
  else if (key === 'disable') void doDisable(row)
  else if (key === 'newVersion') void doNewVersion(row)
  else if (key === 'delete') void remove(row)
}

async function doPublish(row: QuoteTemplate) {
  try {
    await ElMessageBox.confirm(t('sales.template.publishConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await publishQuoteTemplate(row.id)
    ElMessage.success(t('common.message.saveSuccess'))
    void load()
  } catch {
    /* http notifies */
  }
}

async function doDisable(row: QuoteTemplate) {
  try {
    await ElMessageBox.confirm(t('sales.template.disableConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await disableQuoteTemplate(row.id)
    ElMessage.success(t('common.message.saveSuccess'))
    void load()
  } catch {
    /* http notifies */
  }
}

async function doNewVersion(row: QuoteTemplate) {
  try {
    await ElMessageBox.confirm(
      t('sales.template.newVersionConfirm', { n: row.tplVersion + 1 }),
      t('common.action.confirm'),
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    const nv = await newVersionQuoteTemplate(row.id)
    ElMessage.success(t('common.message.saveSuccess'))
    router.push(`/sales/templates/${nv.id}/design`)
  } catch {
    /* http notifies */
  }
}

async function remove(row: QuoteTemplate) {
  try {
    await ElMessageBox.confirm(t('sales.template.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteQuoteTemplate(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    void load()
  } catch {
    /* http notifies */
  }
}
</script>

<template>
  <ListPage :title="t('sales.template.title')" :loading="loading">
    <template #actions>
      <el-input
        v-model="keyword"
        :placeholder="t('common.form.placeholderInput')"
        clearable
        style="width: 220px"
      />
      <el-button v-permission="'sales:template:create'" type="primary" @click="router.push('/sales/templates/new')">
        {{ t('sales.template.create') }}
      </el-button>
    </template>

    <template #table>
      <el-table :data="filtered" v-loading="loading" row-key="id" border>
        <el-table-column prop="name" :label="t('sales.template.name')" min-width="180" />
        <el-table-column prop="key" :label="t('sales.template.key')" width="140" />
        <el-table-column :label="t('sales.template.tplVersion')" width="80" align="center">
          <template #default="{ row }">V{{ row.tplVersion }}</template>
        </el-table-column>
        <el-table-column :label="t('sales.quotation.status')" width="100" align="center">
          <template #default="{ row }">
            <StatusTag :status="row.status" i18n-prefix="sales.template.status" />
          </template>
        </el-table-column>
        <el-table-column prop="sort" :label="t('sales.template.sort')" width="80" align="center" />
        <el-table-column prop="publishedAt" :label="t('sales.template.publishedAt')" width="160" />
        <el-table-column :label="t('common.action.operate')" width="170" fixed="right" align="center" header-align="center">
          <template #default="{ row }">
            <ActionBar :actions="rowActions(row)" @select="(k) => onRowAction(k, row)" />
          </template>
        </el-table-column>
        <template #empty>{{ t('sales.template.empty') }}</template>
      </el-table>
    </template>
  </ListPage>
</template>
