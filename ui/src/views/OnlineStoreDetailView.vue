<script setup>
import { useI18n } from 'vue-i18n'
import { useOnlineStoreDetailPage } from '../composables/useOnlineStoreDetailPage'

const { t } = useI18n()

const {
  appId,
  loading,
  error,
  actionError,
  actionMessage,
  appInfo,
  versions,
  downloadingByVersion,
  installingByVersion,
  load,
  downloadVersion,
  installVersion,
  backToStore,
  isVersionDownloaded,
} = useOnlineStoreDetailPage()
</script>

<template>
  <section class="apps-panel">
    <header class="panel-header">
      <h2>{{ t('store.detailTitle') }}</h2>
      <div class="panel-actions">
        <button class="btn" @click="backToStore">{{ t('store.backToStore') }}</button>
        <button class="btn btn-stable-refresh" :disabled="loading" @click="load">
          {{ loading ? t('common.loadingShort') : t('common.refresh') }}
        </button>
      </div>
    </header>

    <article class="log-panel">
      <h3>{{ appInfo?.name || appId }}</h3>
      <p class="muted">app_id: {{ appId }}</p>
      <p class="muted">{{ appInfo?.description || t('store.noDescription') }}</p>
    </article>

    <p v-if="error" class="error-text">{{ error }}</p>
    <p v-if="actionError" class="error-text">{{ actionError }}</p>
    <p v-if="actionMessage" class="ok-text">{{ actionMessage }}</p>

    <div v-if="!versions.length && !loading" class="empty-box">
      {{ t('store.emptyVersions') }}
    </div>

    <div class="store-version-grid">
      <article class="action-block" v-for="version in versions" :key="version.version">
        <h4>v{{ version.version }}</h4>
        <p class="muted">{{ version.description || t('store.noDescription') }}</p>
        <p class="muted">{{ t('store.updatedAt') }}: {{ version.updated_at || '-' }}</p>
        <p class="muted">{{ t('store.size') }}: {{ version.artifact_size || 0 }}</p>

        <div class="panel-actions wrap">
          <button
            class="btn"
            :disabled="Boolean(downloadingByVersion[version.version])"
            @click="downloadVersion(version.version)"
          >
            {{ downloadingByVersion[version.version] ? t('store.downloading') : t('store.download') }}
          </button>
          <button
            class="btn primary"
            :disabled="Boolean(installingByVersion[version.version]) || !isVersionDownloaded(version.version)"
            @click="installVersion(version.version)"
          >
            {{ installingByVersion[version.version] ? t('store.installing') : t('store.install') }}
          </button>
        </div>

        <p class="muted" v-if="isVersionDownloaded(version.version)">
          {{ t('store.downloadedTag') }}
        </p>
      </article>
    </div>
  </section>
</template>
