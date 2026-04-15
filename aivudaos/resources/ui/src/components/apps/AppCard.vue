<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import SwitchToggle from './SwitchToggle.vue'
import { buildApiPath } from '../../services/core/api'

const props = defineProps({
  app: { type: Object, required: true },
  busy: { type: Boolean, default: false },
  clickable: { type: Boolean, default: true },
  cardId: { type: String, default: '' },
  highlighted: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
})

const emit = defineEmits(['toggle-running', 'toggle-autostart'])
const router = useRouter()
const iconLoadFailed = ref(false)
const { t } = useI18n()

const description = computed(() => props.app.description || t('appCard.noDescription'))
const hasBuiltInUi = computed(() => Boolean(props.app.has_builtin_ui))
const builtInUiHref = computed(() => `/dashboard/apps/${encodeURIComponent(props.app.app_id)}/ui`)
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

function goDetail() {
  if (!props.clickable) return
  router.push(`/dashboard/apps/${encodeURIComponent(props.app.app_id)}`)
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

  event.preventDefault()
  goBuiltInUi()
}

function onIconError() {
  iconLoadFailed.value = true
}
</script>

<template>
  <article
    :id="cardId || undefined"
    class="app-card"
    :class="{ 'card-clickable': clickable, 'app-card-highlighted': highlighted, 'app-card-compact': compact }"
    :tabindex="clickable ? 0 : -1"
    @click="goDetail"
    @keydown.enter.prevent="goDetail"
    @keydown.space.prevent="goDetail"
  >
    <header class="app-card-header">
      <div class="app-title-wrap">
        <img
          class="app-icon"
          :src="iconSrc"
          :alt="t('appCard.iconAlt')"
          @error="onIconError"
        >
        <h3>{{ app.name || app.app_id }}</h3>
      </div>
      <div class="app-header-actions">
        <span class="app-version">{{ app.active_version || '-' }}</span>
      </div>
    </header>

    <div v-if="!compact" class="app-meta">
      <p><strong>{{ t('appCard.appId') }}:</strong> {{ app.app_id }}</p>
      <p><strong>{{ t('appCard.description') }}:</strong> {{ description }}</p>
      <p><strong>{{ t('appCard.status') }}:</strong> {{ app.running ? t('appCard.running') : t('appCard.stopped') }}</p>
    </div>

    <div class="app-card-footer">
      <a
        v-if="hasBuiltInUi"
        class="app-ui-text-btn"
        :href="builtInUiHref"
        :title="t('appCard.openBuiltInUi')"
        :aria-label="t('appCard.openBuiltInUi')"
        @click.stop="onBuiltInUiClick"
      >
        {{ t('appCard.openBuiltInUi') }}
      </a>

      <div class="switch-row">
        <div class="switch-item" @click.stop>
          <span v-if="!compact">{{ t('appCard.start') }}</span>
          <SwitchToggle :model-value="Boolean(app.running)" :disabled="busy" @update:model-value="onRunningChange" />
        </div>

        <div class="switch-item switch-item-autostart" @click.stop>
          <span v-if="!compact">{{ t('appCard.autostart') }}</span>
          <SwitchToggle :model-value="Boolean(app.autostart)" :disabled="busy" @update:model-value="onAutostartChange" />
        </div>
      </div>
    </div>
  </article>
</template>
