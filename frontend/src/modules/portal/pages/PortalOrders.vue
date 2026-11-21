<script setup lang="ts">
/** 在线任务委托（CSV 第 5 项） —— 需求尚未开工，先以需求登记页占位（可追溯回需求原文条目）。 */
import PlannedFeature from '@/modules/common/pages/PlannedFeature.vue'

defineOptions({ name: 'PortalOrders' })
</script>

<template>
  <PlannedFeature feature="portalOrders" />
</template>
