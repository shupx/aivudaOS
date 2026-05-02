<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { buildApiPath } from '../../services/core/api'
import {
  NCard,
  NSpace,
  NText,
  NButton,
  NSwitch,
  NAvatar,
  NIcon,
  NTag
} from 'naive-ui'
import { Star } from 'lucide-vue-next'

const props = defineProps({
  app: { type: Object, required: true },
  busy: { type: Boolean, default: false },
  clickable: { type: Boolean, default: true },
  cardId: { type: String, default: '' },
  highlighted: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
  favorite: { type: Boolean, default: false },
})

const emit = defineEmits(['toggle-running', 'toggle-autostart', 'toggle-favorite'])
const router = useRouter()
const iconLoadFailed = ref(false)
const { t } = useI18n()

const description = computed(() => props.app.description || t('appCard.noDescription'))
const appDisplayName = computed(() => props.app.name || props.app.app_id)
const hasBuiltInUi = computed(() => Boolean(props.app.has_builtin_ui))
const builtInUiHref = computed(() => `/dashboard/apps/${encodeURIComponent(props.app.app_id)}/ui`)
const configButtonTitle = computed(() => t('appCard.openConfig', { name: appDisplayName.value }))
const favoriteTitle = computed(() => props.favorite ? t('appCard.unfavorite') : t('appCard.favorite'))
const iconSrc = computed(() => {
  if (iconLoadFailed.value) {
    return '/app-default-icon.png'
  }
  return buildApiPath(`/api/apps/${encodeURIComponent(props.app.app_id)}/icon`)
})

watch(
  () => props.app.app_id,
  () => {
    iconLoadFailed.value = false
  },
)

function onRunningChange(nextValue) {
  emit('toggle-running', props.app, nextValue)
}

function onAutostartChange(nextValue) {
  emit('toggle-autostart', props.app, nextValue)
}

function onFavoriteClick() {
  emit('toggle-favorite', props.app)
}

function goDetail() {
  if (!props.clickable) return
  router.push(`/dashboard/apps/${encodeURIComponent(props.app.app_id)}`)
}

function goConfigCenter(e) {
  e.stopPropagation()
  router.push({
    path: '/dashboard/apps/configs',
    query: { app_id: props.app.app_id },
  })
}

function goBuiltInUi() {
  if (!hasBuiltInUi.value) return
  router.push(builtInUiHref.value)
}

function onBuiltInUiClick(event) {
  if (!hasBuiltInUi.value) return
  if (event.defaultPrevented) return
  if (event.button !== 0) return
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return

  event.stopPropagation()
  event.preventDefault()
  goBuiltInUi()
}

function onIconError() {
  iconLoadFailed.value = true
}
</script>

<template>
  <NCard
    class="apps-app-card"
    :id="cardId || undefined"
    hoverable
    :style="{ borderColor: highlighted ? '#f59e0b' : undefined, borderWidth: highlighted ? '2px' : '1px', cursor: clickable ? 'pointer' : 'default', display: 'flex', flexDirection: 'column' }"
    :content-style="{ padding: '16px', display: 'flex', flexDirection: 'column', flex: 1, gap: '16px' }"
    @click="goDetail"
  >
    <button
      class="app-favorite-button"
      :class="{ 'app-favorite-button-active': favorite }"
      type="button"
      :title="favoriteTitle"
      :aria-label="favoriteTitle"
      :aria-pressed="favorite ? 'true' : 'false'"
      @click.stop="onFavoriteClick"
    >
      <NIcon class="app-favorite-icon" :size="15">
        <Star />
      </NIcon>
    </button>

    <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; padding-right: 26px;">
      <div style="display: flex; align-items: center; gap: 12px; min-width: 0;">
        <NAvatar
          :src="iconSrc"
          :size="compact ? 36 : 40"
          fallback-src="/app-default-icon.png"
          @error="onIconError"
          style="flex-shrink: 0; background-color: #f8fafc; border: 1px solid #e2e8f0;"
        />
        <div style="min-width: 0; display: flex; flex-direction: column;">
          <NText
            strong
            style="font-size: 16px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer;"
            :title="configButtonTitle"
            @click.stop="goConfigCenter"
            class="app-name-hover"
          >
            {{ appDisplayName }}
          </NText>
          <NText v-if="compact" depth="3" style="font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
            {{ app.active_version || '-' }}
          </NText>
        </div>
      </div>
      <div v-if="!compact" style="flex-shrink: 0;">
        <NTag type="info" size="small">{{ app.active_version || '-' }}</NTag>
      </div>
    </div>

    <div v-if="!compact" style="font-size: 13px; color: #475569; display: flex; flex-direction: column; gap: 4px; flex: 1;">
      <NText depth="3" style="font-size: 12px;">{{ app.app_id }}</NText>
      <div style="display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; text-overflow: ellipsis;">
        {{ description }}
      </div>
    </div>

    <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: auto;">
      <div style="min-width: 0;">
        <NButton
          v-if="hasBuiltInUi"
          size="small"
          tag="a"
          :href="builtInUiHref"
          @click.stop="onBuiltInUiClick"
        >
          {{ t('appCard.openBuiltInUi') }}
        </NButton>
      </div>
      <div style="display: flex; gap: 16px; align-items: center;">
        <div style="display: flex; flex-direction: column; align-items: center; gap: 4px;" @click.stop>
          <NText v-if="!compact" style="font-size: 12px;" depth="3">{{ t('appCard.start') }}</NText>
          <NSwitch
            :value="Boolean(app.running)"
            :disabled="busy"
            @update:value="onRunningChange"
            size="small"
            :theme-overrides="{ railColorActive: '#16a34a' }"
          />
        </div>
        <div style="display: flex; flex-direction: column; align-items: center; gap: 4px;" @click.stop>
          <NText v-if="!compact" style="font-size: 12px;" depth="3">{{ t('appCard.autostart') }}</NText>
          <NSwitch :value="Boolean(app.autostart)" :disabled="busy" @update:value="onAutostartChange" size="small">
             <template #checked-icon>
                A
             </template>
          </NSwitch>
        </div>
      </div>
    </div>
  </NCard>
</template>

<style scoped>
.apps-app-card {
  position: relative;
  overflow: hidden;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.apps-app-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 14px 28px rgba(15, 23, 42, 0.12);
}

.app-name-hover:hover {
  color: #2563eb;
  text-decoration: underline;
}

.app-favorite-button {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 2;
  width: 26px;
  height: 26px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  color: #cbd5e1;
  cursor: pointer;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color 0.16s ease, background-color 0.16s ease, box-shadow 0.16s ease;
}

.app-favorite-button-active {
  color: #f59e0b;
}

.app-favorite-button:hover,
.app-favorite-button:focus-visible {
  color: #f59e0b;
  background: rgba(245, 158, 11, 0.08);
}

.app-favorite-button:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.24);
}

.app-favorite-icon {
  display: flex;
}

.app-favorite-button-active .app-favorite-icon :deep(svg) {
  fill: currentColor;
}
</style>
