<script setup lang="ts">
/** 页面级统一返回按钮：左上标题区右侧放置，带 ← 图标；to 优先于 click。 */
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { Back } from '@element-plus/icons-vue'

defineOptions({ name: 'BackButton' })

const props = defineProps<{ to?: string }>()
const emit = defineEmits<{ (e: 'click'): void }>()

const { t } = useI18n()
const router = useRouter()

function onClick() {
  if (props.to) {
    router.push(props.to)
    return
  }
  emit('click')
}
</script>

<template>
  <el-button class="back-button" :icon="Back" @click="onClick">{{ t('common.action.back') }}</el-button>
</template>
