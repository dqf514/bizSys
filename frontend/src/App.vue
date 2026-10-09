<script setup lang="ts">
import { onMounted } from 'vue'
import { useThemeStore } from '@/stores/theme'
import { useAuthStore } from '@/stores/auth'
import { useHotkeys } from '@/composables/useHotkeys'

const theme = useThemeStore()
const auth = useAuthStore()
useHotkeys()

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
