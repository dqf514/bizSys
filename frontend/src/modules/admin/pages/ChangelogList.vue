<script setup lang="ts">
/** 变更日志（Keep a Changelog + 语义化版本）：数据源 = 仓库根目录 CHANGELOG.md，由后端解析后返回。 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { getChangelog } from '@/api/admin'
import type { ChangelogPayload } from '@/api/types'
import PageHeader from '@/components/common/PageHeader.vue'

defineOptions({ name: 'ChangelogList' })

const { t, te } = useI18n()

const loading = ref(false)
const data = ref<ChangelogPayload | null>(null)

const releases = computed(() => data.value?.releases ?? [])
const currentVersion = computed(() => data.value?.currentVersion ?? '')

/** 分类 → 徽标配色（Element Plus 语义色，不硬编码色值） */
const TAG_TYPES: Record<string, 'primary' | 'success' | 'info' | 'warning' | 'danger'> = {
  added: 'success',
  changed: 'primary',
  deprecated: 'warning',
  removed: 'danger',
  fixed: 'info',
  security: 'danger',
}

function tagType(type: string) {
  return TAG_TYPES[type] ?? 'info'
}

/** 分类名走 i18n；未登记的分类回退显示原始名 */
function typeLabel(type: string) {
  const key = `admin.changelog.type.${type}`
  return te(key) ? t(key) : type
}

function releaseDate(date: string) {
  return date ? date : t('admin.changelog.unreleased')
}

async function load() {
  loading.value = true
  try {
    data.value = await getChangelog()
  } catch {
    /* http notifies */
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())
</script>

<template>
  <div v-loading="loading" class="bs-page bs-page--scroll">
    <PageHeader :title="t('admin.changelog.title')">
      <template #actions>
        <el-tag type="info" effect="plain">{{ t('admin.changelog.currentVersion') }} {{ currentVersion }}</el-tag>
      </template>
    </PageHeader>

    <div class="bs-page-card changelog-card">
      <p class="changelog-tip">{{ t('admin.changelog.specTip') }}</p>

      <el-empty v-if="!releases.length" :description="t('admin.changelog.empty')" />

      <el-timeline v-else>
        <el-timeline-item
          v-for="release in releases"
          :key="release.version"
          :timestamp="releaseDate(release.date)"
          placement="top"
          type="primary"
        >
          <div class="release-head">
            <span class="release-version">{{ release.version }}</span>
            <el-tag v-if="release.version === data?.latestVersion" type="success" size="small" effect="light">
              {{ t('admin.changelog.latest') }}
            </el-tag>
          </div>

          <section v-for="section in release.sections" :key="section.type" class="release-section">
            <el-tag :type="tagType(section.type)" size="small" effect="light" class="section-tag">
              {{ typeLabel(section.type) }}
            </el-tag>
            <ul class="section-items">
              <li v-for="(item, index) in section.items" :key="index">
                <span>{{ item.text }}</span>
                <ul v-if="item.children.length" class="sub-items">
                  <li v-for="(child, childIndex) in item.children" :key="childIndex">{{ child }}</li>
                </ul>
              </li>
            </ul>
          </section>
        </el-timeline-item>
      </el-timeline>
    </div>
  </div>
</template>

<style scoped>
.changelog-card {
  padding: var(--bs-space-4);
}

.changelog-tip {
  margin: 0 0 var(--bs-space-4);
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-sm);
  line-height: 1.7;
}

.release-head {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  margin-bottom: var(--bs-space-2);
}

.release-version {
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.release-section {
  margin-top: var(--bs-space-3);
}

.section-tag {
  margin-bottom: var(--bs-space-1);
}

.section-items {
  margin: 0;
  padding-left: var(--bs-space-5);
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-sm);
  line-height: 1.8;
}

.section-items > li {
  margin-bottom: var(--bs-space-1);
}

.sub-items {
  margin: var(--bs-space-1) 0 0;
  padding-left: var(--bs-space-4);
  color: var(--bs-color-fg-muted);
  list-style-type: circle;
}
</style>
