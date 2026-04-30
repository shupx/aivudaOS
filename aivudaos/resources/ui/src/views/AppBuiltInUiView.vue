<script setup>
import { useI18n } from 'vue-i18n'
import { NButton, NButtonGroup, NIcon } from 'naive-ui'
import { LayoutGrid, FileText, RefreshCw } from 'lucide-vue-next'
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
      <div class="built-in-ui-actions">
        <NButtonGroup class="built-in-ui-action-group">
          <NButton class="built-in-ui-action-btn" @click="backToApps">
            <template #icon>
              <NIcon><LayoutGrid /></NIcon>
            </template>
            <span class="built-in-ui-action-label">{{ t('appBuiltInUi.backToApps') }}</span>
          </NButton>
          <NButton class="built-in-ui-action-btn" @click="backToDetail">
            <template #icon>
              <NIcon><FileText /></NIcon>
            </template>
            <span class="built-in-ui-action-label">{{ t('appBuiltInUi.backToDetail') }}</span>
          </NButton>
          <NButton class="built-in-ui-action-btn built-in-ui-refresh-btn" @click="reloadFrame">
            <template #icon>
              <NIcon><RefreshCw /></NIcon>
            </template>
            <span class="built-in-ui-action-label">{{ t('appBuiltInUi.reload') }}</span>
          </NButton>
        </NButtonGroup>
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

<style scoped>
.panel-header {
  flex-wrap: wrap;
  align-items: flex-start;
}

.built-in-ui-actions {
  display: flex;
  justify-content: flex-end;
  flex: 0 1 auto;
  min-width: 0;
}

.built-in-ui-action-group {
  display: inline-flex;
  flex-wrap: nowrap;
  justify-content: flex-end;
  max-width: 100%;
  border-radius: 14px;
  padding: 1px;
  background: rgba(148, 163, 184, 0.22);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
}

.built-in-ui-action-btn {
  min-width: 0;
}

.built-in-ui-action-label {
  display: inline-block;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.built-in-ui-action-group :deep(.n-button) {
  min-width: 0;
}

.built-in-ui-action-group :deep(.n-button__content) {
  min-width: 0;
  max-width: 100%;
}

.built-in-ui-action-group :deep(.n-button:first-child) {
  border-top-left-radius: 13px;
  border-bottom-left-radius: 13px;
}

.built-in-ui-action-group :deep(.n-button:last-child) {
  border-top-right-radius: 13px;
  border-bottom-right-radius: 13px;
}

.built-in-ui-refresh-btn :deep(.n-icon) {
  transition: transform 0.2s ease;
}

.built-in-ui-refresh-btn:hover :deep(.n-icon) {
  transform: rotate(90deg);
}

@media (max-width: 760px) {
  .built-in-ui-actions {
    width: 100%;
    justify-content: flex-start;
  }

  .built-in-ui-action-group {
    width: 100%;
    justify-content: flex-start;
  }

  .built-in-ui-action-group :deep(.n-button) {
    flex: 1 1 0;
  }
}
</style>
