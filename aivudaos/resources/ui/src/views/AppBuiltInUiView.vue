<script setup>
import { useI18n } from 'vue-i18n'
import { useAppBuiltInUiPage } from '../composables/useAppBuiltInUiPage'

const { t } = useI18n()

const {
  appId,
  uiSrc,
  frameError,
  onFrameLoad,
  onFrameError,
  reloadFrame,
  backToApps,
  backToDetail,
} = useAppBuiltInUiPage()
</script>

<template>
  <section class="apps-panel">
    <header class="panel-header">
      <h2>{{ t('appBuiltInUi.title', { appId }) }}</h2>
      <div class="panel-actions wrap">
        <button class="btn" @click="backToApps">{{ t('appBuiltInUi.backToApps') }}</button>
        <button class="btn" @click="backToDetail">{{ t('appBuiltInUi.backToDetail') }}</button>
        <button class="btn btn-stable-refresh" @click="reloadFrame">{{ t('appBuiltInUi.reload') }}</button>
      </div>
    </header>

    <p v-if="frameError" class="error-text">{{ frameError }}</p>

    <article class="app-ui-frame-wrap">
      <iframe
        v-if="uiSrc"
        :src="uiSrc"
        class="app-ui-frame"
        :title="t('appBuiltInUi.iframeTitle', { appId })"
        @load="onFrameLoad"
        @error="onFrameError"
      />
    </article>

    <p class="muted">
      {{ t('appBuiltInUi.openDirectlyHint') }}
      <a :href="uiSrc" target="_blank" rel="noopener noreferrer">{{ t('appBuiltInUi.openDirectly') }}</a>
    </p>
  </section>
</template>
