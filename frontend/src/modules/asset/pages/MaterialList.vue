<script setup lang="ts">
/** 物料台账（CSV 第 23 项） —— 需求尚未开工，先以需求登记页占位（可追溯回需求原文条目）。 */
import PlannedFeature from '@/modules/common/pages/PlannedFeature.vue'

defineOptions({ name: 'MaterialList' })
</script>

<template>
  <PlannedFeature feature="materialList" />
</template>
