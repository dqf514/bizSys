<script setup lang="ts">
/**
 * 需求登记占位页。
 *
 * 新模块入口在功能开工前先落到这里：展示该入口对应的需求条目
 * （编号 / 名称 / 详细要求 / 计划批次 / 状态），使导航里的"待开工"入口
 * 不是 404，而是可追溯回需求原文的占位。
 *
 * 需求描述是中文文案 → 全部走 i18n（scan:literal --strict 拦截 .vue 里的 CJK 字面量），
 * 条目内容维护在 src/locales/{zh-CN,en-US}/planned.json 的 items 下。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import PageHeader from '@/components/common/PageHeader.vue'

defineOptions({ name: 'PlannedFeature' })

const props = defineProps<{ feature: string }>()
const { t } = useI18n()

function field(name: string): string {
  return t(`planned.items.${props.feature}.${name}`)
}

const itemNo = computed(() => field('no'))
const itemName = computed(() => field('name'))
const itemDesc = computed(() => field('desc'))
const itemBatch = computed(() => field('batch'))
const itemStatus = computed(() => field('status'))

const statusLabel = computed(() => t(`planned.status.${itemStatus.value}`))
const statusType = computed(() => {
  if (itemStatus.value === 'done') return 'success'
  if (itemStatus.value === 'inProgress') return 'warning'
  return 'info'
})
</script>

<template>
  <div class="bs-page bs-page--scroll">
    <PageHeader :title="itemName" />

    <div class="bs-page-card planned-card">
      <el-descriptions :column="1" border>
        <el-descriptions-item :label="t('planned.labels.no')">{{ itemNo }}</el-descriptions-item>
        <el-descriptions-item :label="t('planned.labels.status')">
          <el-tag :type="statusType" size="small" effect="plain">{{ statusLabel }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('planned.labels.batch')">{{ itemBatch }}</el-descriptions-item>
      </el-descriptions>

      <div class="planned-desc-title">{{ t('planned.labels.desc') }}</div>
      <p class="planned-desc">{{ itemDesc }}</p>
    </div>
  </div>
</template>

<style scoped>
.planned-card {
  max-width: var(--bs-layout-form-max-width);
}

.planned-desc-title {
  margin-top: var(--bs-space-3);
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.planned-desc {
  margin: var(--bs-space-2) 0 0;
  white-space: pre-wrap;
  line-height: 1.7;
  color: var(--bs-color-fg-secondary);
}
</style>
