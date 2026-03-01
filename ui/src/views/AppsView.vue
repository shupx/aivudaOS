<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppCard from '../components/apps/AppCard.vue'
import { useDomAppendLog } from '../composables/useDomAppendLog'
import { useAppsPanel } from '../composables/useAppsPanel'

const { t } = useI18n()

const {
  apps,
  loading,
  error,
  refresh,
  busyById,
  toggleRunning,
  toggleAutostart,
  showUploadModal,
  uploadBusy,
  uploadError,
  uploadStatus,
  uploadStatusDone,
  uploadOutput,
  uploadFileName,
  openUploadModal,
  closeUploadModal,
  onUploadFileChange,
  submitUpload,
} = useAppsPanel()

const uploadLogPlaceholder = computed(() => t('apps.waitingOutput'))

const {
  logRef: uploadLogRef,
  onLogScroll: onUploadLogScroll,
} = useDomAppendLog(uploadOutput, {
  visibleRef: showUploadModal,
  placeholderRef: uploadLogPlaceholder,
})
</script>

<template>
  <section class="apps-panel">
    <header class="panel-header">
      <div class="panel-actions panel-title-actions">
        <h2>{{ t('apps.title') }}</h2>
        <button class="btn btn-stable-refresh" :disabled="loading" @click="refresh">
          {{ loading ? t('common.refreshing') : t('common.refresh') }}
        </button>
      </div>
      <div class="panel-actions wrap">
        <button class="link-btn" @click="openUploadModal">{{ t('apps.uploadLink') }}</button>
      </div>
    </header>

    <p v-if="error" class="error-text">{{ error }}</p>

    <div v-if="!apps.length && !loading" class="empty-box">
      {{ t('apps.noInstalledApps') }}
    </div>

    <div class="apps-grid">
      <AppCard
        v-for="app in apps"
        :key="app.app_id"
        :app="app"
        :busy="Boolean(busyById[app.app_id])"
        @toggle-running="toggleRunning"
        @toggle-autostart="toggleAutostart"
      />
    </div>

    <div v-if="showUploadModal" class="modal-overlay" @click.self="closeUploadModal">
      <section class="modal-card">
        <header class="modal-header">
          <h3>{{ t('apps.uploadModalTitle') }}</h3>
        </header>

        <div class="field">
          <label>{{ t('apps.packageFile') }}</label>
          <input
            class="file-input"
            type="file"
            accept=".tar.gz,.zip"
            @change="onUploadFileChange($event.target.files)"
          >
          <p class="muted">{{ uploadFileName || t('apps.noFileSelected') }}</p>
        </div>

        <p v-if="uploadError" class="error-text">{{ uploadError }}</p>
        <p
          v-if="uploadStatus"
          :class="uploadStatusDone ? 'ok-text' : 'muted'"
        >
          {{ t('common.status') }}：{{ uploadStatus }}
        </p>
        <pre
          ref="uploadLogRef"
          class="log-output small"
          @scroll="onUploadLogScroll"
        ></pre>

        <footer class="panel-actions">
          <button class="btn" :disabled="uploadBusy" @click="closeUploadModal">{{ t('common.cancel') }}</button>
          <button class="btn primary" :disabled="uploadBusy || !uploadFileName" @click="submitUpload">
            {{ uploadBusy ? t('apps.uploading') : t('apps.uploadAndInstall') }}
          </button>
        </footer>
      </section>
    </div>

  </section>
</template>
