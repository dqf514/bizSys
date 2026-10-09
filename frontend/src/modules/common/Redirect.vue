<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

onMounted(() => {
  const raw = String(route.params.path ?? '')
  const path = raw.startsWith('/') ? raw : `/${raw}`
  router.replace({ path, query: route.query })
})
</script>

<template>
  <div class="redirect-page" />
</template>
