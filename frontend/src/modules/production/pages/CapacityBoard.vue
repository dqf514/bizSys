<script setup lang="ts">
/** 产能利用率看板（CSV 第 4 项） —— 需求尚未开工，先以需求登记页占位（可追溯回需求原文条目）。 */
import PlannedFeature from '@/modules/common/pages/PlannedFeature.vue'

defineOptions({ name: 'CapacityBoard' })
</script>

<template>
  <PlannedFeature feature="capacityBoard" />
</template>
