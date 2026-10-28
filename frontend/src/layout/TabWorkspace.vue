<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useTabsStore } from '@/stores/tabs'
import ShortcutBar from './ShortcutBar.vue'

const route = useRoute()
const tabsStore = useTabsStore()

const includeNames = computed(() =>
  tabsStore.tabs.filter((tab) => tab.keepAlive && tab.componentName).map((tab) => tab.componentName as string),
)

// scroll restore for list pages (keyed by tab.key, matching tabs store)
const scrollRef = ref<HTMLElement>()

function currentTabKey() {
  return (route.meta?.tabKey as string) || route.path
}

function rememberScroll() {
  const el = scrollRef.value
  if (!el) return
  tabsStore.updateScroll(currentTabKey(), el.scrollTop)
}

function restoreScroll() {
  nextTick(() => {
    const el = scrollRef.value
    if (el) el.scrollTop = tabsStore.getScroll(currentTabKey())
  })
}

onMounted(() => {
  restoreScroll()
})

watch(
  () => route.path,
  () => {
    restoreScroll()
  },
)
</script>

<template>
  <div class="tab-workspace">
    <ShortcutBar />

    <div ref="scrollRef" class="tab-content" @scroll.passive="rememberScroll">
      <router-view v-slot="{ Component }">
        <!-- 不用 Transition 包 KeepAlive：路由重建后 out-in 状态机会卡死导致空白；
             入场动效改为组件根节点的 CSS 动画（见 motion.css .page-anim） -->
        <KeepAlive :include="includeNames">
          <component :is="Component" :key="route.path" class="page-anim" />
        </KeepAlive>
      </router-view>
    </div>
  </div>
</template>

<style scoped>
.tab-workspace {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.tab-content {
  flex: 1;
  min-height: 0;
  overflow: auto;
  background: var(--bs-color-bg-app);
}

/* 移动端：底部 Dock（56px + 安全区）遮挡留白 */
@media (max-width: 767px) {
  .tab-content {
    padding-bottom: calc(64px + env(safe-area-inset-bottom));
  }
}
</style>
