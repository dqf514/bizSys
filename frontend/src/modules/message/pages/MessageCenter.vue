<script setup lang="ts">
/**
 * 消息中心（CSV 第 30 项）：把站内通知（sys_notify）做成统一的收件箱。
 *
 * - 检索：q 关键词（标题/正文）
 * - 页签：全部 / 未读 / 按业务分类，每个页签带计数（all 最左）
 * - 已读：单条标为已读 / 全部标为已读
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar from '@/components/list/ActionBar.vue'
import { useListPage } from '@/composables/useListPage'
import { getNotifyCounts, listNotifies, markAllNotifiesRead, markNotifyRead } from '@/api/workbench'
import type { NotifyCounts, NotifyItem } from '@/api/types'

defineOptions({ name: 'MessageCenter' })

const { t } = useI18n()
const router = useRouter()

type Row = NotifyItem & Record<string, unknown>

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [{ key: 'q', labelKey: 'message.keyword', width: 240 }]

/** 页签取值：all | unread | biz:<biz_type> */
const activeTab = ref('all')
const counts = ref<NotifyCounts>({ all: 0, unread: 0, byBizType: {} })

const bizTypeOptions = computed(() =>
  Object.keys(counts.value.byBizType ?? {})
    .sort()
    .map((k) => ({ value: k, count: counts.value.byBizType[k] })),
)

const statusTabs = computed<StatusTabItem[]>(() => [
  { value: 'all', labelKey: 'message.tabAll', count: counts.value.all },
  { value: 'unread', labelKey: 'message.tabUnread', count: counts.value.unread },
  ...bizTypeOptions.value.map((o) => ({ value: `biz:${o.value}`, label: bizTypeLabel(o.value), count: o.count })),
])

function bizTypeLabel(bt: string): string {
  const key = `message.bizType.${bt}`
  const label = t(key)
  return label === key ? bt : label
}

const list = useListPage<Row>({
  fetch: async (params) => {
    const p = { ...params }
    // 页签 → 查询语义：unread 走 status，未读与业务分类互斥
    if (activeTab.value === 'unread') {
      p.status = 'unread'
    } else if (activeTab.value.startsWith('biz:')) {
      p.status = undefined
      p['filters[biz_type]'] = activeTab.value.slice(4)
    } else {
      p.status = undefined
    }
    p.q = searchModel.value.q || undefined
    const data = await listNotifies(p)
    return { items: (data.items ?? []) as unknown as Row[], total: data.total ?? 0 }
  },
  autoLoad: false,
  onLoaded: () => {
    void refreshCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'title', labelKey: 'message.colTitle', minWidth: 220, fixed: 'left' },
  { prop: 'content', labelKey: 'message.colContent', minWidth: 260, showOverflowTooltip: true },
  { prop: 'bizType', labelKey: 'message.colType', width: 120 },
  { prop: 'readFlag', labelKey: 'message.colStatus', width: 100 },
  { prop: 'createTime', labelKey: 'message.colTime', width: 170, sortable: 'create_time' },
]

async function refreshCounts() {
  try {
    counts.value = (await getNotifyCounts()) ?? { all: 0, unread: 0, byBizType: {} }
  } catch {
    counts.value = { all: 0, unread: 0, byBizType: {} }
  }
}

function switchTab(tab: string) {
  activeTab.value = tab
  list.query.page = 1
  list.refresh()
}

async function onRead(row: Row) {
  if (row.readFlag) {
    await gotoLink(row)
    return
  }
  try {
    await markNotifyRead(row.id)
    row.readFlag = true
    ElMessage.success(t('message.markedRead'))
    void refreshCounts()
  } catch {
    /* http notifies */
  }
}

async function onMarkAllRead() {
  try {
    await markAllNotifiesRead()
    ElMessage.success(t('message.markAllReadSuccess'))
    list.refresh()
    void refreshCounts()
  } catch {
    /* http notifies */
  }
}

function gotoLink(row: Row) {
  if (!row.link) return
  router.push(row.link)
}

/** 已读 → 只给"查看业务页"；未读 → 先给"标为已读"，标完自动跳转业务页 */
function rowActions(row: Row) {
  if (row.readFlag) {
    return [{ key: 'open', tip: 'common.action.view', icon: 'Link' }]
  }
  return [{ key: 'read', tip: 'message.markRead', icon: 'CircleCheck' }]
}

function onAction(row: Row, key: string) {
  if (key === 'read') void onRead(row)
  else gotoLink(row)
}

onMounted(() => {
  list.refresh()
  void refreshCounts()
})
</script>

<template>
  <ListPage :title="t('message.title')" :loading="list.loading.value">
    <template #actions>
      <el-button @click="onMarkAllRead">{{ t('message.markAllRead') }}</el-button>
      <el-button @click="list.refresh(); refreshCounts()">{{ t('common.action.refresh') }}</el-button>
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '' }; list.reset()"
      />
    </template>

    <template #statusTabs>
      <StatusTabs :tabs="statusTabs" :model-value="activeTab" @update:model-value="switchTab" />
    </template>

    <template #table>
      <ListTable
        :columns="columns"
        :data="list.items.value"
        :loading="list.loading.value"
        :total="list.total.value"
        :page="Number(list.query.page)"
        :size="Number(list.query.size)"
        row-key="id"
        @update:page="list.setPage"
        @update:size="list.setSize"
        @sort-change="list.onSortChange"
      >
        <template #title="{ row }">
          <el-button link type="primary" @click="onRead(row)">{{ row.title }}</el-button>
        </template>
        <template #bizType="{ row }">{{ bizTypeLabel(String(row.bizType)) }}</template>
        <template #readFlag="{ row }">
          <el-tag :type="row.readFlag ? 'info' : 'danger'" size="small" effect="plain">
            {{ row.readFlag ? t('message.read') : t('message.unread') }}
          </el-tag>
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="150" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar :actions="rowActions(row)" @select="(key: string) => onAction(row, key)" />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>
</template>
