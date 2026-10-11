<script setup lang="ts">
import { onMounted } from 'vue'
import { useThemeStore } from '@/stores/theme'
import { useAuthStore } from '@/stores/auth'
import { useHotkeys } from '@/composables/useHotkeys'
import { useDocumentTitle } from '@/composables/useDocumentTitle'

const theme = useThemeStore()
const auth = useAuthStore()
useHotkeys()
useDocumentTitle()

onMounted(() => {
  theme.applyToDocument()
  void auth.tryRestore()
})
</script>

<template>
  <el-config-provider :locale="theme.elementLocale">
    <router-view />
  </el-config-provider>
</template>
