<script setup lang="ts">
/** 作业申请流程（CSV 第 32 项） —— 需求尚未开工，先以需求登记页占位（可追溯回需求原文条目）。 */
import PlannedFeature from '@/modules/common/pages/PlannedFeature.vue'

defineOptions({ name: 'WorkApplyList' })
</script>

<template>
  <PlannedFeature feature="workApplyList" />
</template>
