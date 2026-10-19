<script setup lang="ts">
/** OA 统计看板（用户侧）：统计面板共用组件 + /oa/stats 数据源。 */
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import StatsPanel from '@/modules/oa/components/StatsPanel.vue'
import { getOaStats } from '@/api/oa'
import type { OaStats } from '@/api/types'

defineOptions({ name: 'StatsBoard' })

const { t } = useI18n()
const stats = ref<OaStats | null>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    stats.value = await getOaStats()
  } catch {
    /* http notifies */
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <ListPage :title="t('oa.stats.title')" :loading="loading">
    <template #actions>
      <el-button @click="load">{{ t('common.action.refresh') }}</el-button>
    </template>
    <StatsPanel :stats="stats" />
  </ListPage>
</template>
