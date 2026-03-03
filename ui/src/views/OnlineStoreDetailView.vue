<script setup>
import { useI18n } from 'vue-i18n'
import UploadInstallModal from '../components/apps/UploadInstallModal.vue'
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
  actingByVersion,
  localDownloadingByVersion,
  getDownloadProgress,
  load,
  downloadAndInstallVersion,
  downloadPackageToLocal,
  backToStore,
  showUploadModal,
  uploadBusy,
  uploadError,
  uploadStatus,
  uploadStatusDone,
  uploadOutput,
  uploadFileName,
  uploadHint,
  uploadShowFilePicker,
  closeUploadModal,
  onUploadFileChange,
  submitUpload,
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
        <h4>{{ version.version }}</h4>
        <p class="muted">{{ version.description || t('store.noDescription') }}</p>
        <p class="muted">{{ t('store.updatedAt') }}: {{ version.updated_at_display || '-' }}</p>
        <p class="muted">{{ t('store.size') }}: {{ version.artifact_size_display || '0 kB' }}</p>

        <div class="panel-actions wrap">
          <button
            class="btn primary"
            :disabled="Boolean(actingByVersion[version.version])"
            @click="downloadAndInstallVersion(version.version)"
          >
            {{ actingByVersion[version.version] ? t('common.processing') : t('store.downloadAndInstall') }}
          </button>
          <button
            class="btn"
            :title="t('store.downloadLocalTooltip')"
            :aria-label="t('store.downloadLocalTooltip')"
            :disabled="Boolean(localDownloadingByVersion[version.version])"
            @click="downloadPackageToLocal(version.version)"
          >
            {{ localDownloadingByVersion[version.version] ? t('common.processing') : '⬇' }}
          </button>
        </div>

        <div v-if="getDownloadProgress(version.version) > 0" class="download-progress">
          <div class="download-progress-track">
            <div
              class="download-progress-bar"
              :style="{ width: `${getDownloadProgress(version.version)}%` }"
            ></div>
          </div>
          <p class="muted">{{ t('store.downloadProgress', { percent: getDownloadProgress(version.version) }) }}</p>
        </div>
      </article>
    </div>

    <UploadInstallModal
      :visible="showUploadModal"
      :busy="uploadBusy"
      :error="uploadError"
      :status="uploadStatus"
      :status-done="uploadStatusDone"
      :output="uploadOutput"
      :file-name="uploadFileName"
      :hint="uploadHint"
      :show-file-picker="uploadShowFilePicker"
      @close="closeUploadModal"
      @file-change="onUploadFileChange"
      @submit="submitUpload"
    />
  </section>
</template>
