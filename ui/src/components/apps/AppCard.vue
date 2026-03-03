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
})

const emit = defineEmits(['toggle-running', 'toggle-autostart'])
const router = useRouter()
const iconLoadFailed = ref(false)
const { t } = useI18n()

const description = computed(() => props.app.description || t('appCard.noDescription'))
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

function onIconError() {
  iconLoadFailed.value = true
}
</script>

<template>
  <article
    class="app-card"
    :class="{ 'card-clickable': clickable }"
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
      <span class="app-version">{{ app.active_version || '-' }}</span>
    </header>

    <div class="app-meta">
      <p><strong>{{ t('appCard.appId') }}:</strong> {{ app.app_id }}</p>
      <p><strong>{{ t('appCard.description') }}:</strong> {{ description }}</p>
      <p><strong>{{ t('appCard.status') }}:</strong> {{ app.running ? t('appCard.running') : t('appCard.stopped') }}</p>
    </div>

    <div class="switch-row">
      <div class="switch-item" @click.stop>
        <span>{{ t('appCard.start') }}</span>
        <SwitchToggle :model-value="Boolean(app.running)" :disabled="busy" @update:model-value="onRunningChange" />
      </div>

      <div class="switch-item" @click.stop>
        <span>{{ t('appCard.autostart') }}</span>
        <SwitchToggle :model-value="Boolean(app.autostart)" :disabled="busy" @update:model-value="onAutostartChange" />
      </div>
    </div>
  </article>
</template>
