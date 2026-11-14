<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ChatDotRound, Close } from '@element-plus/icons-vue'
import { aiAssistantChat } from '@/api/ai'
import { useAiCapabilities } from '@/composables/useAiCapabilities'
import { useAuthStore } from '@/stores/auth'
import { useIsMobile } from '@/composables/useIsMobile'
import type { AssistantReply, MenuNode } from '@/api/types'

defineOptions({ name: 'AiAssistant' })

interface ChatMsg {
  role: 'user' | 'ai'
  text: string
  reply?: AssistantReply
}

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const aiCaps = useAiCapabilities()
const { isMobile } = useIsMobile()

const open = ref(false)
const sending = ref(false)
const input = ref('')
const msgs = ref<ChatMsg[]>([])
const listRef = ref<HTMLElement | null>(null)

onMounted(() => void aiCaps.ensureLoaded())

/** 本地化菜单候选：title 用 i18n 解析，path 供服务端与权限菜单树取交集 */
function flattenMenus(nodes: MenuNode[], out: { title: string; path: string }[] = []) {
  for (const n of nodes) {
    if (n.menuType === 'menu' && n.path) {
      out.push({ title: n.titleKey ? t(n.titleKey) : n.name, path: n.path })
    }
    if (n.children?.length) flattenMenus(n.children, out)
  }
  return out
}

// 深链静态路由（不占菜单，与后端 STATIC_PATHS 对齐）
const STATIC_LINKS = [
  { titleKey: 'menu.workbench', path: '/workbench' },
  { titleKey: 'menu.approval', path: '/approval' },
  { titleKey: 'menu.knowledgeAsk', path: '/ai/knowledge' },
]

const menuCandidates = computed(() => {
  const out = flattenMenus(auth.menus)
  for (const s of STATIC_LINKS) {
    if (!out.some((m) => m.path === s.path)) out.push({ title: t(s.titleKey), path: s.path })
  }
  return out
})

const TYPE_TAG: Record<string, string> = {
  query: 'ai.assistant.typeQuery',
  navigate: 'ai.assistant.typeNavigate',
  guide: 'ai.assistant.typeGuide',
}

async function scrollBottom() {
  await nextTick()
  listRef.value?.scrollTo({ top: listRef.value.scrollHeight })
}

async function send() {
  const q = input.value.trim()
  if (!q || sending.value) return
  msgs.value.push({ role: 'user', text: q })
  input.value = ''
  sending.value = true
  await scrollBottom()
  try {
    const reply = await aiAssistantChat(q, menuCandidates.value)
    msgs.value.push({ role: 'ai', text: reply.text, reply })
  } catch {
    msgs.value.pop()
  } finally {
    sending.value = false
    await scrollBottom()
  }
}

function goto(reply: AssistantReply) {
  if (!reply.path) return
  open.value = false
  router.push(reply.path)
}
</script>

<template>
  <button
    type="button"
    class="ai-assistant-entry"
    :class="{ mobile: isMobile }"
    :aria-label="t('ai.assistant.entry')"
    @click="open = !open"
  >
    <el-icon :size="22"><ChatDotRound /></el-icon>
  </button>

  <Teleport to="body">
    <div v-if="open" class="ai-assistant-panel" :class="{ mobile: isMobile }" role="dialog">
      <div class="panel-head">
        <span class="panel-title">{{ t('ai.assistant.title') }}</span>
        <el-button link class="panel-kb" @click="open = false; router.push('/ai/knowledge')">
          {{ t('ai.assistant.gotoKnowledge') }}
        </el-button>
        <el-icon class="panel-close" @click="open = false"><Close /></el-icon>
      </div>

      <div ref="listRef" class="panel-body">
        <div v-if="!msgs.length" class="panel-empty">{{ t('ai.assistant.empty') }}</div>
        <div v-for="(m, i) in msgs" :key="i" class="msg" :class="m.role">
          <div class="msg-bubble">
            <el-tag v-if="m.reply" size="small" effect="plain" class="msg-type">
              {{ t(TYPE_TAG[m.reply.type] ?? 'ai.assistant.typeGuide') }}
            </el-tag>
            <template v-if="m.reply?.type === 'navigate'">
              <span>{{ t('ai.assistant.navConfirm', { name: m.reply.menuName }) }}</span>
              <el-button size="small" type="primary" class="msg-goto" @click="goto(m.reply!)">
                {{ t('ai.assistant.goto') }}
              </el-button>
            </template>
            <template v-else-if="m.reply?.type === 'query' && m.reply.data">
              <div class="msg-text">{{ m.reply.data.text }}</div>
              <div v-for="(row, j) in m.reply.data.rows" :key="j" class="msg-row">
                <span>{{ row.label }}</span>
                <span class="msg-row-value">{{ row.value }}</span>
              </div>
              <el-button
                v-if="m.reply.data.link"
                link
                type="primary"
                size="small"
                class="msg-goto"
                @click="goto({ ...m.reply!, path: m.reply!.data!.link })"
              >
                {{ t('ai.assistant.goto') }}
              </el-button>
            </template>
            <template v-else>
              <div v-if="m.text" class="msg-text">{{ m.text }}</div>
              <template v-if="m.reply?.entries?.length">
                <div v-for="e in m.reply.entries" :key="e.id" class="msg-entry">
                  <div class="msg-entry-title">{{ e.title }}</div>
                  <div class="msg-entry-excerpt">{{ e.excerpt }}</div>
                </div>
              </template>
              <div v-if="m.reply?.sources?.length" class="msg-sources">
                {{ t('ai.assistant.sources') }}：{{ m.reply.sources.map((s) => s.title).join('、') }}
              </div>
            </template>
          </div>
        </div>
        <div v-if="sending" class="msg ai">
          <div class="msg-bubble">…</div>
        </div>
      </div>

      <div class="panel-foot">
        <el-input
          v-model="input"
          :placeholder="t('ai.assistant.placeholder')"
          clearable
          @keyup.enter="send"
        />
        <el-button type="primary" :loading="sending" :disabled="!input.trim()" @click="send">
          {{ t('ai.assistant.send') }}
        </el-button>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.ai-assistant-entry {
  position: fixed;
  right: var(--bs-space-5);
  bottom: calc(var(--bs-layout-statusbar-height) + var(--bs-space-5));
  z-index: 900;
  width: 48px;
  height: 48px;
  border: none;
  border-radius: var(--bs-radius-full);
  background: var(--bs-color-brand-primary);
  color: var(--bs-color-brand-on-primary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--bs-shadow-elevation);
  transition: transform var(--bs-motion-fast) var(--bs-motion-curve);
}

.ai-assistant-entry:hover {
  transform: translateY(-2px);
}

/* 移动端：上移避开底部 Dock（56px + 安全区） */
.ai-assistant-entry.mobile {
  bottom: calc(56px + env(safe-area-inset-bottom) + var(--bs-space-4));
}

.ai-assistant-panel {
  position: fixed;
  right: var(--bs-space-5);
  bottom: calc(var(--bs-layout-statusbar-height) + var(--bs-space-5) + 56px);
  z-index: 901;
  width: 360px;
  max-width: calc(100vw - 2 * var(--bs-space-4));
  height: 480px;
  max-height: 70vh;
  display: flex;
  flex-direction: column;
  background: var(--bs-color-bg-surface);
  border: 1px solid var(--bs-color-border-default);
  border-radius: var(--bs-radius-lg);
  box-shadow: var(--bs-shadow-elevation);
  overflow: hidden;
}

.ai-assistant-panel.mobile {
  right: var(--bs-space-3);
  left: var(--bs-space-3);
  width: auto;
  bottom: calc(56px + env(safe-area-inset-bottom) + var(--bs-space-4) + 56px);
}

.panel-head {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  padding: var(--bs-space-2) var(--bs-space-3);
  border-bottom: 1px solid var(--bs-color-border-subtle);
}

.panel-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.panel-kb {
  margin-left: auto;
}

.panel-close {
  cursor: pointer;
  color: var(--bs-color-fg-muted);
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--bs-space-3);
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.panel-empty {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
  text-align: center;
  margin-top: var(--bs-space-6);
}

.msg {
  display: flex;
}

.msg.user {
  justify-content: flex-end;
}

.msg-bubble {
  max-width: 85%;
  padding: var(--bs-space-2) var(--bs-space-3);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-app);
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-default);
  line-height: 1.6;
}

.msg.user .msg-bubble {
  background: var(--bs-color-brand-primary);
  color: var(--bs-color-brand-on-primary);
}

.msg-type {
  margin-bottom: var(--bs-space-1);
}

.msg-goto {
  margin-top: var(--bs-space-1);
}

.msg-row {
  display: flex;
  justify-content: space-between;
  gap: var(--bs-space-3);
}

.msg-row-value {
  font-weight: 600;
}

.msg-sources {
  margin-top: var(--bs-space-1);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.msg-entry {
  margin-top: var(--bs-space-1);
  padding: var(--bs-space-1) var(--bs-space-2);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-sm);
}

.msg-entry-title {
  font-weight: 600;
}

.msg-entry-excerpt {
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-xs);
}

.panel-foot {
  display: flex;
  gap: var(--bs-space-2);
  padding: var(--bs-space-2) var(--bs-space-3);
  border-top: 1px solid var(--bs-color-border-subtle);
}
</style>
