<script setup>
import { useI18n } from 'vue-i18n'
import { appConfigLocation, appDetailPath, appIconUrl } from '../../utils/appLinks'

defineProps({ app: { type: Object, required: true }, busy: Boolean })
defineEmits(['toggle-running'])
const { t } = useI18n()
</script>

<template>
  <article class="station-card" :class="{ active: app.running }" :aria-busy="busy">
    <RouterLink class="station-card-title" :to="appDetailPath(app.app_id)" :title="app.name || app.app_id">
      <img :src="appIconUrl(app.app_id)" alt="">
      <strong>{{ app.name || app.app_id }}</strong>
    </RouterLink>
    <div class="station-card-meta">
      <span>{{ busy ? t('apps.boardBusy') : t(app.running ? 'appCard.running' : 'appCard.stopped') }}</span>
      <small>{{ app.active_version }}</small>
    </div>
    <div class="station-card-actions">
      <button type="button" :disabled="busy" @click="$emit('toggle-running', app, !app.running)">{{ t(app.running ? 'apps.boardStop' : 'appCard.start') }}</button>
      <RouterLink :to="appConfigLocation(app.app_id)">{{ t('apps.boardConfig') }}</RouterLink>
    </div>
  </article>
</template>
